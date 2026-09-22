"""Integration tests — GET /v1/properties/{property_id}."""
import pytest

from app.lib.ingestor import Ingestor
from app.schemas.ingest import (
    DeviceHealth,
    EdgeHealthMessage,
    EdgeHealthMetrics,
    PeriodicMessage,
    TopEvent,
    TransitionMessage,
)

PROVIDER = "bluip"
OTHER = "other_provider"
EDGE_ID = "edge-7"
PROP_ID = "prop_cottons"
HEADERS = {"X-Provider-Id": PROVIDER}


# ── helpers ────────────────────────────────────────────────────────────────────

def _transition(device_id="dev-001", status="unhealthy", score=20):
    return TransitionMessage(
        kind="transition",
        ts=1_746_720_000.0,
        device_id=device_id,
        device_class="poe_switch",
        health=DeviceHealth(status=status, score=score, reasons=["link_down"]),
        top_events=[
            TopEvent(ts=1_746_720_000.0, severity="error", category="link", message="Port down")
        ],
    )


def _periodic(device_id="dev-001", status="healthy", score=95):
    return PeriodicMessage(
        kind="periodic",
        ts=1_746_720_000.0,
        device_id=device_id,
        device_class="poe_switch",
        health=DeviceHealth(status=status, score=score, reasons=[]),
        top_events=[],
    )


def _edge_health(queue_depth=5):
    return EdgeHealthMessage(
        kind="edge_health",
        ts=1_746_720_000.0,
        metrics=EdgeHealthMetrics(
            tracked_devices=3,
            unhealthy_devices=1,
            queue_depth=queue_depth,
            summary_interval_seconds=60,
        ),
    )


async def _ingest(pg_pool, messages, prop_id=PROP_ID):
    async with pg_pool.acquire() as conn:
        ingestor = Ingestor(conn)
        return await ingestor.handle_batch(
            edge_id=EDGE_ID,
            service_provider=PROVIDER,
            property_id=prop_id,
            property_name="Cottons Hotel",
            messages=messages,
        )


# ── GET /v1/properties/{property_id} ──────────────────────────────────────────

async def test_get_property_not_found(http_client):
    resp = await http_client.get("/v1/properties/prop_nonexistent", headers=HEADERS)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_get_property_missing_auth(http_client):
    resp = await http_client.get(f"/v1/properties/{PROP_ID}")
    assert resp.status_code == 401


async def test_get_property_wrong_provider_returns_404(pg_pool, http_client):
    """Cross-provider lookup must return 404, not 403 — don't leak existence."""
    await _ingest(pg_pool, [_transition()])
    resp = await http_client.get(
        f"/v1/properties/{PROP_ID}",
        headers={"X-Provider-Id": OTHER},
    )
    assert resp.status_code == 404


