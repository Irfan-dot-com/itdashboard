#!/usr/bin/env python3
"""
preflight.py - verify the poller is ready before enabling the service.

Ten checks, PASS / WARN / FAIL each. Exit code is 0 only if nothing FAILED.

    python3 preflight.py
    python3 preflight.py --config /etc/sdlan-poller/config.json
    python3 preflight.py --no-post          # skip the live POST to the cloud
"""
import argparse
import json
import os
import socket
import sqlite3
import stat
import sys
import time
from collections import Counter
from urllib.parse import urlparse

import config as poller_config
import mapper
from sdlan_client import SdLanClient, SdLanError, iter_devices

try:
    import requests
except ImportError:
    sys.exit("Missing dependency: pip3 install requests")

RESULTS = []


def report(name, ok, detail="", warn=False):
    tag = "WARN" if warn else ("PASS" if ok else "FAIL")
    RESULTS.append((tag, name))
    print(f"  [{tag}] {name}")
    for line in str(detail).splitlines():
        if line.strip():
            print(f"         {line}")


# ------------------------------------------------------------------ checks

def check_config(cfg, path):
    missing = poller_config.missing_keys(cfg)
    exists = os.path.exists(path)
    src = path if exists else f"{path} NOT FOUND - using built-in defaults"
    if missing:
        return report("1. config has all required values", False,
                      f"source: {src}\nunset or empty: {missing}")
    placeholders = [k for k, v in cfg.items()
                    if isinstance(v, str) and ("EDIT-ME" in v or "REPLACE-ME" in v)]
    if placeholders:
        return report("1. config has all required values", False,
                      f"source: {src}\nstill contains placeholder text: {placeholders}")
    report("1. config has all required values", True,
           f"source: {src}\n"
           f"edge_id={cfg['edge_id']}  property_id={cfg['property_id']}  "
           f"provider={cfg['service_provider']}\n"
           f"platform={poller_config.safe_url(cfg)}\n"
           f"poll_interval={cfg['poll_interval_seconds']}s")
    if not exists:
        report("1b. config file exists on disk", False,
               f"{path} is missing, so this box is running on defaults - every "
               f"poller would report the same property_id and a placeholder URL.")


def check_secret_permissions(path):
    """The config holds SD-LAN credentials; it must not be world-readable."""
    if not os.path.exists(path):
        return report("2. config file permissions", True, "no file yet - skipped",
                      warn=True)
    try:
        st = os.stat(path)
        mode = stat.S_IMODE(st.st_mode)
        world = mode & 0o007
        group_w = mode & 0o020
        detail = f"{path} mode {oct(mode)}"
        if world:
            return report("2. config file permissions", False,
                          f"{detail}\nWORLD-READABLE and it contains the SD-LAN "
                          f"password. Fix:\n"
                          f"  sudo chown root:sdlan-poller {path}\n"
                          f"  sudo chmod 640 {path}")
        if group_w:
            return report("2. config file permissions", True,
                          f"{detail}\ngroup-writable; 640 is tighter", warn=True)
        report("2. config file permissions", True, detail)
    except OSError as e:
        report("2. config file permissions", False, f"{path}: {e}")


def check_sqlite(cfg):
    for label, key in (("queue", "queue_db_path"), ("state", "state_db_path")):
        p = cfg.get(key, "")
        try:
            os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
            conn = sqlite3.connect(p)
            conn.execute("CREATE TABLE IF NOT EXISTS _preflight (x INTEGER)")
            conn.execute("DROP TABLE _preflight")
            conn.close()
            report(f"3. {label} db writable", True, p)
        except Exception as e:
            report(f"3. {label} db writable", False,
                   f"{p}\n{type(e).__name__}: {e}\n"
                   f"fix: sudo mkdir -p {os.path.dirname(p) or '/'} && "
                   f"sudo chown sdlan-poller:sdlan-poller {os.path.dirname(p) or '/'}")


def check_logs(cfg):
    for label, key in (("cloud upload log", "cloud_upload_log_path"),
                       ("sdlan raw log", "sdlan_raw_log_path")):
        p = (cfg.get(key) or "").strip()
        if not p:
            report(f"4. {label} writable", True, "disabled (empty)", warn=True)
            continue
        try:
            os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
            with open(p, "a", encoding="utf-8"):
                pass
            extra = ""
            if key == "sdlan_raw_log_path":
                extra = ("\nthis logs every raw API response - useful while mapping, "
                         "grows fast. Set to \"\" once the mapping is settled.")
            report(f"4. {label} writable", True, f"{p}{extra}")
        except Exception as e:
            report(f"4. {label} writable", False, f"{p}\n{type(e).__name__}: {e}")


