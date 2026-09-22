"""Integration tests — GET /v1/exec (stub)."""
import pytest

HEADERS = {"X-Provider-Id": "bluip"}


async def test_exec_missing_auth_returns_401(http_client):
    resp = await http_client.get("/v1/exec")
    assert resp.status_code == 401


async def test_exec_returns_200(http_client):
    resp = await http_client.get("/v1/exec", headers=HEADERS)
    assert resp.status_code == 200


async def test_exec_default_range(http_client):
    resp = await http_client.get("/v1/exec", headers=HEADERS)
    data = resp.json()
    assert data["range"] == "30d"
    assert data["compare_to"] == "prior_period"


async def test_exec_custom_range(http_client):
    resp = await http_client.get("/v1/exec?range=7d&compare_to=prior_week", headers=HEADERS)
    data = resp.json()
    assert data["range"] == "7d"
    assert data["compare_to"] == "prior_week"


async def test_exec_tiles_present(http_client):
    resp = await http_client.get("/v1/exec", headers=HEADERS)
    tiles = resp.json()["tiles"]
    assert "estate_uptime" in tiles
    assert "mttr_by_severity" in tiles
    assert "cost_of_poor_quality" in tiles
    assert "technical_debt_index" in tiles
    assert "agent_activity" in tiles
    assert "top_problem_properties" in tiles
    assert "top_problem_device_classes" in tiles


async def test_exec_stub_note_present(http_client):
    tiles = (await http_client.get("/v1/exec", headers=HEADERS)).json()["tiles"]
    assert tiles["_stub_note"] == "exec view aggregations are phase 2"


async def test_exec_nulls_for_unimplemented(http_client):
    tiles = (await http_client.get("/v1/exec", headers=HEADERS)).json()["tiles"]
    assert tiles["estate_uptime"]["current"] is None
    assert tiles["mttr_by_severity"]["p1_minutes"]["current"] is None
    assert tiles["cost_of_poor_quality"]["current_gbp"] is None
    assert tiles["technical_debt_index"]["score"] is None
