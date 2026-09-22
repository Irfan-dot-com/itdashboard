"""
Contract test: every message the poller emits must validate against the
BACKEND'S OWN pydantic schema, imported from ../backend in this repo.

This is the test that catches a drift between the poller and the cloud API
before it shows up as a 422 in production. If backend/ or pydantic is not
available it skips rather than failing, so it stays runnable on an edge box.

Run:  python3 -m pytest tests/test_cloud_schema.py -v
      python3 tests/test_cloud_schema.py
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
POLLER = os.path.dirname(HERE)
REPO = os.path.dirname(POLLER)
sys.path.insert(0, POLLER)

import config as poller_config   # noqa: E402
import mapper                    # noqa: E402

NOW = 1_800_000_000.0


def _load_schema():
    """Import IngestRequest from the sibling backend/ directory, if present."""
    backend = os.path.join(REPO, "backend")
    if not os.path.isdir(os.path.join(backend, "app", "schemas")):
        return None, f"backend/ not found next to poller/ (looked in {backend})"
    if backend not in sys.path:
        sys.path.insert(0, backend)
    try:
        from app.schemas.ingest import IngestRequest
        return IngestRequest, None
    except Exception as e:
        return None, f"could not import backend schema: {type(e).__name__}: {e}"


def _cfg():
    c = dict(poller_config.DEFAULT_CONFIG)
    c.update({"device_id_prefix": "t", "cloud_upload_log_path": "",
              "sdlan_raw_log_path": ""})
    return c


def _device(**over):
    d = {
        "dev_id": 11, "hw_mfg": "Corning", "endpoint_name": "MDF Core",
        "hw_ip": "10.0.0.11", "hw_model": "Corning ONE PoE-24",
        "hw_hostname": "mdf-core", "hw_sn": "SN11",
        "hw_ident": "00:11:22:33:44:55", "lost_contact": None,
        "attributes": {"Fan1": "OK", "PSU1": "OK", "Temp1": 38.0},
        "connections": {},
    }
    d.update(over)
    return d


def _envelope(cfg, messages):
    return {
        "schema_version": "1.0",
        "edge_id": cfg["edge_id"],
        "service_provider": cfg["service_provider"],
        "property_id": cfg["property_id"],
        "property_name": cfg.get("property_name"),
        "messages": messages,
    }


def test_every_message_kind_validates_against_the_backend_schema():
    IngestRequest, why = _load_schema()
    if IngestRequest is None:
        print(f"  SKIP: {why}")
        return

    cfg = _cfg()
    healthy = _device()
    broken = _device(attributes={"PSU1": "FAIL", "Temp1": 78.0},
                     connections={"3": {"port_status": "Down"},
                                  "7": {"port_status": "Down"}})
    dead = _device(dev_id=12, lost_contact=NOW - 500,
                   lost_reason="No contact within 300s")
    status_resp = {"hostname": "sdlan.example.net", "freespace": 8.0,
                   "bufferwatch": "Destination Host Unreachable",
                   "fttp_lost_contact": 2,
                   "tenant_licenses": {"valid": "TRUE", "expired": "FALSE",
                                       "not_after": NOW + 5 * 86400}}
    problems = [{"element_name": "sw-1", "message": "Power supply 1 reported FAIL"}]

    messages = [
        mapper.edge_health_message(cfg, 4, 2, 7, now=NOW),
        mapper.device_message(cfg, healthy, "Corning", "Site1", now=NOW),
        mapper.device_message(cfg, broken, "Corning", "Site1", now=NOW),
        mapper.device_message(cfg, broken, "Corning", "Site1",
                              kind="transition", now=NOW),
        mapper.device_message(cfg, dead, "Corning", "Site1", now=NOW),
        mapper.device_message(cfg, dead, "Corning", "Site1",
                              kind="transition", now=NOW),
        mapper.platform_message(cfg, status_resp, problems, now=NOW),
        mapper.platform_message(cfg, status_resp, problems,
                                kind="transition", now=NOW),
    ]
    assert all(m is not None for m in messages)

    parsed = IngestRequest.model_validate(_envelope(cfg, messages))
    kinds = [m.kind for m in parsed.messages]
    assert kinds.count("edge_health") == 1
    assert kinds.count("transition") == 3
    assert kinds.count("periodic") == 4
    print(f"  validated {len(kinds)} messages: {kinds}")


def test_the_vanished_device_message_validates():
    """The synthetic message main.py emits when a device leaves the report."""
    IngestRequest, why = _load_schema()
    if IngestRequest is None:
        print(f"  SKIP: {why}")
        return
    cfg = _cfg()
    vanished = {
        "kind": "transition", "ts": NOW, "device_id": "t-99",
        "health": {"status": "unhealthy", "score": 0,
                   "reasons": ["absent_from_platform_report_900s"]},
        "metrics": {"event_count": 1, "error_count": 1, "warn_count": 0},
        "top_events": [{"ts": NOW, "severity": "crit", "category": "availability",
                        "message": "device no longer present in the report"}],
    }
    parsed = IngestRequest.model_validate(_envelope(cfg, [vanished]))
    assert parsed.messages[0].device_id == "t-99"


def test_scores_stay_inside_the_schemas_range_for_extreme_inputs():
    IngestRequest, why = _load_schema()
    if IngestRequest is None:
        print(f"  SKIP: {why}")
        return
    cfg = _cfg()
    worst = _device(
        lost_contact=NOW - 99999,
        attributes={"PSU1": "FAIL", "PSU2": "FAIL", "Fan1": "FAIL",
                    "Fan2": "Missing", "Temp1": 120.0},
        connections={str(p): {"port_status": "Down", "sfp_type": "Optical",
                              "rx_optical_level": -40.0,
                              "last_link_change": NOW - 10}
                     for p in range(1, 49)})
    msgs = [mapper.device_message(cfg, worst, "d", "s", now=NOW),
            mapper.device_message(cfg, worst, "d", "s", kind="transition", now=NOW)]
    parsed = IngestRequest.model_validate(_envelope(cfg, msgs))
    for m in parsed.messages:
        assert 0 <= m.health.score <= 100


def test_reasons_and_messages_do_not_grow_unbounded():
    """A device with many faults must not produce a huge payload."""
    cfg = _cfg()
    worst = _device(
        attributes={f"PSU{i}": "FAIL" for i in range(1, 12)},
        connections={str(p): {"port_status": "Down"} for p in range(1, 49)})
    msg = mapper.device_message(cfg, worst, "d", "s", kind="transition", now=NOW)
    assert len(msg["health"]["reasons"]) <= 10
    assert len(msg["top_events"]) <= 5
    for ev in msg["top_events"]:
        assert len(ev["message"]) <= 200


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
            except Exception as e:
                fails += 1
                print(f"  FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{'FAILED' if fails else 'OK'} ({fails} failure(s))")
    sys.exit(1 if fails else 0)
