"""Integration tests — GET /v1/estate."""
from datetime import datetime, timezone, timedelta

import pytest

from app.lib.ingestor import Ingestor
from app.repositories.properties import PropertiesRepository
from app.schemas.ingest import (
    DeviceHealth,
    EdgeHealthMessage,
    EdgeHealthMetrics,
    PeriodicMessage,
    TransitionMessage,
    TopEvent,
)

PROVIDER = "bluip"
EDGE_ID = "edge-7"
HEADERS = {"X-Provider-Id": PROVIDER}


async def _ingest(pg_pool, messages, prop_id="prop_cottons", prop_name="Cottons Hotel"):
    async with pg_pool.acquire() as conn:
        ingestor = Ingestor(conn)
        return await ingestor.handle_batch(
            edge_id=EDGE_ID,
            service_provider=PROVIDER,
            property_id=prop_id,
            property_name=prop_name,
            messages=messages,
        )


def _periodic(device_id="dev-001", status="healthy", score=90, device_class="poe_switch"):
    return PeriodicMessage(
        kind="periodic", ts=1_746_720_000.0, device_id=device_id,
        device_class=device_class,
        health=DeviceHealth(status=status, score=score),
    )


def _transition(device_id="dev-001", status="unhealthy", score=20):
    return TransitionMessage(
        kind="transition", ts=1_746_720_001.0, device_id=device_id,
        device_class="poe_switch",
        health=DeviceHealth(status=status, score=score, reasons=["link_down"]),
        top_events=[TopEvent(ts=1_746_720_000.0, severity="error", category="link", message="down")],
    )


def _edge_health(ts=1_746_720_000.0, tracked=2, unhealthy=0, queue=0):
    return EdgeHealthMessage(
        kind="edge_health", ts=ts,
        metrics=EdgeHealthMetrics(
            tracked_devices=tracked, unhealthy_devices=unhealthy,
            queue_depth=queue, summary_interval_seconds=60,
        ),
    )


# ── auth ───────────────────────────────────────────────────────────────────────

async def test_missing_auth_returns_401(http_client):
    resp = await http_client.get("/v1/estate")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTH_REQUIRED"


# ── empty provider ─────────────────────────────────────────────────────────────

