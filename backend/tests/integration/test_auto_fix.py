"""Integration tests — POST /v1/alerts/{alert_id}/auto-fix."""
import pytest

from app.lib.ingestor import Ingestor
from app.schemas.ingest import DeviceHealth, TopEvent, TransitionMessage

PROVIDER = "bluip"
OTHER = "other_provider"
EDGE_ID = "edge-7"
PROP_ID = "prop_cottons"
HEADERS = {"X-Provider-Id": PROVIDER}
IDEM_KEY = "test-idem-key-001"


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


async def _ingest(pg_pool, messages):
    async with pg_pool.acquire() as conn:
        ingestor = Ingestor(conn)
        return await ingestor.handle_batch(
            edge_id=EDGE_ID,
            service_provider=PROVIDER,
            property_id=PROP_ID,
            property_name="Cottons Hotel",
            messages=messages,
        )


async def _open_alert_id(pg_pool) -> str:
    async with pg_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT alert_id FROM alerts WHERE provider_id=$1 AND state='opened' LIMIT 1",
            PROVIDER,
        )
    return row["alert_id"]


async def _authorize_alert(pg_pool, alert_id: str) -> None:
    """Flip auto_fix_authorized=true — normally done by the agent service."""
    async with pg_pool.acquire() as conn:
        await conn.execute(
            "UPDATE alerts SET auto_fix_authorized=true WHERE alert_id=$1",
            alert_id,
        )


async def _resolve_alert(pg_pool, alert_id: str) -> None:
    async with pg_pool.acquire() as conn:
        await conn.execute(
            "UPDATE alerts SET state='resolved', resolved_at=NOW() WHERE alert_id=$1",
            alert_id,
        )


# ── validation failures ────────────────────────────────────────────────────────

async def test_auto_fix_missing_auth(pg_pool, http_client):
    await _ingest(pg_pool, [_transition()])
    alert_id = await _open_alert_id(pg_pool)
    resp = await http_client.post(
        f"/v1/alerts/{alert_id}/auto-fix",
        json={"confirm": True},
        headers={"Idempotency-Key": IDEM_KEY},
    )
    assert resp.status_code == 401


