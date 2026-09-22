# Edge Agent — Ubuntu Deployment Runbook

Deploying the `syslog/` agent onto an Ubuntu box on a customer network, and
testing it before it carries real traffic.

> **Syslog is push, not pull.** This agent cannot reach into the customer
> network and fetch anything. Every device must be reconfigured to *send* its
> syslog to this box's IP. That work happens on the customer's switches,
> routers and firewalls, needs their change process, and is usually the longest
> lead-time item in the whole deployment. Budget a change window for it.
>
> Before committing to that: check how much of the estate the **Corning SD-LAN
> REST API** already covers (`poller/`). For those devices none of this is
> needed, and the data is better. See `CUSTOMER_REQUIREMENTS.md` at the repo
> root.

---

## 0. What you need before you start

| Item | Why | Who provides |
|---|---|---|
| Ubuntu 22.04/24.04 box on the customer LAN, static IP | the collector | customer / you |
| That IP reachable on **UDP 514** from every monitored device's VLAN | syslog delivery | customer network team |
| Outbound **TCP 443** from the box to the dashboard host | uploads | customer firewall team |
| Admin access to each device's syslog config | to point them at the box | customer network team |
| `service_provider` value that exists in the cloud DB | FK on ingest | you (`add_provider.py`) |
| `property_id` for this site | groups devices in the dashboard | you |

Sizing: ~100 devices at a few msg/s is comfortable on 2 vCPU / 2 GB / 20 GB.
The agent summarises rather than storing raw logs, so disk growth is driven by
the upload log, not by syslog volume.

---

## 1. Install

From a checkout of the repo on the edge box:

```bash
cd it-dashboard/syslog
sudo bash deploy/install.sh
```

This creates:

| Path | Contents |
|---|---|
| `/opt/edge-agent/app/` | application code (`main.py`, `discover.py`, `preflight.py`, …) |
| `/opt/edge-agent/venv/` | virtualenv with `requests` |
| `/etc/edge-agent/config.json` | **your configuration — this is the file you edit** |
| `/var/lib/edge-agent/queue.db` | SQLite outbound queue (survives reboots) |
| `/var/log/edge-agent/cloud_upload.log` | full request/response log of every upload |
| `/etc/systemd/system/edge-agent.service` | the service (installed, not started) |
| `/etc/logrotate.d/edge-agent` | rotation for the upload log |

It runs as the unprivileged `edge-agent` user and gets `CAP_NET_BIND_SERVICE`
so it can bind UDP 514 without root.

The simulator (`syslog_simulator.py`) and the `lab/` folder are deliberately
**not** installed on an edge box.

---

## 2. Apply the `listen_port` patch (required)

`main.py` hardcodes `LISTEN_PORT = 5514` and ignores config, so setting
`listen_port` in `config.json` has no effect until this is applied:

```bash
cd it-dashboard/syslog
git apply deploy/main.py.listen_port.patch
```

It is a 5-line change to `listener_loop()`. Without it, either re-run
`install.sh` after editing `LISTEN_PORT` by hand, or leave the agent on 5514
and use the iptables redirect in section 4.

---

## 3. Configure — everything lives in one file

**`/etc/edge-agent/config.json`** is the only file you edit. It overrides
`DEFAULT_CONFIG` in `config.py` key by key, so the code needs no changes per
site.

```bash
sudo nano /etc/edge-agent/config.json
```

| Key | Set it to | Notes |
|---|---|---|
| `edge_id` | `edge-<property>-01` | unique per box; defaults to the hostname, which is not good enough |
| `service_provider` | `bluip` | **must already exist** in the cloud `service_providers` table |
| `property_id` | the site's ID | groups this box's devices in the dashboard |
| `property_name` | human-readable hotel name | shown in the UI |
| `cloud_endpoint` | `https://host/v1/edge/ingest` | see the HTTPS note below |
| `listen_port` | `514` | what the devices will actually send to |
| `queue_db_path` | `/var/lib/edge-agent/queue.db` | must be writable by `edge-agent` |
| `cloud_upload_log_path` | `/var/log/edge-agent/cloud_upload.log` | set `""` to disable |
| `stale_threshold_seconds` | `180` | silence before a device is called unhealthy — raise it if a relay is involved (section 5b) |
| `device_map` | see section 5 | **nothing works until this is right** |

> **HTTPS:** `preflight.py` fails on an `http://` endpoint by design. The
> `X-Provider-Id` header is the only credential the ingest API has, and it would
> cross the network in clear text. Stand up TLS on the cloud side first —
> `backend/CLOUD_DEPLOY.md` has a Caddy setup with automatic certificates.

