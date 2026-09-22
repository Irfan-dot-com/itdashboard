#!/usr/bin/env python3
"""
preflight.py — verify an edge box is ready BEFORE pointing real devices at it.

Runs eight checks and prints PASS / FAIL / WARN for each:

  1. config.json loads and every required key is present
  2. queue_db_path is writable (SQLite queue can be created)
  3. cloud_upload_log_path is writable
  4. the syslog UDP port can be bound
  5. the cloud endpoint's host:port is reachable (TCP)
  6. GET /livez on the cloud host answers
  7. POST a synthetic batch to the real ingest endpoint and show the response
     (uses device_id _preflight:<edge_id> so it cannot be mistaken for a real device)
  8. device_map sanity: entry count, wildcard rows, duplicate device_ids

Exit code is 0 only if no check FAILED.

Usage
-----
    python3 preflight.py
    python3 preflight.py --config /etc/edge-agent/config.json
    python3 preflight.py --port 514            # check the port you'll really use
    python3 preflight.py --no-post             # skip the live POST (check 7)
"""
import argparse
import json
import os
import socket
import sqlite3
import sys
import tempfile
import time
from collections import Counter
from urllib.parse import urlparse

try:
    import config as agent_config
except ImportError:
    sys.exit("Run this from the syslog/ directory (needs config.py).")

try:
    import requests
except ImportError:
    sys.exit("Missing dependency: pip3 install requests")

RESULTS = []
REQUIRED_KEYS = [
    "edge_id", "service_provider", "property_id", "cloud_endpoint",
    "summary_interval_seconds", "window_seconds", "stale_threshold_seconds",
    "upload_batch_size", "upload_retry_seconds", "queue_db_path", "device_map",
]


def report(name, ok, detail="", warn=False):
    tag = "WARN" if warn else ("PASS" if ok else "FAIL")
    RESULTS.append((tag, name))
    print(f"  [{tag}] {name}")
    for line in str(detail).splitlines():
        if line.strip():
            print(f"         {line}")


def check_config(cfg, path):
    missing = [k for k in REQUIRED_KEYS if k not in cfg or cfg[k] in (None, "")]
    src = path if os.path.exists(path) else f"{path} NOT FOUND — using DEFAULT_CONFIG from config.py"
    if missing:
        report("1. config loads with all required keys", False,
               f"source: {src}\nmissing/empty: {missing}")
        return
    detail = (f"source: {src}\n"
              f"edge_id={cfg['edge_id']}  service_provider={cfg['service_provider']}  "
              f"property_id={cfg['property_id']}\n"
              f"cloud_endpoint={cfg['cloud_endpoint']}")
    report("1. config loads with all required keys", True, detail)
    if not os.path.exists(path):
        report("1b. config.json exists on disk", False,
               f"{path} is missing — the agent is running on built-in defaults.\n"
               f"Create it (see config.example.json) or every edge box will report "
               f"the same property_id.")


def check_queue_writable(cfg):
    p = cfg.get("queue_db_path", "")
    try:
        d = os.path.dirname(p) or "."
        os.makedirs(d, exist_ok=True)
        conn = sqlite3.connect(p)
        conn.execute("CREATE TABLE IF NOT EXISTS _preflight (x INTEGER)")
        conn.execute("DROP TABLE _preflight")
        conn.close()
        report("2. queue_db_path is writable", True, p)
    except Exception as e:
        report("2. queue_db_path is writable", False,
               f"{p}\n{type(e).__name__}: {e}\n"
               f"fix: sudo mkdir -p {os.path.dirname(p) or '/'} && "
               f"sudo chown edge-agent:edge-agent {os.path.dirname(p) or '/'}")


def check_log_writable(cfg):
    p = (cfg.get("cloud_upload_log_path") or cfg.get("cloud_payload_log_path") or "").strip()
    if not p:
        report("3. cloud_upload_log_path is writable", True, "disabled (empty) — nothing to check",
               warn=True)
        return
    try:
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write("")
        report("3. cloud_upload_log_path is writable", True,
               f"{p}\nNOTE: this file is never rotated — it grows with every upload. "
               f"Add a logrotate rule.")
    except Exception as e:
        report("3. cloud_upload_log_path is writable", False, f"{p}\n{type(e).__name__}: {e}")


