from datetime import datetime
from typing import Any

from pydantic import BaseModel


class OpenAlerts(BaseModel):
    p1: int = 0
    p2: int = 0
    p3: int = 0
    p4: int = 0


# ── Alert list ────────────────────────────────────────────────────────────────

class AlertListItem(BaseModel):
    alert_id: str
    provider_id: str
    property_id: str
    property_name: str | None
    device_id: str | None
    device_class: str | None
    severity: str
    state: str
    alert_kind: str
    summary: str | None
    opened_at: datetime
    triaged_at: datetime | None
    acted_at: datetime | None
    resolved_at: datetime | None
    auto_fix_authorized: bool
    impact_summary: str | None
    recommended_action: None = None   # Phase 2

    model_config = {"from_attributes": True}


class AlertListResponse(BaseModel):
    items: list[AlertListItem]
    next_cursor: str | None
    has_more: bool


# ── Alert detail (GET /v1/alerts/{id}) ───────────────────────────────────────

class AlertIdentity(BaseModel):
    severity: str
    state: str
    opened_at: str
    triaged_at: str | None = None
    acted_at: str | None = None
    resolved_at: str | None = None
    property_id: str
    property_name: str | None = None
    device_id: str | None = None
    device_label: str | None = None
    alert_kind: str
    correlation_id: str | None = None
    on_call_user: str | None = None


class CausalChainTier(BaseModel):
    tier: str                              # element | signal | kpi | consequence
    title: str
    description: str
    evidence_event_ids: list[str] = []
    metadata: dict[str, Any] = {}
    stubbed_until: str | None = None       # "phase_2_business_projections" or None


class AlertSignal(BaseModel):
    metric: str
    current_value: str
    baseline_value: str
    threshold_breached: str
    series: list[dict[str, Any]] = []
    unit: str


class AlertDetail(BaseModel):
    alert_id: str
    schema_version: str = "1.0"
    identity: AlertIdentity
    signal: AlertSignal | None = None
    causal_chain: list[CausalChainTier] = []
    agent_reasoning: dict[str, Any] = {}
    recommended_action: None = None        # Phase 2
    runbook_history: list = []
    related_tickets: list = []

    model_config = {"from_attributes": True}


# ── Auto-fix ──────────────────────────────────────────────────────────────────

class AutoFixRequest(BaseModel):
    confirm: bool
    actor_note: str | None = None


class AutoFixResponse(BaseModel):
    alert_id: str
    action_event_id: str
    dispatched_at: datetime
    expected_recovery_by: datetime
    status_url: str
