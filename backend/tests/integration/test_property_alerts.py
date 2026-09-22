"""Integration tests — GET /v1/properties/{property_id}/alerts"""
import pytest

PROVIDER = "bluip"
HEADERS = {"X-Provider-Id": PROVIDER}

INGEST_BODY = {
    "schema_version": "1.0",
    "edge_id": "edge-pa-01",
    "service_provider": PROVIDER,
    "property_id": "prop_pa_test",
    "property_name": "PA Test Hotel",
    "messages": [
        {
            "kind": "edge_health",
            "ts": 1700000000.0,
            "metrics": {"tracked_devices": 2, "unhealthy_devices": 1,
                        "queue_depth": 0, "summary_interval_seconds": 60},
        },
        {
            "kind": "transition",
            "ts": 1700000100.0,
            "device_id": "dev-pa-router",
            "device_name": "Router HQ",
            "device_class": "router",
            "vendor": "mikrotik",
            "site": "hq",
            "health": {"status": "unhealthy", "score": 30, "reasons": ["link_flap"]},
            "metrics": {"event_count": 8, "error_count": 6, "warn_count": 2},
            "top_events": [
                {"ts": 1700000100.0, "severity": "error", "category": "link",
                 "message": "Interface down"},
            ],
        },
        {
            "kind": "transition",
            "ts": 1700000200.0,
            "device_id": "dev-pa-switch",
            "device_name": "Switch HQ",
            "device_class": "switch",
            "vendor": "cisco",
            "site": "hq",
            "health": {"status": "degraded", "score": 65, "reasons": ["high_latency"]},
            "metrics": {"event_count": 3, "error_count": 1, "warn_count": 2},
            "top_events": [
                {"ts": 1700000200.0, "severity": "warning", "category": "latency",
                 "message": "Latency exceeded threshold"},
            ],
        },
    ],
}


@pytest.fixture
async def seeded(http_client):
    resp = await http_client.post("/v1/edge/ingest", json=INGEST_BODY, headers=HEADERS)
    assert resp.status_code == 200
    return resp.json()


async def test_property_alerts_missing_auth(http_client):
    resp = await http_client.get("/v1/properties/prop_pa_test/alerts")
    assert resp.status_code == 401


async def test_property_alerts_not_found(http_client):
    resp = await http_client.get("/v1/properties/no_such_prop/alerts", headers=HEADERS)
    assert resp.status_code == 404


async def test_property_alerts_wrong_provider(http_client, seeded):
    resp = await http_client.get(
        "/v1/properties/prop_pa_test/alerts",
        headers={"X-Provider-Id": "other_provider"},
    )
    assert resp.status_code == 404


async def test_property_alerts_returns_200(http_client, seeded):
    resp = await http_client.get("/v1/properties/prop_pa_test/alerts", headers=HEADERS)
    assert resp.status_code == 200


async def test_property_alerts_returns_all_open(http_client, seeded):
    resp = await http_client.get("/v1/properties/prop_pa_test/alerts", headers=HEADERS)
    data = resp.json()
    assert data["property_id"] == "prop_pa_test"
    assert len(data["items"]) == 2
    assert data["has_more"] is False
    assert data["total_returned"] == 2


async def test_property_alerts_item_has_full_detail(http_client, seeded):
    resp = await http_client.get("/v1/properties/prop_pa_test/alerts", headers=HEADERS)
    item = resp.json()["items"][0]
    # Must have same shape as GET /v1/alerts/{id}
    assert "alert_id" in item
    assert "identity" in item
    assert "signal" in item
    assert "causal_chain" in item
    assert "agent_reasoning" in item


async def test_property_alerts_top_events_in_signal_series(http_client, seeded):
    resp = await http_client.get("/v1/properties/prop_pa_test/alerts", headers=HEADERS)
    item = resp.json()["items"][0]
    series = item["signal"]["series"]
    assert len(series) > 0
    assert "message" in series[0]


async def test_property_alerts_ordered_by_severity(http_client, seeded):
    resp = await http_client.get("/v1/properties/prop_pa_test/alerts", headers=HEADERS)
    items = resp.json()["items"]
    severities = [i["identity"]["severity"] for i in items]
    # p1 must come before p2
    assert severities.index("p1") < severities.index("p2")


async def test_property_alerts_pagination_limit(http_client, seeded):
    resp = await http_client.get(
        "/v1/properties/prop_pa_test/alerts?limit=1", headers=HEADERS
    )
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["has_more"] is True
    assert data["next_cursor"] is not None


async def test_property_alerts_cursor_second_page(http_client, seeded):
    page1 = (await http_client.get(
        "/v1/properties/prop_pa_test/alerts?limit=1", headers=HEADERS
    )).json()
    cursor = page1["next_cursor"]

    page2 = (await http_client.get(
        f"/v1/properties/prop_pa_test/alerts?limit=1&cursor={cursor}", headers=HEADERS
    )).json()
    assert len(page2["items"]) == 1
    assert page2["has_more"] is False
    # No duplicates
    assert page1["items"][0]["alert_id"] != page2["items"][0]["alert_id"]


async def test_property_alerts_status_filter_resolved(http_client, seeded):
    resp = await http_client.get(
        "/v1/properties/prop_pa_test/alerts?status=resolved", headers=HEADERS
    )
    data = resp.json()
    assert data["items"] == []


async def test_property_alerts_invalid_status(http_client, seeded):
    resp = await http_client.get(
        "/v1/properties/prop_pa_test/alerts?status=invalid", headers=HEADERS
    )
    assert resp.status_code == 400
