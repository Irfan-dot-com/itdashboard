from __future__ import annotations

import asyncpg
from datetime import datetime


class PropertiesRepository:
    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    async def upsert(
        self,
        provider_id: str,
        property_id: str,
        name: str,
        site_code: str | None = None,
        address: str | None = None,
    ) -> None:
        # Auto-create service_provider row if it doesn't exist yet
        await self.conn.execute(
            """
            INSERT INTO service_providers (provider_id, name)
            VALUES ($1, $2)
            ON CONFLICT (provider_id) DO NOTHING
            """,
            provider_id, provider_id,
        )
        await self.conn.execute(
            """
            INSERT INTO properties (provider_id, property_id, name, site_code, address)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (provider_id, property_id) DO UPDATE SET
                name      = EXCLUDED.name,
                site_code = COALESCE(EXCLUDED.site_code, properties.site_code),
                address   = COALESCE(EXCLUDED.address,   properties.address)
            """,
            provider_id, property_id, name, site_code, address,
        )

    async def get(self, provider_id: str, property_id: str) -> asyncpg.Record | None:
        return await self.conn.fetchrow(
            """
            SELECT * FROM properties
            WHERE provider_id = $1 AND property_id = $2
            """,
            provider_id, property_id,
        )

    async def list(self, provider_id: str) -> list[asyncpg.Record]:
        return await self.conn.fetch(
            "SELECT * FROM properties WHERE provider_id = $1 ORDER BY name",
            provider_id,
        )

    async def upsert_edge_box(
        self,
        edge_id: str,
        provider_id: str,
        property_id: str,
        last_heartbeat_at: datetime,
        tracked_devices: int,
        unhealthy_devices: int,
        queue_depth: int,
        summary_interval_seconds: int = 60,
    ) -> None:
        await self.conn.execute(
            """
            INSERT INTO edge_boxes
                (edge_id, provider_id, property_id, last_heartbeat_at,
                 tracked_devices, unhealthy_devices, queue_depth, summary_interval_seconds)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (edge_id) DO UPDATE SET
                last_heartbeat_at        = EXCLUDED.last_heartbeat_at,
                tracked_devices          = EXCLUDED.tracked_devices,
                unhealthy_devices        = EXCLUDED.unhealthy_devices,
                queue_depth              = EXCLUDED.queue_depth
            """,
            edge_id, provider_id, property_id, last_heartbeat_at,
            tracked_devices, unhealthy_devices, queue_depth, summary_interval_seconds,
        )

    async def get_edge_box(self, edge_id: str) -> asyncpg.Record | None:
        return await self.conn.fetchrow(
            "SELECT * FROM edge_boxes WHERE edge_id = $1",
            edge_id,
        )

    async def get_edge_box_for_property(
        self, provider_id: str, property_id: str
    ) -> asyncpg.Record | None:
        """Return the single most-recently-seen edge box — used by estate summary."""
        return await self.conn.fetchrow(
            """
            SELECT * FROM edge_boxes
            WHERE provider_id = $1 AND property_id = $2
            ORDER BY last_heartbeat_at DESC NULLS LAST
            LIMIT 1
            """,
            provider_id, property_id,
        )

    async def list_edge_boxes_for_property(
        self, provider_id: str, property_id: str
    ) -> list[asyncpg.Record]:
        """Return ALL edge boxes for a property, newest heartbeat first."""
        return await self.conn.fetch(
            """
            SELECT * FROM edge_boxes
            WHERE provider_id = $1 AND property_id = $2
            ORDER BY last_heartbeat_at DESC NULLS LAST
            """,
            provider_id, property_id,
        )