def check_platform_tls(cfg):
    url = urlparse(cfg["sdlan_base_url"])
    if url.scheme != "https":
        return report("5. platform URL uses HTTPS", False,
                      f"sdlan_base_url is {url.scheme}:// - the SD-LAN username and "
                      f"password would cross the customer network in clear text. "
                      f"Use https://.")
    if not cfg.get("sdlan_verify_tls", True):
        return report("5. platform URL uses HTTPS", True,
                      f"{cfg['sdlan_base_url']} but sdlan_verify_tls is false, so the "
                      f"certificate is not checked. Acceptable only for a lab. For a "
                      f"private CA set sdlan_ca_bundle instead.", warn=True)
    report("5. platform URL uses HTTPS", True, cfg["sdlan_base_url"])


def check_platform_tcp(cfg):
    url = urlparse(cfg["sdlan_base_url"])
    host = url.hostname
    port = url.port or (443 if url.scheme == "https" else 80)
    t0 = time.time()
    try:
        with socket.create_connection((host, port), timeout=10):
            ms = int((time.time() - t0) * 1000)
        report(f"6. platform reachable {host}:{port}", True, f"connected in {ms} ms")
        return True
    except Exception as e:
        report(f"6. platform reachable {host}:{port}", False,
               f"{type(e).__name__}: {e}\n"
               f"check: the edge box can route to the orchestration platform, and "
               f"the customer's firewall allows it")
        return False


def check_platform_auth(cfg):
    """Does the API answer, and with what?"""
    try:
        data = SdLanClient(cfg).status()
    except SdLanError as e:
        report("7. SD-LAN API answers query=status", False,
               f"{e}\n"
               f"if this is an encoding mismatch, run:  python3 probe.py --try-formats")
        return None
    if not isinstance(data, dict):
        report("7. SD-LAN API answers query=status", False,
               f"expected a JSON object, got {type(data).__name__}")
        return None
    report("7. SD-LAN API answers query=status", True,
           f"hostname={data.get('hostname')}  switches={data.get('switches')}  "
           f"optical_edge={data.get('fttp_active')}\n"
           f"problems={len(data.get('problems') or [])}  "
           f"uptime={data.get('uptime')}")
    return data


def check_devices(cfg):
    try:
        networks = SdLanClient(cfg).networks()
    except SdLanError as e:
        report("8. SD-LAN API returns devices", False, str(e))
        return []
    rows = list(iter_devices(networks))
    if not rows:
        report("8. SD-LAN API returns devices", False,
               "no device records recognised in the networks response.\n"
               "dump and inspect it:  python3 probe.py --raw networks")
        return []

    ids, bad = [], []
    for domain, site, dev in rows:
        msg = mapper.device_message(cfg, dev, domain, site)
        if msg is None:
            bad.append(list(dev)[:4])
            continue
        ids.append(msg["device_id"])

    dupes = {k: n for k, n in Counter(ids).items() if n > 1}
    lines = [f"{len(rows)} device records, {len(set(ids))} distinct device_ids",
             f"sample ids: {ids[:4]}"]
    ok = True
    if bad:
        ok = False
        lines.append(f"FAIL: {len(bad)} record(s) had no usable id field: {bad[:3]}")
    if dupes:
        ok = False
        lines.append(f"FAIL: duplicate device_ids {dupes} - two devices would "
                     f"overwrite each other in the cloud devices table. Change "
                     f"device_id_source (dev_id | hw_sn | hw_ident).")
    if not (cfg.get("device_id_prefix") or "").strip():
        lines.append("WARN: device_id_prefix is empty. Set it per property or ids "
                     "from two platforms can collide in the cloud.")
    report("8. SD-LAN API returns devices", ok, "\n".join(lines),
           warn=ok and not (cfg.get("device_id_prefix") or "").strip())
    return rows


