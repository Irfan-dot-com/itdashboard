"""Integration tests — repositories against real PostgreSQL."""
from datetime import datetime, timezone

import pytest

from app.repositories.properties import PropertiesRepository
from app.repositories.devices import DevicesRepository
from app.repositories.alerts import AlertsRepository
from app.repositories.raw_events import RawEventsRepository
from app.lib.cursor import decode_cursor

PROVIDER = "bluip"
PROP_ID  = "prop_cottons"
NOW      = datetime(2026, 5, 8, 10, 0, 0, tzinfo=timezone.utc)


# ── PropertiesRepository ──────────────────────────────────────────────────────

async def test_upsert_and_get_property(conn):
    repo = PropertiesRepository(conn)
    await repo.upsert(PROVIDER, PROP_ID, "Cottons Hotel", site_code="CTH")
    row = await repo.get(PROVIDER, PROP_ID)
    assert row["name"] == "Cottons Hotel"
    assert row["site_code"] == "CTH"


async def test_upsert_property_updates_name(conn):
    repo = PropertiesRepository(conn)
    await repo.upsert(PROVIDER, PROP_ID, "Old Name")
    await repo.upsert(PROVIDER, PROP_ID, "New Name")
    row = await repo.get(PROVIDER, PROP_ID)
    assert row["name"] == "New Name"


async def test_upsert_property_preserves_site_code_on_null(conn):
    repo = PropertiesRepository(conn)
    await repo.upsert(PROVIDER, PROP_ID, "Hotel", site_code="CTH")
    await repo.upsert(PROVIDER, PROP_ID, "Hotel", site_code=None)
    row = await repo.get(PROVIDER, PROP_ID)
    assert row["site_code"] == "CTH"   # COALESCE preserved existing value


async def test_list_properties(conn):
    repo = PropertiesRepository(conn)
    await repo.upsert(PROVIDER, "prop_a", "Alpha Hotel")
    await repo.upsert(PROVIDER, "prop_b", "Beta Hotel")
    rows = await repo.list(PROVIDER)
    names = [r["name"] for r in rows]
    assert names == sorted(names)   # ordered by name


async def test_upsert_edge_box(conn):
    repo = PropertiesRepository(conn)
    await repo.upsert(PROVIDER, PROP_ID, "Cottons Hotel")
    await repo.upsert_edge_box(
        "edge-7", PROVIDER, PROP_ID, NOW,
        tracked_devices=5, unhealthy_devices=1, queue_depth=0,
    )
    box = await repo.get_edge_box("edge-7")
    assert box["tracked_devices"] == 5
    assert box["unhealthy_devices"] == 1


async def test_get_edge_box_for_property(conn):
    repo = PropertiesRepository(conn)
    await repo.upsert(PROVIDER, PROP_ID, "Cottons Hotel")
    await repo.upsert_edge_box("edge-7", PROVIDER, PROP_ID, NOW, 5, 1, 0)
    box = await repo.get_edge_box_for_property(PROVIDER, PROP_ID)
    assert box["edge_id"] == "edge-7"


# ── DevicesRepository ─────────────────────────────────────────────────────────

async def _seed_property(conn):
    await PropertiesRepository(conn).upsert(PROVIDER, PROP_ID, "Cottons Hotel")


async def test_upsert_and_get_device(conn):
    await _seed_property(conn)
    repo = DevicesRepository(conn)
    await repo.upsert("dev-001", PROVIDER, PROP_ID, device_class="poe_switch", vendor="aruba")
    dev = await repo.get("dev-001")
    assert dev["device_class"] == "poe_switch"
    assert dev["vendor"] == "aruba"


async def test_upsert_device_preserves_class_on_null(conn):
    await _seed_property(conn)
    repo = DevicesRepository(conn)
    await repo.upsert("dev-001", PROVIDER, PROP_ID, device_class="poe_switch")
    await repo.upsert("dev-001", PROVIDER, PROP_ID, device_class=None)
    dev = await repo.get("dev-001")
    assert dev["device_class"] == "poe_switch"


