"""Integration tests — Ingestor against real PostgreSQL."""
from datetime import datetime, timezone

import pytest

from app.lib.ingestor import Ingestor
from app.repositories.alerts import AlertsRepository
from app.repositories.devices import DevicesRepository
from app.repositories.properties import PropertiesRepository
from app.schemas.ingest import (
    DeviceHealth,
    DeviceMetrics,
    EdgeHealthMessage,
    EdgeHealthMetrics,
    PeriodicMessage,
    TopEvent,
    TransitionMessage,
)

PROVIDER = "bluip"
PROP_ID = "prop_cottons"
EDGE_ID = "edge-7"


def _edge_health_msg(ts=1_746_720_000.0, tracked=3, unhealthy=0, queue=0):
    return EdgeHealthMessage(
        kind="edge_health",
        ts=ts,
        metrics=EdgeHealthMetrics(
            tracked_devices=tracked,
            unhealthy_devices=unhealthy,
            queue_depth=queue,
            summary_interval_seconds=60,
        ),
    )


def _periodic_msg(device_id="dev-001", status="healthy", score=90, device_class="poe_switch"):
    return PeriodicMessage(
        kind="periodic",
        ts=1_746_720_001.0,
        device_id=device_id,
        device_class=device_class,
        health=DeviceHealth(status=status, score=score),
    )


def _transition_msg(device_id="dev-001", status="unhealthy", score=20, device_class="poe_switch"):
    return TransitionMessage(
        kind="transition",
        ts=1_746_720_002.0,
        device_id=device_id,
        device_class=device_class,
        health=DeviceHealth(status=status, score=score, reasons=["link_down"]),
        top_events=[
            TopEvent(
                ts=1_746_720_000.0,
                severity="error",
                category="link",
                message="Port Gi0/1 down",
            )
        ],
    )


async def _run(conn, messages):
    ingestor = Ingestor(conn)
    return await ingestor.handle_batch(
        edge_id=EDGE_ID,
        service_provider=PROVIDER,
        property_id=PROP_ID,
        property_name="Cottons Hotel",
        messages=messages,
    )


# ── edge_health ────────────────────────────────────────────────────────────────

async def test_edge_health_upserts_edge_box(conn):
    result = await _run(conn, [_edge_health_msg(tracked=5, unhealthy=1, queue=2)])
    assert result["accepted"] == 1
    assert result["rejected"] == []

    box = await PropertiesRepository(conn).get_edge_box_for_property(PROVIDER, PROP_ID)
    assert box is not None
    assert box["edge_id"] == EDGE_ID
    assert box["tracked_devices"] == 5
    assert box["unhealthy_devices"] == 1
    assert box["queue_depth"] == 2


async def test_edge_health_enqueues_heartbeat_event(conn):
    await _run(conn, [_edge_health_msg()])
    row = await conn.fetchrow(
        "SELECT event_kind FROM event_outbox WHERE property_id = $1 ORDER BY enqueued_at LIMIT 1",
        PROP_ID,
    )
    assert row["event_kind"] == "edge.heartbeat"


# ── periodic ───────────────────────────────────────────────────────────────────

async def test_periodic_upserts_device(conn):
    result = await _run(conn, [_periodic_msg(device_class="dect_base")])
    assert result["accepted"] == 1

    dev = await DevicesRepository(conn).get("dev-001")
    assert dev is not None
    assert dev["device_class"] == "dect_base"
    assert dev["health_status"] == "healthy"
    assert dev["health_score"] == 90


async def test_periodic_health_change_enqueues_event(conn):
    # First periodic: unknown → healthy (status changes)
    await _run(conn, [_periodic_msg(status="healthy")])
    count_before = await conn.fetchval(
        "SELECT COUNT(*) FROM event_outbox WHERE event_kind = 'device.health_changed'"
    )
    # Second periodic: healthy → degraded (status changes)
    await _run(conn, [_periodic_msg(status="degraded")])
    count_after = await conn.fetchval(
        "SELECT COUNT(*) FROM event_outbox WHERE event_kind = 'device.health_changed'"
    )
    assert count_after > count_before


async def test_periodic_no_event_when_status_unchanged(conn):
    # First call: unknown → healthy
    await _run(conn, [_periodic_msg(status="healthy", score=90)])
    # Second call: healthy → healthy (same status, only score changed)
    await _run(conn, [_periodic_msg(status="healthy", score=85)])
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM event_outbox WHERE event_kind = 'device.health_changed'"
    )
    # Only the first status change (unknown→healthy) should produce one event
    assert count == 1


# ── transition ─────────────────────────────────────────────────────────────────

async def test_transition_unhealthy_opens_alert(conn):
    result = await _run(conn, [_transition_msg(status="unhealthy", score=20)])
    assert result["accepted"] == 1

    alerts_repo = AlertsRepository(conn)
    counts = await alerts_repo.count_by_severity(PROVIDER, PROP_ID)
    assert counts["p1"] == 1   # unhealthy → p1


