#!/usr/bin/env python3
"""
discover.py — find out what is actually sending syslog to this edge box.

You cannot write config.json's device_map until you know the real source IPs and
syslog hostnames of the customer's devices. This tool listens on the syslog port,
shows every talker it hears, and writes a ready-to-paste device_map skeleton.

It never uploads anything and never writes to the outbound queue. Safe to run on
a customer network.

Usage
-----
    # listen for 10 minutes on the port the devices are pointed at
    sudo python3 discover.py --port 514 --duration 600

    # listen until Ctrl-C, refreshing the table every 15s
    python3 discover.py --port 5514 --interval 15

    # write the device_map skeleton somewhere specific
    python3 discover.py --port 514 --duration 300 --out /tmp/device_map.json

Output
------
  * a live table of every (src_ip, hostname) pair, packet counts and severities
  * MAPPED / UNMAPPED against the device_map currently in config.json
  * a device_map skeleton written to --out, ready to paste into config.json
"""
import argparse
import json
import re
import signal
import socket
import sys
import time
from collections import defaultdict

try:
    import config as agent_config
    from syslog_listener import parse_message
except ImportError:
    sys.exit("Run this from the syslog/ directory (needs config.py and syslog_listener.py).")


class Talker:
    __slots__ = ("src_ip", "host", "count", "parse_errors", "severities",
                 "first_seen", "last_seen", "samples", "tags")

    def __init__(self, src_ip, host):
        self.src_ip = src_ip
        self.host = host
        self.count = 0
        self.parse_errors = 0
        self.severities = defaultdict(int)
        self.tags = defaultdict(int)
        self.first_seen = time.time()
        self.last_seen = self.first_seen
        self.samples = []

    def record(self, event):
        self.count += 1
        self.last_seen = time.time()
        self.severities[event.get("severity", "?")] += 1
        tag = (event.get("tag") or "").strip()
        if tag:
            self.tags[tag[:40]] += 1
        msg = event.get("message", "")
        if len(self.samples) < 3 and msg:
            self.samples.append(msg[:120])


def guess_class(host, tags):
    """Best-effort device_class guess from hostname and syslog tag."""
    blob = (host + " " + " ".join(tags)).lower()
    for needle, klass in (
        ("switch", "switch"), ("sw-", "switch"), ("poe", "poe_switch"),
        ("router", "router"), ("rtr", "router"), ("gw", "router"),
        ("firewall", "firewall"), ("fw", "firewall"), ("fortigate", "firewall"),
        ("asa", "firewall"), ("palo", "firewall"),
        ("ap-", "wifi_ap"), ("wlc", "wifi_controller"), ("hostapd", "wifi_ap"),
        ("ups", "ups"), ("apc", "ups"),
        ("pbx", "pbx"), ("asterisk", "pbx"), ("sip", "pbx"), ("dect", "dect"),
        ("printer", "printer"), ("cam", "camera"),
        ("esx", "hypervisor"), ("vmware", "hypervisor"),
    ):
        if needle in blob:
            return klass
    return "unknown"


def guess_vendor(tags, samples):
    blob = (" ".join(tags) + " " + " ".join(samples)).lower()
    for needle, vendor in (
        ("%sys-", "cisco"), ("%link", "cisco"), ("%lineproto", "cisco"),
        ("ios", "cisco"), ("nx-os", "cisco"),
        ("fortigate", "fortinet"), ("logid=", "fortinet"),
        ("juniper", "juniper"), ("mgd", "juniper"),
        ("mikrotik", "mikrotik"), ("routeros", "mikrotik"),
        ("ubnt", "ubiquiti"), ("unifi", "ubiquiti"),
        ("aruba", "aruba"), ("hpe", "hpe"), ("procurve", "hpe"),
        ("arista", "arista"), ("apc", "apc"), ("asterisk", "asterisk"),
    ):
        if needle in blob:
            return vendor
    return "unknown"