async def test_update_health_returns_prior_when_changed(conn):
    await _seed_property(conn)
    repo = DevicesRepository(conn)
    await repo.upsert("dev-001", PROVIDER, PROP_ID)
    prior = await repo.update_health("dev-001", "unhealthy", 28, NOW)
    assert prior == "unknown"    # default health_status is 'unknown'


async def test_update_health_returns_none_when_unchanged(conn):
    await _seed_property(conn)
    repo = DevicesRepository(conn)
    await repo.upsert("dev-001", PROVIDER, PROP_ID)
    await repo.update_health("dev-001", "healthy", 92, NOW)
    prior = await repo.update_health("dev-001", "healthy", 90, NOW)
    assert prior is None   # status didn't change


async def test_list_devices_for_property(conn):
    await _seed_property(conn)
    repo = DevicesRepository(conn)
    await repo.upsert("dev-001", PROVIDER, PROP_ID, label="Switch A")
    await repo.upsert("dev-002", PROVIDER, PROP_ID, label="Switch B")
    devs = await repo.list_for_property(PROVIDER, PROP_ID)
    assert len(devs) == 2


# ── AlertsRepository ──────────────────────────────────────────────────────────

async def _seed_device(conn, device_id="dev-001"):
    await _seed_property(conn)
    await DevicesRepository(conn).upsert(device_id, PROVIDER, PROP_ID, device_class="dect_base")


async def _make_alert(conn, alert_id="alr_001", severity="p1", device_id="dev-001"):
    repo = AlertsRepository(conn)
    await repo.create(
        alert_id=alert_id,
        provider_id=PROVIDER,
        property_id=PROP_ID,
        device_id=device_id,
        severity=severity,
        alert_kind="health_transition_to_unhealthy",
        summary="DECT base lost registrations",
        correlation_id="corr_abc",
        opened_at=NOW,
        detail={"schema_version": "1.0", "identity": {"severity": severity}},
    )
    return repo


async def test_create_and_get_alert(conn):
    await _seed_device(conn)
    await _make_alert(conn)
    repo = AlertsRepository(conn)
    row = await repo.get("alr_001", PROVIDER)
    assert row["severity"] == "p1"
    assert row["state"] == "opened"


async def test_get_alert_wrong_provider_returns_none(conn):
    await _seed_device(conn)
    await _make_alert(conn)
    repo = AlertsRepository(conn)
    row = await repo.get("alr_001", "other_provider")
    assert row is None


async def test_update_state_returns_prior(conn):
    await _seed_device(conn)
    await _make_alert(conn)
    repo = AlertsRepository(conn)
    prior = await repo.update_state("alr_001", "triaged", NOW)
    assert prior == "opened"
    row = await repo.get("alr_001", PROVIDER)
    assert row["state"] == "triaged"
    assert row["triaged_at"] is not None


async def test_update_state_not_found_returns_none(conn):
    repo = AlertsRepository(conn)
    result = await repo.update_state("nonexistent", "triaged", NOW)
    assert result is None


async def test_find_open_for_device(conn):
    await _seed_device(conn)
    await _make_alert(conn)
    repo = AlertsRepository(conn)
    row = await repo.find_open_for_device("dev-001", "health_transition_to_unhealthy")
    assert row["alert_id"] == "alr_001"


async def test_find_open_for_device_resolved_returns_none(conn):
    await _seed_device(conn)
    await _make_alert(conn)
    repo = AlertsRepository(conn)
    await repo.update_state("alr_001", "resolved", NOW)
    row = await repo.find_open_for_device("dev-001", "health_transition_to_unhealthy")
    assert row is None


async def test_count_by_severity(conn):
    await _seed_device(conn)
    await _make_alert(conn, "alr_001", "p1")
    await _make_alert(conn, "alr_002", "p2")
    await _make_alert(conn, "alr_003", "p2")
    repo = AlertsRepository(conn)
    counts = await repo.count_by_severity(PROVIDER)
    assert counts["p1"] == 1
    assert counts["p2"] == 2
    assert counts["p3"] == 0


