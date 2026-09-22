# Understanding GET /v1/properties/{property_id}/alerts Response

This endpoint returns the **full detail of every open alert for one hotel property**.
The React dashboard calls this to build the alert list panel on the property detail page.

---

## How the backend builds this response (step by step)

```
GET /v1/properties/123/alerts
        │
        ├── 1. Check property exists (404 if not found)
        ├── 2. Query alerts table → all open alerts for this property, ordered by severity then recency
        ├── 3. For each alert row → read detail_json (stored as JSONB) + patch live state fields
        └── 4. Return paginated list
```

---

## Outer wrapper fields

```json
{
    "property_id": "123",
    "items": [ ... ],
    "next_cursor": null,
    "has_more": false,
    "total_returned": 3
}
```

| Field            | Meaning |
|------------------|---------|
| `property_id`    | The hotel this alert list belongs to. |
| `items[]`        | The actual alert objects — one per open alert. |
| `next_cursor`    | A pagination token. If not `null`, pass it as `?cursor=...` to get the next page. |
| `has_more`       | `true` means there are more alerts beyond this page. `false` here — all 3 fit on one page. |
| `total_returned` | How many alerts are in this response (3). |

**Alert ordering** (most important first):

```
ORDER BY severity rank ASC, opened_at DESC, alert_id DESC
p1 → p2 → p3 → p4, newest first within each severity
```

---

## Inside each alert item

Every item in `items[]` has the same structure. It is the `detail_json` JSONB blob
stored in the `alerts` table when the alert was created, with a few live fields patched on top.

```
alert item
├── alert_id          ← patched on top by the router
├── schema_version    ← always "1.0"
├── identity          ← who/what/when (some fields patched live)
├── signal            ← what metric triggered the alert + time series
├── causal_chain[]    ← 4-tier root cause analysis
├── agent_reasoning   ← why the AI classified it this way
├── recommended_action← what to do next (null in Phase 1)
├── runbook_history[] ← past actions taken (empty now)
└── related_tickets[] ← linked support tickets (empty now)
```

---

## Part 1 — `identity` — who/what/when

```json
"identity": {
    "state": "opened",
    "severity": "p1",
    "device_id": "dev-006",
    "device_label": "wifi_ap_lobby",
    "alert_kind": "health_transition_to_unhealthy",
    "opened_at": "2026-05-08T17:53:57Z",
    "triaged_at": null,
    "acted_at": null,
    "resolved_at": null,
    "property_id": "123",
    "property_name": "sheraton",
    "on_call_user": null,
    "correlation_id": "corr_842a8177...",
    "edge_id": "edge-box-7"
}
```

| Field            | Meaning |
|------------------|---------|
| `state`          | Current lifecycle state: `opened → triaged → acting → resolved`. Patched live from the DB row. |
| `severity`       | `p1` = critical, `p2` = high, `p3` = medium, `p4` = low. Set when the alert was created from device health status. |
| `device_id`      | Which device triggered this alert. |
| `device_label`   | Human-readable device name. |
| `alert_kind`     | What happened: `health_transition_to_unhealthy` or `health_transition_to_degraded`. |
| `opened_at`      | When the alert was first created. |
| `triaged_at`     | When IT staff acknowledged it. `null` = not yet triaged. |
| `acted_at`       | When auto-fix or manual fix was triggered. `null` = not yet. |
| `resolved_at`    | When the device recovered (healthy transition). `null` = still open. |
| `on_call_user`   | Which IT person is assigned. `null` until Phase 2. |
| `correlation_id` | A unique ID that groups related alerts together (same incident). |
| `edge_id`        | Which physical edge box detected and reported this alert. |

**Severity → health status mapping:**

| Device health status | Alert severity |
|---|---|
| `unhealthy` | `p1` (critical) |
| `degraded`  | `p2` (high) |
| `unknown`   | `p3` (medium) |
| `healthy`   | resolves the alert — no new alert created |

---

## Part 2 — `signal` — what metric triggered it

