"""Integration tests — /livez and /readyz health endpoints."""
import pytest


async def test_livez_returns_200(http_client):
    resp = await http_client.get("/livez")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_readyz_returns_200_when_healthy(http_client):
    resp = await http_client.get("/readyz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["db"] is True
    assert data["redis"] is True


async def test_healthz_legacy_returns_200(http_client):
    resp = await http_client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
