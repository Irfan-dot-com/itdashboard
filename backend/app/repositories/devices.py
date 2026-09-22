import asyncpg
from datetime import datetime


class DevicesRepository:
    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    async def upsert(
        self,
        device_id: str,
        provider_id: str,
        property_id: str,
        edge_id: str | None = None,
        label: str | None = None,
        device_class: str | None = None,
        vendor: str | None = None,
        site: str | None = None,
    ) -> None:
        # COALESCE keeps existing non-null value if incoming field is None
        await self.conn.execute(
            """
            INSERT INTO devices
                (device_id, provider_id, property_id, edge_id, label, device_class, vendor, site)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (device_id) DO UPDATE SET
                edge_id      = COALESCE(EXCLUDED.edge_id,      devices.edge_id),
                label        = COALESCE(EXCLUDED.label,        devices.label),
                device_class = COALESCE(EXCLUDED.device_class, devices.device_class),
                vendor       = COALESCE(EXCLUDED.vendor,       devices.vendor),
                site         = COALESCE(EXCLUDED.site,         devices.site)
            """,
            device_id, provider_id, property_id, edge_id, label, device_class, vendor, site,
        )

    async def update_health(
        self,
        device_id: str,
        health_status: str,
        health_score: int,
        last_seen_at: datetime,
    ) -> str | None:
        """Update health fields. Returns prior health_status if it changed, else None."""
        prior = await self.conn.fetchval(
            "SELECT health_status FROM devices WHERE device_id = $1",
            device_id,
        )
        await self.conn.execute(
            """
            UPDATE devices
               SET health_status = $2, health_score = $3, last_seen_at = $4
             WHERE device_id = $1
            """,
            device_id, health_status, health_score, last_seen_at,
        )
        return prior if prior != health_status else None

    async def list_for_property(
        self, provider_id: str, property_id: str
    ) -> list[asyncpg.Record]:
        return await self.conn.fetch(
            """
            SELECT * FROM devices
            WHERE provider_id = $1 AND property_id = $2
            ORDER BY label NULLS LAST
            """,
            provider_id, property_id,
        )

    async def get(self, device_id: str) -> asyncpg.Record | None:
        return await self.conn.fetchrow(
            "SELECT * FROM devices WHERE device_id = $1",
            device_id,
        )
