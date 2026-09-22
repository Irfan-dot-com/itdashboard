# How to Run This Project — Step by Step

All commands are run from this folder:
```
c:\Office\Jazz\Syslog_dev_my_Claude\
```

---

## Prerequisites

Make sure Python and the required packages are installed.

**Check Python:**
```
python --version
```
Expected: `Python 3.12.x` (or 3.10+)

**Install required packages:**
```
pip install requests pytest
```

---

## Scenario A — Run the Regression Tests (No Hardware Needed)

This verifies that all the logic is working correctly. No network, no devices needed.

**Step 1 — Open a terminal in the project folder:**
```
cd c:\Office\Jazz\Syslog_dev_my_Claude
```

**Step 2 — Run pytest:**
```
python -m pytest
```

**Expected output:**
```
collected 68 items

tests/test_aggregator.py::TestIngest::test_first_event_creates_device_state PASSED
tests/test_aggregator.py::TestIngest::test_noise_is_dropped PASSED
...
tests/test_integration.py::test_full_pipeline_healthy_then_unhealthy PASSED
...
tests/test_uploader.py::TestRunLoop::test_successful_batch_is_acked PASSED

==================== 68 passed in 2.5s ====================
```

If you see `68 passed` — everything is working. Done.

**Run only one test file** (useful for debugging a specific module):
```
python -m pytest tests/test_aggregator.py -v
python -m pytest tests/test_classify.py -v
python -m pytest tests/test_integration.py -v
```

**Run only one specific test:**
```
python -m pytest tests/test_aggregator.py::TestHealth::test_silent_device_marked_unhealthy -v
```

---

## Scenario B — Run the Listener + Simulator (Live Demo)

This sends fake syslog messages and shows the parsed output in real time.

You need **two terminal windows** open in the project folder.

---

### Terminal 1 — Start the Listener

```
cd c:\Office\Jazz\Syslog_dev_my_Claude
python syslog_listener.py
```

Expected output:
```
Listening for syslog on 0.0.0.0:5514/udp
```

It is now waiting for syslog packets. Leave this running.

---

### Terminal 2 — Start the Simulator

```
cd c:\Office\Jazz\Syslog_dev_my_Claude
python syslog_simulator.py --host 127.0.0.1 --port 5514 --rate 5 --burst
```

Expected output in Terminal 2:
```
Sending to 127.0.0.1:5514 at ~5 msg/s. Ctrl-C to stop.
```

When an error burst occurs:
```
--- Incident starting on switch-floor2 ---
```

---

### What You Will See in Terminal 1 (the listener)

Incoming syslog messages will be printed as Python dicts:
```python
{'rfc': '3164', 'src_ip': '127.0.0.1', 'received_at': '2026-05-04T10:22:01Z',
 'host': 'switch-floor1', 'facility': 'local0', 'severity': 'info',
 'tag': 'ciscoios', 'message': 'Interface GigabitEthernet0/12 link state changed to up'}

{'rfc': '3164', 'src_ip': '127.0.0.1', 'received_at': '2026-05-04T10:22:01Z',
 'host': 'firewall-dmz', 'facility': 'local0', 'severity': 'err',
 'tag': 'pf', 'message': 'Power supply 1 fault detected'}
```

**To stop:** Press `Ctrl+C` in both terminals.

---

### Simulator Options

| Flag | Default | What it does |
|------|---------|-------------|
| `--host` | `127.0.0.1` | IP to send packets to |
| `--port` | `5514` | UDP port to target |
| `--rate` | `2.0` | Messages per second |
| `--burst` | off | Randomly simulate error storms on a device |

**Examples:**
```
# Slow and steady, no bursts
python syslog_simulator.py --rate 2

# Fast traffic with incident simulation
python syslog_simulator.py --rate 10 --burst

# Send to a different machine
python syslog_simulator.py --host 192.168.1.50 --port 5514 --rate 5
```

---

## Scenario C — Run the Full Agent (Aggregator + Queue + Uploader)

