#!/usr/bin/env python3
"""
Mock Corning SD-LAN platform, for testing the poller without real hardware.

Serves /api/request with doc-shaped JSON for all four queries, and deliberately
includes an unhealthy mix: a good switch, one with a failed PSU, one out of
contact, and one with ports down plus weak optics. Enough to see periodic
messages, transitions and alerts flow end to end.

    python3 mock_sdlan.py --port 8443
    python3 main.py --config test-config.json --once

Scenarios (change what the mock reports, to exercise transitions):
    curl -X POST localhost:8443/_scenario -d degrade   # PSU on sw-core-01 fails
    curl -X POST localhost:8443/_scenario -d recover   # everything healthy
    curl -X POST localhost:8443/_scenario -d outage    # sw-poe-f3 loses contact
    curl -X POST localhost:8443/_scenario -d default

NOT part of the deployed application - a test fixture only. install.sh does
not copy it to an edge box.
"""
import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

USERNAME = "apiuser"
PASSWORD = "apipass"

STATE = {"scenario": "default"}


def _device(dev_id, name, ip, model, *, psu="OK", fan="OK", temp=38.0,
            lost=None, ports=None, is_tor=False, sn=None):
    return {
        "dev_id": dev_id,
        "hw_mfg": "Corning",
        "endpoint_id": 1000 + dev_id,
        "endpoint_name": name,
        "hw_ip": ip,
        "topology_depth": 1 if is_tor else 2,
        "is_tor": is_tor,
        "hw_ident": f"00:1b:44:11:3a:{dev_id:02x}",
        "lost_contact": lost,
        "lost_reason": "No contact within 300s" if lost else None,
        "hw_model": model,
        "hw_hostname": name.lower().replace(" ", "-"),
        "hw_sn": sn or f"SN{dev_id:06d}",
        "management_ip": ip,
        "attributes": {
            "Fan1": fan,
            "PSU1": psu,
            "Temp1": temp,
            "mgmt_vlan": "100",
            "ActiveImage": "5.4.8.157",
        },
        "connections": ports or {
            "1": {"remote_port": 1, "remote_dev_id": 99, "mode": "up",
                  "local_port_name": "Gi1/0/1", "remote_name": "wan-edge",
                  "remote_port_name": "Gi0/1", "port_status": "Up",
                  "last_link_change": time.time() - 86400,
                  "poe_status": "not provisioned", "sfp_type": "Optical",
                  "rx_optical_level": -6.2, "tx_optical_level": -5.1},
            "2": {"remote_port": 2, "remote_dev_id": 0, "mode": "down",
                  "local_port_name": "Gi1/0/2", "remote_name": "ap-lobby",
                  "remote_port_name": "eth0", "port_status": "Up",
                  "last_link_change": time.time() - 90000,
                  "poe_status": "Powered", "sfp_type": "Copper"},
        },
    }


def _down_port(name, last_change_ago, rx=None):
    return {
        "remote_port": 0, "remote_dev_id": 0, "mode": "down",
        "local_port_name": name, "remote_name": "", "remote_port_name": "",
        "port_status": "Down", "last_link_change": time.time() - last_change_ago,
        "poe_status": "unpowered", "sfp_type": "Optical" if rx is not None else "Copper",
        **({"rx_optical_level": rx, "tx_optical_level": -5.0} if rx is not None else {}),
    }


