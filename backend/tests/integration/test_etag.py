"""Integration tests — ETag and Cache-Control headers on GET responses."""
import pytest

HEADERS = {"X-Provider-Id": "bluip"}


async def test_estate_has_etag(http_client):
    resp = await http_client.get("/v1/estate", headers=HEADERS)
    assert resp.status_code == 200
    assert "etag" in resp.headers


async def test_estate_cache_control_tile(http_client):
    resp = await http_client.get("/v1/estate", headers=HEADERS)
    assert resp.headers["cache-control"] == "private, max-age=10"


async def test_exec_cache_control_tile(http_client):
    resp = await http_client.get("/v1/exec", headers=HEADERS)
    assert resp.headers["cache-control"] == "private, max-age=10"


async def test_alerts_cache_control_live(http_client):
    resp = await http_client.get("/v1/alerts", headers=HEADERS)
    assert resp.headers["cache-control"] == "private, max-age=2"


async def test_if_none_match_returns_304(http_client):
    resp1 = await http_client.get("/v1/estate", headers=HEADERS)
    etag = resp1.headers["etag"]

    resp2 = await http_client.get("/v1/estate", headers={**HEADERS, "if-none-match": etag})
    assert resp2.status_code == 304


async def test_if_none_match_stale_returns_200(http_client):
    resp = await http_client.get("/v1/estate", headers={**HEADERS, "if-none-match": '"stale_etag"'})
    assert resp.status_code == 200


async def test_health_probes_no_etag(http_client):
    resp = await http_client.get("/livez")
    assert "etag" not in resp.headers


async def test_error_responses_no_etag(http_client):
    resp = await http_client.get("/v1/estate")  # missing auth → 401
    assert resp.status_code == 401
    assert "etag" not in resp.headers


async def test_post_no_etag(http_client):
    """ETag middleware must not touch POST responses."""
    resp = await http_client.post(
        "/v1/edge/ingest",
        json={"provider_id": "bluip", "property_id": "p1", "messages": []},
        headers=HEADERS,
    )
    assert "etag" not in resp.headers
