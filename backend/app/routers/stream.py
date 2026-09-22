import json
import time
from collections.abc import AsyncGenerator
from typing import Callable

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse

from app.lib.sse_buffer import BufferedEvent, SseReplayBuffer
from app.middleware.auth import get_provider_id
from app.redis_client import get_redis

router = APIRouter()
_buffer = SseReplayBuffer()   # one buffer per worker process

_SEV_ORDER = ["p1", "p2", "p3", "p4"]


def _passes_filter(
    data: dict,
    requested_pids: list[str] | None,
    kind_filter: set[str] | None,
    min_severity: str | None,
) -> bool:
    if requested_pids and data.get("property_id") not in requested_pids:
        return False
    if kind_filter and data.get("event_kind") not in kind_filter:
        return False
    if min_severity and data.get("severity"):
        try:
            if _SEV_ORDER.index(data["severity"]) > _SEV_ORDER.index(min_severity):
                return False
        except ValueError:
            pass
    return True


async def sse_event_stream(
    pubsub,
    requested_pids: list[str] | None,
    kind_filter: set[str] | None,
    min_severity: str | None,
    last_event_id: str | None,
    is_disconnected: Callable,
    buffer: SseReplayBuffer,
) -> AsyncGenerator[str, None]:
    """Async generator that yields SSE text frames.

    Extracted from the route handler so it can be unit-tested with mock
    pubsub objects without needing a running HTTP server.
    """
    if requested_pids:
        await pubsub.subscribe(*[f"hosp:prop:{pid}" for pid in requested_pids])
    else:
        await pubsub.psubscribe("hosp:prop:*")

    # Replay events the client may have missed during reconnect
    if last_event_id:
        for ev in buffer.events_since(last_event_id):
            data = json.loads(ev.payload)
            if _passes_filter(data, requested_pids, kind_filter, min_severity):
                yield f"id: {ev.event_id}\nevent: {ev.event_kind}\ndata: {ev.payload}\n\n"

    yield ": connected\n\n"

    consecutive_idle = 0
    try:
        while not await is_disconnected():
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0
            )
            if message is None:
                consecutive_idle += 1
                if consecutive_idle >= 15:
                    yield ": keepalive\n\n"
                    consecutive_idle = 0
                continue
            if message["type"] not in ("message", "pmessage"):
                continue
            raw = message["data"]
            try:
                data = json.loads(raw)
            except Exception:
                continue
            if not _passes_filter(data, requested_pids, kind_filter, min_severity):
                continue
            event_id = data.get("event_id", f"evt_{int(time.time() * 1000)}")
            event_kind = data.get("event_kind", "message")
            buffer.add(BufferedEvent(
                event_id=event_id,
                event_kind=event_kind,
                property_id=data.get("property_id", ""),
                payload=raw,
            ))
            yield f"id: {event_id}\nevent: {event_kind}\ndata: {raw}\n\n"
            consecutive_idle = 0
    finally:
        await pubsub.unsubscribe()
        await pubsub.aclose()


@router.get("/v1/stream")
async def stream(
    request: Request,
    provider_id: str = Depends(get_provider_id),
    redis=Depends(get_redis),
    property_id: str | None = Query(None),
    kinds: str | None = Query(None),
    min_severity: str | None = Query(None),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    requested_pids = property_id.split(",") if property_id else None
    kind_filter = set(kinds.split(",")) if kinds else None

    async def generator():
        pubsub = redis.pubsub()
        async for chunk in sse_event_stream(
            pubsub, requested_pids, kind_filter, min_severity,
            last_event_id, request.is_disconnected, _buffer,
        ):
            yield chunk

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
