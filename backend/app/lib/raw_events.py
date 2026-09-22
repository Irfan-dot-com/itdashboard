from __future__ import annotations

import asyncpg

from app.repositories.raw_events import RawEventsRepository


async def insert_raw_event(
    conn: asyncpg.Connection,
    *,
    kind: str,
    provider_id: str,
    property_id: str,
    payload: dict,
    edge_id: str | None = None,
    device_id: str | None = None,
) -> str:
    return await RawEventsRepository(conn).insert(
        kind=kind,
        provider_id=provider_id,
        property_id=property_id,
        payload=payload,
        edge_id=edge_id,
        device_id=device_id,
    )
