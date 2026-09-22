from datetime import datetime

from pydantic import BaseModel

from app.schemas.alerts import OpenAlerts


class KpiStrip(BaseModel):
    estate_health_score: int
    sites_online: int
    sites_total: int
    open_alerts: OpenAlerts
    mttr_p1_minutes_30d: None = None        # Phase 2
    agent_autofix_rate_30d: None = None     # Phase 2
    wakeup_sla_30d: None = None             # Phase 2


class EdgeBoxSummary(BaseModel):
    edge_id: str
    online: bool
    last_heartbeat_at: datetime | None
    tracked_devices: int
    unhealthy_devices: int
    queue_depth: int
    summary_interval_seconds: int


class PropertySummary(BaseModel):
    provider_id: str
    property_id: str
    name: str
    site_code: str | None
    address: str | None
    health_score: int
    health_status: str
    open_alerts: OpenAlerts
    worst_alert_summary: str | None
    edge_box: EdgeBoxSummary | None


class EstateResponse(BaseModel):
    kpi_strip: KpiStrip
    properties: list[PropertySummary]
