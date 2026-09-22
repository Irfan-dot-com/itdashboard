# Frequently Asked Questions

---

## General Understanding

### Q: What does this project actually do?

It runs on an Ubuntu edge box sitting on your local network. It listens for syslog messages from switches, routers, firewalls, and other devices, scores the health of each device (0–100), and queues a health summary to be sent to a cloud dashboard. If a device suddenly starts reporting errors, it immediately sends an alert — it does not wait for the next scheduled report.

---

### Q: What is the simulator for?

The simulator (`syslog_simulator.py`) pretends to be 6 network devices and sends fake syslog packets. It exists so you can test the full system on a laptop without needing real network hardware. It is a testing tool only — you never deploy it to production.

---

### Q: What is the edge box in production?

In production, the edge box is a small Ubuntu Linux machine (like an Intel NUC or a Raspberry Pi 4) installed at your site. It receives real syslog traffic from real devices over UDP port 514 or 5514. The simulator is not needed once you have real devices sending logs.

---

## Testing and Deployment Strategy

### Q: Should I test on one production edge device before mass deployment?

**Yes, always.** Here is the recommended order:

**Stage 1 — Laptop / VM (where you are now)**
- Run `python3 -m pytest` to verify all 68 tests pass
- Run the simulator + listener to confirm the parsing works
- Run `main.py` + simulator to see the aggregator and health scoring in action

**Stage 2 — Single production edge device at one site**
- Install Python and the project on one Ubuntu edge box
- Point one real device (e.g., one switch) at the edge box on port 514 or 5514
- Add that device to `config.py`'s device_map
- Run `main.py` and watch real logs arrive
- Leave it running for 24–48 hours
- Confirm: health summaries appear, alerts fire when expected, no crashes

**Stage 3 — Mass deployment**
- Only after Stage 2 is stable
- Deploy to all edge boxes using the same configuration template
- Scale the device_map entries per site

Skipping Stage 2 and going directly to mass deployment risks deploying a misconfigured system to every site simultaneously.

---

### Q: What do I need to change in the code before deploying to a real edge box?

Three things:

1. **`config.py` — device_map**: Replace the example IPs (192.168.1.x) with the real IPs and hostnames of your actual devices:
   ```python
   "192.168.1.10|switch-floor1": {"device_id": "dev-001", "site": "hq", "type": "switch"},
   ```

2. **`config.py` — cloud endpoint**: Replace the placeholder URL with the real server URL:
   ```python
   "cloud_endpoint": "https://your-real-server.com/api/v1/ingest",
   ```

3. **`config.py` — api_key**: Replace with your real API key.

The manager confirmed the cloud server is stubbed out for now, so steps 2 and 3 can wait until the cloud server is ready.

---

### Q: Do I need to run the simulator on the production edge box?

No. The simulator is only for testing. In production, real network devices send syslog packets to the edge box automatically. You run `main.py` on the edge box and it listens for those real packets.

---

### Q: Do real devices send syslog to port 5514 or 514?

Most enterprise devices default to **port 514** (the official syslog UDP port). Port 5514 is used in this project because port 514 requires root/admin privileges on Linux. For production:

- Either run the edge agent on port 514 with `sudo`
- Or configure the edge box to redirect port 514 to 5514 with an iptables rule:
  ```bash
  sudo iptables -t nat -A PREROUTING -p udp --dport 514 -j REDIRECT --to-port 5514
  ```
  Then your devices send to 514, and the agent listens on 5514 without needing root.

Check your switch/router documentation for how to set the syslog server IP and port.

---

## Understanding the Tests

### Q: What does "68 passed" actually guarantee?

It guarantees every tested behavior works correctly:
- The syslog parser handles both RFC 3164 and RFC 5424 formats
- The noise filter drops the right messages
- Deduplication prevents event floods from inflating health scores
- The 5-minute rolling window expires old events correctly
- Health scores and status labels (healthy/degraded/unhealthy) are computed correctly
- A device going silent is detected as unhealthy
- State change alerts are sent immediately, not delayed until the next heartbeat
- The SQLite queue survives a restart
- The uploader sends correctly formatted JSON with authentication headers

### Q: What does "68 passed" NOT guarantee?

