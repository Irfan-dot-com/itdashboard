"""
Property health score aggregation and alert materialisation.

Direct port of the Python reference (Syslog scripts for IT Dashboard/health.py).
No DB access — pure functions, fully unit-testable.
"""
import uuid
from datetime import datetime, timezone


SEVERITY_FROM_HEALTH: dict[str, str] = {
    "unhealthy": "p1",
    "degraded":  "p2",
    "healthy":   "p4",
    "unknown":   "p3",
}

STATUS_TO_SCORE_FLOOR: dict[str, int] = {
    "unhealthy": 40,
    "degraded":  70,
    "healthy":   100,
    "unknown":   60,
}


def property_health_score(devices: list[dict]) -> tuple[int, str]:
    """Aggregate per-device health into a property-level (score, status) pair.

    Algorithm:
      1. Worst device status determines the property status.
      2. Average all device health_scores.
      3. Clamp the average to STATUS_TO_SCORE_FLOOR[status].
    """
    if not devices:
        return 0, "unknown"

    statuses = [d["health_status"] for d in devices if d["health_status"]]
    if not statuses:
        return 0, "unknown"

    if "unhealthy" in statuses:
        status = "unhealthy"
    elif "degraded" in statuses:
        status = "degraded"
    elif all(s == "healthy" for s in statuses):
        status = "healthy"
    else:
        status = "degraded"  # mix of healthy + unknown

    scores = [d["health_score"] for d in devices if d["health_score"] is not None]
    avg = sum(scores) / len(scores) if scores else STATUS_TO_SCORE_FLOOR[status]

    ceiling = STATUS_TO_SCORE_FLOOR[status]
    return min(int(avg), ceiling), status


def severity_for_transition(new_status: str) -> str:
    """Map a device's new health status to an alert severity code."""
    return SEVERITY_FROM_HEALTH.get(new_status, "p3")


def materialize_alert_from_transition(
    *,
    edge_summary: dict,
    device_row: dict,
    property_row: dict,
    opened_at: float,
) -> dict:
    """Build a full alert detail_json from a kind:transition edge message.

    Tier 1 (element) and Tier 2 (signal) are populated from the edge data.
    Tiers 3 (kpi) and 4 (consequence) are stubbed until Phase 2.
    """
    new_status = edge_summary["health"]["status"]
    severity = severity_for_transition(new_status)
    metrics = edge_summary.get("metrics", {})
    top_events = edge_summary.get("top_events", [])
    summary = _build_summary_text(device_row, edge_summary)

    # Tier 1 — the device element that flipped
    tier1 = {
        "tier": "element",
        "title": f"{device_row['device_class'] or 'device'} health: {new_status}",
        "description": summary,
        "evidence_event_ids": [],
        "metadata": {
            "device_id": device_row["device_id"],
            "reasons": edge_summary["health"].get("reasons", []),
            "event_count": metrics.get("event_count", 0),
            "error_count": metrics.get("error_count", 0),
            "top_events": top_events,
        },
        "stubbed_until": None,
    }
    chain = [tier1]

    # Tier 2 — dominant event category (if discernible)
    categories = metrics.get("categories", {})
    if categories:
        top_cat = max(categories.items(), key=lambda kv: kv[1])
        chain.append({
            "tier": "signal",
            "title": f"{top_cat[0]} events dominant",
            "description": (
                f"{top_cat[1]} events of category '{top_cat[0]}' "
                f"in the last {edge_summary.get('window_seconds', 300)}s."
            ),
            "evidence_event_ids": [],
            "metadata": {"category": top_cat[0], "count": top_cat[1]},
            "stubbed_until": None,
        })

    # Tiers 3 & 4 — stubbed until business projections exist
    chain.append({
        "tier": "kpi",
        "title": "Business KPI impact pending",
        "description": "Linkage to KPI projection not yet wired.",
        "evidence_event_ids": [],
        "metadata": {},
        "stubbed_until": "phase_2_business_projections",
    })
    chain.append({
        "tier": "consequence",
        "title": "Revenue impact pending",
        "description": "Cost-of-poor-quality model not yet wired.",
        "evidence_event_ids": [],
        "metadata": {},
        "stubbed_until": "phase_2_business_projections",
    })

    series = [
        {
            "t": e.get("ts"),
            "v": 1,
            "severity": e.get("severity"),
            "category": e.get("category"),
            "message": e.get("message"),
        }
        for e in sorted(top_events, key=lambda x: x.get("ts", 0))
    ]

    return {
        "schema_version": "1.0",
        "identity": {
            "severity": severity,
            "state": "opened",
            "opened_at": _iso(opened_at),
            "triaged_at": None,
            "acted_at": None,
            "resolved_at": None,
            "property_id": property_row["property_id"],
            "property_name": property_row["name"],
            "device_id": device_row["device_id"],
            "device_label": device_row.get("label") or device_row["device_id"],
            "alert_kind": f"health_transition_to_{new_status}",
            "correlation_id": f"corr_{uuid.uuid4().hex}",
            "on_call_user": None,
        },
        "signal": {
            "metric": "device_health",
            "current_value": new_status,
            "baseline_value": "healthy",
            "threshold_breached": "status_transition",
            "series": series,
            "unit": "status",
        },
        "causal_chain": chain,
        "agent_reasoning": {
            "model": "edge-rules-v1",
            "confidence": 0.7,
            "rationale": (
                f"Edge agent classified device as {new_status} based on reasons: "
                f"{', '.join(edge_summary['health'].get('reasons', [])) or 'aggregate metrics'}."
            ),
            "policy_check": {
                "policy_id": "policy_default",
                "passed": True,
                "rules_evaluated": [],
            },
            "alternatives_considered": [],
            "similar_past_incidents": [],
        },
        "recommended_action": None,
        "runbook_history": [],
        "related_tickets": [],
    }


def _build_summary_text(device_row: dict, edge_summary: dict) -> str:
    reasons = edge_summary["health"].get("reasons", [])
    label = device_row.get("label") or device_row["device_id"]
    if reasons:
        return f"{label}: {', '.join(reasons[:3])}"
    return f"{label}: status changed to {edge_summary['health']['status']}"


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")
