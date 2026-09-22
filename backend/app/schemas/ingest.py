from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class EdgeHealthMetrics(BaseModel):
    tracked_devices: int = 0
    unhealthy_devices: int = 0
    queue_depth: int = 0
    summary_interval_seconds: int = 60


class DeviceHealth(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy", "unknown"]
    score: int = Field(ge=0, le=100)
    reasons: list[str] = []


class DeviceMetrics(BaseModel):
    event_count: int = 0
    error_count: int = 0
    warn_count: int = 0


class TopEvent(BaseModel):
    ts: float
    severity: str   # normalized by ingestor: warning→warn, error→err, information→info
    category: str
    message: str


class EdgeHealthMessage(BaseModel):
    kind: Literal["edge_health"]
    ts: float
    metrics: EdgeHealthMetrics


class PeriodicMessage(BaseModel):
    kind: Literal["periodic"]
    ts: float
    device_id: str
    device_name: str | None = None
    device_class: str | None = None
    vendor: str | None = None
    site: str | None = None
    health: DeviceHealth
    metrics: DeviceMetrics = DeviceMetrics()


class TransitionMessage(BaseModel):
    kind: Literal["transition"]
    ts: float
    device_id: str
    device_name: str | None = None
    device_class: str | None = None
    vendor: str | None = None
    site: str | None = None
    health: DeviceHealth
    metrics: DeviceMetrics = DeviceMetrics()
    top_events: list[TopEvent] = []


AnyMessage = Annotated[
    Union[EdgeHealthMessage, PeriodicMessage, TransitionMessage],
    Field(discriminator="kind"),
]


class IngestRequest(BaseModel):
    schema_version: str = "1.0"
    edge_id: str
    service_provider: str
    property_id: str
    property_name: str | None = None
    messages: list[AnyMessage] = Field(min_length=1, max_length=100)


class RejectedMessage(BaseModel):
    index: int
    kind: str
    device_id: str | None = None
    reason: str


class IngestResponse(BaseModel):
    edge_id: str
    accepted: int
    rejected: list[RejectedMessage] = []