def check_port(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind(("0.0.0.0", port))
        extra = ""
        if port >= 1024:
            extra = ("\nNOTE: most switches/routers send syslog to UDP 514 by default. "
                     "If you listen on 5514 you must either reconfigure every device or "
                     "add:  sudo iptables -t nat -A PREROUTING -p udp --dport 514 "
                     "-j REDIRECT --to-port 5514")
        report(f"4. UDP port {port} can be bound", True, f"0.0.0.0:{port}/udp{extra}")
    except PermissionError:
        report(f"4. UDP port {port} can be bound", False,
               f"permission denied (port <1024 needs root).\n"
               f"fix: give the service CAP_NET_BIND_SERVICE, or listen on 5514 and "
               f"redirect 514 -> 5514 with iptables")
    except OSError as e:
        report(f"4. UDP port {port} can be bound", False,
               f"{type(e).__name__}: {e}\ncheck what already holds it: sudo ss -ulnp | grep {port}")
    finally:
        s.close()


def check_tcp(cfg):
    url = urlparse(cfg["cloud_endpoint"])
    host = url.hostname
    port = url.port or (443 if url.scheme == "https" else 80)
    if url.scheme != "https":
        report("5a. cloud_endpoint uses HTTPS", False,
               f"endpoint is {url.scheme}:// — device health data and the X-Provider-Id "
               f"header cross the network in clear text. Terminate TLS "
               f"(nginx/Caddy) in front of the API and use https://.")
    else:
        report("5a. cloud_endpoint uses HTTPS", True, cfg["cloud_endpoint"])
    t0 = time.time()
    try:
        with socket.create_connection((host, port), timeout=8):
            ms = int((time.time() - t0) * 1000)
        report(f"5b. TCP reachable {host}:{port}", True, f"connected in {ms} ms")
        return True
    except Exception as e:
        report(f"5b. TCP reachable {host}:{port}", False,
               f"{type(e).__name__}: {e}\n"
               f"check: outbound firewall on the customer network allows this box to "
               f"reach {host}:{port}, and any egress proxy/NAT rule")
        return False


def check_livez(cfg):
    url = urlparse(cfg["cloud_endpoint"])
    base = f"{url.scheme}://{url.netloc}"
    try:
        r = requests.get(f"{base}/livez", timeout=8)
        ok = r.status_code == 200
        report("6. cloud API /livez", ok, f"{base}/livez -> HTTP {r.status_code} {r.text[:200]}")
    except Exception as e:
        report("6. cloud API /livez", False, f"{base}/livez -> {type(e).__name__}: {e}")


def check_post(cfg):
    now = time.time()
    dev = f"_preflight:{cfg['edge_id']}"
    body = {
        "schema_version": "1.0",
        "edge_id": cfg["edge_id"],
        "service_provider": cfg["service_provider"],
        "property_id": cfg["property_id"],
        "property_name": cfg.get("property_name") or cfg["property_id"],
        "messages": [
            {"kind": "edge_health", "ts": now,
             "metrics": {"tracked_devices": 0, "unhealthy_devices": 0, "queue_depth": 0,
                         "summary_interval_seconds": cfg["summary_interval_seconds"]}},
            {"kind": "periodic", "ts": now, "device_id": dev,
             "device_name": "preflight_probe", "device_class": "unknown",
             "vendor": "unknown", "site": "preflight",
             "health": {"status": "healthy", "score": 100, "reasons": []},
             "metrics": {"event_count": 0, "error_count": 0, "warn_count": 0}},
        ],
    }
    try:
        r = requests.post(cfg["cloud_endpoint"], json=body,
                          headers={"X-Provider-Id": cfg["service_provider"]}, timeout=15)
    except Exception as e:
        report("7. POST /v1/edge/ingest accepted", False, f"{type(e).__name__}: {e}")
        return

    ok = 200 <= r.status_code < 300
    detail = [f"HTTP {r.status_code} {getattr(r, 'reason', '')}", f"response: {r.text[:600]}"]
    if ok:
        try:
            j = r.json()
            if j.get("rejected"):
                detail.append(f"WARNING: server rejected {len(j['rejected'])} message(s): "
                              f"{j['rejected']}")
                ok = False
        except Exception:
            pass
        detail.append(f"a device named {dev} now exists in the dashboard — "
                      f"delete it after testing if you don't want it there")
    elif r.status_code == 422:
        detail.append("422 = payload shape rejected. Check the agent's message schema "
                      "against backend/app/schemas/ingest.py.")
    elif r.status_code in (401, 403):
        detail.append("auth rejected — check the X-Provider-Id / service_provider value.")
    elif r.status_code >= 500:
        detail.append(f"server-side error. Likely the provider "
                      f"'{cfg['service_provider']}' does not exist in service_providers. "
                      f"On the cloud host run: docker exec hosp_api python add_provider.py")
    report("7. POST /v1/edge/ingest accepted", ok, "\n".join(detail))


def check_device_map(cfg):
    raw = cfg.get("device_map", {}) or {}
    # tolerate "_README"-style comment keys someone may leave in config.json
    dm = {k: v for k, v in raw.items()
          if not k.startswith("_") and isinstance(v, dict)}
    if not dm:
        report("8. device_map sanity", False,
               "device_map is EMPTY — every incoming syslog packet will be silently "
               "discarded. Run discover.py to build it.")
        return
    wildcards = [k for k in dm if k.startswith("*|")]
    ids = Counter(v.get("device_id") for v in dm.values())
    dupes = {k: n for k, n in ids.items() if n > 1}
    placeholders = [k for k, v in dm.items()
                    if "REPLACE-ME" in str(v.get("device_id", ""))
                    or "REPLACE-ME" in str(v.get("site", ""))]
    lines = [f"{len(dm)} entries, {len(set(ids))} distinct device_ids"]
    ok = True
    if placeholders:
        ok = False
        lines.append(f"FAIL: {len(placeholders)} entries still contain REPLACE-ME: "
                     f"{placeholders[:5]}")
    if wildcards:
        lines.append(f"WARN: {len(wildcards)} wildcard entries {wildcards[:8]} — these accept "
                     f"that hostname from ANY source IP. Remove the simulator rows "
                     f"(*|switch-floor1 etc.) before going live or spoofed/duplicate "
                     f"hostnames will be attributed to real devices.")
    if dupes:
        lines.append(f"WARN: device_ids reused across entries: {dupes} — two physical "
                     f"devices sharing one device_id will overwrite each other's health.")
    report("8. device_map sanity", ok, "\n".join(lines), warn=bool(wildcards or dupes) and ok)


def main():
    ap = argparse.ArgumentParser(description="Pre-deployment readiness check for the edge agent.")
    ap.add_argument("--config", default="/etc/edge-agent/config.json")
    ap.add_argument("--port", type=int, default=None,
                    help="syslog UDP port to test (default: listen_port from config, else 5514)")
    ap.add_argument("--no-post", action="store_true", help="skip the live POST to the cloud")
    args = ap.parse_args()

    cfg = agent_config.load(args.config)
    port = args.port or cfg.get("listen_port") or 5514

    print("=" * 78)
    print("EDGE AGENT PREFLIGHT")
    print("=" * 78)
    check_config(cfg, args.config)
    check_queue_writable(cfg)
    check_log_writable(cfg)
    check_port(port)
    reachable = check_tcp(cfg)
    if reachable:
        check_livez(cfg)
        if not args.no_post:
            check_post(cfg)
    else:
        report("6. cloud API /livez", False, "skipped — host not reachable")
        report("7. POST /v1/edge/ingest accepted", False, "skipped — host not reachable")
    check_device_map(cfg)

    tally = Counter(t for t, _ in RESULTS)
    print()
    print("=" * 78)
    print(f"SUMMARY: {tally['PASS']} passed, {tally['WARN']} warnings, {tally['FAIL']} failed")
    if tally["FAIL"]:
        print("\nFAILED checks:")
        for t, n in RESULTS:
            if t == "FAIL":
                print(f"  - {n}")
        print("\nDo NOT point customer devices at this box until these are fixed.")
    else:
        print("\nReady. Point one device at this box and run discover.py to confirm arrival.")
    print("=" * 78)
    sys.exit(1 if tally["FAIL"] else 0)


if __name__ == "__main__":
    main()
