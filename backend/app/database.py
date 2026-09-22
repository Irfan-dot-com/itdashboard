from contextlib import asynccontextmanager
import json

import asyncpg
from fastapi import Request


async def _init_conn(conn: asyncpg.Connection) -> None:
    """Register JSON/JSONB codecs so Python dicts pass through transparently."""
    for typename in ("json", "jsonb"):
        await conn.set_type_codec(
            typename,
            encoder=json.dumps,
            decoder=json.loads,
            schema="pg_catalog",
        )


class Database:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    @property
    def pool(self) -> asyncpg.Pool:
        return self._pool

    async def fetch(self, query: str, *args) -> list[asyncpg.Record]:
        async with self._pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args) -> asyncpg.Record | None:
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args):
        async with self._pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def execute(self, query: str, *args) -> str:
        async with self._pool.acquire() as conn:
            return await conn.execute(query, *args)

    @asynccontextmanager
    async def acquire(self):
        """Yield a raw connection for explicit transaction management."""
        async with self._pool.acquire() as conn:
            yield conn


async def get_db(request: Request) -> Database:
    return request.app.state.db