def check_cloud(cfg, do_post):
    url = urlparse(cfg["cloud_endpoint"])
    base = f"{url.scheme}://{url.netloc}"
    if url.scheme != "https":
        report("9a. cloud endpoint uses HTTPS", False,
               f"{cfg['cloud_endpoint']} is plain HTTP - terminate TLS in front of "
               f"the dashboard API.")
    else:
        report("9a. cloud endpoint uses HTTPS", True, cfg["cloud_endpoint"])

    try:
        r = requests.get(f"{base}/livez", timeout=10)
        report("9b. cloud API /livez", r.status_code == 200,
               f"{base}/livez -> HTTP {r.status_code} {r.text[:150]}")
    except Exception as e:
        report("9b. cloud API /livez", False,
               f"{base}/livez -> {type(e).__name__}: {e}")
        report("10. cloud accepts a test batch", False, "skipped - cloud unreachable")
        return

    if not do_post:
        report("10. cloud accepts a test batch", True, "skipped (--no-post)", warn=True)
        return

    now = time.time()
    dev = f"_preflight:{cfg['edge_id']}"
    body = {
        "schema_version": "1.0",
        "edge_id": cfg["edge_id"],
        "service_provider": cfg["service_provider"],
        "property_id": cfg["property_id"],
        "property_name": cfg.get("property_name") or cfg["property_id"],
        "messages": [
            mapper.edge_health_message(cfg, 0, 0, 0, now=now),
            {"kind": "periodic", "ts": now, "device_id": dev,
             "device_name": "preflight_probe", "device_class": "unknown",
             "vendor": "unknown", "site": "preflight",
             "health": {"status": "healthy", "score": 100, "reasons": []},
             "metrics": {"event_count": 0, "error_count": 0, "warn_count": 0}},
        ],
    }
    try:
        r = requests.post(cfg["cloud_endpoint"], json=body,
                          headers={"X-Provider-Id": cfg["service_provider"]},
                          timeout=20)
    except Exception as e:
        return report("10. cloud accepts a test batch", False,
                      f"{type(e).__name__}: {e}")

    ok = 200 <= r.status_code < 300
    detail = [f"HTTP {r.status_code} {getattr(r, 'reason', '')}",
              f"response: {r.text[:400]}"]
    if ok:
        try:
            j = r.json()
            if j.get("rejected"):
                ok = False
                detail.append(f"server rejected {len(j['rejected'])}: {j['rejected']}")
        except Exception:
            pass
        detail.append(f"a device named {dev} now exists in the dashboard - remove it "
                      f"after testing if you don't want it there")
    elif r.status_code in (401, 403):
        detail.append("auth rejected - check service_provider / X-Provider-Id")
    elif r.status_code >= 500:
        detail.append(f"likely the provider '{cfg['service_provider']}' is not in the "
                      f"service_providers table. On the cloud host run:\n"
                      f"  docker exec hosp_api python add_provider.py")
    report("10. cloud accepts a test batch", ok, "\n".join(detail))


def main():
    ap = argparse.ArgumentParser(description="SD-LAN poller readiness check")
    ap.add_argument("--config", default="/etc/sdlan-poller/config.json")
    ap.add_argument("--no-post", action="store_true")
    args = ap.parse_args()

    cfg = poller_config.load(args.config)

    print("=" * 78)
    print("SD-LAN POLLER PREFLIGHT")
    print("=" * 78)
    check_config(cfg, args.config)
    check_secret_permissions(args.config)
    check_sqlite(cfg)
    check_logs(cfg)
    check_platform_tls(cfg)
    if check_platform_tcp(cfg):
        if check_platform_auth(cfg) is not None:
            check_devices(cfg)
        else:
            report("8. SD-LAN API returns devices", False, "skipped - status failed")
    else:
        report("7. SD-LAN API answers query=status", False, "skipped - unreachable")
        report("8. SD-LAN API returns devices", False, "skipped - unreachable")
    check_cloud(cfg, not args.no_post)

    tally = Counter(t for t, _ in RESULTS)
    print()
    print("=" * 78)
    print(f"SUMMARY: {tally['PASS']} passed, {tally['WARN']} warnings, "
          f"{tally['FAIL']} failed")
    if tally["FAIL"]:
        print("\nFAILED:")
        for t, n in RESULTS:
            if t == "FAIL":
                print(f"  - {n}")
        print("\nFix these before enabling the service.")
    else:
        print("\nReady. Start it with:  sudo systemctl enable --now sdlan-poller")
    print("=" * 78)
    sys.exit(1 if tally["FAIL"] else 0)


if __name__ == "__main__":
    main()
