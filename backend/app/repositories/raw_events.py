import asyncpg
import uuid


class RawEventsRepository:
    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    async def insert(
        self,
        kind: str,
        provider_id: str,
        property_id: str,
        payload: dict,
        edge_id: str | None = None,
        device_id: str | None = None,
    ) -> str:
        event_id = f"evt_{uuid.uuid4().hex}"
        await self.conn.execute(
            """
            INSERT INTO raw_events
                (event_id, edge_id, device_id, provider_id, property_id, kind, payload_json)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            event_id, edge_id, device_id, provider_id, property_id, kind, payload,
        )
        return event_id

    async def recent_for_property(
        self, provider_id: str, property_id: str, limit: int = 20
    ) -> list[asyncpg.Record]:
        return await self.conn.fetch(
            """
            SELECT * FROM raw_events
             WHERE provider_id = $1 AND property_id = $2
             ORDER BY received_at DESC
             LIMIT $3
            """,
            provider_id, property_id, limit,
        )
