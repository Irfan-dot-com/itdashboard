"""Integration tests — GET /v1/stream (SSE).

httpx.AsyncClient + ASGITransport (and the equivalent Starlette TestClient in
Starlette ≥ 0.20) both buffer the full response body before returning.  An
infinite SSE stream therefore hangs any test that goes through the HTTP layer.

Strategy:
  * Auth guard (401) — tested via http_client since the exception is raised
    *before* the stream starts, so ASGITransport returns immediately.
  * Streaming behaviour — tested by calling sse_event_stream() directly with
    a real Redis pubsub, plus a controlled is_disconnected() callable that
    terminates the generator after receiving the expected events.
"""
import asyncio
import json

import pytest
import redis.asyncio as aioredis

from app.lib.sse_buffer import SseReplayBuffer
from app.routers.stream import _passes_filter, sse_event_stream

PROVIDER = "bluip"
HEADERS = {"X-Provider-Id": PROVIDER}


# ── auth ───────────────────────────────────────────────────────────────────────

async def test_stream_missing_auth_returns_401(http_client):
    """401 is raised before streaming — safe with ASGITransport."""
    resp = await http_client.get("/v1/stream")
    assert resp.status_code == 401


# ── sse_event_stream — unit-level with mock pubsub ────────────────────────────

class _FinitePubSub:
    """Returns a fixed list of messages then signals disconnect via is_done."""

    def __init__(self, messages: list[dict]):
        self._msgs = list(messages)
        self._idx = 0
        self.closed = False

    async def psubscribe(self, *args): pass
    async def subscribe(self, *args): pass
    async def unsubscribe(self): pass
    async def aclose(self): self.closed = True

    async def get_message(self, ignore_subscribe_messages=False, timeout=None):
        if self._idx < len(self._msgs):
            msg = self._msgs[self._idx]
            self._idx += 1
            return msg
        return None


def _msg(event_id: str, event_kind: str = "alert.opened",
         property_id: str = "prop_x") -> dict:
    return {
        "type": "message",
        "data": json.dumps({
            "event_id": event_id,
            "event_kind": event_kind,
            "property_id": property_id,
        }),
    }


async def _collect(pubsub, **kwargs) -> list[str]:
    """Drain sse_event_stream into a list, disconnecting once messages run out."""
    buf = kwargs.pop("buffer", SseReplayBuffer())
    disconnects_after = kwargs.pop("disconnects_after", 2)
    checks = [0]

    async def is_disconnected():
        checks[0] += 1
        # Disconnect after the pubsub is empty (extra safety: 2 consecutive None returns)
        return checks[0] > disconnects_after

    chunks = []
    async for chunk in sse_event_stream(
        pubsub, kwargs.get("requested_pids"), kwargs.get("kind_filter"),
        kwargs.get("min_severity"), kwargs.get("last_event_id"),
        is_disconnected, buf,
    ):
        chunks.append(chunk)
    return chunks


async def test_event_stream_yields_connected_comment():
    pubsub = _FinitePubSub([])
    chunks = await _collect(pubsub)
    assert chunks[0] == ": connected\n\n"


async def test_event_stream_pubsub_closed_on_exit():
    pubsub = _FinitePubSub([])
    await _collect(pubsub)
    assert pubsub.closed


async def test_event_stream_delivers_message():
    pubsub = _FinitePubSub([_msg("evt_mock_01")])
    chunks = await _collect(pubsub, disconnects_after=5)
    assert any("evt_mock_01" in c for c in chunks)


async def test_event_stream_frame_format():
    pubsub = _FinitePubSub([_msg("evt_fmt_01", event_kind="alert.opened")])
    chunks = await _collect(pubsub, disconnects_after=5)
    data_chunks = [c for c in chunks if c.startswith("id:")]
    assert data_chunks
    frame = data_chunks[0]
    assert "id: evt_fmt_01" in frame
    assert "event: alert.opened" in frame
    assert "data:" in frame