- That your specific device IPs and hostnames are correctly entered in `config.py`
- That real syslog packets from your actual switches/routers will parse correctly (they might use a slightly different format)
- That the cloud server will accept the payloads (the cloud server is stubbed)
- That the network between the edge box and the cloud server is reliable

These are things you verify in Stage 2 (single device pilot).

---

### Q: Do tests need network access or a real database?

No. All 68 tests run completely offline:
- No UDP sockets opened
- No HTTP requests made (mocked)
- No files written to disk (`:memory:` SQLite or temporary files cleaned up after each test)

---

### Q: Why does the test suite use a FakeClock?

Real time-dependent tests would need `time.sleep(300)` to test a 5-minute rolling window. That would make the test suite take 10+ minutes to run. Instead, the aggregator accepts a `clock` function as a parameter. Tests inject a `FakeClock` that can jump forward 300 seconds instantly. This is why 68 tests finish in under 1 second.

---

### Q: Why do some tests use `monkeypatch`?

To temporarily change a constant during one test without affecting others. For example, `MAX_PERIODIC_ROWS = 5000` normally, but a trim test sets it to 5 so the test doesn't have to insert 5000 rows to trigger trimming.

---

## Running the System

### Q: Can I run both the simulator and listener on the same machine?

Yes. That is exactly what the TUTORIAL (Scenario B) describes. The simulator sends to `127.0.0.1:5514` and the listener binds to `0.0.0.0:5514`, which includes localhost. This is the standard way to demo the system on a laptop.

### Q: What happens if I run main.py and the cloud upload fails?

That is expected and handled gracefully. The uploader logs the error:
```
Upload error: HTTPSConnectionPool(host='dashboard.example.com', ...): Max retries exceeded
```
Messages are kept in the SQLite queue on disk. When the cloud server becomes available, the uploader will automatically send everything that accumulated during the outage. No data is lost.

### Q: How long does it take to see health summaries in main.py?

60 seconds. The aggregator emits a summary for every tracked device every 60 seconds. If a device changes state (e.g., healthy → degraded), an alert is sent immediately without waiting for the 60-second mark.

### Q: What happens if a device stops sending syslog?

After 180 seconds of silence (the `stale_threshold_seconds` in config), the device is flagged as `unhealthy` with the reason `silent_for_Xs`. This catches hardware failures, network outages, and devices that have been powered off.

---

## Configuration

### Q: What is the device_map key format?

```
"<src_ip>|<syslog_hostname>": { ... }
```

Examples:
- `"192.168.1.10|switch-floor1"` — exact match: only this IP with this hostname
- `"*|firewall-dmz"` — wildcard IP: any source IP using hostname `firewall-dmz`

Exact matches always win over wildcards.

### Q: What if a device sends syslog from an IP I don't know in advance?

Use a wildcard entry with the device's syslog hostname:
```python
"*|firewall-dmz": {"device_id": "dev-004", "site": "hq", "type": "firewall"},
```

### Q: What if a device doesn't appear in the listener output?

If the device is not in `config.py`'s device_map, it is silently ignored. Add an entry for it. If you are not sure of the hostname, run `syslog_listener.py` first and look at the `host` field in the printed dicts — that is the hostname to use as the key.

---

## Troubleshooting

### Q: "No module named requests"
```bash
pip3 install requests
```

### Q: "No module named pytest"
```bash
pip3 install pytest
```

### Q: "OSError: [Errno 98] Address already in use"
Another process is already using port 5514. Find and stop it:
```bash
sudo ss -ulnp | grep 5514
```
Or change the port in both `syslog_listener.py` (edit `LISTEN_PORT`) and use `--port` on the simulator.

### Q: Tests fail with "ImportError: No module named aggregator"
You are running pytest from inside the `tests/` folder. Always run from the project root:
```bash
cd ~/Desktop/Syslog_dev_my_Claude
python3 -m pytest
```

### Q: The listener prints messages but they all show `parse_error: True`
The syslog packets are malformed. This was caused by a bug in `syslog_simulator.py` that corrupted the timestamp. It has been fixed. Verify the fix is present:
```bash
grep "now.day" syslog_simulator.py
```
Expected output:
```
    ts = now.strftime(f"%b {now.day:2d} %H:%M:%S")
```
If the output is empty or shows `.replace(" 0", "  ")`, the old buggy version is still there. Replace the file from the fixed copy.
