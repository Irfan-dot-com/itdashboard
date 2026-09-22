from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from app.database import Database, get_db
from app.lib.health import property_health_score
from app.middleware.auth import get_provider_id
from app.repositories.alerts import AlertsRepository
from app.repositories.devices import DevicesRepository
from app.repositories.properties import PropertiesRepository
from app.schemas.alerts import OpenAlerts
from app.schemas.estate import EdgeBoxSummary, EstateResponse, KpiStrip, PropertySummary

router = APIRouter()


@router.get("/v1/estate", response_model=EstateResponse)
async def get_estate(
    provider_id: str = Depends(get_provider_id),
    db: Database = Depends(get_db),
    sort: str = Query("worst_first", pattern="^(worst_first|name_asc)$"),
):
    async with db.acquire() as conn:
        props_repo = PropertiesRepository(conn)
        dev_repo = DevicesRepository(conn)
        alert_repo = AlertsRepository(conn)

        properties = await props_repo.list(provider_id)
        all_sev = {"p1": 0, "p2": 0, "p3": 0, "p4": 0}
        sites_online = 0
        tiles = []
        now = datetime.now(timezone.utc)

        for prop in properties:
            devices = await dev_repo.list_for_property(provider_id, prop["property_id"])
            score, status = property_health_score([dict(d) for d in devices])
            sev_counts = await alert_repo.count_by_severity(provider_id, prop["property_id"])
            for k, v in sev_counts.items():
                all_sev[k] += v

            worst = await alert_repo.worst_open(provider_id, prop["property_id"])
            edge_box = await props_repo.get_edge_box_for_property(provider_id, prop["property_id"])

            edge_box_obj = None
            online = False
            if edge_box:
                interval = edge_box["summary_interval_seconds"] or 60
                if edge_box["last_heartbeat_at"]:
                    hb = edge_box["last_heartbeat_at"]
                    if hb.tzinfo is None:
                        hb = hb.replace(tzinfo=timezone.utc)
                    age = (now - hb).total_seconds()
                    online = age <= interval * 2
                edge_box_obj = EdgeBoxSummary(
                    edge_id=edge_box["edge_id"],
                    online=online,
                    last_heartbeat_at=edge_box["last_heartbeat_at"],
                    tracked_devices=edge_box["tracked_devices"],
                    unhealthy_devices=edge_box["unhealthy_devices"],
                    queue_depth=edge_box["queue_depth"],
                    summary_interval_seconds=edge_box["summary_interval_seconds"],
                )
            if online:
                sites_online += 1

            tiles.append(PropertySummary(
                provider_id=provider_id,
                property_id=prop["property_id"],
                name=prop["name"],
                site_code=prop["site_code"],
                address=prop["address"],
                health_score=score,
                health_status=status,
                open_alerts=OpenAlerts(**sev_counts),
                worst_alert_summary=worst["summary"] if worst else None,
                edge_box=edge_box_obj,
            ))

    if sort == "worst_first":
        tiles.sort(key=lambda t: (t.open_alerts.p1 == 0, t.health_score))
    else:
        tiles.sort(key=lambda t: t.name)

    avg_score = int(sum(t.health_score for t in tiles) / len(tiles)) if tiles else 0
    return EstateResponse(
        kpi_strip=KpiStrip(
            estate_health_score=avg_score,
            sites_online=sites_online,
            sites_total=len(tiles),
            open_alerts=OpenAlerts(**all_sev),
        ),
        properties=tiles,
    )