def networks_payload():
    sc = STATE["scenario"]

    core = _device(11, "MDF Core Switch", "10.20.30.11", "Corning ONE TOR-48",
                   is_tor=True, temp=41.0,
                   psu="FAIL" if sc in ("degrade",) else "OK")

    poe3 = _device(12, "Floor 3 PoE Switch", "10.20.30.12", "Corning ONE PoE-24",
                   temp=52.0,
                   lost=int(time.time() - 420) if sc == "outage" else None)

    poe4 = _device(13, "Floor 4 PoE Switch", "10.20.30.13", "Corning ONE PoE-24",
                   temp=72.5 if sc == "degrade" else 44.0,
                   ports={
                       "1": {"port_status": "Up", "local_port_name": "Gi1/0/1",
                             "sfp_type": "Optical", "rx_optical_level": -7.0,
                             "tx_optical_level": -5.0, "mode": "up",
                             "last_link_change": time.time() - 86400},
                       "14": _down_port("Gi1/0/14", 120),
                       "15": _down_port("Gi1/0/15", 200),
                       "16": _down_port("Gi1/0/16", 300, rx=-27.4),
                   })

    lobby = _device(14, "Lobby Aggregation", "10.20.30.14",
                    "Corning ONE Agg-12", temp=36.0)

    if sc == "recover":
        core = _device(11, "MDF Core Switch", "10.20.30.11",
                       "Corning ONE TOR-48", is_tor=True, temp=40.0)
        poe4 = _device(13, "Floor 4 PoE Switch", "10.20.30.13",
                       "Corning ONE PoE-24", temp=42.0)

    return {
        "Corning": {
            "SheratonDowntown": {
                core["endpoint_name"]: core,
                poe3["endpoint_name"]: poe3,
                poe4["endpoint_name"]: poe4,
                lobby["endpoint_name"]: lobby,
            }
        }
    }


def status_payload():
    sc = STATE["scenario"]
    problems = []
    if sc == "degrade":
        problems = [{
            "installation_name": "SheratonDowntown", "tenant_id": 1,
            "element": "Corning.SheratonDowntown.MDF-Core-Switch",
            "tenant_name": "BluIP", "message": "Power supply 1 reported FAIL",
            "element_id": 11, "element_name": "mdf-core-switch",
            "Installation_id": 1,
        }]
    elif sc == "outage":
        problems = [{
            "installation_name": "SheratonDowntown", "tenant_id": 1,
            "element": "Corning.SheratonDowntown.Floor-3-PoE-Switch",
            "tenant_name": "BluIP", "message": "Management connection lost",
            "element_id": 12, "element_name": "floor-3-poe-switch",
            "Installation_id": 1,
        }]

    return {
        "fttp_active": 128,
        "switches": 4,
        "vnetc_ifaces": [{"eth0": "00:50:56:aa:bb:cc"}],
        "fttp_lost_contact": 2 if sc == "outage" else 0,
        "fttp_rebooted": 1 if sc == "degrade" else 0,
        "uptime": 1842391.5,
        "tenant_licenses": {
            "Tenant count": 1,
            "annotations": {"support": "support@corning.com",
                            "licensing": "sales@corning.com"},
            "valid": "TRUE", "licensed_mac": "00:50:56:aa:bb:cc",
            "endpoint_use": 128, "not_after": int(time.time() + 180 * 86400),
            "missing": "FALSE", "fqdn": "sdlan.sheraton.example.net",
            "valid_hardware": "TRUE", "not_before": int(time.time() - 365 * 86400),
            "voip_limit": 200, "version": 2, "voip_use": 143,
            "sd_wan_sites": 1, "ont_add_on": "TRUE", "sha256": "ab12cd34",
            "expired": "FALSE", "endpoint_limit": 256, "ports_use": 96,
        },
        "last_pg_archive": int(time.time() - 7200),
        "hostname": "sdlan.sheraton.example.net",
        "sites": 1,
        "site_vfs_status": {},
        "site_freespace": 42,
        "bufferwatch": "Destination Host Unreachable" if sc == "outage" else "Normal",
        "installations": 1,
        "timestamp": int(time.time()),
        "problems": problems,
        "date": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "freespace": 9.0 if sc == "degrade" else 61.0,
        "switch_status": {
            "Network": {
                "endpoint_name": "Corning.SheratonDowntown.MDF-Core-Switch",
                ".state": "True", "Temp": [41.0, 39.5],
                "PSU": "BAD" if sc == "degrade" else "OK",
            }
        },
        "package": "5.4.8.157",
        "site_wan_status": None,
        "loadavg": 0.42,
        "tenants": 1,
        "user_email": USERNAME,
    }