async def test_get_property_basic_fields(pg_pool, http_client):
    await _ingest(pg_pool, [_transition(device_id="dev-001")])

    resp = await http_client.get(f"/v1/properties/{PROP_ID}", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()

    assert data["property_id"] == PROP_ID
    assert data["provider_id"] == PROVIDER
    assert data["name"] == "Cottons Hotel"
    assert data["health_status"] == "unhealthy"
    assert data["health_score"] <= 40
    assert data["integration_health"] == []


async def test_get_property_devices_included(pg_pool, http_client):
    await _ingest(pg_pool, [_transition(device_id="dev-001")])

    resp = await http_client.get(f"/v1/properties/{PROP_ID}", headers=HEADERS)
    data = resp.json()

    assert len(data["devices"]) == 1
    dev = data["devices"][0]
    assert dev["device_id"] == "dev-001"
    assert dev["device_class"] == "poe_switch"
    assert dev["health_status"] == "unhealthy"


async def test_get_property_device_has_site_field(pg_pool, http_client):
    """DeviceSummary must expose the `site` field even when None."""
    await _ingest(pg_pool, [_transition(device_id="dev-001")])

    resp = await http_client.get(f"/v1/properties/{PROP_ID}", headers=HEADERS)
    dev = resp.json()["devices"][0]
    assert "site" in dev


async def test_get_property_unhealthy_device_has_open_alerts(pg_pool, http_client):
    await _ingest(pg_pool, [_transition(device_id="dev-001", status="unhealthy")])

    resp = await http_client.get(f"/v1/properties/{PROP_ID}", headers=HEADERS)
    dev = resp.json()["devices"][0]
    total = sum(dev["open_alerts"].values())
    assert total >= 1


async def test_get_property_healthy_device_has_zero_alerts(pg_pool, http_client):
    await _ingest(pg_pool, [_periodic(device_id="dev-001", status="healthy")])

    resp = await http_client.get(f"/v1/properties/{PROP_ID}", headers=HEADERS)
    dev = resp.json()["devices"][0]
    assert dev["health_status"] == "healthy"
    total = sum(dev["open_alerts"].values())
    assert total == 0


async def test_get_property_open_alerts_aggregate(pg_pool, http_client):
    await _ingest(pg_pool, [_transition(device_id="dev-001", status="unhealthy")])

    resp = await http_client.get(f"/v1/properties/{PROP_ID}", headers=HEADERS)
    data = resp.json()
    assert data["open_alerts"]["p1"] >= 1


async def test_get_property_edge_box_present(pg_pool, http_client):
    await _ingest(pg_pool, [_edge_health(queue_depth=3)])

    resp = await http_client.get(f"/v1/properties/{PROP_ID}", headers=HEADERS)
    data = resp.json()
    assert len(data["edge_boxes"]) == 1
    eb = data["edge_boxes"][0]
    assert eb["edge_id"] == EDGE_ID
    assert eb["queue_depth"] == 3
    assert eb["tracked_devices"] == 3
    assert eb["unhealthy_devices"] == 1
    assert "online" in eb


async def test_get_property_no_edge_box(pg_pool, http_client):
    """Property with no edge_health messages yet → edge_boxes is empty list."""
    await _ingest(pg_pool, [_transition(device_id="dev-001")])

    resp = await http_client.get(f"/v1/properties/{PROP_ID}", headers=HEADERS)
    assert resp.json()["edge_boxes"] == []


async def test_get_property_multiple_edge_boxes(pg_pool, http_client):
    """Two edge boxes on same property both appear in edge_boxes list."""
    async with pg_pool.acquire() as conn:
        ingestor = Ingestor(conn)
        await ingestor.handle_batch(
            edge_id="edge-7", service_provider=PROVIDER,
            property_id=PROP_ID, property_name="Cottons Hotel",
            messages=[_edge_health(queue_depth=1)],
        )
        await ingestor.handle_batch(
            edge_id="edge-8", service_provider=PROVIDER,
            property_id=PROP_ID, property_name="Cottons Hotel",
            messages=[_edge_health(queue_depth=2)],
        )

    resp = await http_client.get(f"/v1/properties/{PROP_ID}", headers=HEADERS)
    edge_boxes = resp.json()["edge_boxes"]
    assert len(edge_boxes) == 2
    edge_ids = {eb["edge_id"] for eb in edge_boxes}
    assert edge_ids == {"edge-7", "edge-8"}


async def test_get_property_recent_events_populated(pg_pool, http_client):
    await _ingest(pg_pool, [_transition(device_id="dev-001"), _edge_health()])

    resp = await http_client.get(f"/v1/properties/{PROP_ID}", headers=HEADERS)
    data = resp.json()
    events = data["recent_events"]
    assert len(events) >= 1

    kinds = {e["kind"] for e in events}
    assert kinds & {"transition", "edge_health"}

    first = events[0]
    assert "event_id" in first
    assert "kind" in first
    assert "received_at" in first
    assert "summary" in first
    assert len(first["summary"]) > 0


async def test_get_property_recent_event_summary_edge_health(pg_pool, http_client):
    await _ingest(pg_pool, [_edge_health(queue_depth=7)])

    resp = await http_client.get(f"/v1/properties/{PROP_ID}", headers=HEADERS)
    events = resp.json()["recent_events"]
    edge_events = [e for e in events if e["kind"] == "edge_health"]
    assert edge_events
    assert "queue_depth=7" in edge_events[0]["summary"]


async def test_get_property_recent_event_summary_transition(pg_pool, http_client):
    await _ingest(pg_pool, [_transition(device_id="dev-001", status="unhealthy")])

    resp = await http_client.get(f"/v1/properties/{PROP_ID}", headers=HEADERS)
    events = resp.json()["recent_events"]
    trans_events = [e for e in events if e["kind"] == "transition"]
    assert trans_events
    assert "dev-001" in trans_events[0]["summary"]
    assert "unhealthy" in trans_events[0]["summary"]


async def test_get_property_no_devices(pg_pool, http_client):
    """Property created via edge_health only has no devices — must still return 200."""
    await _ingest(pg_pool, [_edge_health()])

    resp = await http_client.get(f"/v1/properties/{PROP_ID}", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["devices"] == []
    assert data["health_status"] == "unknown"
    assert data["health_score"] == 0


async def test_get_property_multiple_devices(pg_pool, http_client):
    await _ingest(pg_pool, [
        _transition(device_id="dev-001", status="unhealthy"),
        _periodic(device_id="dev-002", status="healthy"),
    ])

    resp = await http_client.get(f"/v1/properties/{PROP_ID}", headers=HEADERS)
    data = resp.json()
    assert len(data["devices"]) == 2
    assert data["health_status"] == "unhealthy"
