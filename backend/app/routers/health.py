from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.database import Database, get_db
from app.redis_client import get_redis

router = APIRouter(tags=["health"])


@router.get("/livez")
async def livez():
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(db: Database = Depends(get_db), redis=Depends(get_redis)):
    db_ok = False
    redis_ok = False
    try:
        await db.fetchval("SELECT 1")
        db_ok = True
    except Exception:
        pass
    try:
        await redis.ping()
        redis_ok = True
    except Exception:
        pass

    if not (db_ok and redis_ok):
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "db": db_ok, "redis": redis_ok},
        )
    return {"status": "ok", "db": True, "redis": True}


@router.get("/healthz")
async def healthz():
    return {"status": "ok"}
