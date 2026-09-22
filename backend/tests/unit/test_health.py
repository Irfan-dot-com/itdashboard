import pytest
from app.lib.health import property_health_score, severity_for_transition, materialize_alert_from_transition


# ── property_health_score ─────────────────────────────────────────────────────

def test_empty_devices():
    assert property_health_score([]) == (0, "unknown")


def test_single_healthy_device():
    devices = [{"health_status": "healthy", "health_score": 92}]
    score, status = property_health_score(devices)
    assert status == "healthy"
    assert score == 92


def test_single_unhealthy_device():
    # score=28 is below ceiling=40, so stored raw value wins
    devices = [{"health_status": "unhealthy", "health_score": 28}]
    score, status = property_health_score(devices)
    assert status == "unhealthy"
    assert score == 28


def test_unhealthy_caps_avg():
    # avg(28, 88) = 58 but ceiling=40 because one device is unhealthy
    devices = [
        {"health_status": "unhealthy", "health_score": 28},
        {"health_status": "healthy",   "health_score": 88},
    ]
    score, status = property_health_score(devices)
    assert status == "unhealthy"
    assert score == 40   # min(58, 40)


def test_score_above_ceiling_clamped():
    # score=48 stored raw; at read time min(48, ceiling=40) = 40
    devices = [{"health_status": "unhealthy", "health_score": 48}]
    score, status = property_health_score(devices)
    assert status == "unhealthy"
    assert score == 40


def test_degraded_status():
    devices = [{"health_status": "degraded", "health_score": 65}]
    score, status = property_health_score(devices)
    assert status == "degraded"
    assert score == 65   # 65 < ceiling 70


def test_degraded_caps_high_score():
    devices = [{"health_status": "degraded", "health_score": 85}]
    score, status = property_health_score(devices)
    assert status == "degraded"
    assert score == 70   # min(85, 70)


def test_mixed_healthy_unknown_is_degraded():
    devices = [
        {"health_status": "healthy", "health_score": 95},
        {"health_status": "unknown", "health_score": None},
    ]
    score, status = property_health_score(devices)
    assert status == "degraded"


def test_all_healthy():
    devices = [
        {"health_status": "healthy", "health_score": 90},
        {"health_status": "healthy", "health_score": 80},
    ]
    score, status = property_health_score(devices)
    assert status == "healthy"
    assert score == 85   # avg(90,80)=85, ceiling=100 → 85


def test_no_scores_uses_floor():
    # All scores are None — fall back to status ceiling
    devices = [{"health_status": "degraded", "health_score": None}]
    score, status = property_health_score(devices)
    assert status == "degraded"
    assert score == 70   # STATUS_TO_SCORE_FLOOR["degraded"]


def test_unhealthy_takes_precedence_over_degraded():
    devices = [
        {"health_status": "degraded",  "health_score": 65},
        {"health_status": "unhealthy", "health_score": 30},
    ]
    score, status = property_health_score(devices)
    assert status == "unhealthy"
    assert score == 40   # min(avg(65,30)=47, ceiling=40)


# ── severity_for_transition ───────────────────────────────────────────────────

def test_severity_unhealthy():
    assert severity_for_transition("unhealthy") == "p1"

def test_severity_degraded():
    assert severity_for_transition("degraded") == "p2"

def test_severity_unknown():
    assert severity_for_transition("unknown") == "p3"

def test_severity_healthy():
    assert severity_for_transition("healthy") == "p4"

def test_severity_unknown_input():
    assert severity_for_transition("bogus") == "p3"


# ── materialize_alert_from_transition ─────────────────────────────────────────

@pytest.fixture
def transition_inputs():
    return dict(
        edge_summary={
            "health": {"status": "unhealthy", "score": 22, "reasons": ["no_registrations"]},
            "metrics": {"event_count": 40, "error_count": 15, "warn_count": 5,
                        "categories": {"registration": 12, "network": 3}},
            "top_events": [
                {"ts": 1746720001.0, "severity": "err", "category": "registration",
                 "message": "base lost 8 handsets"},
            ],
            "window_seconds": 300,
        },
        device_row={
            "device_id": "dev-002",
            "device_class": "dect_base",
            "label": "Reception DECT",
        },
        property_row={"property_id": "prop_cottons", "name": "Cottons Hotel"},
        opened_at=1746720000.0,
    )


def test_materialize_severity(transition_inputs):
    detail = materialize_alert_from_transition(**transition_inputs)
    assert detail["identity"]["severity"] == "p1"


def test_materialize_state_is_opened(transition_inputs):
    detail = materialize_alert_from_transition(**transition_inputs)
    assert detail["identity"]["state"] == "opened"


def test_materialize_causal_chain_length(transition_inputs):
    detail = materialize_alert_from_transition(**transition_inputs)
    # tier1 (element) + tier2 (signal — categories present) + kpi + consequence = 4
    assert len(detail["causal_chain"]) == 4


def test_materialize_tier1_element(transition_inputs):
    detail = materialize_alert_from_transition(**transition_inputs)
    t1 = detail["causal_chain"][0]
    assert t1["tier"] == "element"
    assert t1["stubbed_until"] is None
    assert "no_registrations" in t1["metadata"]["reasons"]


def test_materialize_tier2_signal(transition_inputs):
    detail = materialize_alert_from_transition(**transition_inputs)
    t2 = detail["causal_chain"][1]
    assert t2["tier"] == "signal"
    assert t2["metadata"]["category"] == "registration"   # highest count


def test_materialize_tiers_3_4_stubbed(transition_inputs):
    detail = materialize_alert_from_transition(**transition_inputs)
    for tier in detail["causal_chain"][2:]:
        assert tier["stubbed_until"] == "phase_2_business_projections"


def test_materialize_no_categories_omits_tier2():
    detail = materialize_alert_from_transition(
        edge_summary={
            "health": {"status": "degraded", "score": 61, "reasons": ["high_latency"]},
            "metrics": {},   # no categories
            "top_events": [],
        },
        device_row={"device_id": "dev-003", "device_class": "router", "label": None},
        property_row={"property_id": "prop_1", "name": "Test Hotel"},
        opened_at=1746720000.0,
    )
    # Only tier1 + kpi + consequence = 3 tiers (no signal tier)
    assert len(detail["causal_chain"]) == 3
    assert detail["causal_chain"][0]["tier"] == "element"
    assert detail["causal_chain"][1]["tier"] == "kpi"


def test_materialize_recommended_action_is_none(transition_inputs):
    detail = materialize_alert_from_transition(**transition_inputs)
    assert detail["recommended_action"] is None
