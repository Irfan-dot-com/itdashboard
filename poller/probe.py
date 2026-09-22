#!/usr/bin/env python3
"""
probe.py - point this at the customer's SD-LAN platform and see what comes back.

This is the first thing to run after setting the URL and credentials. It does
not touch the cloud dashboard, does not write to the outbound queue, and only
ever reads. Safe to run on a customer network.

    python3 probe.py                         # connect, list devices, assess health
    python3 probe.py --try-formats           # find which POST encoding works
    python3 probe.py --raw status            # dump one raw response
    python3 probe.py --raw networks --save /tmp/networks.json
    python3 probe.py --device-details 11     # per-port stats for one device
    python3 probe.py --slice "MDF Core Switch"

What to check in the output:
  * every device you expect appears, with a sensible name and site
  * the assessed status matches reality on the floor
  * device_id values look right - they become permanent keys in the cloud DB
  * the field-coverage report at the end shows nothing important "missing",
    which would mean the real platform names that field differently
"""
import argparse
import json
import sys
import time

import config as poller_config
import mapper
from sdlan_client import SdLanClient, SdLanError, iter_devices, iter_problems

# Fields the mapper relies on. Anything missing here means the real platform
# differs from the tech pub and the mapping needs adjusting.
EXPECTED_DEVICE_FIELDS = [
    "dev_id", "hw_mfg", "endpoint_name", "hw_ip", "hw_model", "hw_hostname",
    "hw_sn", "hw_ident", "lost_contact", "attributes", "connections",
    "is_tor", "topology_depth", "endpoint_id",
]
EXPECTED_STATUS_FIELDS = [
    "switches", "fttp_active", "fttp_lost_contact", "fttp_rebooted", "uptime",
    "hostname", "freespace", "bufferwatch", "problems", "tenant_licenses",
    "loadavg", "switch_status", "timestamp",
]


def hr(title=""):
    print("=" * 78)
    if title:
        print(title)
        print("=" * 78)


def try_formats(cfg):
    """The tech pub is ambiguous about POST encoding; find what the box accepts."""
    hr("TRYING EACH REQUEST ENCODING")
    combos = [("POST", "form"), ("POST", "json"), ("POST", "query"), ("GET", "form")]
    winners = []
    for method, fmt in combos:
        probe_cfg = {**cfg, "sdlan_http_method": method, "sdlan_post_format": fmt}
        label = f"{method} + {fmt}"
        try:
            data = SdLanClient(probe_cfg).status()
            keys = list(data)[:6] if isinstance(data, dict) else type(data).__name__
            print(f"  [OK  ] {label:<14} -> {keys}")
            winners.append((method, fmt))
        except SdLanError as e:
            print(f"  [FAIL] {label:<14} -> {str(e)[:150]}")
    print()
    if winners:
        m, f = winners[0]
        print(f"  Use these in config.json:")
        print(f'      "sdlan_http_method": "{m}",')
        print(f'      "sdlan_post_format": "{f}"')
        if ("POST", "form") not in winners and ("POST", "json") not in winners:
            print("  WARNING: only a query-string form worked, which puts credentials")
            print("           in the URL. Ask Corning whether POST body is supported.")
    else:
        print("  Nothing worked. Check the base URL, credentials and TLS settings.")
    print()
    return winners


# Fields whose normal value is null, so "present but null" is healthy, not a
# mapping problem: lost_contact is null while a device IS in contact.
NULLABLE_OK = {"lost_contact", "lost_reason", "site_wan_status", "site_vfs_status"}


def coverage(label, records, expected):
    """
    Report which expected fields the platform actually returns.

    Distinguishes a key that is absent (the mapper will never see it - a real
    mapping problem) from a key present with a null value (normal for
    lost_contact and friends).
    """
    if not records:
        print(f"  no {label} records to check")
        return
    total = len(records)
    present, null_only, absent = [], [], []
    for f in expected:
        has_key = sum(1 for r in records if isinstance(r, dict) and f in r)
        has_val = sum(1 for r in records
                      if isinstance(r, dict) and r.get(f) is not None)
        if has_val:
            present.append(f"{f}({has_val}/{total})")
        elif has_key:
            null_only.append(f)
        else:
            absent.append(f)

    print(f"  {label} fields with values : {', '.join(present) or 'none'}")
    if null_only:
        expected_nulls = [f for f in null_only if f in NULLABLE_OK]
        odd_nulls = [f for f in null_only if f not in NULLABLE_OK]
        if expected_nulls:
            print(f"  {label} present but null   : {', '.join(expected_nulls)}  "
                  f"(normal - null here means nothing wrong)")
        if odd_nulls:
            print(f"  {label} present but null   : {', '.join(odd_nulls)}  "
                  f"(worth a look - expected a value)")
    if absent:
        print(f"  {label} fields ABSENT      : {', '.join(absent)}")
        print(f"      ^ the mapper looks for these and will never find them. If any")
        print(f"        matter, this platform names them differently - dump a raw")
        print(f"        response and adjust mapper.py.")
    else:
        print(f"  {label} fields ABSENT      : none")