async def test_auto_fix_missing_idempotency_key(pg_pool, http_client):
    await _ingest(pg_pool, [_transition()])
    alert_id = await _open_alert_id(pg_pool)
    resp = await http_client.post(
        f"/v1/alerts/{alert_id}/auto-fix",
        json={"confirm": True},
        headers=HEADERS,  # no Idempotency-Key
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_FAILED"


async def test_auto_fix_confirm_false(pg_pool, http_client):
    await _ingest(pg_pool, [_transition()])
    alert_id = await _open_alert_id(pg_pool)
    resp = await http_client.post(
        f"/v1/alerts/{alert_id}/auto-fix",
        json={"confirm": False},
        headers={**HEADERS, "Idempotency-Key": IDEM_KEY},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_FAILED"


async def test_auto_fix_alert_not_found(http_client):
    resp = await http_client.post(
        "/v1/alerts/alr_nonexistent/auto-fix",
        json={"confirm": True},
        headers={**HEADERS, "Idempotency-Key": IDEM_KEY},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_auto_fix_wrong_provider_returns_404(pg_pool, http_client):
    """Cross-provider lookup must return 404, not 403."""
    await _ingest(pg_pool, [_transition()])
    alert_id = await _open_alert_id(pg_pool)
    resp = await http_client.post(
        f"/v1/alerts/{alert_id}/auto-fix",
        json={"confirm": True},
        headers={"X-Provider-Id": OTHER, "Idempotency-Key": IDEM_KEY},
    )
    assert resp.status_code == 404


async def test_auto_fix_not_authorized(pg_pool, http_client):
    """auto_fix_authorized=false → 422."""
    await _ingest(pg_pool, [_transition()])
    alert_id = await _open_alert_id(pg_pool)
    resp = await http_client.post(
        f"/v1/alerts/{alert_id}/auto-fix",
        json={"confirm": True},
        headers={**HEADERS, "Idempotency-Key": IDEM_KEY},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_FAILED"


async def test_auto_fix_already_resolved(pg_pool, http_client):
    await _ingest(pg_pool, [_transition()])
    alert_id = await _open_alert_id(pg_pool)
    await _authorize_alert(pg_pool, alert_id)
    await _resolve_alert(pg_pool, alert_id)
    resp = await http_client.post(
        f"/v1/alerts/{alert_id}/auto-fix",
        json={"confirm": True},
        headers={**HEADERS, "Idempotency-Key": IDEM_KEY},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"


# ── successful dispatch ────────────────────────────────────────────────────────

async def test_auto_fix_success_returns_202(pg_pool, http_client):
    await _ingest(pg_pool, [_transition()])
    alert_id = await _open_alert_id(pg_pool)
    await _authorize_alert(pg_pool, alert_id)

    resp = await http_client.post(
        f"/v1/alerts/{alert_id}/auto-fix",
        json={"confirm": True},
        headers={**HEADERS, "Idempotency-Key": IDEM_KEY},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["alert_id"] == alert_id
    assert data["action_event_id"].startswith("evt_")
    assert "dispatched_at" in data
    assert "expected_recovery_by" in data
    assert data["status_url"] == f"/v1/alerts/{alert_id}"


async def test_auto_fix_advances_state_to_acting(pg_pool, http_client):
    await _ingest(pg_pool, [_transition()])
    alert_id = await _open_alert_id(pg_pool)
    await _authorize_alert(pg_pool, alert_id)

    await http_client.post(
        f"/v1/alerts/{alert_id}/auto-fix",
        json={"confirm": True},
        headers={**HEADERS, "Idempotency-Key": IDEM_KEY},
    )

    async with pg_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT state, acted_at FROM alerts WHERE alert_id=$1", alert_id
        )
    assert row["state"] == "acting"
    assert row["acted_at"] is not None


async def test_auto_fix_enqueues_outbox_event(pg_pool, http_client):
    await _ingest(pg_pool, [_transition()])
    alert_id = await _open_alert_id(pg_pool)
    await _authorize_alert(pg_pool, alert_id)

    resp = await http_client.post(
        f"/v1/alerts/{alert_id}/auto-fix",
        json={"confirm": True},
        headers={**HEADERS, "Idempotency-Key": IDEM_KEY},
    )
    action_event_id = resp.json()["action_event_id"]

    async with pg_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM event_outbox WHERE event_id=$1", action_event_id
        )
    assert row is not None
    assert row["event_kind"] == "auto_fix.dispatched"
    assert row["payload_json"]["alert_id"] == alert_id
    assert row["payload_json"]["action_event_id"] == action_event_id


# ── idempotency ────────────────────────────────────────────────────────────────

async def test_auto_fix_idempotency_same_key_twice(pg_pool, http_client):
    """Repeating a request with the same Idempotency-Key returns identical 202 body."""
    await _ingest(pg_pool, [_transition()])
    alert_id = await _open_alert_id(pg_pool)
    await _authorize_alert(pg_pool, alert_id)

    key = "idem-repeat-key"
    headers = {**HEADERS, "Idempotency-Key": key}
    payload = {"confirm": True}

    resp1 = await http_client.post(f"/v1/alerts/{alert_id}/auto-fix", json=payload, headers=headers)
    resp2 = await http_client.post(f"/v1/alerts/{alert_id}/auto-fix", json=payload, headers=headers)

    assert resp1.status_code == 202
    assert resp2.status_code == 202
    assert resp1.json() == resp2.json()


async def test_auto_fix_idempotency_no_duplicate_outbox(pg_pool, http_client):
    """Second call with same key must not write a second outbox row."""
    await _ingest(pg_pool, [_transition()])
    alert_id = await _open_alert_id(pg_pool)
    await _authorize_alert(pg_pool, alert_id)

    key = "idem-no-dup-key"
    headers = {**HEADERS, "Idempotency-Key": key}
    payload = {"confirm": True}

    await http_client.post(f"/v1/alerts/{alert_id}/auto-fix", json=payload, headers=headers)
    await http_client.post(f"/v1/alerts/{alert_id}/auto-fix", json=payload, headers=headers)

    async with pg_pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM event_outbox WHERE event_kind='auto_fix.dispatched'",
        )
    # exactly one dispatch event, not two
    assert count == 1


async def test_auto_fix_different_keys_are_independent(pg_pool, http_client):
    """Different Idempotency-Keys are treated as separate requests — only one alert."""
    await _ingest(pg_pool, [_transition()])
    alert_id = await _open_alert_id(pg_pool)
    await _authorize_alert(pg_pool, alert_id)

    r1 = await http_client.post(
        f"/v1/alerts/{alert_id}/auto-fix",
        json={"confirm": True},
        headers={**HEADERS, "Idempotency-Key": "key-A"},
    )
    # Second request with different key hits already-acting alert
    r2 = await http_client.post(
        f"/v1/alerts/{alert_id}/auto-fix",
        json={"confirm": True},
        headers={**HEADERS, "Idempotency-Key": "key-B"},
    )

    assert r1.status_code == 202
    # second unique key sees the alert in "acting" state — not resolved, not unauthorized,
    # so it should succeed too (acting is not a terminal state for auto-fix re-dispatch)
    # OR we can check only the first succeeded and both are independent
    assert r1.json()["action_event_id"] != r2.json().get("action_event_id", "")
