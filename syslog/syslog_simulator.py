import socket
import time
import random
import argparse
from datetime import datetime

DEVICES = [
    {"hostname": "switch-floor1",  "tag": "ciscoios", "profile": "healthy"},
    {"hostname": "switch-floor2",  "tag": "ciscoios", "profile": "flaky"},
    {"hostname": "router-edge",    "tag": "junos",    "profile": "healthy"},
    {"hostname": "ap-lobby",       "tag": "hostapd",  "profile": "healthy"},
    {"hostname": "firewall-dmz",   "tag": "pf",       "profile": "degraded"},
    {"hostname": "sensor-hvac-01", "tag": "modbus",   "profile": "healthy"},
]

EVENT_LIBRARY = {
    "info": [
        (6, "Interface GigabitEthernet0/{p} link state changed to up"),
        (6, "User {u} logged in from 10.0.{a}.{b}"),
        (6, "DHCP lease granted to client {mac}"),
        (5, "Configuration saved by user {u}"),
    ],
    "warn": [
        (4, "CPU utilization at {pct}%"),
        (4, "Memory usage high: {pct}%"),
        (4, "Temperature sensor reading {temp}C"),
        (4, "Packet loss detected on interface eth{p}"),
    ],
    "error": [
        (3, "Interface GigabitEthernet0/{p} link state changed to down"),
        (3, "Authentication failure for user {u} from 10.0.{a}.{b}"),
        (3, "Power supply {n} fault detected"),
        (2, "BGP neighbor 10.0.{a}.{b} state changed to Idle"),
    ],
}

PROFILES = {
    "healthy":  {"info": 0.92, "warn": 0.07, "error": 0.01},
    "flaky":    {"info": 0.65, "warn": 0.25, "error": 0.10},
    "degraded": {"info": 0.40, "warn": 0.35, "error": 0.25},
}

FACILITY_LOCAL0 = 16


def render(template):
    return template.format(
        p=random.randint(0, 47),
        u=random.choice(["admin", "netops", "alice", "bob"]),
        a=random.randint(0, 255),
        b=random.randint(1, 254),
        mac=":".join(f"{random.randint(0, 255):02x}" for _ in range(6)),
        pct=random.randint(70, 99),
        temp=random.randint(45, 85),
        n=random.choice([1, 2]),
    )


def build_rfc3164(device, severity, msg):
    pri = FACILITY_LOCAL0 * 8 + severity
    now = datetime.now()
    ts = now.strftime(f"%b {now.day:2d} %H:%M:%S")  # space-pad day only, keep zero-padded time
    return f"<{pri}>{ts} {device['hostname']} {device['tag']}: {msg}"


def pick_event(profile_name):
    weights = PROFILES[profile_name]
    cls = random.choices(list(weights.keys()), weights=list(weights.values()))[0]
    sev, template = random.choice(EVENT_LIBRARY[cls])
    return sev, render(template)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5514)
    ap.add_argument("--rate", type=float, default=2.0, help="messages per second")
    ap.add_argument("--burst", action="store_true", help="simulate error bursts")
    args = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    interval = 1.0 / args.rate
    print(f"Sending to {args.host}:{args.port} at ~{args.rate} msg/s. Ctrl-C to stop.")

    burst_counter = 0
    burst_device = None
    while True:
        device = random.choice(DEVICES)

        if args.burst and burst_counter == 0 and random.random() < 0.01:
            burst_counter = random.randint(10, 25)
            burst_device = device
            print(f"--- Incident starting on {burst_device['hostname']} ---")

        if burst_counter > 0:
            device = burst_device
            sev, msg = random.choice(EVENT_LIBRARY["error"])
            msg = render(msg)
            burst_counter -= 1
        else:
            sev, msg = pick_event(device["profile"])

        packet = build_rfc3164(device, sev, msg)
        sock.sendto(packet.encode("utf-8"), (args.host, args.port))
        time.sleep(interval + random.uniform(-interval / 3, interval / 3))


if __name__ == "__main__":
    main()
