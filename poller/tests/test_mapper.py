"""
Tests for the SD-LAN -> cloud message mapping.

Deliberately assert at the MESSAGE level, not just on the health function.
The syslog agent's suite passes while device-down produces no alert, because
it only checked that the scoring function returned "unhealthy" and never that
a transition message was emitted. These tests check the messages.

Run:  python3 -m pytest tests/ -v
      python3 tests/run_tests.py      (no pytest needed)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as poller_config          # noqa: E402
import mapper                            # noqa: E402
from outbound_queue import OutboundQueue  # noqa: E402
from state_store import StateStore        # noqa: E402

NOW = 1_800_000_000.0


def cfg(**over):
    c = dict(poller_config.DEFAULT_CONFIG)
    c.update({"device_id_prefix": "t", "queue_db_path": ":memory:",
              "state_db_path": ":memory:", "cloud_upload_log_path": "",
              "sdlan_raw_log_path": ""})
    c.update(over)
    return c


def device(**over):
    d = {
        "dev_id": 11, "hw_mfg": "Corning", "endpoint_name": "MDF Core",
        "hw_ip": "10.0.0.11", "hw_model": "Corning ONE PoE-24",
        "hw_hostname": "mdf-core", "hw_sn": "SN11", "hw_ident": "00:11:22:33:44:55",
        "lost_contact": None, "is_tor": False, "topology_depth": 2,
        "attributes": {"Fan1": "OK", "PSU1": "OK", "Temp1": 38.0},
        "connections": {},
    }
    d.update(over)
    return d


# ------------------------------------------------------------------ identity

def test_device_id_uses_prefix_and_source():
    assert mapper.device_id_for(cfg(), device()) == "t-11"


def test_device_id_can_use_serial_instead():
    c = cfg(device_id_source="hw_sn")
    assert mapper.device_id_for(c, device()) == "t-SN11"


def test_device_id_falls_back_when_source_field_absent():
    c = cfg(device_id_source="hw_sn")
    assert mapper.device_id_for(c, device(hw_sn=None)) == "t-11"


def test_device_id_none_when_nothing_identifies_the_device():
    assert mapper.device_id_for(cfg(), {"foo": "bar"}) is None


# -------------------------------------------------------------------- health

def test_healthy_device_scores_100():
    status, score, reasons, _m = mapper.assess_device(cfg(), device(), NOW)
    assert status == "healthy"
    assert score == 100
    assert reasons == []


def test_lost_contact_is_unhealthy_with_reason():
    status, score, reasons, _m = mapper.assess_device(
        cfg(), device(lost_contact=NOW - 400, lost_reason="No contact within 300s"), NOW)
    assert status == "unhealthy"
    assert score == 0
    assert any(r.startswith("lost_contact") for r in reasons)


def test_state_false_also_means_lost_contact():
    d = device()
    d[".state"] = "False"
    status, _s, reasons, _m = mapper.assess_device(cfg(), d, NOW)
    assert status == "unhealthy"
    assert any("lost_contact" in r for r in reasons)


def test_failed_psu_is_unhealthy():
    d = device(attributes={"Fan1": "OK", "PSU1": "FAIL", "Temp1": 38.0})
    status, score, reasons, metrics = mapper.assess_device(cfg(), d, NOW)
    assert status == "unhealthy"
    assert score < 85
    assert any(r.startswith("hardware_fault") for r in reasons)
    assert metrics["error_count"] >= 1


def test_missing_fan_is_flagged():
    d = device(attributes={"Fan1": "Missing", "PSU1": "OK"})
    status, _s, reasons, _m = mapper.assess_device(cfg(), d, NOW)
    assert status == "unhealthy"
    assert any("Fan1" in r for r in reasons)


def test_temperature_thresholds():
    warm = device(attributes={"Temp1": 60.0})
    status, _s, reasons, _m = mapper.assess_device(cfg(), warm, NOW)
    assert status == "degraded"
    assert any(r.startswith("thermal_warning") for r in reasons)

    hot = device(attributes={"Temp1": 75.0})
    status, _s, reasons, _m = mapper.assess_device(cfg(), hot, NOW)
    assert status == "unhealthy"
    assert any(r.startswith("thermal_critical") for r in reasons)


def test_temperature_parsed_from_string_with_unit():
    d = device(attributes={"Temp1": "75 C"})
    status, _s, _r, _m = mapper.assess_device(cfg(), d, NOW)
    assert status == "unhealthy"


def test_distinct_down_ports_each_count():
    """Contrast with the syslog agent, where 4 dead ports dedup to 1 event."""
    ports = {str(p): {"port_status": "Down", "local_port_name": f"Gi1/0/{p}"}
             for p in (3, 7, 24, 48)}
    status, score, reasons, _m = mapper.assess_device(cfg(), device(connections=ports), NOW)
    assert status == "degraded"
    assert score < 100
    assert any(r == "ports_down:4" for r in reasons)


def test_link_flap_detected_from_last_link_change():
    ports = {str(p): {"port_status": "Up", "last_link_change": NOW - 60}
             for p in (1, 2, 3, 4)}
    _s, _sc, reasons, _m = mapper.assess_device(cfg(), device(connections=ports), NOW)
    assert any(r.startswith("link_flap") for r in reasons)


def test_low_optical_receive_level_flagged():
    ports = {"1": {"port_status": "Up", "sfp_type": "Optical",
                   "rx_optical_level": -27.5}}
    status, _s, reasons, _m = mapper.assess_device(cfg(), device(connections=ports), NOW)
    assert status == "degraded"
    assert any(r.startswith("optical_low") for r in reasons)


def test_copper_port_not_checked_for_optical_level():
    ports = {"1": {"port_status": "Up", "sfp_type": "Copper",
                   "rx_optical_level": -99.0}}
    _s, _sc, reasons, _m = mapper.assess_device(cfg(), device(connections=ports), NOW)
    assert not any(r.startswith("optical_low") for r in reasons)


def test_connections_as_a_list_also_works():
    ports = [{"Port Number": 3, "port_status": "Down"},
             {"Port Number": 7, "port_status": "Down"}]
    _s, _sc, reasons, _m = mapper.assess_device(cfg(), device(connections=ports), NOW)
    assert any(r == "ports_down:2" for r in reasons)


def test_score_never_leaves_the_schema_range():
    """The cloud schema requires 0 <= score <= 100."""
    d = device(lost_contact=NOW - 9999,
               attributes={"PSU1": "FAIL", "Fan1": "FAIL", "Temp1": 99.0})
    _s, score, _r, _m = mapper.assess_device(cfg(), d, NOW)
    assert 0 <= score <= 100


# ------------------------------------------------------------------ messages

def test_periodic_message_has_the_fields_the_cloud_needs():
    msg = mapper.device_message(cfg(), device(), "Corning", "Site1", now=NOW)
    for key in ("kind", "ts", "device_id", "device_name", "device_class",
                "vendor", "site", "health", "metrics"):
        assert key in msg, key
    assert msg["kind"] == "periodic"
    assert msg["health"]["status"] in ("healthy", "degraded", "unhealthy", "unknown")
    assert "top_events" not in msg


def test_transition_message_carries_top_events():
    d = device(attributes={"PSU1": "FAIL"})
    msg = mapper.device_message(cfg(), d, "Corning", "Site1",
                                kind="transition", now=NOW)
    assert msg["kind"] == "transition"
    assert msg["top_events"]
    ev = msg["top_events"][0]
    assert set(ev) == {"ts", "severity", "category", "message"}
    assert ev["severity"] in ("emerg", "alert", "crit", "err", "warning",
                              "notice", "info", "debug")


def test_device_overrides_win():
    c = cfg(device_overrides={"t-11": {"device_class": "poe_switch",
                                       "site": "floor3",
                                       "device_name": "Renamed"}})
    msg = mapper.device_message(c, device(), "Corning", "Site1", now=NOW)
    assert msg["device_class"] == "poe_switch"
    assert msg["site"] == "floor3"
    assert msg["device_name"] == "Renamed"


def test_tor_switch_classified():
    msg = mapper.device_message(cfg(), device(is_tor=True), "d", "s", now=NOW)
    assert msg["device_class"] == "tor_switch"


def test_edge_health_message_shape():
    msg = mapper.edge_health_message(cfg(), 12, 3, 44, now=NOW)
    assert msg["kind"] == "edge_health"
    assert msg["metrics"]["tracked_devices"] == 12
    assert msg["metrics"]["unhealthy_devices"] == 3
    assert msg["metrics"]["queue_depth"] == 44


# ------------------------------------------------------------------ platform

def test_expired_license_is_unhealthy():
    status, _s, reasons, _m = mapper.assess_platform(
        cfg(), {"tenant_licenses": {"expired": "TRUE"}}, [], NOW)
    assert status == "unhealthy"
    assert "license_expired" in reasons


def test_license_expiring_soon_warns():
    resp = {"tenant_licenses": {"expired": "FALSE", "valid": "TRUE",
                                "not_after": NOW + 10 * 86400}}
    status, _s, reasons, _m = mapper.assess_platform(cfg(), resp, [], NOW)
    assert status == "degraded"
    assert any("license_expires_in" in r for r in reasons)


def test_low_platform_disk_warns():
    status, _s, reasons, _m = mapper.assess_platform(cfg(), {"freespace": 5.0}, [], NOW)
    assert status == "degraded"
    assert any(r.startswith("platform_disk_low") for r in reasons)


def test_bufferwatch_abnormal_state_warns():
    status, _s, reasons, _m = mapper.assess_platform(
        cfg(), {"bufferwatch": "Destination Host Unreachable"}, [], NOW)
    assert status == "degraded"
    assert any(r.startswith("bufferwatch") for r in reasons)


def test_bufferwatch_normal_is_fine():
    status, _s, reasons, _m = mapper.assess_platform(
        cfg(), {"bufferwatch": "Normal"}, [], NOW)
    assert status == "healthy"
    assert reasons == []


def test_active_problems_surface_in_platform_transition():
    problems = [{"element_name": "sw-1", "message": "Power supply 1 reported FAIL"}]
    msg = mapper.platform_message(cfg(), {"hostname": "sdlan.example.net"},
                                  problems, kind="transition", now=NOW)
    assert msg["health"]["status"] != "healthy"
    assert any("Power supply" in e["message"] for e in msg["top_events"])


# ----------------------------------------------------------------- state

def test_first_sighting_returns_no_previous_status():
    s = StateStore(":memory:")
    assert s.record("t-11", "healthy", 100) is None


def test_second_sighting_returns_previous_status():
    s = StateStore(":memory:")
    s.record("t-11", "healthy", 100)
    assert s.record("t-11", "unhealthy", 0) == "healthy"


def test_counts_track_unhealthy_devices():
    s = StateStore(":memory:")
    s.record("a", "healthy", 100)
    s.record("b", "unhealthy", 0)
    s.record("c", "degraded", 70)
    assert s.counts() == (3, 1)


def test_devices_not_seen_since_finds_stale_entries():
    ticks = {"t": 1000.0}
    s = StateStore(":memory:", clock=lambda: ticks["t"])
    s.record("old", "healthy", 100)
    ticks["t"] = 5000.0
    s.record("new", "healthy", 100)
    stale = [d["device_id"] for d in s.devices_not_seen_since(4000.0)]
    assert stale == ["old"]


# ----------------------------------------------------------------- queue

def test_quarantine_lets_the_queue_keep_draining():
    q = OutboundQueue(":memory:")
    for i in range(4):
        q.enqueue({"kind": "periodic", "n": i})
    first = [rid for rid, _ in q.take_batch(2)]
    q.quarantine(first, "HTTP 422")
    assert q.depth() == 2
    remaining = [p["n"] for _rid, p in q.take_batch(10)]
    assert remaining == [2, 3]


def test_enqueue_many_records_all_kinds():
    q = OutboundQueue(":memory:")
    q.enqueue_many([{"kind": "periodic"}, {"kind": "transition"},
                    {"kind": "edge_health"}])
    assert q.depth() == 3
    kinds = {s["kind"] for s in q.stats()}
    assert kinds == {"periodic", "transition", "edge_health"}


# ------------------------------------------------------------- redaction

def test_redact_masks_passwords_at_any_depth():
    out = poller_config.redact(
        {"username": "u", "password": "p",
         "nested": {"sdlan_password": "x", "Token": "y", "keep": 1},
         "list": [{"passwd": "z"}]})
    assert out["password"] == "***"
    assert out["nested"]["sdlan_password"] == "***"
    assert out["nested"]["Token"] == "***"
    assert out["list"][0]["passwd"] == "***"
    assert out["nested"]["keep"] == 1
    assert out["username"] == "u"


def test_safe_url_has_no_credentials():
    url = poller_config.safe_url({"sdlan_base_url": "https://sdlan.example.com/"})
    assert url == "https://sdlan.example.com/api/request"
    assert "password" not in url
