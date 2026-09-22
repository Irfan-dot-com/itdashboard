"""Integration tests — outbox poller against real PostgreSQL + Redis."""
import asyncio
import json

import pytest

from app.lib.outbox_poller import _poll_once


async def _next_message(pubsub, timeout: float = 2.0) -> dict:
    """Await the first 'message'-type event from a subscribed pubsub."""
    async def _read():
        async for msg in pubsub.listen():
            if msg["type"] == "message":
                return msg
    return await asyncio.wait_for(_read(), timeout=timeout)


async def _insert_outbox(pool, *, event_id, property_id, event_kind, payload):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO event_outbox (event_id, property_id, event_kind, payload_json)
            VALUES ($1, $2, $3, $4)
            """,
            event_id, property_id, event_kind, payload,
        )


async def test_poll_once_publishes_to_redis(pg_pool, db, redis_client):
    await _insert_outbox(
        pg_pool,
        event_id="evt_ob1",
        property_id="prop_a",
        event_kind="edge.heartbeat",
        payload={"ts": 1234567890, "edge_id": "edge-7"},
    )

    pubsub = redis_client.pubsub()
    await pubsub.subscribe("hosp:prop:prop_a")

    await _poll_once(db, redis_client)

    msg = await _next_message(pubsub)
    data = json.loads(msg["data"])
    assert data["event_kind"] == "edge.heartbeat"
    assert data["ts"] == 1234567890
    assert data["edge_id"] == "edge-7"

    await pubsub.unsubscribe("hosp:prop:prop_a")
    await pubsub.aclose()


async def test_poll_once_marks_published_at(pg_pool, db, redis_client):
    await _insert_outbox(
        pg_pool,
        event_id="evt_ob2",
        property_id="prop_b",
        event_kind="device.transition",
        payload={"device_id": "dev-001"},
    )

    await _poll_once(db, redis_client)

    async with pg_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT published_at, attempts FROM event_outbox WHERE event_id = $1",
            "evt_ob2",
        )
    assert row["published_at"] is not None
    assert row["attempts"] == 1


async def test_poll_once_does_nothing_when_empty(db, redis_client):
    # No rows — should complete without error and publish nothing
    await _poll_once(db, redis_client)


async def test_poll_once_skips_already_published(pg_pool, db, redis_client):
    """Rows with published_at already set must not be re-published."""
    async with pg_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO event_outbox
                (event_id, property_id, event_kind, payload_json, published_at, attempts)
            VALUES ($1, $2, $3, $4, NOW(), 1)
            """,
            "evt_ob3", "prop_c", "edge.heartbeat", {"ts": 999},
        )

    pubsub = redis_client.pubsub()
    await pubsub.subscribe("hosp:prop:prop_c")

    await _poll_once(db, redis_client)

    # No new message should arrive — use a short timeout
    got = None
    try:
        got = await _next_message(pubsub, timeout=0.3)
    except asyncio.TimeoutError:
        pass

    assert got is None, "poller re-published an already-published row"

    await pubsub.unsubscribe("hosp:prop:prop_c")
    await pubsub.aclose()


async def test_poll_once_publishes_multiple_rows(pg_pool, db, redis_client):
    for i in range(3):
        await _insert_outbox(
            pg_pool,
            event_id=f"evt_multi_{i}",
            property_id="prop_multi",
            event_kind="edge.heartbeat",
            payload={"seq": i},
        )

    pubsub = redis_client.pubsub()
    await pubsub.subscribe("hosp:prop:prop_multi")

    await _poll_once(db, redis_client)

    received = []
    for _ in range(3):
        msg = await _next_message(pubsub)
        received.append(json.loads(msg["data"]))

    assert len(received) == 3
    seqs = sorted(r["seq"] for r in received)
    assert seqs == [0, 1, 2]

    await pubsub.unsubscribe("hosp:prop:prop_multi")
    await pubsub.aclose()