This is the complete system: it receives syslog, aggregates health per device, stores summaries in SQLite, and attempts to upload to the cloud.

> The cloud upload will fail with a connection error (placeholder URL) — that is expected. The rest of the system works fully.

You need **two terminal windows**.

---

### Terminal 1 — Start the Full Agent

```
cd c:\Office\Jazz\Syslog_dev_my_Claude
python main.py
```

Expected output:
```
Listening on 0.0.0.0:5514/udp
```

After a minute, if the cloud upload fails, you will also see:
```
Upload error: HTTPSConnectionPool(host='dashboard.example.com', ...): Max retries exceeded
```

This is expected — ignore it.

---

### Terminal 2 — Start the Simulator

```
cd c:\Office\Jazz\Syslog_dev_my_Claude
python syslog_simulator.py --host 127.0.0.1 --port 5514 --rate 5 --burst
```

---

### What Happens Behind the Scenes

1. Simulator sends fake syslog UDP packets to port 5514
2. `main.py` receives each packet and passes it to the aggregator
3. The aggregator:
   - Looks up the device in `config.py` → **switch-floor1, router-edge, firewall-dmz etc. are NOT in the default device_map** (they use simulated hostnames, not real IPs)
   - Unknown devices are silently dropped
4. Every 60 seconds, the aggregator emits health summaries for tracked devices
5. The uploader tries to POST to `https://dashboard.example.com/...` → fails → retries with backoff

> **Note:** The simulator sends packets with hostnames like `switch-floor1`, `router-edge`, etc. but from IP `127.0.0.1`. The default `config.py` maps specific IPs like `192.168.1.10`. To see the full aggregation working, add the simulator's devices to `config.py` first (see below).

---

### Add Simulator Devices to config.py

Open [config.py](config.py) and find the `device_map` section. Add these entries:

```python
"device_map": {
    # Existing entries...
    "192.168.1.10|switch-floor1":  {"device_id": "dev-001", "site": "hq", "type": "switch"},

    # Add these for the simulator (127.0.0.1 = localhost):
    "127.0.0.1|switch-floor1":  {"device_id": "dev-001", "site": "hq", "type": "switch"},
    "127.0.0.1|switch-floor2":  {"device_id": "dev-002", "site": "hq", "type": "switch"},
    "127.0.0.1|router-edge":    {"device_id": "dev-003", "site": "hq", "type": "router"},
    "127.0.0.1|ap-lobby":       {"device_id": "dev-005", "site": "hq", "type": "ap"},
    "127.0.0.1|sensor-hvac-01": {"device_id": "dev-006", "site": "hq", "type": "sensor"},
    "*|firewall-dmz":           {"device_id": "dev-004", "site": "hq", "type": "firewall"},
},
```

After this change, restart `main.py`. Now the aggregator will track all 6 simulated devices and you will see health summaries being built.

---

## Quick Reference — What Each Script Does

| Script | Purpose | Run When |
|--------|---------|----------|
| `python -m pytest` | Runs all 68 automated tests | Before a demo; after any code change |
| `python syslog_listener.py` | Bare listener — just prints received messages | Quick check that messages are arriving |
| `python syslog_simulator.py` | Sends fake syslog packets | Testing the listener or agent |
| `python main.py` | Full agent — aggregates, scores health, uploads | The real demo |

---

## Troubleshooting

**"No module named requests"**
```
pip install requests
```

**"No module named pytest"**
```
pip install pytest
```

**Port already in use (OSError: [WinError 10048])**

Something else is using port 5514. Either stop the other process or change the port:
```
python syslog_simulator.py --port 5515
```
And in `syslog_listener.py`, change `LISTEN_PORT = 5515`.

**Tests fail with ImportError**

Make sure you are running pytest from the project root folder, not from inside `tests\`:
```
cd c:\Office\Jazz\Syslog_dev_my_Claude
python -m pytest
```

**Simulator running but nothing appears in listener**

Check both are using the same port:
```
python syslog_simulator.py --host 127.0.0.1 --port 5514
python syslog_listener.py                               # also uses 5514 by default
```