def main():
    ap = argparse.ArgumentParser(description="Inspect a Corning SD-LAN platform")
    ap.add_argument("--config", default="/etc/sdlan-poller/config.json")
    ap.add_argument("--try-formats", action="store_true",
                    help="test each HTTP method / body encoding and report what works")
    ap.add_argument("--raw", choices=["status", "networks"],
                    help="print one raw JSON response and exit")
    ap.add_argument("--save", help="with --raw, also write the JSON to this file")
    ap.add_argument("--device-details", metavar="DEV_ID",
                    help="fetch per-port statistics for one dev_id")
    ap.add_argument("--slice", metavar="ENDPOINT", help="fetch the slice view")
    ap.add_argument("--hours", type=int, default=1,
                    help="with --device-details, how far back (default 1h)")
    args = ap.parse_args()

    cfg = poller_config.load(args.config)
    missing = poller_config.missing_keys(cfg)
    if missing:
        sys.exit(f"config {args.config} incomplete - set: {', '.join(missing)}")

    hr("SD-LAN PROBE")
    print(f"  config   : {args.config}")
    print(f"  platform : {poller_config.safe_url(cfg)}")
    print(f"  user     : {cfg['sdlan_username']}  (password not shown)")
    print(f"  method   : {cfg.get('sdlan_http_method')} / {cfg.get('sdlan_post_format')}")
    print(f"  verify   : tls={cfg.get('sdlan_verify_tls')} "
          f"ca={cfg.get('sdlan_ca_bundle') or '(system)'}")
    print()

    if args.try_formats:
        try_formats(cfg)
        return

    client = SdLanClient(cfg)

    if args.raw:
        data = client.status() if args.raw == "status" else client.networks()
        text = json.dumps(poller_config.redact(data), indent=2, default=str)
        print(text)
        if args.save:
            with open(args.save, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"\n  saved to {args.save}")
        return

    if args.device_details:
        now = int(time.time())
        data = client.device_details(dev_id=args.device_details,
                                     start=now - args.hours * 3600, stop=now)
        print(json.dumps(poller_config.redact(data), indent=2, default=str)[:6000])
        return

    if args.slice:
        data = client.slice_view(args.slice)
        print(json.dumps(poller_config.redact(data), indent=2, default=str))
        return

    # ---------------------------------------------------------- devices
    t0 = time.time()
    try:
        networks = client.networks()
    except SdLanError as e:
        sys.exit(f"\n  networks query FAILED: {e}\n\n"
                 f"  Try:  python3 probe.py --config {args.config} --try-formats")
    elapsed = time.time() - t0

    rows = list(iter_devices(networks))
    hr(f"DEVICES ({len(rows)} found in {elapsed:.1f}s)")
    if not rows:
        print("  No device records recognised in the networks response.")
        print("  Dump it and check the shape:")
        print(f"      python3 probe.py --config {args.config} --raw networks")
        return

    print(f"  {'DEVICE_ID':<26} {'NAME':<24} {'STATUS':<10} {'SCORE':>5}  REASONS")
    print("  " + "-" * 94)
    devices = []
    by_status = {}
    for domain, site, dev in rows:
        msg = mapper.device_message(cfg, dev, domain, site)
        if msg is None:
            print(f"  (skipped a record with no usable id: {list(dev)[:5]})")
            continue
        devices.append(dev)
        st = msg["health"]["status"]
        by_status[st] = by_status.get(st, 0) + 1
        reasons = ", ".join(msg["health"]["reasons"]) or "-"
        print(f"  {msg['device_id']:<26} {msg['device_name'][:24]:<24} "
              f"{st:<10} {msg['health']['score']:>5}  {reasons[:46]}")

    print()
    print(f"  by status: {by_status}")
    print(f"  sites seen: {sorted({(s or d or '?') for d, s, _ in rows})}")
    print()

    # ---------------------------------------------------------- platform
    hr("PLATFORM (query=status)")
    try:
        status = client.status() or {}
        problems = list(iter_problems(status))
        pmsg = mapper.platform_message(cfg, status, problems)
        print(f"  hostname   : {status.get('hostname')}")
        print(f"  switches   : {status.get('switches')}   "
              f"optical edge active: {status.get('fttp_active')}   "
              f"out of contact: {status.get('fttp_lost_contact')}")
        up = status.get("uptime")
        if isinstance(up, (int, float)):
            print(f"  uptime     : {up / 86400:.1f} days")
        print(f"  freespace  : {status.get('freespace')}   "
              f"loadavg: {status.get('loadavg')}   "
              f"bufferwatch: {status.get('bufferwatch')}")
        print(f"  assessed   : {pmsg['health']['status']} "
              f"score={pmsg['health']['score']} {pmsg['health']['reasons']}")
        print(f"  problems   : {len(problems)}")
        for p in problems[:8]:
            print(f"     - {p.get('element_name') or p.get('element') or '?'}: "
                  f"{p.get('message')}")
    except SdLanError as e:
        status, problems = {}, []
        print(f"  status query FAILED: {e}")
    print()

    # ---------------------------------------------------------- coverage
    hr("FIELD COVERAGE (tech pub vs what this platform actually returns)")
    coverage("device", devices, EXPECTED_DEVICE_FIELDS)
    print()
    coverage("status", [status] if status else [], EXPECTED_STATUS_FIELDS)
    print()

    hr("NEXT")
    print("  1. Check the device_id column above - those become permanent keys in")
    print("     the cloud devices table. Set device_id_prefix per property.")
    print("  2. Check the assessed status against reality. If a device you know is")
    print("     faulty reads healthy, the relevant field is probably in the MISSING")
    print("     list - dump it with --raw networks and adjust mapper.py.")
    print("  3. Then run preflight.py, and start the service.")
    print()


if __name__ == "__main__":
    main()
