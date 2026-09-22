"""Integration tests — GET /v1/alerts and GET /v1/alerts/{alert_id}."""
from datetime import datetime, timezone

import pytest

from app.lib.ingestor import Ingestor
from app.repositories.alerts import AlertsRepository
from app.schemas.ingest import (
    DeviceHealth,
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


async def _open_alert_id(pg_pool) -> str:
    """Return the alert_id of the first open alert for PROVIDER."""
    async with pg_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT alert_id FROM alerts WHERE provider_id=$1 AND state='opened' LIMIT 1",
            PROVIDER,
        )
    return row["alert_id"]


# ── GET /v1/alerts ─────────────────────────────────────────────────────────────

async def test_list_alerts_empty(http_client):
    resp = await http_client.get("/v1/alerts", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["has_more"] is False
    assert data["next_cursor"] is None


async def test_list_alerts_missing_auth(http_client):
    resp = await http_client.get("/v1/alerts")
    assert resp.status_code == 401


async def test_list_alerts_returns_items(pg_pool, http_client):
    await _ingest(pg_pool, [_transition(device_id="dev-001")])

    resp = await http_client.get("/v1/alerts", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["severity"] == "p1"
    assert item["state"] == "opened"
    assert item["property_id"] == PROP_ID
    assert item["device_id"] == "dev-001"
    assert item["impact_summary"] == "Impact assessment pending"
    assert item["alert_kind"] == "health_transition_to_unhealthy"


async def test_list_alerts_sorted_severity_ascending(pg_pool, http_client):
    await _ingest(pg_pool, [_transition(device_id="dev-p2", status="degraded", score=60)])
    await _ingest(pg_pool, [_transition(device_id="dev-p1", status="unhealthy", score=20)])

    resp = await http_client.get("/v1/alerts", headers=HEADERS)
    items = resp.json()["items"]
    assert len(items) == 2
    assert items[0]["severity"] == "p1"
    assert items[1]["severity"] == "p2"


async def test_list_alerts_state_filter_resolved(pg_pool, http_client):
    # Open then resolve
    await _ingest(pg_pool, [_transition(status="unhealthy")])
    await _ingest(pg_pool, [_transition(status="healthy", score=95)])

    # Default filter (opened,triaged,acting) → no resolved alerts
    resp = await http_client.get("/v1/alerts", headers=HEADERS)
    assert resp.json()["items"] == []

    # Explicit resolved filter
    resp = await http_client.get("/v1/alerts", headers=HEADERS, params={"status": "resolved"})
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["state"] == "resolved"


async def test_list_alerts_invalid_state_returns_400(http_client):
    resp = await http_client.get("/v1/alerts", headers=HEADERS, params={"status": "bad_state"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_FAILED"


async def test_list_alerts_cursor_pagination(pg_pool, http_client):
    for i, sev in enumerate(["unhealthy", "unhealthy", "degraded"]):
        await _ingest(pg_pool, [_transition(device_id=f"dev-{i:03d}", status=sev, score=20)])

    # Page 1 — limit=2
    resp1 = await http_client.get("/v1/alerts", headers=HEADERS, params={"limit": 2})
    data1 = resp1.json()
    assert len(data1["items"]) == 2
    assert data1["has_more"] is True
    assert data1["next_cursor"] is not None

    # Page 2 — use cursor
    resp2 = await http_client.get(
        "/v1/alerts", headers=HEADERS,
        params={"limit": 2, "cursor": data1["next_cursor"]},
    )
    data2 = resp2.json()
    assert len(data2["items"]) == 1
    assert data2["has_more"] is False

    # No overlap
    ids1 = {r["alert_id"] for r in data1["items"]}
    ids2 = {r["alert_id"] for r in data2["items"]}
    assert ids1.isdisjoint(ids2)


async def test_list_alerts_provider_isolation(pg_pool, http_client):
    """Alerts from a different provider must not appear."""
    async with pg_pool.acquire() as conn:
        # Insert a property + alert for OTHER provider directly
        await conn.execute(
            "INSERT INTO service_providers (provider_id, name) VALUES ($1,$1) ON CONFLICT DO NOTHING",
            OTHER,
        )
        await conn.execute(
            "INSERT INTO properties (provider_id, property_id, name) VALUES ($1,'prop_x','X') "
            "ON CONFLICT DO NOTHING",
            OTHER,
        )
        await conn.execute(
            """INSERT INTO alerts
               (alert_id, provider_id, property_id, severity, alert_kind, summary, opened_at, detail_json)
               VALUES ('alr_other',$1,'prop_x','p1','test','test',NOW(),'{}')""",
            OTHER,
        )
    resp = await http_client.get("/v1/alerts", headers=HEADERS)
    # PROVIDER's list must be empty (no alerts for bluip)
    assert resp.json()["items"] == []


# ── GET /v1/alerts/{alert_id} ─────────────────────────────────────────────────

async def test_get_alert_returns_detail(pg_pool, http_client):
    await _ingest(pg_pool, [_transition(status="unhealthy")])
    alert_id = await _open_alert_id(pg_pool)

    resp = await http_client.get(f"/v1/alerts/{alert_id}", headers=HEADERS)
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["alert_id"] == alert_id
    assert detail["identity"]["state"] == "opened"
    assert detail["identity"]["severity"] == "p1"
    assert len(detail["causal_chain"]) >= 2


async def test_get_alert_not_found_returns_404(http_client):
    resp = await http_client.get("/v1/alerts/alr_nonexistent", headers=HEADERS)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_get_alert_wrong_provider_returns_404(pg_pool, http_client):
    """Cross-provider lookup must return 404, not 403 — don't leak existence."""
    await _ingest(pg_pool, [_transition(status="unhealthy")])
    alert_id = await _open_alert_id(pg_pool)

    resp = await http_client.get(
        f"/v1/alerts/{alert_id}",
        headers={"X-Provider-Id": OTHER},
    )
    assert resp.status_code == 404


async def test_get_alert_state_refreshed_after_transition(pg_pool, http_client):
    """identity.state must reflect the live DB state, not the stale materialized value."""
    await _ingest(pg_pool, [_transition(status="unhealthy")])
    alert_id = await _open_alert_id(pg_pool)

    # Manually advance to triaged
    async with pg_pool.acquire() as conn:
        now = datetime.now(timezone.utc)
        await AlertsRepository(conn).update_state(alert_id, "triaged", now)

    resp = await http_client.get(f"/v1/alerts/{alert_id}", headers=HEADERS)
    detail = resp.json()
    assert detail["identity"]["state"] == "triaged"
    assert detail["identity"]["triaged_at"] is not None


async def test_get_alert_missing_auth_returns_401(http_client):
    resp = await http_client.get("/v1/alerts/alr_any")
    assert resp.status_code == 401
