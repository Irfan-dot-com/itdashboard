#!/usr/bin/env python3
"""
compare_paths.py - prove what happens to syslog on each delivery path, BEFORE
asking the customer to change anything.

Runs on one Linux box. No Docker, no root, no customer involvement.

Paths exercised with the SAME input messages:

  A. DIRECT     device -> our agent                     (the dual-send target)
  B. RELAYED    device -> rsyslog -> our agent           (their collector),
                tested against EVERY rsyslog forwarding template, because the
                template decides whether anything survives
  C. DUAL-SEND  device -> their collector AND our agent  (both at once)

Why this matters: rsyslog's default forwarding template rewrites the header to
an RFC 3339 timestamp with no RFC 5424 version digit. Unpatched, the agent's
parser matches neither of its regexes, every message becomes a parse_error, and
main.py discards it SILENTLY - a relay deployment that looks healthy and
collects nothing. This harness makes that visible in 30 seconds.

Usage
-----
    python3 compare_paths.py                  # everything
    python3 compare_paths.py --skip-relay     # no rsyslogd installed
    python3 compare_paths.py --keep-captures  # dump raw bytes to ./captures/
"""
import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
sys.path.insert(0, AGENT)
try:
    import config as agent_config
    from syslog_listener import parse_message
except ImportError:
    sys.exit(f"Run this from syslog/lab/ - could not import the agent from {AGENT}")

PORT_DIRECT = 5516
PORT_DUAL_THEIRS = 5517
RELAY_IN_BASE = 6700          # one port pair per template

# Templates rsyslog can forward with. The first is its modern default.
TEMPLATES = [
    ("RSYSLOG_ForwardFormat",
     "rsyslog's DEFAULT for omfwd - RFC3339 timestamp, no version digit"),
    ("RSYSLOG_TraditionalForwardFormat",
     "classic RFC 3164 header - loses the year and sub-second precision"),
    ("RSYSLOG_SyslogProtocol23Format",
     "proper RFC 5424 - keeps precision and timezone"),
]

TEST_MESSAGES = [
    ("cisco_psu",
     "<131>Sep 21 19:00:00 HTL-SW-CORE-01 %SYS-3-POWER: Power supply 1 failed"),
    ("cisco_link",
     "<131>Sep 21 19:00:01 HTL-SW-POE-F3 %LINK-3-UPDOWN: Interface "
     "GigabitEthernet1/0/14 link state changed to down"),
    ("fortigate_kv",
     "<132>Sep 21 19:00:02 HTL-FG-EDGE date=2026-09-21 logid=0100032003 "
     "type=event subtype=system level=warning msg=SSL VPN tunnel down"),
    ("asterisk_pid",
     "<130>Sep 21 19:00:03 PBX-ASTERISK-01 asterisk[912]: SIP registration "
     "failed for 1001"),
    ("rfc5424",
     "<134>1 2026-09-21T19:00:04.123Z ARISTA-SW-01 Syslog 1234 - - "
     "BGP session established with 10.0.0.1"),
    ("ups_plain",
     "<134>Sep 21 19:00:05 APC-UPS-LOBBY apcupsd: UPS on battery power"),
]

HOSTS = ["HTL-SW-CORE-01", "HTL-SW-POE-F3", "HTL-FG-EDGE",
         "PBX-ASTERISK-01", "ARISTA-SW-01", "APC-UPS-LOBBY"]

# Both key styles for the same devices, so we can see which one can match.
TEST_DEVICE_MAP = {}
for _h in HOSTS:
    TEST_DEVICE_MAP[f"10.20.30.99|{_h}"] = {"device_id": f"exact-{_h}"}
    TEST_DEVICE_MAP[f"*|{_h}"] = {"device_id": f"wildcard-{_h}"}


class Capture(threading.Thread):
    def __init__(self, port):
        super().__init__(daemon=True)
        self.port = port
        self.packets = []
        self.error = None
        self._stop = threading.Event()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.bind(("127.0.0.1", port))
        except OSError as e:
            self.error = f"cannot bind {port}: {e}"
            return
        self.sock.settimeout(0.3)

    def run(self):
        if self.error:
            return
        while not self._stop.is_set():
            try:
                data, addr = self.sock.recvfrom(16384)
            except socket.timeout:
                continue
            except OSError:
                break
            self.packets.append((addr[0], data.decode("utf-8", "replace")))

    def stop(self):
        self._stop.set()
        try:
            self.sock.close()
        except Exception:
            pass


