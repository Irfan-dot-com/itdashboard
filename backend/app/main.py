import asyncio
from contextlib import asynccontextmanager

import asyncpg
import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import Database, _init_conn
from app.lib.errors import register_exception_handlers
from app.lib.logging_config import configure_logging, shutdown_logging
from app.lib.outbox_poller import run_outbox_poller
from app.middleware.etag import ETagMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.request_logger import RequestLoggerMiddleware

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)

    pool = await asyncpg.create_pool(
        settings.DATABASE_URL,
        min_size=settings.DB_POOL_MIN,
        max_size=settings.DB_POOL_MAX,
        init=_init_conn,
    )
    redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    app.state.db = Database(pool)
    app.state.redis = redis
    app.state.settings = settings

    poller = asyncio.create_task(run_outbox_poller(app.state.db, redis))

    logger.info("startup.complete", env=settings.ENVIRONMENT)
    yield

    poller.cancel()
    await asyncio.gather(poller, return_exceptions=True)
    await pool.close()
    await redis.aclose()
    logger.info("shutdown.complete")
    shutdown_logging()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="IT Dashboard API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url=None,
    )

    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.add_middleware(ETagMiddleware)
    # RequestLoggerMiddleware runs after RequestIDMiddleware so request_id is already set
    app.add_middleware(
        RequestLoggerMiddleware,
        detailed=settings.LOGGING_ENABLED,
        log_request_body=settings.LOG_REQUEST_BODY,
    )
    app.add_middleware(RequestIDMiddleware)

    register_exception_handlers(app)

    from app.routers import health, ingest, estate, alerts, properties, stream, exec
    app.include_router(health.router)
    app.include_router(ingest.router)
    app.include_router(estate.router)
    app.include_router(alerts.router)
    app.include_router(properties.router)
    app.include_router(stream.router)
    app.include_router(exec.router)

    return app


app = create_app()