def device_details_payload(dev_id):
    now = int(time.time())
    return {
        "dev_id": int(dev_id or 11),
        "endpoint_name": "MDF Core Switch",
        "hw_ident": "00:1b:44:11:3a:0b",
        "hw_mfg": "Corning", "hw_model": "Corning ONE TOR-48",
        "hw_sn": "SN000011", "lost_contact": None,
        "lost_reason": None, "management_ip": "10.20.30.11",
        "statistics": {
            "step": 300, "start": now - 3600, "stop": now,
            "device": {"cpu.load": [0.4, 0.5, 0.4], "temp.sensor1": [41.0, 41.5, 41.0]},
            "ports": {"Gi1/0/1": {"rx.bytes": [1e9, 1.1e9], "tx.bytes": [8e8, 9e8]}},
        },
        "ports": {
            "Gi1/0/1": {
                "port_status": "Up", "last_link_change": now - 86400,
                "poe_status": "not provisioned", "sfp_type": "Optical",
                "rx_optical_level": -6.2, "tx_optical_level": -5.1,
                "sfp_vendor_name": "Corning", "sfp_vendor_part_number": "SFP-1G-LX",
                "sfp_vendor_serial_number": "SFP00123",
            }
        },
        "mac_addresses": {
            "Gi1/0/1": [{"mac": "00:11:22:33:44:55", "service": "guest-wifi",
                         "vlan_id": 200, "down": True, "fabric": False,
                         "org": "Cisco Systems"}]
        },
    }


def slice_payload(endpoint):
    return {
        "domain": "Corning", "site": "SheratonDowntown",
        "endpoints": [
            {"dev_id": 13, "endpoint_name": endpoint or "Floor 4 PoE Switch",
             "topology_depth": 2},
            {"dev_id": 11, "endpoint_name": "MDF Core Switch", "topology_depth": 1},
        ],
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _params(self):
        parsed = urlparse(self.path)
        params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        n = int(self.headers.get("Content-Length", 0) or 0)
        if n:
            raw = self.rfile.read(n).decode("utf-8", "replace")
            ctype = (self.headers.get("Content-Type") or "").lower()
            if "json" in ctype:
                try:
                    params.update(json.loads(raw) or {})
                except ValueError:
                    pass
            else:
                params.update({k: v[0] for k, v in parse_qs(raw).items()})
        return parsed.path, params

    def do_GET(self):
        self._handle()

    def do_POST(self):
        path, params = self._params()
        if path == "/_scenario":
            want = (params.get("scenario")
                    or next(iter(params), "default") if params else "default")
            # also accept a bare body like: curl -d degrade
            STATE["scenario"] = want if want in (
                "default", "degrade", "recover", "outage") else "default"
            return self._send(200, {"scenario": STATE["scenario"]})
        self._handle(path, params)

    def _handle(self, path=None, params=None):
        if path is None:
            path, params = self._params()

        if path in ("/livez", "/health"):
            return self._send(200, {"status": "ok", "scenario": STATE["scenario"]})
        if path != "/api/request":
            return self._send(404, {"error": f"no such path {path}"})

        if params.get("username") != USERNAME or params.get("password") != PASSWORD:
            return self._send(401, {"error": "bad credentials"})

        q = params.get("query")
        if q == "status":
            return self._send(200, status_payload())
        if q == "networks":
            return self._send(200, networks_payload())
        if q == "device_details":
            return self._send(200, device_details_payload(params.get("dev_id")))
        if q == "slice":
            return self._send(200, slice_payload(params.get("endpoint")))
        return self._send(400, {"error": f"unknown query {q!r}"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8443)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--scenario", default="default",
                    choices=["default", "degrade", "recover", "outage"])
    args = ap.parse_args()
    STATE["scenario"] = args.scenario
    print(f"mock SD-LAN on http://{args.host}:{args.port}/api/request "
          f"(user={USERNAME} pass={PASSWORD}) scenario={STATE['scenario']}",
          flush=True)
    HTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
