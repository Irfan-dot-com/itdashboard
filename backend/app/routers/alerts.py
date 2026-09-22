import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, Query

from app.database import Database, get_db
from app.lib.errors import AppError
from app.middleware.auth import get_provider_id
from app.middleware.idempotency import cache_response, get_cached_response
from app.redis_client import get_redis
from app.repositories.alerts import AlertsRepository
from app.schemas.alerts import (
    AlertListItem,
    AlertListResponse,
    AutoFixRequest,
    AutoFixResponse,
)

router = APIRouter()

_VALID_STATES = {"opened", "triaged", "acting", "resolved"}


@router.get("/v1/alerts", response_model=AlertListResponse)
async def list_alerts(
    provider_id: str = Depends(get_provider_id),
    db: Database = Depends(get_db),
    status: str = Query("opened,triaged,acting"),
    severity: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(None),
):
    states = [s.strip() for s in status.split(",")]
    if bad := set(states) - _VALID_STATES:
        raise AppError("VALIDATION_FAILED", f"Invalid status values: {bad}", 400)

    async with db.acquire() as conn:
        result = await AlertsRepository(conn).list(
            provider_id, states=states, limit=limit, cursor=cursor
        )

    items = [
        AlertListItem(**row, impact_summary="Impact assessment pending")
        for row in result["items"]
    ]
    return AlertListResponse(
        items=items,
        next_cursor=result["next_cursor"],
        has_more=result["has_more"],
    )


@router.get("/v1/alerts/{alert_id}")
async def get_alert(
    alert_id: str,
    provider_id: str = Depends(get_provider_id),
    db: Database = Depends(get_db),
):
    async with db.acquire() as conn:
        row = await AlertsRepository(conn).get(alert_id, provider_id)
    if not row:
        raise AppError("NOT_FOUND", f"No alert with id {alert_id} visible to this provider", 404)

    detail = dict(row["detail_json"])   # JSONB codec already decoded to dict
    detail["alert_id"] = row["alert_id"]

    # Refresh live state fields — they may have changed since materialization
    detail["identity"]["state"] = row["state"]
    detail["identity"]["edge_id"] = row["edge_id"]
    if row["triaged_at"]:
        detail["identity"]["triaged_at"] = row["triaged_at"].isoformat()
    if row["acted_at"]:
        detail["identity"]["acted_at"] = row["acted_at"].isoformat()
    if row["resolved_at"]:
        detail["identity"]["resolved_at"] = row["resolved_at"].isoformat()

    return detail


@router.post("/v1/alerts/{alert_id}/auto-fix", status_code=202,
             response_model=AutoFixResponse)
async def auto_fix(
    alert_id: str,
    body: AutoFixRequest,
    provider_id: str = Depends(get_provider_id),
    db: Database = Depends(get_db),
    redis=Depends(get_redis),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if not idempotency_key:
        raise AppError("VALIDATION_FAILED", "Idempotency-Key header is required", 400)
    if not body.confirm:
        raise AppError("VALIDATION_FAILED", "confirm must be true", 400)

    cached = await get_cached_response(idempotency_key, redis)
    if cached:
        return cached

    async with db.acquire() as conn:
        repo = AlertsRepository(conn)
        row = await repo.get(alert_id, provider_id)
        if not row:
            raise AppError("NOT_FOUND", f"No alert with id {alert_id} visible to this provider", 404)
        if row["state"] == "resolved":
            raise AppError("CONFLICT", f"Alert {alert_id} is already resolved", 409)
        if not row["auto_fix_authorized"]:
            raise AppError(
                "VALIDATION_FAILED",
                "Auto-fix has not been pre-authorized by the agent for this alert",
                422,
            )

        now = datetime.now(timezone.utc)
        await repo.update_state(alert_id, "acting", now)
        action_event_id = f"evt_{uuid.uuid4().hex}"

        await conn.execute(
            """
            INSERT INTO event_outbox (event_id, property_id, event_kind, payload_json)
            VALUES ($1, $2, $3, $4)
            """,
            action_event_id, row["property_id"], "auto_fix.dispatched",
            {"alert_id": alert_id, "action_event_id": action_event_id},
        )

    response = AutoFixResponse(
        alert_id=alert_id,
        action_event_id=action_event_id,
        dispatched_at=now,
        expected_recovery_by=now + timedelta(seconds=90),
        status_url=f"/v1/alerts/{alert_id}",
    )
    response_dict = response.model_dump(mode="json")
    await cache_response(idempotency_key, provider_id, response_dict, redis)
    return response