async def test_event_stream_property_filter_excludes():
    pubsub = _FinitePubSub([
        _msg("evt_other", property_id="prop_b"),
        _msg("evt_wanted", property_id="prop_a"),
    ])
    chunks = await _collect(pubsub, requested_pids=["prop_a"], disconnects_after=10)
    assert not any("evt_other" in c for c in chunks)
    assert any("evt_wanted" in c for c in chunks)


async def test_event_stream_kind_filter_excludes():
    pubsub = _FinitePubSub([
        _msg("evt_hb", event_kind="edge.heartbeat"),
        _msg("evt_alrt", event_kind="alert.opened"),
    ])
    chunks = await _collect(pubsub, kind_filter={"alert.opened"}, disconnects_after=10)
    assert not any("evt_hb" in c for c in chunks)
    assert any("evt_alrt" in c for c in chunks)


async def test_event_stream_replay_from_buffer():
    buf = SseReplayBuffer()
    # Pre-populate buffer
    import json as _json
    from app.lib.sse_buffer import BufferedEvent
    buf.add(BufferedEvent(
        event_id="evt_old_1",
        event_kind="alert.opened",
        property_id="prop_x",
        payload=_json.dumps({"event_id": "evt_old_1", "event_kind": "alert.opened",
                              "property_id": "prop_x"}),
    ))
    buf.add(BufferedEvent(
        event_id="evt_old_2",
        event_kind="alert.opened",
        property_id="prop_x",
        payload=_json.dumps({"event_id": "evt_old_2", "event_kind": "alert.opened",
                              "property_id": "prop_x"}),
    ))

    pubsub = _FinitePubSub([])
    chunks = await _collect(pubsub, last_event_id="evt_old_1", buffer=buf)
    # Should replay evt_old_2 (the event after evt_old_1)
    assert any("evt_old_2" in c for c in chunks)
    assert not any("evt_old_1" in c for c in chunks)


# ── sse_event_stream — integration with real Redis ───────────────────────────

async def test_event_stream_live_redis_delivery(redis_client):
    """Publish a real Redis message and verify it arrives through sse_event_stream."""
    event_id = "evt_live_integ_001"
    channel = "hosp:prop:prop_live_integ"
    payload_str = json.dumps({
        "event_id": event_id,
        "event_kind": "alert.opened",
        "property_id": "prop_live_integ",
    })

    pubsub = redis_client.pubsub()
    buf = SseReplayBuffer()
    received: list[str] = []
    found = asyncio.Event()

    async def is_disconnected():
        return found.is_set()

    async def consume():
        async for chunk in sse_event_stream(
            pubsub, None, None, None, None, is_disconnected, buf
        ):
            received.append(chunk)
            if event_id in chunk:
                found.set()

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.3)  # let psubscribe complete

    await redis_client.publish(channel, payload_str)

    await asyncio.wait_for(found.wait(), timeout=5.0)
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass

    assert found.is_set()
    assert any(event_id in c for c in received)


async def test_event_stream_live_property_filter(redis_client):
    """Only events matching the property_id filter arrive from real Redis."""
    wanted_id = "evt_live_filter_002"
    other_id = "evt_live_other_002"
    received: list[str] = []
    found = asyncio.Event()

    pubsub = redis_client.pubsub()
    buf = SseReplayBuffer()

    async def is_disconnected():
        return found.is_set()

    async def consume():
        async for chunk in sse_event_stream(
            pubsub, ["prop_wanted_x"], None, None, None, is_disconnected, buf
        ):
            received.append(chunk)
            if wanted_id in chunk:
                found.set()

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.3)

    await redis_client.publish("hosp:prop:prop_other_x", json.dumps({
        "event_id": other_id, "event_kind": "alert.opened",
        "property_id": "prop_other_x",
    }))
    await redis_client.publish("hosp:prop:prop_wanted_x", json.dumps({
        "event_id": wanted_id, "event_kind": "alert.opened",
        "property_id": "prop_wanted_x",
    }))

    await asyncio.wait_for(found.wait(), timeout=5.0)
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass

    assert found.is_set()
    assert not any(other_id in c for c in received), "Other-property event leaked"
    assert any(wanted_id in c for c in received)