async def test_empty_estate(http_client):
    resp = await http_client.get("/v1/estate", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["properties"] == []
    assert data["kpi_strip"]["sites_total"] == 0
    assert data["kpi_strip"]["estate_health_score"] == 0
    assert data["kpi_strip"]["sites_online"] == 0


# ── single property ────────────────────────────────────────────────────────────

async def test_estate_single_property_no_devices(pg_pool, http_client):
    async with pg_pool.acquire() as conn:
        await PropertiesRepository(conn).upsert(PROVIDER, "prop_cottons", "Cottons Hotel", site_code="CTH")

    resp = await http_client.get("/v1/estate", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["properties"]) == 1
    prop = data["properties"][0]
    assert prop["property_id"] == "prop_cottons"
    assert prop["name"] == "Cottons Hotel"
    assert prop["site_code"] == "CTH"
    assert prop["health_score"] == 0
    assert prop["health_status"] == "unknown"
    assert prop["edge_box"] is None
    assert prop["worst_alert_summary"] is None


async def test_estate_healthy_device_score(pg_pool, http_client):
    await _ingest(pg_pool, [_periodic(status="healthy", score=85)])

    resp = await http_client.get("/v1/estate", headers=HEADERS)
    data = resp.json()
    prop = data["properties"][0]
    assert prop["health_status"] == "healthy"
    assert prop["health_score"] == 85


async def test_estate_unhealthy_device_caps_score(pg_pool, http_client):
    """Unhealthy device caps the property health score at 40."""
    await _ingest(pg_pool, [_periodic(status="unhealthy", score=20)])

    resp = await http_client.get("/v1/estate", headers=HEADERS)
    data = resp.json()
    prop = data["properties"][0]
    assert prop["health_status"] == "unhealthy"
    assert prop["health_score"] == 20   # min(20, ceiling=40) = 20


async def test_estate_open_alerts_counted(pg_pool, http_client):
    await _ingest(pg_pool, [_transition(status="unhealthy")])

    resp = await http_client.get("/v1/estate", headers=HEADERS)
    data = resp.json()
    prop = data["properties"][0]
    assert prop["open_alerts"]["p1"] == 1
    assert data["kpi_strip"]["open_alerts"]["p1"] == 1
    assert prop["worst_alert_summary"] is not None


# ── edge box online / offline ──────────────────────────────────────────────────

async def test_estate_site_online_recent_heartbeat(pg_pool, http_client):
    """Edge box with heartbeat < 2×interval seconds ago → online."""
    import time
    recent_ts = time.time() - 30   # 30s ago, well within 2×60=120s window
    await _ingest(pg_pool, [_edge_health(ts=recent_ts)])

    resp = await http_client.get("/v1/estate", headers=HEADERS)
    data = resp.json()
    assert data["kpi_strip"]["sites_online"] == 1
    assert data["properties"][0]["edge_box"]["online"] is True


async def test_estate_site_offline_old_heartbeat(pg_pool, http_client):
    """Edge box with heartbeat > 2×interval seconds ago → offline."""
    import time
    old_ts = time.time() - 300   # 300s ago, beyond 2×60=120s window
    await _ingest(pg_pool, [_edge_health(ts=old_ts)])

    resp = await http_client.get("/v1/estate", headers=HEADERS)
    data = resp.json()
    assert data["kpi_strip"]["sites_online"] == 0
    assert data["properties"][0]["edge_box"]["online"] is False


# ── sorting ────────────────────────────────────────────────────────────────────

async def test_estate_sort_worst_first(pg_pool, http_client):
    """Property with p1 alert should appear before healthy one."""
    await _ingest(pg_pool, [_transition(status="unhealthy")], prop_id="prop_bad", prop_name="Bad Hotel")
    await _ingest(pg_pool, [_periodic(status="healthy", score=90)], prop_id="prop_good", prop_name="Good Hotel")

    resp = await http_client.get("/v1/estate", headers=HEADERS, params={"sort": "worst_first"})
    data = resp.json()
    names = [p["property_id"] for p in data["properties"]]
    assert names[0] == "prop_bad"


async def test_estate_sort_name_asc(pg_pool, http_client):
    await _ingest(pg_pool, [_periodic()], prop_id="prop_z", prop_name="Zeta Hotel")
    await _ingest(pg_pool, [_periodic()], prop_id="prop_a", prop_name="Alpha Hotel")

    resp = await http_client.get("/v1/estate", headers=HEADERS, params={"sort": "name_asc"})
    data = resp.json()
    names = [p["name"] for p in data["properties"]]
    assert names == sorted(names)


# ── kpi strip aggregate ────────────────────────────────────────────────────────

async def test_estate_kpi_strip_aggregates_across_properties(pg_pool, http_client):
    await _ingest(pg_pool, [_transition(device_id="dev-001", status="unhealthy")],
                  prop_id="prop_a", prop_name="Alpha")
    await _ingest(pg_pool, [_transition(device_id="dev-002", status="degraded", score=60)],
                  prop_id="prop_b", prop_name="Beta")

    resp = await http_client.get("/v1/estate", headers=HEADERS)
    data = resp.json()
    kpi = data["kpi_strip"]
    assert kpi["sites_total"] == 2
    assert kpi["open_alerts"]["p1"] == 1   # from prop_a
    assert kpi["open_alerts"]["p2"] == 1   # from prop_b


# ── invalid query param ────────────────────────────────────────────────────────

async def test_estate_invalid_sort_returns_400(http_client):
    resp = await http_client.get("/v1/estate", headers=HEADERS, params={"sort": "bad_value"})
    assert resp.status_code == 400
