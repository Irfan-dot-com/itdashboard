# What to Ask the Customer

Two collectors, two very different asks. The poller needs almost nothing from
them; the syslog agent needs work on their devices. Ask for the poller items
first — a single `query=networks` call will then tell you how much syslog work
is actually left.

---

## Shared — needed either way

| Item | Detail |
|---|---|
| Ubuntu box on their network | VM or small physical box, static IP. 2 vCPU / 2 GB / 20 GB is plenty for ~100 devices |
| Outbound TCP 443 from that box to the dashboard host | plus details of any egress proxy |
| Site naming | how they want properties grouped and labelled in the dashboard |

Both collectors can run on the same box. They are separate services with
separate users, configs and state, and neither depends on the other.

---

## 1. Poller (Corning SD-LAN REST API) — pull

No device configuration. No change window. Nothing touched on their switches.

| Ask | Why |
|---|---|
| **SD-LAN platform URL**, e.g. `https://sdlan.hotel.example.net` | what to poll |
| **A read-only API account** (username + password) | the poller only ever reads |
| **Outbound HTTPS** from the edge box to that URL | the only firewall change |
| **Their CA certificate**, if the platform uses a private CA | so TLS is verified rather than disabled |
| **One platform for all sites, or one per property?** | decides how many pollers to deploy |
| **Is polling faster than every 10 minutes acceptable?** | the tech pub's stated minimum; it bounds alerting latency |

The tech pub's examples use `admin/admin`. Ask for a dedicated read-only
account — the poller issues only the four documented read queries (`status`,
`networks`, `device_details`, `slice`) and never writes.

### The ask, in plain language

> We'd like to read device health from your Corning ONE SD-LAN platform via its
> JSON REST Northbound Interface. Please provide the platform URL and a
> **read-only** API account. We only issue the four documented read queries — no
> writes, and no access to individual devices. We'll also need outbound HTTPS
> from our collector box to that URL.

---

## 2. Syslog agent — push

Syslog is push, not pull. Nothing can reach in and fetch it: **every device must
be reconfigured to send**. That is work on their switches, routers and
firewalls, through their change process, and it is the longest lead-time item in
the whole project.

| Ask | Why |
|---|---|
| **Inbound UDP 514** to the box, from every monitored device's VLAN | how syslog arrives; ACLs and inter-VLAN routing both matter |
| **A syslog destination added on each device** (`logging host <box-ip>`) | nothing arrives until this is done, per device |
| **A change window + admin access** on each device | see above |
| **Device inventory**: what each device is, which site, and the IP it *sends from* | to build `device_map` |
| **Do you already run a syslog collector or SIEM?** | can remove most of the work — see below |
| **Are device hostnames globally unique?** | matters if a relay is used |

**No credentials needed.** The agent never logs into anything; it catches UDP.
Worth leading with when you talk to their security team.

> **"Sends from" is not "management IP."** A Cisco switch sources syslog from
> whichever interface routes to the destination, unless someone sets
> `logging source-interface`. Treat their inventory as a checklist of what
> *should* appear, and use `discover.py` for the real values.

### The ask, in plain language

> Please configure the following devices to send syslog to `<box-ip>` on UDP
> port 514: [list]. This is send-only — we need no access to the devices and no
> credentials. We'll also need inbound UDP 514 permitted to that box from each
> device VLAN.

### Device configuration lines, by vendor

**Cisco IOS**
```
conf t
 logging host <box-ip>
 logging trap informational
 logging source-interface Loopback0
end
write memory
```

**FortiGate**
```
config log syslogd setting
 set status enable
 set server "<box-ip>"
 set port 514
 set mode udp
end
```

**MikroTik**
```
/system logging action set remote remote=<box-ip> remote-port=514
/system logging add topics=error,warning,critical action=remote
```

**Juniper**
```
set system syslog host <box-ip> any info
commit
```

---

## 3. If they already have a syslog collector

Ask three questions first:

1. **What is it?** rsyslog or syslog-ng relay easily. Splunk, QRadar, Sentinel
   and Graylog can forward a copy, but it is real work for their team — in which
   case dual-send is usually faster.
2. **Do all the devices you care about already send to it?** Their collector may
   only cover servers, not network gear.
3. **How many syslog destinations do your devices support?** Nearly all support
   at least two.

### Option A — dual-send

Each device gets a *second* destination. Their collector keeps receiving exactly
what it does today; we get our own copy directly.

- Real source IPs, full fidelity, no dependency on their infrastructure.
- Still per-device work — but *additive*, so nothing that works today changes,
  which is usually a much easier approval.
- Ask whether they have config management (Ansible, Cisco DNA Center, Prime). If
  so this becomes one push rather than 200 logins.

### Option B — relay a copy from their collector

One config change on one box. Hand them `syslog/lab/rsyslog-relay.conf` or
`syslog/lab/syslog-ng-relay.conf` — both are written to be read by someone
else's network team, only *add* a destination, and end with a verification step.

Three things to tell them:

- **The forwarding template is load-bearing.** rsyslog's default for `omfwd`
  (`RSYSLOG_ForwardFormat`) emits an RFC 3339 timestamp with no RFC 5424 version
  digit. Measured in the lab: **0 of 6 messages parsed** by a strict parser. Pin
  `template="RSYSLOG_SyslogProtocol23Format"`. For syslog-ng, set
  `keep-hostname(yes)` or every device arrives stamped with the relay's name.
- **All devices arrive from the collector's IP.** UDP carries the last hop, so
  `device_map` must use `"*|hostname"` wildcard keys — which means **hostnames
  must be unique** across everything behind that relay.
- **Their collector becomes a single point of failure for your monitoring.** If
  it dies, every device goes silent at once and the agent would flag the whole
  estate unhealthy simultaneously. Raise `stale_threshold_seconds` accordingly.

### Recommendation

Relay for the pilot — one change, near-zero customer effort, and you learn the
real hostnames and message formats in days rather than weeks. Dual-send for
production on the devices that matter, to remove the dependency.

Prove both on your own box first: `python3 syslog/lab/compare_paths.py`.

---

## 4. Sequencing

1. Ask for the **poller** items. One credential and one firewall rule.
2. Run `poller/probe.py`. `query=networks` tells you exactly which devices the
   SD-LAN platform already covers.
3. Scope **syslog** to whatever is left — third-party firewalls, PBX, DECT, UPS,
   anything not Corning-managed.
4. For that remainder, ask whether they have a collector, and pick relay or
   dual-send.

Anything the SD-LAN API covers needs no syslog work at all, and gives better
data: explicit `lost_contact` rather than inferred silence, structured PSU and
fan state rather than regex-matched log lines, and per-port optical levels that
syslog would never carry.

---

## 5. One thing to check on your side first

Both agents' `preflight.py` fail on a plain-HTTP `cloud_endpoint`, by design —
`X-Provider-Id` is the only credential the ingest API has. Stand up TLS on the
cloud side before any customer traffic flows. See `backend/CLOUD_DEPLOY.md`.