```json
"signal": {
    "metric": "device_health",
    "unit": "status",
    "current_value": "unhealthy",
    "baseline_value": "healthy",
    "threshold_breached": "status_transition",
    "series": [
        {
            "t": 1746724075.0,
            "v": 1,
            "severity": "warn",
            "category": "hardware",
            "message": "PoE port Gi0/12 power draw spike: 32W (normal: 18W)"
        },
        ...
    ]
}
```

| Field                | Meaning |
|----------------------|---------|
| `metric`             | Always `device_health` in Phase 1. What we are measuring. |
| `unit`               | Always `status`. The unit of the metric. |
| `current_value`      | What the device status is now (`unhealthy`). |
| `baseline_value`     | What it should be normally (`healthy`). |
| `threshold_breached` | Always `status_transition` — the alert fired because the status changed. |
| `series[]`           | **The timeline of events** that led up to this alert — these are the `top_events` from the original `transition` message, sorted oldest → newest. |

**`series[]` entry fields:**

| Field      | Meaning |
|------------|---------|
| `t`        | Unix timestamp of when this specific log event happened. |
| `v`        | Always `1` — presence flag (this event occurred). |
| `severity` | Normalised severity: `err`, `warn`, `info`, `crit`. |
| `category` | What type of problem: `connectivity`, `hardware`, `link`, `software`, etc. |
| `message`  | The actual raw log line from the device — exactly what the edge agent captured. |

**Reading the series like a story** (alert 2 — wifi_ap_lobby):

```
t=1746724075  warn  hardware     PoE port power draw spike: 32W (normal 18W)   ← first warning sign
t=1746724080  err   connectivity  SSID no longer broadcasting                   ← guests lose wifi
t=1746724085  err   hardware     PoE power budget exceeded — AP lost power      ← root cause
t=1746724090  err   connectivity  AP unreachable — ICMP ping timeout             ← device is dead
```

The series tells you exactly **what happened and in what order**.

---

## Part 3 — `causal_chain[]` — 4-tier root cause analysis

This is the **most important part** of an alert. It explains WHY the device failed,
broken into 4 tiers from device-level up to business impact.

```json
"causal_chain": [
    { "tier": "element",     ... },
    { "tier": "kpi",         ... },
    { "tier": "consequence", ... }
]
```

### Tier 1 — `element` (LIVE — populated from edge data)

```json
{
    "tier": "element",
    "title": "wifi_ap health: unhealthy",
    "description": "wifi_ap_lobby: device_unreachable, hardware_fault",
    "metadata": {
        "device_id": "dev-006",
        "reasons": ["device_unreachable", "hardware_fault"],
        "event_count": 20,
        "error_count": 18,
        "top_events": [ ... ]
    },
    "stubbed_until": null,
    "evidence_event_ids": []
}
```

**What it means:** The physical device that failed and why.
Built directly from the `transition` message sent by the edge agent.

| Field            | Meaning |
|------------------|---------|
| `title`          | `{device_class} health: {status}` |
| `description`    | `{device_label}: {reasons joined by comma}` |
| `reasons`        | Machine-readable codes from the edge agent explaining the failure. |
| `event_count`    | Total log events seen from this device in the last interval. |
| `error_count`    | How many were error-level. |
| `top_events`     | The most relevant log lines — same as `signal.series` but in the raw format. |
| `stubbed_until`  | `null` — this tier is LIVE, not stubbed. |

### Tier 2 — `signal` (would show dominant event category)

Not present in these alerts because the `transition` message did not include a `categories`
breakdown in `metrics`. If it did, it would show: `"connectivity events dominant — 12 events in 300s"`.

### Tier 3 — `kpi` (STUBBED — Phase 2)

```json
{
    "tier": "kpi",
    "title": "Business KPI impact pending",
    "description": "Linkage to KPI projection not yet wired.",
    "stubbed_until": "phase_2_business_projections"
}
```

**What it will do in Phase 2:** Connect the device failure to a business KPI impact.
Example: "WiFi AP down in lobby → guest check-in kiosk offline → 23 guests affected."

`stubbed_until: "phase_2_business_projections"` means: honestly declared as not yet implemented.

### Tier 4 — `consequence` (STUBBED — Phase 2)