async def test_transition_alert_has_correct_detail(conn):
    await _run(conn, [_transition_msg(status="unhealthy", score=20)])
    alerts_repo = AlertsRepository(conn)
    page = await alerts_repo.list(PROVIDER, states=["opened"])
    assert len(page["items"]) == 1
    item = page["items"][0]
    assert item["severity"] == "p1"
    assert item["state"] == "opened"
    # causal_chain should have 4 tiers (element, signal, kpi, consequence)
    assert len(item["detail_json"]["causal_chain"]) >= 2
    # severity normalized: "error" → "err"
    series = item["detail_json"]["signal"]["series"]
    assert all(e["severity"] == "err" for e in series)


async def test_transition_duplicate_does_not_open_second_alert(conn):
    await _run(conn, [_transition_msg(status="unhealthy")])
    await _run(conn, [_transition_msg(status="unhealthy")])

    alerts_repo = AlertsRepository(conn)
    counts = await alerts_repo.count_by_severity(PROVIDER, PROP_ID)
    assert counts["p1"] == 1   # still only one open alert


async def test_transition_healthy_resolves_open_alert(conn):
    # Open an alert
    await _run(conn, [_transition_msg(status="unhealthy")])
    # Recover
    await _run(conn, [_transition_msg(status="healthy", score=95)])

    alerts_repo = AlertsRepository(conn)
    counts = await alerts_repo.count_by_severity(PROVIDER, PROP_ID)
    assert counts["p1"] == 0   # resolved, not counted as open
    # alert.state_changed event should be in outbox
    row = await conn.fetchrow(
        "SELECT event_kind FROM event_outbox WHERE event_kind = 'alert.state_changed' LIMIT 1"
    )
    assert row is not None


async def test_transition_degraded_opens_p2_alert(conn):
    result = await _run(conn, [_transition_msg(status="degraded", score=60)])
    assert result["accepted"] == 1

    alerts_repo = AlertsRepository(conn)
    counts = await alerts_repo.count_by_severity(PROVIDER, PROP_ID)
    assert counts["p2"] == 1


# ── raw events ─────────────────────────────────────────────────────────────────

async def test_each_message_inserts_raw_event(conn):
    await _run(conn, [
        _edge_health_msg(),
        _periodic_msg(),
        _transition_msg(),
    ])
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM raw_events WHERE provider_id = $1", PROVIDER
    )
    assert count == 3


# ── full batch ─────────────────────────────────────────────────────────────────

async def test_batch_4_messages(conn):
    messages = [
        _edge_health_msg(tracked=3, unhealthy=1),
        _periodic_msg(device_id="dev-001", status="healthy", score=90),
        _transition_msg(device_id="dev-001", status="unhealthy", score=20),
        _periodic_msg(device_id="dev-002", status="degraded", score=60, device_class="dect_base"),
    ]
    result = await _run(conn, messages)
    assert result["accepted"] == 4
    assert result["rejected"] == []

    # edge_box row exists
    box = await PropertiesRepository(conn).get_edge_box_for_property(PROVIDER, PROP_ID)
    assert box is not None

    # two devices
    devices = await DevicesRepository(conn).list_for_property(PROVIDER, PROP_ID)
    assert len(devices) == 2

    # one open p1 alert from the transition
    counts = await AlertsRepository(conn).count_by_severity(PROVIDER, PROP_ID)
    assert counts["p1"] == 1


# ── HTTP smoke test ────────────────────────────────────────────────────────────

async def test_http_ingest_returns_accepted(http_client):
    body = {
        "schema_version": "1.0",
        "edge_id": EDGE_ID,
        "service_provider": PROVIDER,
        "property_id": PROP_ID,
        "property_name": "Cottons Hotel",
        "messages": [
            {
                "kind": "edge_health",
                "ts": 1_746_720_000.0,
                "metrics": {
                    "tracked_devices": 2,
                    "unhealthy_devices": 0,
                    "queue_depth": 0,
                    "summary_interval_seconds": 60,
                },
            },
            {
                "kind": "periodic",
                "ts": 1_746_720_001.0,
                "device_id": "dev-http-001",
                "device_class": "poe_switch",
                "health": {"status": "healthy", "score": 95, "reasons": []},
            },
            {
                "kind": "transition",
                "ts": 1_746_720_002.0,
                "device_id": "dev-http-001",
                "device_class": "poe_switch",
                "health": {"status": "unhealthy", "score": 15, "reasons": ["port_flap"]},
                "top_events": [
                    {
                        "ts": 1_746_720_000.0,
                        "severity": "error",
                        "category": "link",
                        "message": "Port Gi0/1 down",
                    }
                ],
            },
            {
                "kind": "periodic",
                "ts": 1_746_720_003.0,
                "device_id": "dev-http-002",
                "device_class": "dect_base",
                "health": {"status": "degraded", "score": 55, "reasons": []},
            },
        ],
    }
    resp = await http_client.post("/v1/edge/ingest", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["edge_id"] == EDGE_ID
    assert data["accepted"] == 4
    assert data["rejected"] == []
