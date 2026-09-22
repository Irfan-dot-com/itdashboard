# SD-LAN Poller — Deployment Runbook

Polls the Corning ONE SD-LAN orchestration platform over its JSON REST
Northbound Interface and feeds device health into the IT Dashboard.

Separate application from `syslog/`. Different service, different user,
different config, different state. They can run on the same Ubuntu box or on
different boxes, and neither depends on the other.

> **This one is pull, not push.** Nothing has to be reconfigured on the
> customer's switches. You need one URL, one read-only API credential, and
> outbound HTTPS from the box to the platform. That is the whole customer-side
> ask — which is why this is worth doing before the syslog rollout.

---

## 0. What to ask the customer for

| Item | Why |
|---|---|
| SD-LAN platform URL (e.g. `https://sdlan.hotel.example.net`) | what to poll |
| A **read-only** API account | the poller only reads; it never needs admin |
| Whether one platform covers all sites, or one per property | decides how many pollers |
| Outbound HTTPS from the edge box to that URL | the only firewall change needed |
| The platform's CA certificate, if it uses a private CA | so TLS can be verified properly |

The tech pub's examples use `admin/admin`. Ask for a dedicated read-only
account instead — this poller only issues the four documented read queries.

---

## 1. Install

```bash
# copy the poller folder to the box
scp -r poller user@<ubuntu-ip>:~/poller

# on the box
cd ~/poller
sudo bash deploy/install.sh
```

Creates:

| Path | Contents |
|---|---|
| `/opt/sdlan-poller/app/` | application code |
| `/opt/sdlan-poller/venv/` | virtualenv with `requests` |
| `/etc/sdlan-poller/config.json` | **the file you edit** — holds credentials, mode 0640 |
| `/var/lib/sdlan-poller/queue.db` | outbound queue (survives restarts) |
| `/var/lib/sdlan-poller/state.db` | last known status per device (survives restarts) |
| `/var/log/sdlan-poller/cloud_upload.log` | every upload, request and response |
| `/etc/systemd/system/sdlan-poller.service` | the service (installed, not started) |

Runs as the unprivileged `sdlan-poller` user with **no capabilities at all** —
it binds no listening port, it only makes outbound HTTPS calls.

---

## 2. Configure

```bash
sudo nano /etc/sdlan-poller/config.json
```

| Key | Set to |
|---|---|
| `sdlan_base_url` | `https://sdlan.customer.example.net` — `/api/request` is appended |
| `sdlan_username` / `sdlan_password` | the read-only API account |
| `sdlan_verify_tls` | `true`; for a private CA set `sdlan_ca_bundle` rather than disabling this |
| `poll_interval_seconds` | `300` (see the note below) |
| `edge_id` | `sdlan-<property>-01` — unique per poller |
| `property_id` / `property_name` | the site, as the dashboard should group it |
| `cloud_endpoint` | `https://<dashboard>/v1/edge/ingest` |
| `device_id_prefix` | e.g. `sdlan-234` — **set this per property** |
| `device_id_source` | `dev_id` (default), or `hw_sn` / `hw_ident` |

**On the poll interval:** the tech pub says the monitoring system is expected to
poll "at least once every ten minutes". 300s is a reasonable default. Going much
below that adds load on the customer's platform for little gain — confirm with
Corning before you do. Note this bounds your alerting latency: an outage is
detected at worst one interval after it happens.

**Credentials live in this file.** It must stay `0640 root:sdlan-poller` and
must never be committed to git. `preflight.py` check 2 verifies the mode and
fails if it is world-readable.

On the **cloud** side, once per environment:

```bash
docker exec hosp_api python add_provider.py
```

---

## 3. Commands to run, in order

```bash
cd /opt/sdlan-poller/app
VENV=/opt/sdlan-poller/venv/bin/python

# a) what does the platform actually return?
sudo -u sdlan-poller $VENV probe.py

# b) if the API rejects the request encoding, find one that works
sudo -u sdlan-poller $VENV probe.py --try-formats

# c) ten readiness checks, including a live test POST to the dashboard
sudo -u sdlan-poller $VENV preflight.py

# d) one real poll, uploaded, then exit — no service needed
sudo -u sdlan-poller $VENV main.py --once

# e) start it for real
sudo systemctl enable --now sdlan-poller
journalctl -u sdlan-poller -f
```

### What `probe.py` tells you

```
DEVICES (4 found in 0.4s)
  DEVICE_ID                  NAME                     STATUS     SCORE  REASONS
  sdlan-234-11               MDF Core Switch          unhealthy     60  hardware_fault:PSU1
  sdlan-234-12               Floor 3 PoE Switch       healthy      100  -
  sdlan-234-13               Floor 4 PoE Switch       unhealthy     30  thermal_critical:72C, ports_down:3
  sdlan-234-14               Lobby Aggregation        healthy      100  -

FIELD COVERAGE (tech pub vs what this platform actually returns)
  device fields with values : dev_id(4/4), hw_mfg(4/4), endpoint_name(4/4), ...
  device present but null   : lost_contact  (normal - null means nothing wrong)
  device fields ABSENT      : none
```

Three things to check:

1. **Every device you expect appears**, with a sensible name and site.
2. **The assessed status matches reality.** If a switch you know is faulty reads
   healthy, the field carrying that fault is probably in the `ABSENT` list.
3. **`device_id` values look right** — they become permanent primary keys in the
   cloud `devices` table. Changing them later orphans history.

The `ABSENT` list is the important one. The field names come from the tech pub
and **have not been verified against real hardware**. If something important is
absent, dump the raw response and correct `mapper.py`:

