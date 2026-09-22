from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from app.database import Database, get_db
from app.lib.cursor import decode_cursor, encode_cursor
from app.lib.errors import AppError
from app.lib.health import property_health_score
from app.middleware.auth import get_provider_id
from app.repositories.alerts import AlertsRepository
from app.repositories.devices import DevicesRepository
from app.repositories.properties import PropertiesRepository
from app.schemas.alerts import OpenAlerts
from app.schemas.estate import EdgeBoxSummary
from app.schemas.properties import DeviceSummary, PropertyDetailResponse, RecentEvent

router = APIRouter()


def _event_summary(kind: str, payload: dict) -> str:
    if kind == "edge_health":
        return f"edge heartbeat (queue_depth={payload.get('metrics', {}).get('queue_depth', 0)})"
    if kind == "transition":
        return f"{payload.get('device_id')} → {payload.get('health', {}).get('status', '?')}"
    return f"{kind} on {payload.get('device_id', '?')}"


@router.get("/v1/properties/{property_id}", response_model=PropertyDetailResponse)
async def get_property(
    property_id: str,
    provider_id: str = Depends(get_provider_id),
    db: Database = Depends(get_db),
):
    async with db.acquire() as conn:
        props_repo = PropertiesRepository(conn)
        dev_repo = DevicesRepository(conn)
        alert_repo = AlertsRepository(conn)

        prop = await props_repo.get(provider_id, property_id)
        if not prop:
            raise AppError("NOT_FOUND", f"No property {property_id!r} visible to this provider", 404)

        devices = await dev_repo.list_for_property(provider_id, property_id)
        score, status = property_health_score([dict(d) for d in devices])
        sev_counts = await alert_repo.count_by_severity(provider_id, property_id)

        now = datetime.now(timezone.utc)
        edge_box_rows = await props_repo.list_edge_boxes_for_property(provider_id, property_id)
        edge_box_objs = []
        for eb in edge_box_rows:
            interval = eb["summary_interval_seconds"] or 60
            hb = eb["last_heartbeat_at"]
            online = False
            if hb:
                if hb.tzinfo is None:
                    hb = hb.replace(tzinfo=timezone.utc)
                online = (now - hb).total_seconds() <= interval * 2
            edge_box_objs.append(EdgeBoxSummary(
                edge_id=eb["edge_id"],
                online=online,
                last_heartbeat_at=eb["last_heartbeat_at"],
                tracked_devices=eb["tracked_devices"],
                unhealthy_devices=eb["unhealthy_devices"],
                queue_depth=eb["queue_depth"],
                summary_interval_seconds=eb["summary_interval_seconds"],
            ))

        empty_alerts = OpenAlerts(p1=0, p2=0, p3=0, p4=0)
        prop_alerts = OpenAlerts(**sev_counts)
        device_objs = [
            DeviceSummary(
                device_id=d["device_id"],
                label=d["label"],
                device_class=d["device_class"],
                vendor=d["vendor"],
                site=d["site"],
                health_status=d["health_status"],
                health_score=d["health_score"],
                last_seen_at=d["last_seen_at"],
                open_alerts=prop_alerts if d["health_status"] != "healthy" else empty_alerts,
            )
            for d in devices
        ]

        raw_rows = await conn.fetch(
            """
            SELECT event_id, kind, received_at, payload_json
              FROM raw_events
             WHERE provider_id = $1 AND property_id = $2
             ORDER BY received_at DESC
             LIMIT 20
            """,
            provider_id, property_id,
        )
        recent_events = [
            RecentEvent(
                event_id=r["event_id"],
                kind=r["kind"],
                received_at=r["received_at"],
                summary=_event_summary(r["kind"], r["payload_json"]),
            )
            for r in raw_rows
        ]

    return PropertyDetailResponse(
        provider_id=provider_id,
        property_id=prop["property_id"],
        name=prop["name"],
        site_code=prop["site_code"],
        address=prop["address"],
        health_score=score,
        health_status=status,
        open_alerts=prop_alerts,
        edge_boxes=edge_box_objs,
        devices=device_objs,
        integration_health=[],
        recent_events=recent_events,
    )


_VALID_STATES = {"opened", "triaged", "acting", "resolved"}


@router.get("/v1/properties/{property_id}/alerts")
async def list_property_alerts(
    property_id: str,
    provider_id: str = Depends(get_provider_id),
    db: Database = Depends(get_db),
    status: str = Query("opened,triaged,acting", description="Comma-separated alert states"),
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(None),
):
    """Return full alert details for a property, ordered by severity then recency.

    Each item in `items[]` has the same shape as GET /v1/alerts/{alert_id}.
    Use `next_cursor` + `has_more` for pagination.
    """
    states = [s.strip() for s in status.split(",")]
    if bad := set(states) - _VALID_STATES:
        raise AppError("VALIDATION_FAILED", f"Invalid status values: {bad}", 400)

    async with db.acquire() as conn:
        props_repo = PropertiesRepository(conn)
        prop = await props_repo.get(provider_id, property_id)
        if not prop:
            raise AppError("NOT_FOUND", f"No property {property_id!r} visible to this provider", 404)

        result = await AlertsRepository(conn).list_by_property(
            provider_id, property_id, states=states, limit=limit, cursor=cursor
        )

    items = []
    for row in result["items"]:
        detail = dict(row["detail_json"])
        detail["alert_id"] = row["alert_id"]
        detail["identity"]["state"] = row["state"]
        detail["identity"]["edge_id"] = row["edge_id"]
        if row["triaged_at"]:
            detail["identity"]["triaged_at"] = row["triaged_at"].isoformat()
        if row["acted_at"]:
            detail["identity"]["acted_at"] = row["acted_at"].isoformat()
        if row["resolved_at"]:
            detail["identity"]["resolved_at"] = row["resolved_at"].isoformat()
        items.append(detail)

    return {
        "property_id": property_id,
        "items": items,
        "next_cursor": result["next_cursor"],
        "has_more": result["has_more"],
        "total_returned": len(items),
    }
