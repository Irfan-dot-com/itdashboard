from datetime import datetime

from pydantic import BaseModel

from app.schemas.alerts import OpenAlerts
from app.schemas.estate import EdgeBoxSummary


class DeviceSummary(BaseModel):
    device_id: str
    label: str | None
    device_class: str | None
    vendor: str | None
    site: str | None
    health_status: str
    health_score: int | None
    last_seen_at: datetime | None
    open_alerts: OpenAlerts


class RecentEvent(BaseModel):
    event_id: str
    kind: str
    received_at: datetime
    summary: str


class PropertyDetailResponse(BaseModel):
    provider_id: str
    property_id: str
    name: str
    site_code: str | None
    address: str | None
    health_score: int
    health_status: str
    open_alerts: OpenAlerts
    edge_boxes: list[EdgeBoxSummary]
    devices: list[DeviceSummary]
    integration_health: list = []
    recent_events: list[RecentEvent]