On the **cloud** side, once per environment:

```bash
docker exec hosp_api python add_provider.py
```

Skip it and every upload fails with a 500 on the `service_providers` foreign key.

---

## 4. Port 514 vs 5514

Enterprise switches, routers and firewalls send syslog to **UDP 514** by
default, and many cannot be changed. Pick one:

**A — listen on 514 directly** (what the systemd unit is set up for): set
`"listen_port": 514`. `CAP_NET_BIND_SERVICE` in the unit covers the privileged
bind; no root needed.

**B — listen on 5514 and redirect:** leave `listen_port` at 5514 and add

```bash
sudo iptables -t nat -A PREROUTING -p udp --dport 514 -j REDIRECT --to-port 5514
sudo apt-get install -y iptables-persistent   # or the rule is lost on reboot
```

Option A is simpler and has one less moving part. Use B only if something else
on the box already owns 514 — check with `sudo ss -ulnp | grep :514`.

If `rsyslog` holds 514, either stop it (`sudo systemctl disable --now rsyslog`)
or use option B.

---

## 5. Build `device_map` — the step that actually decides whether this works

`device_map` keys are `"<source_ip>|<syslog_hostname>"` and **both parts must
match exactly what the device puts on the wire**. Anything not in the map is
dropped silently: no log line, no counter, no hint on the dashboard. A fully
healthy-looking agent receiving thousands of packets can be discarding all of
them.

You cannot write this map from an asset spreadsheet, because the syslog hostname
a device sends is often not its DNS name or its label in inventory. Discover it:

```bash
# 1. have the network team point the devices at this box on UDP 514
# 2. listen and see what actually turns up
cd /opt/edge-agent/app
sudo /opt/edge-agent/venv/bin/python discover.py --port 514 --duration 600
```

`discover.py` prints every talker it hears — source IP, syslog hostname, packet
count, severity mix, and whether the current map would keep or drop it — then
writes a `device_map` skeleton with `device_class` and `vendor` guessed from the
hostname and syslog tag:

```
  SRC IP           HOSTNAME                     PKTS STATE     TOP SEVERITIES        MAPS TO
  10.20.30.11      HTL-SW-CORE-01                412 UNMAPPED  info:380, err:22      -- dropped --
  10.20.30.12      HTL-SW-POE-F3                 198 UNMAPPED  info:190, warning:8   -- dropped --
  10.20.30.1       HTL-FG-EDGE                    77 UNMAPPED  warning:77            -- dropped --

  MAPPED devices   : 0
  UNMAPPED devices : 3  <-- their syslog is being DISCARDED
  UNPARSEABLE pkts : 14 <-- not RFC3164/5424; parser needs extending
```

Replace every `REPLACE-ME` value, verify the guessed `device_class`/`vendor`,
and merge the object into `device_map` in `/etc/edge-agent/config.json`.

Rules:
- `device_id` must be **globally unique across all properties** — it is the
  primary key in the cloud `devices` table. Two devices sharing one ID overwrite
  each other's health.
- Use `"*|hostname"` only when a source IP genuinely varies (DHCP), or when a
  relay is in the path (section 5b). A wildcard accepts that hostname from *any*
  IP.
- **Delete the six simulator wildcards** shipped in `DEFAULT_CONFIG`
  (`*|switch-floor1`, `*|switch-floor2`, `*|router-edge`, `*|ap-lobby`,
  `*|sensor-hvac-01`, `*|firewall-dmz`). Defining your own `device_map` in
  `config.json` replaces the default map wholesale, which is the clean way to
  drop them.

If a device shows up as `UNPARSEABLE`, its syslog format isn't RFC 3164, RFC
5424 or the relayed RFC 3339 form. Note which vendor and raise it.

---

## 5b. If the customer already has a syslog collector

Most sites do. This can remove nearly all the per-device work — or silently
break everything. Two options:

**Dual-send** — each device gets a *second* `logging host` line. Their collector
keeps receiving what it does today; we get our own copy. Real source IPs, full
fidelity, no dependency on their infrastructure. Still per-device work, but
purely additive, so nothing that works today changes.

**Relay** — their collector forwards a copy to us. One config change on one box.
Hand them `lab/rsyslog-relay.conf` or `lab/syslog-ng-relay.conf`.

Three things that will bite you on the relay path:

