# syslog/lab — test both delivery approaches before involving the customer

Two ways syslog can reach the agent when the customer already runs a collector:

- **Dual-send** — each device sends to their collector *and* to us.
- **Relay** — their collector forwards a copy to us.

This folder lets you prove which one works, and exactly what to hand their
network team, on one Linux box with no customer involvement.

---

## The finding that makes this worth running

**rsyslog's default forwarding template silently drops every message.**

`RSYSLOG_ForwardFormat` — the default for `omfwd`, and what most documentation
suggests — rewrites the header to an RFC 3339 timestamp with **no RFC 5424
version digit**:

```
device sends:   <131>Sep 21 19:00:00 HTL-SW-CORE-01 %SYS-3-POWER: Power supply 1 failed
relay forwards: <131>2026-09-21T19:00:00+00:00 HTL-SW-CORE-01 %SYS-3-POWER: Power supply 1 failed
```

That form matches neither of the agent's regexes, so `parse_message()` returns
`parse_error` and `main.py` does `continue` — no log line, no counter, nothing.
A relay deployment would look perfectly healthy and collect **zero** data.

Measured with real rsyslog 8.2112:

| Template | Parsed | Notes |
|---|---|---|
| `RSYSLOG_ForwardFormat` | **0/6** | rsyslog's default — unusable unpatched |
| `RSYSLOG_TraditionalForwardFormat` | 6/6 | classic RFC 3164; loses year and sub-second precision |
| `RSYSLOG_SyslogProtocol23Format` | 6/6 | proper RFC 5424; keeps timezone and precision — **use this** |

Two things were done about it:

1. **`syslog_listener.py` now parses the relayed form too** (`RFC3164_RFC3339_RE`).
   Four previously-unparseable formats now parse; zero regressions. This matters
   because you may not control the customer's relay config.
2. **`rsyslog-relay.conf` pins the template explicitly**, with a comment
   explaining why. Belt and braces.

---

## Run it

```bash
cd syslog/lab
python3 compare_paths.py
```

Needs `rsyslogd` on PATH for the relay path (`sudo apt-get install rsyslog`).
It runs rsyslogd in the foreground, unprivileged, on high ports, with a
throwaway config — **it does not touch the system rsyslog service.**

```bash
python3 compare_paths.py --skip-relay       # no rsyslogd available
python3 compare_paths.py --keep-captures    # dump raw bytes to ./captures/
```

What it tests, with the same six realistic vendor messages down every path:

| Path | What it proves |
|---|---|
| A — direct | baseline; the dual-send target parses cleanly |
| B — relayed | run through real rsyslog against **all three** templates |
| C — dual-send | both destinations receive the full stream independently |

and then reports: does the hostname survive, does the body survive, is the
header rewritten, and does `device_map` still resolve.

---

## What the lab cannot show, and why it doesn't matter

Everything runs on one host, so every path reports `127.0.0.1` and the
**source-IP difference is invisible here**.

That part isn't in doubt though: UDP carries the last hop, so a relayed message
always arrives from the collector's IP, never the device's. The consequence is
what matters, and it's certain:

- **With a relay, exact `"<ip>|<hostname>"` device_map keys all collapse onto
  one IP.** Use `"*|hostname"` wildcards.
- **Hostnames must therefore be unique** across every device behind that relay.
  Ask the customer whether their naming is globally unique — two properties both
  having `sw-floor1` would merge into one device.

To see it with real distinct IPs you need separate hosts or containers. On a box
with Docker and root, `docker compose` with one container per simulated device
plus an rsyslog container will show it; that's worth doing only if you want the
demo, since the conclusion is already known.

---

## Files

| File | Purpose |
|---|---|
| `compare_paths.py` | the harness — run this |
| `rsyslog-relay.conf` | **hand this to the customer** if they run rsyslog |
| `syslog-ng-relay.conf` | **hand this to the customer** if they run syslog-ng |
| `README.md` | this file |

Both config files are written to be read by someone else's network team: they
only add a destination, they explain the template trap, and they end with a
verification step.

---

## Checklist before you talk to the customer

- [ ] `compare_paths.py` run, and you have seen the template comparison yourself
- [ ] Decided relay vs dual-send for the pilot (relay is faster; dual-send is
      more robust)
- [ ] If relay: `rsyslog-relay.conf` edited with the real collector IP and
      device subnets
- [ ] If relay: asked whether device hostnames are globally unique
- [ ] If relay: raised `stale_threshold_seconds` — when their collector dies,
      every device goes silent at once and the agent would flag the whole estate
      unhealthy simultaneously
- [ ] Asked what their collector actually is (rsyslog and syslog-ng relay
      easily; Splunk, QRadar and Sentinel are more work for their team, in which
      case dual-send is usually faster)
- [ ] Checked how much of the estate the Corning SD-LAN API already covers — for
      those devices none of this is needed at all