def main():
    ap = argparse.ArgumentParser(description="Discover syslog talkers on this edge box.")
    ap.add_argument("--host", default="0.0.0.0", help="bind address (default 0.0.0.0)")
    ap.add_argument("--port", type=int, default=5514,
                    help="UDP port to listen on (default 5514; use 514 with sudo)")
    ap.add_argument("--duration", type=int, default=0,
                    help="stop after N seconds (default: run until Ctrl-C)")
    ap.add_argument("--interval", type=int, default=15,
                    help="seconds between table refreshes (default 15)")
    ap.add_argument("--out", default="discovered_device_map.json",
                    help="where to write the device_map skeleton")
    ap.add_argument("--config", default="/etc/edge-agent/config.json",
                    help="config to compare against (default /etc/edge-agent/config.json)")
    args = ap.parse_args()

    cfg = agent_config.load(args.config)
    existing = cfg.get("device_map", {})

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
    try:
        sock.bind((args.host, args.port))
    except PermissionError:
        sys.exit(f"Permission denied binding UDP {args.port}. Ports below 1024 need sudo, "
                 f"or redirect 514 -> 5514 with iptables and listen on 5514.")
    except OSError as e:
        sys.exit(f"Could not bind UDP {args.port}: {e}")
    sock.settimeout(1.0)

    print(f"discover.py listening on {args.host}:{args.port}/udp")
    print(f"comparing against device_map in: {args.config} "
          f"({len(existing)} entries)")
    print(f"point the customer's devices at this box on UDP {args.port}, then wait.\n")

    talkers = {}
    unparsed = 0
    started = time.time()
    stopping = {"flag": False}

    def handle_sig(*_):
        stopping["flag"] = True
    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    last_print = 0.0
    while not stopping["flag"]:
        if args.duration and (time.time() - started) >= args.duration:
            break
        try:
            data, addr = sock.recvfrom(8192)
        except socket.timeout:
            data = None
        except OSError:
            break

        if data:
            src_ip = addr[0]
            event = parse_message(data.decode("utf-8", errors="replace"), src_ip)
            if event.get("parse_error"):
                unparsed += 1
                key = (src_ip, "<UNPARSEABLE>")
                t = talkers.setdefault(key, Talker(src_ip, "<UNPARSEABLE>"))
                t.count += 1
                t.parse_errors += 1
                t.last_seen = time.time()
                if len(t.samples) < 3:
                    t.samples.append(event.get("raw", "")[:120])
            else:
                key = (src_ip, event["host"])
                talkers.setdefault(key, Talker(src_ip, event["host"])).record(event)

        now = time.time()
        if now - last_print >= args.interval:
            last_print = now
            render(talkers, existing, cfg, started, unparsed)

    render(talkers, existing, cfg, started, unparsed, final=True)
    write_skeleton(talkers, existing, args.out)
    sock.close()


def render(talkers, existing, cfg, started, unparsed, final=False):
    elapsed = int(time.time() - started)
    total = sum(t.count for t in talkers.values())
    print("=" * 100)
    print(f"{'FINAL — ' if final else ''}elapsed {elapsed}s   packets {total}   "
          f"talkers {len(talkers)}   unparseable {unparsed}")
    print("=" * 100)
    if not talkers:
        print("  nothing received yet.")
        print("  check: device syslog config, firewall/ACL, that UDP reaches this box")
        print("         (verify with:  sudo tcpdump -n -i any udp port 514 )\n")
        return

    print(f"  {'SRC IP':<16} {'HOSTNAME':<26} {'PKTS':>6} {'STATE':<9} {'TOP SEVERITIES':<28} MAPS TO")
    print("  " + "-" * 96)
    for (src_ip, host), t in sorted(talkers.items(), key=lambda kv: -kv[1].count):
        meta = agent_config.resolve_device(cfg, src_ip, host)
        state = "MAPPED" if meta else "UNMAPPED"
        maps_to = meta["device_id"] if meta else "-- dropped --"
        sev = ", ".join(f"{s}:{c}" for s, c in
                        sorted(t.severities.items(), key=lambda kv: -kv[1])[:3])
        print(f"  {src_ip:<16} {host:<26} {t.count:>6} {state:<9} {sev:<28} {maps_to}")

    unmapped = [(k, t) for k, t in talkers.items()
                if agent_config.resolve_device(cfg, k[0], k[1]) is None
                and k[1] != "<UNPARSEABLE>"]
    print()
    print(f"  MAPPED devices   : {len(talkers) - len(unmapped)}")
    print(f"  UNMAPPED devices : {len(unmapped)}  <-- their syslog is being DISCARDED")
    if unparsed:
        print(f"  UNPARSEABLE pkts : {unparsed}  <-- not RFC3164/5424; parser needs extending")
    print()

    if final and unmapped:
        print("  sample messages from unmapped devices:")
        for (src_ip, host), t in unmapped[:6]:
            print(f"    [{src_ip} / {host}]  tags={list(t.tags)[:3]}")
            for s in t.samples[:2]:
                print(f"        {s}")
        print()


def write_skeleton(talkers, existing, out_path):
    """Write a device_map skeleton for every talker not already mapped."""
    skeleton = {}
    n = 0
    for (src_ip, host), t in sorted(talkers.items(), key=lambda kv: -kv[1].count):
        if host == "<UNPARSEABLE>":
            continue
        key = f"{src_ip}|{host}"
        if key in existing or f"*|{host}" in existing:
            continue
        n += 1
        skeleton[key] = {
            "device_id": f"REPLACE-ME-{n:03d}",
            "device_name": re.sub(r"[^a-z0-9]+", "_", host.lower()).strip("_") or f"device_{n:03d}",
            "device_class": guess_class(host, list(t.tags)),
            "vendor": guess_vendor(list(t.tags), t.samples),
            "site": "REPLACE-ME-SITE",
        }
    if not skeleton:
        print(f"  nothing new to add — every talker is already in the device_map.\n")
        return
    doc = {
        "_comment": ("Generated by discover.py. Replace every REPLACE-ME value, then merge "
                     "this object into device_map in /etc/edge-agent/config.json. "
                     "device_class and vendor are guesses - verify them."),
        "device_map": skeleton,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
    print(f"  wrote device_map skeleton for {len(skeleton)} device(s) -> {out_path}")
    print(f"  edit the REPLACE-ME values, then merge it into config.json's device_map.\n")


if __name__ == "__main__":
    main()
