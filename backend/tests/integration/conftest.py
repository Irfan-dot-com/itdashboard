"""Shared fixtures for integration tests — real PostgreSQL, never mocked.

Tests connect to TEST_DATABASE_URL (hosp_test) if set, otherwise they derive
it from DATABASE_URL by replacing the DB name with hosp_test.
This keeps the dev database (hosp_dev) untouched when running tests.
"""
import pytest
import pytest_asyncio
import asyncpg
import redis.asyncio as aioredis
from app.config import get_settings
from app.database import Database, _init_conn


def _test_db_url() -> str:
    s = get_settings()
    if s.TEST_DATABASE_URL:
        return s.TEST_DATABASE_URL
    # Derive test URL by swapping the database name to hosp_test
    return s.DATABASE_URL.rsplit("/", 1)[0] + "/hosp_test"


@pytest_asyncio.fixture(scope="session")
async def pg_pool():
    url = _test_db_url()
    pool = await asyncpg.create_pool(url, min_size=1, max_size=3, init=_init_conn)
    yield pool
    await pool.close()


@pytest_asyncio.fixture(autouse=True)
async def clean_db(pg_pool, redis_client):
    """Truncate all tables and flush Redis before each test — guarantees a clean slate."""
    async with pg_pool.acquire() as conn:
        await conn.execute("""
            TRUNCATE TABLE
                idempotency_keys, alerts, event_outbox,
                raw_events, devices, edge_boxes, properties, service_providers
            RESTART IDENTITY CASCADE
        """)
    await redis_client.flushdb()
    yield


@pytest_asyncio.fixture
async def conn(pg_pool):
    """Yield a single connection for repository tests."""
    async with pg_pool.acquire() as connection:
        yield connection


@pytest_asyncio.fixture(scope="session")
async def redis_client():
    s = get_settings()
    client = aioredis.from_url(s.REDIS_URL, decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture(scope="session")
def db(pg_pool):
    """Database wrapper around the session pool."""
    return Database(pg_pool)


@pytest_asyncio.fixture(scope="session")
async def http_client(pg_pool, redis_client):
    """Minimal FastAPI app using the session pool — for HTTP-level smoke tests.

    ASGITransport does not send ASGI lifespan events, so app state is set
    directly on the app instance rather than through a lifespan handler.
    """
    from fastapi import FastAPI
    from httpx import AsyncClient, ASGITransport
    from app.lib.errors import register_exception_handlers
    from app.middleware.etag import ETagMiddleware
    from app.middleware.request_id import RequestIDMiddleware

    app = FastAPI()
    app.state.db = Database(pg_pool)
    app.state.redis = redis_client

    register_exception_handlers(app)
    app.add_middleware(ETagMiddleware)
    app.add_middleware(RequestIDMiddleware)

    from app.routers import (
        health as health_router,
        ingest as ingest_router, estate as estate_router,
        alerts as alerts_router, properties as properties_router,
        stream as stream_router, exec as exec_router,
    )
    app.include_router(health_router.router)
    app.include_router(ingest_router.router)
    app.include_router(estate_router.router)
    app.include_router(alerts_router.router)
    app.include_router(properties_router.router)
    app.include_router(stream_router.router)
    app.include_router(exec_router.router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
