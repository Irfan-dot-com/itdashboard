import asyncio
import json
import logging

import redis.asyncio as aioredis

from app.database import Database

logger = logging.getLogger(__name__)

POLL_INTERVAL = 0.1   # 100 ms


async def run_outbox_poller(db: Database, redis: aioredis.Redis) -> None:
    logger.info("outbox poller started")
    while True:
        try:
            await _poll_once(db, redis)
        except Exception:
            logger.exception("outbox poller error — will retry")
        await asyncio.sleep(POLL_INTERVAL)


async def _poll_once(db: Database, redis: aioredis.Redis) -> None:
    async with db.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch("""
                SELECT outbox_id, event_id, property_id, event_kind, payload_json
                  FROM event_outbox
                 WHERE published_at IS NULL
                 ORDER BY enqueued_at
                 LIMIT 50
                   FOR UPDATE SKIP LOCKED
            """)
            if not rows:
                return
            for row in rows:
                channel = f"hosp:prop:{row['property_id']}"
                message = json.dumps({
                    "event_kind": row["event_kind"],
                    **row["payload_json"],
                })
                await redis.publish(channel, message)
                await conn.execute(
                    """
                    UPDATE event_outbox
                       SET published_at = NOW(), attempts = attempts + 1
                     WHERE outbox_id = $1
                    """,
                    row["outbox_id"],
                )