async def test_list_alerts_basic(conn):
    await _seed_device(conn)
    await _make_alert(conn, "alr_001", "p1")
    await _make_alert(conn, "alr_002", "p2")
    repo = AlertsRepository(conn)
    result = await repo.list(PROVIDER, states=["opened"])
    assert len(result["items"]) == 2
    assert result["has_more"] is False
    # p1 should come before p2
    assert result["items"][0]["severity"] == "p1"


async def test_list_alerts_cursor_pagination(conn):
    await _seed_device(conn)
    # Create 3 alerts of different severities
    for i, sev in enumerate(["p1", "p2", "p3"]):
        await _make_alert(conn, f"alr_{i:03d}", sev)

    repo = AlertsRepository(conn)
    # Fetch first page with limit=2
    page1 = await repo.list(PROVIDER, states=["opened"], limit=2)
    assert len(page1["items"]) == 2
    assert page1["has_more"] is True
    assert page1["next_cursor"] is not None

    # Fetch second page using cursor
    page2 = await repo.list(PROVIDER, states=["opened"], limit=2, cursor=page1["next_cursor"])
    assert len(page2["items"]) == 1
    assert page2["has_more"] is False

    # No overlap between pages
    ids_p1 = {r["alert_id"] for r in page1["items"]}
    ids_p2 = {r["alert_id"] for r in page2["items"]}
    assert ids_p1.isdisjoint(ids_p2)


async def test_resolve_all_for_device(conn):
    await _seed_device(conn)
    await _make_alert(conn, "alr_001", "p1")
    await _make_alert(conn, "alr_002", "p2")
    repo = AlertsRepository(conn)
    resolved = await repo.resolve_all_for_device("dev-001", NOW)
    assert len(resolved) == 2
    # Both should now be resolved
    row = await repo.get("alr_001", PROVIDER)
    assert row["state"] == "resolved"


async def test_worst_open(conn):
    await _seed_device(conn)
    await _make_alert(conn, "alr_001", "p3")
    await _make_alert(conn, "alr_002", "p1")
    repo = AlertsRepository(conn)
    worst = await repo.worst_open(PROVIDER, PROP_ID)
    assert worst["severity"] == "p1"


# ── RawEventsRepository ───────────────────────────────────────────────────────

async def test_insert_and_fetch_raw_event(conn):
    await _seed_property(conn)
    repo = RawEventsRepository(conn)
    event_id = await repo.insert(
        kind="edge_health",
        provider_id=PROVIDER,
        property_id=PROP_ID,
        payload={"kind": "edge_health", "ts": 1746720000.0},
        edge_id="edge-7",
    )
    assert event_id.startswith("evt_")
    rows = await repo.recent_for_property(PROVIDER, PROP_ID)
    assert len(rows) == 1
    assert rows[0]["kind"] == "edge_health"


# ── Full round-trip ───────────────────────────────────────────────────────────

async def test_full_round_trip(conn):
    """upsert property → upsert device → create alert → list → verify cursor."""
    prop_repo  = PropertiesRepository(conn)
    dev_repo   = DevicesRepository(conn)
    alrt_repo  = AlertsRepository(conn)

    await prop_repo.upsert(PROVIDER, PROP_ID, "Cottons Hotel", site_code="CTH")
    await dev_repo.upsert("dev-rt", PROVIDER, PROP_ID, device_class="dect_base", label="DECT-1")
    await dev_repo.update_health("dev-rt", "unhealthy", 22, NOW)

    await alrt_repo.create(
        alert_id="alr_rt",
        provider_id=PROVIDER,
        property_id=PROP_ID,
        device_id="dev-rt",
        severity="p1",
        alert_kind="health_transition_to_unhealthy",
        summary="DECT base unhealthy",
        correlation_id="corr_rt",
        opened_at=NOW,
        detail={"schema_version": "1.0", "causal_chain": []},
    )

    result = await alrt_repo.list(PROVIDER, states=["opened"])
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["alert_id"] == "alr_rt"
    assert item["property_name"] == "Cottons Hotel"
    assert item["device_class"] == "dect_base"

    # detail_json returned as dict (JSONB)
    alert_row = await alrt_repo.get("alr_rt", PROVIDER)
    assert alert_row["detail_json"]["schema_version"] == "1.0"
