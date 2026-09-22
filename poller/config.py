"""
Configuration for the Corning ONE SD-LAN poller.

Loads /etc/sdlan-poller/config.json over DEFAULT_CONFIG, the same pattern the
syslog agent uses, so the code is identical on every edge box.

Credentials live in this file. It must be chmod 640 root:sdlan-poller.
"""
import json
import socket
from pathlib import Path

DEFAULT_CONFIG = {
    # --- identity reported to the cloud dashboard -------------------------
    "edge_id": f"sdlan-{socket.gethostname()}",
    "service_provider": "bluip",
    "property_id": "234",
    "property_name": "sheraton",
    "cloud_endpoint": "http://127.0.0.1:4000/v1/edge/ingest",

    # --- the Corning SD-LAN platform -------------------------------------
    # Base URL of the orchestration platform. "/api/request" is appended.
    "sdlan_base_url": "https://sdlan.example.com",
    "sdlan_username": "",
    "sdlan_password": "",
    # POST keeps credentials out of the URL/query string. The tech pub
    # recommends it explicitly. Only switch to "GET" for debugging.
    "sdlan_http_method": "POST",
    # How POST parameters are encoded. The tech pub documents them as a query
    # string, so a CGI-style endpoint most likely wants "form". If the platform
    # rejects that, try "json", then "query" (params in the URL, empty body).
    # probe.py --try-formats tests all three and tells you which works.
    "sdlan_post_format": "form",
    "sdlan_verify_tls": True,
    # Path to a CA bundle if the platform uses a private/self-signed CA.
    "sdlan_ca_bundle": "",
    "sdlan_timeout_seconds": 30,

    # --- polling ----------------------------------------------------------
    # The tech pub expects polling "at least once every ten minutes" (600s).
    # Lower it only after confirming the load is acceptable with Corning.
    "poll_interval_seconds": 300,
    # Narrow the networks query to one endpoint set / site. "" = whole system.
    "sdlan_setname": "",
    "sdlan_site": "",

    # --- device identity mapping ------------------------------------------
    # Which API field becomes the cloud device_id. dev_id is the platform's
    # internal key (stable, but only unique WITHIN one platform), hw_sn and
    # hw_ident are globally unique but change if hardware is swapped.
    "device_id_source": "dev_id",          # dev_id | hw_sn | hw_ident
    # Prefixed so device_ids from two platforms can never collide in the
    # cloud devices table. Set this per property.
    "device_id_prefix": "sdlan-234",
    # Fallback device_class when it cannot be derived from hw_model/is_tor.
    "default_device_class": "switch",
    # Per-device overrides, keyed by the FINAL device_id:
    #   "sdlan-234-17": {"device_class": "poe_switch", "site": "floor3"}
    "device_overrides": {},
    # Also report the orchestration platform itself as a device, so its
    # problems list, uptime and disk space surface on the dashboard.
    "report_platform_as_device": True,
    "platform_device_class": "orchestrator",

    # --- health thresholds ------------------------------------------------
    # Temperature (Celsius) at which a device is degraded / unhealthy.
    "temp_warn_celsius": 55.0,
    "temp_crit_celsius": 70.0,
    # Optical receive level (dBm) below which a port is flagged.
    "optical_rx_warn_dbm": -20.0,
    # Ports whose link changed within this window count as flapping.
    "link_flap_window_seconds": 900,
    "link_flap_min_changes": 3,
    # Platform disk free percentage below which the platform is degraded.
    "platform_freespace_warn_percent": 15.0,

    # --- local state ------------------------------------------------------
    "queue_db_path": "/var/lib/sdlan-poller/queue.db",
    "state_db_path": "/var/lib/sdlan-poller/state.db",
    "upload_batch_size": 50,
    "upload_retry_seconds": 30,
    # Plain-text log of every cloud upload (request + response).
    # SD-LAN credentials are ALWAYS redacted before anything is written here.
    "cloud_upload_log_path": "/var/log/sdlan-poller/cloud_upload.log",
    # Raw SD-LAN API responses, for correcting the field mapping against a
    # real platform. Grows fast - "" disables it. Credentials redacted.
    "sdlan_raw_log_path": "",
}

REQUIRED_KEYS = [
    "edge_id", "service_provider", "property_id", "cloud_endpoint",
    "sdlan_base_url", "sdlan_username", "sdlan_password",
    "poll_interval_seconds", "queue_db_path", "state_db_path",
    "device_id_prefix",
]

SECRET_KEYS = ("sdlan_password", "password", "passwd", "secret", "token")


def load(path="/etc/sdlan-poller/config.json"):
    p = Path(path)
    if not p.exists():
        return dict(DEFAULT_CONFIG)
    with open(p, encoding="utf-8") as f:
        cfg = json.load(f)
    merged = {**DEFAULT_CONFIG, **{k: v for k, v in cfg.items() if not k.startswith("_")}}
    return merged


def missing_keys(cfg):
    """Required keys that are absent or still empty."""
    return [k for k in REQUIRED_KEYS if cfg.get(k) in (None, "")]


def redact(obj):
    """
    Deep-copy a dict/list, replacing any secret-looking value with '***'.

    Every log path in this application runs its payload through this first.
    A plaintext SD-LAN admin password in a log file on an edge box on a
    customer network is not an acceptable failure mode.
    """
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and any(s in k.lower() for s in SECRET_KEYS):
                out[k] = "***"
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [redact(v) for v in obj]
    return obj


def safe_url(cfg):
    """The API URL with no credentials in it, for logging and error messages."""
    return cfg["sdlan_base_url"].rstrip("/") + "/api/request"