```bash
sudo -u sdlan-poller $VENV probe.py --raw networks --save /tmp/networks.json
```

Expect at least one round of this on first contact with a real platform. It is a
field-name mismatch, not a rewrite — the mapping lives in `mapper.py` and the
accessors already tolerate missing fields rather than crashing.

---

## 4. What it sends to the dashboard

Each poll emits, into the same three message kinds the syslog agent uses:

- **`periodic`** — one per device, plus one for the platform itself
- **`transition`** — only when a device's status *changes* since the last poll,
  which is what opens and resolves alerts in the cloud
- **`edge_health`** — this poller's own heartbeat, with tracked/unhealthy counts
  and queue depth

Health is **read from the API**, not inferred:

| Condition | Result |
|---|---|
| `lost_contact` set, or `.state` false | `unhealthy`, score 0, reason `lost_contact` |
| `PSU`/`Fan` reporting `FAIL`/`Missing` | `unhealthy`, reason `hardware_fault:<name>` |
| `Temp` ≥ `temp_crit_celsius` | `unhealthy`, reason `thermal_critical` |
| `Temp` ≥ `temp_warn_celsius` | `degraded`, reason `thermal_warning` |
| Ports `Down` | `degraded`, reason `ports_down:<n>` |
| ≥3 ports changing link inside `link_flap_window_seconds` | `degraded`, reason `link_flap` |
| Optical `rx_optical_level` below `optical_rx_warn_dbm` | `degraded`, reason `optical_low` |
| Device drops out of the report for 2.5 intervals | `unhealthy`, reason `absent_from_platform_report` |
| Platform: expired/missing licence, low disk, abnormal `bufferwatch`, active `problems` | scored on the platform device |

Last known status is kept in `state.db`, so restarting the poller does **not**
re-raise alerts for devices that were already unhealthy.

---

## 5. Test plan

**Stage 1 — on a laptop, no customer involvement.** A mock platform ships with
the app:

```bash
cd poller
python3 -m pytest tests/ -v          # or: python3 tests/run_tests.py

# terminal 1
python3 mock_sdlan.py --port 8443
# terminal 2 — point config at http://127.0.0.1:8443 and the dashboard dev API
python3 main.py --config test-config.json --once

# drive fault scenarios and watch transitions fire
curl -X POST "localhost:8443/_scenario?scenario=degrade"   # PSU fails, disk low
curl -X POST "localhost:8443/_scenario?scenario=outage"    # a switch loses contact
curl -X POST "localhost:8443/_scenario?scenario=recover"   # everything healthy
```

`tests/test_cloud_schema.py` validates every emitted message against the real
backend schema imported from `../backend`, so a drift between poller and API
shows up as a failing test rather than a 422 in production.

**Stage 2 — against the customer's real platform, read-only.**

1. Configure URL and credentials, `chmod 640`.
2. `probe.py` — confirm the device list and the `ABSENT` field report.
3. Correct `mapper.py` if needed, re-run `probe.py`.
4. `preflight.py` — all checks pass.
5. `main.py --once` — confirm the devices appear in the dashboard.
6. **Ask the customer to unplug one non-critical device**, or wait for a real
   fault. Confirm a transition fires and an alert opens, then that it resolves.
7. Leave the service running 24–48 h. Check for restarts, queue depth near
   zero, and log size.

**Stage 3 — more properties.** One poller per platform. Give each a distinct
`edge_id` and `device_id_prefix`.

---

## 6. Operating it

```bash
systemctl status sdlan-poller
journalctl -u sdlan-poller --since "1 hour ago"

# current view of every device
sudo sqlite3 /var/lib/sdlan-poller/state.db \
  "SELECT device_id, status, score, datetime(last_seen,'unixepoch') FROM device_state ORDER BY status;"

# queue health — 'pending' should hover near zero
sudo sqlite3 /var/lib/sdlan-poller/queue.db \
  "SELECT state, kind, COUNT(*), MAX(attempts) FROM outbound GROUP BY state, kind;"

# anything the cloud permanently refused
sudo sqlite3 /var/lib/sdlan-poller/queue.db \
  "SELECT id, kind, last_error FROM outbound WHERE state='quarantined' LIMIT 10;"

sudo tail -f /var/log/sdlan-poller/cloud_upload.log
```

A growing `pending` count means uploads are failing — check the log tail for the
HTTP status. Unlike the syslog agent, a batch the cloud permanently rejects (a
4xx) is retried three times and then **quarantined**, so one bad message cannot
block the queue forever. Quarantined rows stay on disk for inspection.

Restart after a config change:

```bash
sudo systemctl restart sdlan-poller
```

---

## 7. Known limitations

1. **Field names are unverified against real hardware.** Taken from the 2022
   tech pub. Expect one mapping correction on first contact; `probe.py`'s
   coverage report is built to make that quick.
2. **Alerting latency is bounded by the poll interval.** At 300s, an outage is
   seen up to 5 minutes late. Syslog is near-real-time; this is not.
3. **Only covers SD-LAN-managed devices.** Anything not on the platform —
   third-party firewalls, PBX, DECT, UPS — is invisible here and still needs the
   syslog agent.
4. **`device_details` and `slice` are implemented but not polled.** The client
   supports them (`probe.py --device-details <dev_id>`, `--slice <endpoint>`) and
   they carry per-port history, MAC tables and topology. Polling them for every
   device every cycle would be heavy, so nothing does yet. Worth adding for
   specific devices once you know what the dashboard should show.
5. **No push/webhook.** The API is poll-only, so there is no way to be notified
   the instant something breaks.