1. **The forwarding template is load-bearing.** rsyslog's default for `omfwd`
   (`RSYSLOG_ForwardFormat`) rewrites the header to an RFC 3339 timestamp with
   **no RFC 5424 version digit**:
   ```
   <131>2026-09-21T19:00:00+00:00 HTL-SW-CORE-01 %SYS-3-POWER: Power supply 1 failed
   ```
   Measured against real rsyslog 8.2112: **0 of 6 messages parsed** before
   `syslog_listener.py` was extended for it. `main.py` discards a parse failure
   with a bare `continue` — no log line — so the agent looks perfectly healthy
   and collects nothing.

   Two things were done: the parser now handles this form
   (`RFC3164_RFC3339_RE`, reported as `rfc=3164-rfc3339`), **and**
   `lab/rsyslog-relay.conf` pins `template="RSYSLOG_SyslogProtocol23Format"`.
   Pin the template anyway — don't rely on the parser alone.

   | Template | Parsed |
   |---|---|
   | `RSYSLOG_ForwardFormat` (rsyslog's default) | 0/6 before the fix, 6/6 after |
   | `RSYSLOG_TraditionalForwardFormat` | 6/6 |
   | `RSYSLOG_SyslogProtocol23Format` | 6/6 — **use this** |

   For syslog-ng, set `keep-hostname(yes)` or every device arrives stamped with
   the relay's own hostname.

2. **Every device arrives from the collector's IP.** UDP carries the last hop
   only. Exact `"<ip>|<hostname>"` keys all collapse onto one address, so use
   `"*|hostname"` wildcards — which means **device hostnames must be unique**
   across everything behind that relay. Ask the customer directly.

3. **Their collector becomes a single point of failure for your monitoring.**
   If it dies, every device goes silent simultaneously and the agent flags the
   whole estate unhealthy at once — an alert storm caused by their box, not by
   any real fault. Raise `stale_threshold_seconds`, and monitor their collector
   separately if you can.

**Prove all of this on your own box before involving them:**

```bash
cd it-dashboard/syslog/lab
python3 compare_paths.py
```

It runs a real (unprivileged, throwaway-config) `rsyslogd` and reports what
survives each path against every template. See `lab/README.md`.

**Recommendation:** relay for the pilot — one change, near-zero customer effort,
and you learn the real hostnames and formats in days. Dual-send for production
on the devices that matter.

---

## 6. Verify before starting

```bash
cd /opt/edge-agent/app
sudo -u edge-agent /opt/edge-agent/venv/bin/python preflight.py
```

Eight checks: config completeness, queue and log writability, UDP bind, cloud
TCP reachability, `/livez`, a **live POST of a synthetic batch** to the real
ingest endpoint, and `device_map` sanity (placeholders, wildcards, duplicate
device_ids). Exit code is non-zero if anything failed.

The synthetic POST registers a device called `_preflight:<edge_id>` so it can't
be confused with a real one. Remove it from the dashboard afterwards if you
don't want it there.

Fix every FAIL before pointing customer devices at the box.

---

## 7. Start it

```bash
sudo systemctl enable --now edge-agent
journalctl -u edge-agent -f
```

Expected on startup:

```
Cloud HTTP log (text): /var/log/edge-agent/cloud_upload.log
Listening on 0.0.0.0:514/udp  (edge_id=edge-sheraton-01)
```

Then within ~60 seconds the first summaries upload. Watch them:

```bash
sudo tail -f /var/log/edge-agent/cloud_upload.log
```

Each block shows the POST URL, headers, the full JSON body, and the HTTP status
and response body — the fastest way to see exactly what the cloud received and
what it said back.

---

## 8. Test plan, in order

**Stage 0 — on your own machine, before the customer is involved**

```bash
cd it-dashboard/syslog
pip install pytest requests
python -m pytest -v                      # 16 parser tests among them

# prove the delivery paths, with a real rsyslog relay
cd lab && python3 compare_paths.py
```

**Stage 1 — laptop or VM, full pipeline**

```bash
# two terminals:
python main.py
python syslog_simulator.py --host 127.0.0.1 --port 5514 --rate 5 --burst
```

Confirm: summaries build, transitions fire on a burst, queue depth rises and
falls. Point `cloud_endpoint` at a dev instance of the API and confirm a 200
with `"accepted": N` and an empty `rejected` list.

**Stage 2 — one edge box, one real device**

1. `install.sh`, apply the patch, configure `config.json`.
2. `preflight.py` — all checks pass.
3. Network team points **one** switch at the box on UDP 514 (or sets up the
   relay).
4. `discover.py --duration 300` — confirm the packets arrive and capture the
   real hostname. If nothing arrives, the problem is upstream:
   ```bash
   sudo tcpdump -n -i any udp port 514        # are packets even reaching the box?
   ```
   Nothing in tcpdump → device syslog config, VLAN routing, or an ACL. Packets
   in tcpdump but nothing in discover → wrong port, or the agent isn't bound.
   Packets arriving but `UNPARSEABLE` → header format; check the relay template.
5. Add that device to `device_map`, restart, confirm it appears in the dashboard.
6. **Pull its network cable** and confirm what happens after
   `stale_threshold_seconds`. See the known-issues note below — today this
   produces a `periodic` message with status `unhealthy` but **no alert**.
7. Leave it running 24–48 h. Check for restarts (`systemctl status`), queue
   growth (`sqlite3 /var/lib/edge-agent/queue.db "SELECT COUNT(*) FROM outbound"`
   — should hover near zero), and log size.

**Stage 3 — full site, then more sites**

Only after stage 2 is stable. Add devices to `device_map` in batches, re-running
`discover.py` to catch talkers you missed. Re-run `preflight.py` after each
config change.

---

## 9. Operating it

```bash
systemctl status edge-agent
journalctl -u edge-agent --since "1 hour ago"
journalctl -u edge-agent -p err

# queue depth by message type — should stay near zero
sudo sqlite3 /var/lib/edge-agent/queue.db \
  "SELECT kind, COUNT(*), MAX(attempts) FROM outbound GROUP BY kind;"

# what the cloud actually received and replied
sudo tail -100 /var/log/edge-agent/cloud_upload.log
```

**A queue that only grows means uploads are failing.** Check `attempts` and the
tail of the upload log for the HTTP status. Note that the uploader retries a
4xx forever and always retries the oldest rows first, so one permanently
rejected batch blocks everything behind it — see known issues.

Restart after a config change:

```bash
sudo systemctl restart edge-agent
```

---

## 10. Known issues to be aware of while testing

These are in the current code. They change what you'll see during stage 2, so
read them before you interpret results.

1. **A device going offline raises no alert.** Silence is detected — the
   periodic summary correctly says `unhealthy` with `silent_for_Ns` — but only
   a `transition` message opens an alert in the cloud, and transitions are
   emitted only from `ingest()`, which needs an incoming packet. A dead device
   sends nothing, so nothing fires. `state.last_status` is also never updated by
   the periodic loop. *(The poller does not have this problem — the SD-LAN API
   states `lost_contact` outright.)*
2. **No `edge_health` message is ever sent.** The `edge_boxes` table and the
   dashboard's edge-box panel stay empty; there's no heartbeat, queue-depth or
   tracked-device visibility for the box itself. *(The poller does send these.)*
3. **Dedup collapses distinct ports into one event.** The signature normalises
   all digits to `#`, so `Gi0/3`, `Gi0/7`, `Gi0/24` and `Gi0/48` going down
   within 60 s count as a *single* event. A four-port outage scores 92/100
   (healthy), and `link_flap` — which needs 3 link events — can't trigger.
4. **The classifier misses real vendor syslog.** The nine regexes match tidy
   English phrases; tested against real Cisco (`%SYS-3-POWER: Power supply 1
   failed`, `%ILPOWER-3-...`, `%PLATFORM_THERMAL-1-OVERTEMP`), Fortigate
   key-value, Asterisk and hostapd lines, **0 of 7 classified** — all fell
   through to `other`. Severity still drives the score, so devices aren't
   invisible, but every category-based reason (`hardware_fault`, `link_flap`,
   `auth_failures`) stays silent, and `other` at info severity is dropped as
   noise. Note this is the *classifier*, and is separate from the *parser* fix
   in section 5b.
5. **One bad message rejects the whole batch.** Ingest validation is
   all-or-nothing: one message failing the schema returns 422 for all 50.
   Combined with the 4xx-retried-forever behaviour above, that stalls the queue
   permanently. *(The poller quarantines a 4xx batch after three attempts so the
   queue keeps draining.)*
6. **A parse failure is invisible.** `main.py` does `continue` on
   `parse_error` with no log line and no counter, which is why the relay
   template problem in section 5b was so hard to see. Worth adding a
   rate-limited warning.
7. **Docs are out of date.** `md-files/FAQ.md` and `TUTORIAL.md` reference
   `c:\Office\Jazz\...` paths, an `api_key` config key that doesn't exist (auth
   is `X-Provider-Id`), a `type` field in `device_map` (it's `device_class`),
   and describe the cloud server as "stubbed" — it isn't.

**Fixed since the first review:** the parser now handles the relayed RFC 3339
header form (section 5b), with 7 new tests in
`tests/test_listener_parser.py` and zero regressions.

The message shape the agent sends **does** validate cleanly against the
backend's current schema, including `top_events` on transitions. That part is
sound.
