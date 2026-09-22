import json
import socket
import tempfile
from pathlib import Path

_DEFAULT_UPLOAD_LOG = str(Path(tempfile.gettempdir()) / "edge_cloud_upload.log")

DEFAULT_CONFIG = {
    "edge_id": socket.gethostname(),
    "service_provider": "bluip",
    "property_id": "234",
    "property_name": "sheraton",
    "cloud_endpoint": "http://35.95.218.125:4000/v1/edge/ingest",
    "summary_interval_seconds": 60,
    "window_seconds": 300,
    "stale_threshold_seconds": 180,
    "upload_batch_size": 50,
    "upload_retry_seconds": 30,
    "queue_db_path": "/var/lib/edge-agent/queue.db",
    # Plain-text log: each upload logs POST URL, headers, JSON body, HTTP status, response body.
    # Set to "" to disable. Legacy key cloud_payload_log_path is still read if this is empty.
    "cloud_upload_log_path": _DEFAULT_UPLOAD_LOG,
    "device_map": {
        "192.168.1.10|switch-floor1": {
            "device_id": "dev-001",
            "device_name": "switch_floor1",
            "device_class": "switch",
            "vendor": "cisco",
            "site": "hq",
        },
        "192.168.1.11|switch-floor2": {
            "device_id": "dev-002",
            "device_name": "switch_floor2",
            "device_class": "switch",
            "vendor": "cisco",
            "site": "hq",
        },
        "192.168.1.20|router-edge": {
            "device_id": "dev-003",
            "device_name": "router_edge",
            "device_class": "router",
            "vendor": "mikrotik",
            "site": "hq",
        },
        "*|firewall-dmz": {
            "device_id": "dev-004",
            "device_name": "firewall_dmz",
            "device_class": "firewall",
            "vendor": "fortigate",
            "site": "hq",
        },
        # Localhost / simulator: any source IP + syslog hostname (exact IP rows above still win in production)
        "*|switch-floor1": {
            "device_id": "dev-001",
            "device_name": "switch_floor1",
            "device_class": "switch",
            "vendor": "cisco",
            "site": "hq",
        },
        "*|switch-floor2": {
            "device_id": "dev-002",
            "device_name": "switch_floor2",
            "device_class": "switch",
            "vendor": "cisco",
            "site": "hq",
        },
        "*|router-edge": {
            "device_id": "dev-003",
            "device_name": "router_edge",
            "device_class": "router",
            "vendor": "mikrotik",
            "site": "hq",
        },
        "*|ap-lobby": {
            "device_id": "dev-005",
            "device_name": "ap_lobby",
            "device_class": "wifi_ap",
            "vendor": "ubiquiti",
            "site": "hq",
        },
        "*|sensor-hvac-01": {
            "device_id": "dev-006",
            "device_name": "sensor_hvac_01",
            "device_class": "sensor",
            "vendor": "generic",
            "site": "hq",
        },
    },
}


def load(path="/etc/edge-agent/config.json"):
    p = Path(path)
    if not p.exists():
        return dict(DEFAULT_CONFIG)
    with open(p) as f:
        cfg = json.load(f)
    return {**DEFAULT_CONFIG, **cfg}


def resolve_device(cfg, src_ip, hostname):
    key = f"{src_ip}|{hostname}"
    if key in cfg["device_map"]:
        return cfg["device_map"][key]
    wildcard = f"*|{hostname}"
    if wildcard in cfg["device_map"]:
        return cfg["device_map"][wildcard]
    return None