```json
{
    "tier": "consequence",
    "title": "Revenue impact pending",
    "description": "Cost-of-poor-quality model not yet wired.",
    "stubbed_until": "phase_2_business_projections"
}
```

**What it will do in Phase 2:** Translate KPI impact into money.
Example: "Estimated £420 revenue at risk if unresolved within 2 hours."

---

## Part 4 — `agent_reasoning` — why the AI classified it this way

```json
"agent_reasoning": {
    "model": "edge-rules-v1",
    "confidence": 0.7,
    "rationale": "Edge agent classified device as unhealthy based on reasons: device_unreachable, hardware_fault.",
    "policy_check": {
        "policy_id": "policy_default",
        "passed": true,
        "rules_evaluated": []
    },
    "alternatives_considered": [],
    "similar_past_incidents": []
}
```

| Field                    | Meaning |
|--------------------------|---------|
| `model`                  | Which reasoning model was used. `edge-rules-v1` = rule-based edge agent (Phase 1). Phase 2 will use Claude AI. |
| `confidence`             | How confident the model is: `0.7` = 70%. Set to a fixed value in Phase 1. |
| `rationale`              | Plain-English explanation of why this alert was raised. |
| `policy_check.passed`    | Whether the auto-fix policy allows acting on this alert. `true` = allowed. |
| `policy_check.policy_id` | Which policy was checked. `policy_default` in Phase 1. |
| `rules_evaluated`        | Which specific rules were checked. Empty in Phase 1. |
| `alternatives_considered`| Other possible root causes the model considered. Empty in Phase 1. |
| `similar_past_incidents` | Past incidents that look like this one. Empty in Phase 1. |

---

## Part 5 — Other fields

```json
"recommended_action": null,
"runbook_history": [],
"related_tickets": []
```

| Field                | Meaning |
|----------------------|---------|
| `recommended_action` | What the system recommends doing (e.g. "cycle PoE port"). `null` = no auto-fix available yet in Phase 1. |
| `runbook_history`    | Log of past actions taken on this alert (auto-fix runs, manual interventions). Empty now. |
| `related_tickets`    | Linked helpdesk/JIRA tickets. Empty in Phase 1. |

---

## The 3 alerts in your response — plain English

| Alert | Device | What happened |
|---|---|---|
| `alr_ed155737...` | `dect_base_floor2` (dev-007) | DECT base station lost all phone registrations — phones on floor 2 can't make calls. |
| `alr_a91976cf...` | `wifi_ap_lobby` (dev-006) | WiFi AP in lobby lost power (PoE overload) and is completely unreachable — guests have no WiFi. |
| `alr_f612f2f3...` | `switch_floor3_wing_a` (dev-101) | PoE switch on floor 3 is overheating (92°C), two interfaces went down — multiple devices on floor 3 are offline. |

---

## Full response map

```
GET /v1/properties/123/alerts
│
├── property_id         ← which hotel
├── total_returned      ← how many in this page
├── has_more            ← pagination: more pages?
├── next_cursor         ← pagination: token for next page
│
└── items[]             ← one entry per open alert
        │
        ├── alert_id            ← unique alert ID
        ├── schema_version      ← always "1.0"
        │
        ├── identity            ← who/what/when
        │       state, severity, device_id, device_label,
        │       alert_kind, opened_at, triaged_at, acted_at,
        │       resolved_at, correlation_id, edge_id
        │
        ├── signal              ← what metric triggered it
        │       metric, current_value, baseline_value,
        │       series[] (the event timeline)
        │
        ├── causal_chain[]      ← 4-tier root cause
        │       tier=element    ← LIVE: device + reasons + top_events
        │       tier=kpi        ← STUBBED until Phase 2
        │       tier=consequence← STUBBED until Phase 2
        │
        ├── agent_reasoning     ← why AI classified it this way
        │       model, confidence, rationale, policy_check
        │
        ├── recommended_action  ← null (Phase 1)
        ├── runbook_history[]   ← empty (Phase 1)
        └── related_tickets[]   ← empty (Phase 1)
```