def relay_config(workdir, template, port_in, port_out):
    spool = os.path.join(workdir, f"spool-{port_in}")
    os.makedirs(spool, exist_ok=True)
    conf = os.path.join(workdir, f"relay-{port_in}.conf")
    with open(conf, "w") as f:
        f.write(f"""module(load="imudp")
input(type="imudp" port="{port_in}")
global(workDirectory="{spool}")
$ActionQueueType Direct
$RepeatedMsgReduction off
*.* action(type="omfwd" target="127.0.0.1" port="{port_out}"
           protocol="udp" template="{template}")
""")
    return conf


def run_relay_test(workdir, template, port_in, port_out, wait):
    """Send every test message through a real rsyslogd and capture the output."""
    cap = Capture(port_out)
    if cap.error:
        return None, cap.error
    cap.start()

    conf = relay_config(workdir, template, port_in, port_out)
    check = subprocess.run(["rsyslogd", "-N1", "-f", conf],
                           capture_output=True, text=True)
    if "End of config validation run" not in (check.stdout + check.stderr):
        cap.stop()
        return None, f"config rejected: {(check.stdout + check.stderr)[:200]}"

    proc = subprocess.Popen(
        ["rsyslogd", "-n", "-f", conf,
         "-i", os.path.join(workdir, f"pid-{port_in}")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    if proc.poll() is not None:
        cap.stop()
        return None, "rsyslogd exited immediately"

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for _name, text in TEST_MESSAGES:
        s.sendto(text.encode(), ("127.0.0.1", port_in))
        time.sleep(0.05)
    s.close()
    time.sleep(wait)

    cap.stop()
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    return cap.packets, None


def analyse(packets):
    """Parse each packet; return (parsed_count, total, per-packet detail)."""
    detail = []
    for src, raw in packets:
        ev = parse_message(raw, src)
        detail.append({
            "raw": raw,
            "ok": not ev.get("parse_error"),
            "host": ev.get("host"),
            "rfc": ev.get("rfc"),
            "severity": ev.get("severity"),
            "tag": ev.get("tag"),
            "message": ev.get("message"),
        })
    return sum(1 for d in detail if d["ok"]), len(detail), detail


def hr(t=""):
    print("=" * 98)
    if t:
        print(t)
        print("=" * 98)


def main():
    ap = argparse.ArgumentParser(description="Compare syslog delivery paths")
    ap.add_argument("--skip-relay", action="store_true")
    ap.add_argument("--keep-captures", action="store_true")
    ap.add_argument("--wait", type=float, default=2.5)
    args = ap.parse_args()

    workdir = tempfile.mkdtemp(prefix="syslog-lab-")
    hr("SYSLOG DELIVERY PATH COMPARISON")
    print(f"  agent code    : {AGENT}")
    print(f"  test messages : {len(TEST_MESSAGES)} realistic vendor lines")
    has_rsyslog = bool(shutil.which("rsyslogd"))
    print(f"  rsyslogd      : {shutil.which('rsyslogd') or 'NOT FOUND'}")
    print()

    # ------------------------------------------------- A and C (no relay)
    cap_direct = Capture(PORT_DIRECT)
    cap_theirs = Capture(PORT_DUAL_THEIRS)
    for c in (cap_direct, cap_theirs):
        if c.error:
            sys.exit(f"  {c.error}\n  (ss -ulnp | grep {c.port})")
        c.start()

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for _n, text in TEST_MESSAGES:
        s.sendto(text.encode(), ("127.0.0.1", PORT_DIRECT))
        s.sendto(text.encode(), ("127.0.0.1", PORT_DUAL_THEIRS))
        time.sleep(0.05)
    s.close()
    time.sleep(1.0)
    cap_direct.stop()
    cap_theirs.stop()

    d_ok, d_total, d_detail = analyse(cap_direct.packets)
    t_ok, t_total, _ = analyse(cap_theirs.packets)

    hr("PATH A - DIRECT  (device -> our agent; this is the dual-send target)")
    print(f"  {'HOSTNAME':<18} {'RFC':<14} {'SEV':<8} {'TAG':<22} PARSED")
    print("  " + "-" * 78)
    for d in d_detail:
        print(f"  {str(d['host'] or '-')[:18]:<18} {str(d['rfc'] or '-'):<14} "
              f"{str(d['severity'] or '-'):<8} {str(d['tag'] or '-')[:22]:<22} "
              f"{'yes' if d['ok'] else 'NO'}")
    print(f"\n  parsed {d_ok}/{d_total}")
    print()

    # ----------------------------------------------------------- B: relay
    hr("PATH B - RELAYED  (device -> their rsyslog -> our agent)")
    results = {}
    if args.skip_relay or not has_rsyslog:
        print(f"  skipped ({'--skip-relay' if args.skip_relay else 'rsyslogd not installed'})")
        print("  install it to test this path:  sudo apt-get install rsyslog")
    else:
        print("  Testing every rsyslog forwarding template. The template decides")
        print("  whether the agent can parse anything at all.\n")
        for i, (tmpl, note) in enumerate(TEMPLATES):
            pin = RELAY_IN_BASE + i * 2
            pout = pin + 1
            packets, err = run_relay_test(workdir, tmpl, pin, pout, args.wait)
            if packets is None:
                print(f"  {tmpl}: could not test ({err})")
                continue
            ok, total, detail = analyse(packets)
            results[tmpl] = (ok, total, detail, note)
            verdict = ("ALL DROPPED" if ok == 0 else
                       "all parsed" if ok == total else f"{ok}/{total} parsed")
            print(f"  {tmpl:<34} {ok}/{total} parsed   {verdict}")
        print()

        hr("TEMPLATE COMPARISON - what each one puts on the wire")
        for tmpl, (ok, total, detail, note) in results.items():
            flag = "  <-- UNUSABLE" if ok == 0 else ""
            print(f"\n  {tmpl}{flag}")
            print(f"    {note}")
            print(f"    parsed {ok}/{total}")
            for d in detail[:2]:
                print(f"      wire : {d['raw'][:96]}")
                if d["ok"]:
                    print(f"      -> host={d['host']} rfc={d['rfc']} "
                          f"sev={d['severity']} tag={d['tag']!r}")
                else:
                    print(f"      -> PARSE FAILED (main.py would discard this "
                          f"silently)")
        print()

    # -------------------------------------------------------- C: dual-send
    hr("PATH C - DUAL-SEND  (one device, two destinations)")
    print(f"  our agent       received {d_total}, parsed {d_ok}")
    print(f"  their collector received {t_total}, parsed {t_ok}")
    if d_total == t_total == len(TEST_MESSAGES):
        print("  >> both destinations got the full stream, independently. The")
        print("     DEVICE fans out, so neither destination depends on the other.")
    print()

    # ---------------------------------------------------------- verdicts
    hr("VERDICTS")
    if results:
        good = [t for t, (ok, tot, _d, _n) in results.items() if ok == tot and tot]
        bad = [t for t, (ok, _tot, _d, _n) in results.items() if ok == 0]

        print("  1. THE RELAY TEMPLATE IS LOAD-BEARING")
        if bad:
            for t in bad:
                print(f"       {t} -> 0 parsed. Every message discarded,")
                print(f"       silently. This is rsyslog's DEFAULT for omfwd.")

        # A template that only parses via the non-standard relayed form is
        # working because syslog_listener.py was patched for it, not because
        # the wire format is standard. Say so, or the finding is lost.
        nonstd = [t for t, (ok, tot, d, _n) in results.items()
                  if tot and ok == tot
                  and any(x["rfc"] == "3164-rfc3339" for x in d if x["ok"])]
        standard = [t for t in good if t not in nonstd]

        if nonstd:
            for t in nonstd:
                print(f"       {t} parses ONLY because")
                print(f"       syslog_listener.py was patched to accept its")
                print(f"       non-standard header (rfc=3164-rfc3339): an RFC 3339")
                print(f"       timestamp with no RFC 5424 version digit. Any strict")
                print(f"       syslog parser - including this agent before the")
                print(f"       patch - rejects every one of these silently.")
        if standard:
            print(f"       Templates emitting STANDARD syslog: "
                  f"{', '.join(standard)}")
        if good:
            print(f"       >> tell the customer to pin "
                  f"template=\"RSYSLOG_SyslogProtocol23Format\"")
            print(f"          (proper RFC 5424, keeps timezone and sub-second")
            print(f"          precision). Never leave the template unset.")
        print()

        # hostname preservation, from whichever template parsed
        ref = next((d for _t, (ok, tot, d, _n) in results.items()
                    if ok == tot and tot), None)
        if ref:
            relayed_hosts = {d["host"] for d in ref if d["ok"]}
            direct_hosts = {d["host"] for d in d_detail if d["ok"]}
            kept = direct_hosts & relayed_hosts
            print(f"  2. HOSTNAME SURVIVES THE RELAY: "
                  f"{len(kept)}/{len(direct_hosts)}")
            lost = direct_hosts - relayed_hosts
            if lost:
                print(f"       lost: {sorted(lost)}")
                print(f"       >> wildcard \"*|hostname\" keys would NOT work.")
            else:
                print(f"       >> every hostname intact, so \"*|hostname\" "
                      f"device_map keys WILL work.")
            print()

            same = sum(1 for d in ref if d["ok"] and any(
                x["ok"] and x["host"] == d["host"] and x["message"] == d["message"]
                for x in d_detail))
            print(f"  3. MESSAGE BODY UNCHANGED: {same}/{len(kept)}")
            print()

            dl = {d["host"]: d["rfc"] for d in d_detail if d["ok"]}
            rl = {d["host"]: d["rfc"] for d in ref if d["ok"]}
            changed = [h for h in kept if dl.get(h) != rl.get(h)]
            print(f"  4. HEADER FORMAT REWRITTEN: {len(changed)}/{len(kept)}")
            for h in changed[:3]:
                print(f"       {h}: {dl[h]} -> {rl[h]}")
            if changed:
                print(f"       >> survivable, but RFC 5424 structured data and")
                print(f"          the procid are lost in the rewrite.")
            print()

    print("  5. SOURCE IP")
    print("       This lab is single-host, so every path shows 127.0.0.1 and the")
    print("       difference cannot be demonstrated here. It is not in doubt: UDP")
    print("       carries the LAST HOP, so a relayed message always arrives from")
    print("       the collector's IP, never the device's.")
    print("       >> With a relay, exact \"<ip>|<hostname>\" device_map keys all")
    print("          collapse onto one IP. Use \"*|hostname\" wildcards, and make")
    print("          sure hostnames are unique across everything behind it.")
    print("       >> To prove it with real distinct IPs you need separate hosts")
    print("          or containers - see lab/README.md.")
    print()

    hr("WHAT TO TELL THE CUSTOMER")
    print("  Dual-send : real source IPs, full fidelity, no dependency on their")
    print("              collector - but one config line on every device.")
    print("  Relay     : one change on one box - but all devices share the")
    print("              collector's IP (so wildcard keys), the forwarding")
    print("              TEMPLATE must be set correctly or nothing parses, and")
    print("              their collector becomes a single point of failure.")
    print()
    print("  If you rely on a relay, raise stale_threshold_seconds: when their")
    print("  collector dies EVERY device goes silent at once, and the agent would")
    print("  flag the whole estate unhealthy simultaneously.")
    print()

    if args.keep_captures:
        os.makedirs("captures", exist_ok=True)
        with open("captures/direct.txt", "w", encoding="utf-8") as f:
            for src, raw in cap_direct.packets:
                f.write(f"{src}\t{raw}\n")
        for tmpl, (_ok, _tot, detail, _n) in results.items():
            with open(f"captures/relayed-{tmpl}.txt", "w", encoding="utf-8") as f:
                for d in detail:
                    f.write(d["raw"] + "\n")
        print(f"  raw captures in ./captures/")
        print()

    shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
