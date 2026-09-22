from fastapi import APIRouter, Depends, Query

from app.middleware.auth import get_provider_id

router = APIRouter()


@router.get("/v1/exec")
async def get_exec(
    _: str = Depends(get_provider_id),
    range: str = Query("30d"),
    compare_to: str = Query("prior_period"),
):
    return {
        "range": range,
        "compare_to": compare_to,
        "tiles": {
            "estate_uptime": {"current": None, "delta_pp": None, "target": 0.995, "trend": []},
            "mttr_by_severity": {
                "p1_minutes": {"current": None, "delta": None},
                "p2_minutes": {"current": None, "delta": None},
                "p3_minutes": {"current": None, "delta": None},
            },
            "cost_of_poor_quality": {"current_gbp": None, "delta_gbp": None, "prevented_gbp": None},
            "technical_debt_index": {"score": None, "delta": None, "components": {}},
            "agent_activity": {
                "alerts_auto_resolved": 0,
                "alerts_triaged_only": 0,
                "false_positives": 0,
            },
            "top_problem_properties": [],
            "top_problem_device_classes": [],
            "_stub_note": "exec view aggregations are phase 2",
        },
    }
