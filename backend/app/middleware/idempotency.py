import json

import redis.asyncio as aioredis


async def get_cached_response(key: str, redis: aioredis.Redis) -> dict | None:
    raw = await redis.get(f"idem:{key}")
    return json.loads(raw) if raw else None


async def cache_response(
    key: str,
    provider_id: str,
    response: dict,
    redis: aioredis.Redis,
    ttl: int = 86_400,
) -> None:
    await redis.setex(f"idem:{key}", ttl, json.dumps(response))
