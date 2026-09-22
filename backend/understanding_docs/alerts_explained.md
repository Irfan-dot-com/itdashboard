# Alerts — Complete Guide

## 1. What Is an Alert?

An alert is a record that says **"something went wrong at a specific device in a hotel property"**.

It is created automatically — no human triggers it. When an edge box detects that a device
(e.g. a WiFi AP, PoE switch, DECT phone) has changed from healthy to unhealthy or degraded,
it sends a `transition` message to the backend. The backend turns that message into an alert
and stores it in the database.

---

## 2. What Triggers an Alert?

Only one message kind creates an alert: **`kind: transition`**.

```
edge agent  →  POST /v1/edge/ingest  →  ingestor  →  alert created in DB
```

The ingestor reads the transition message and checks two things:

| Condition | Result |
|---|---|
| `health.status == "healthy"` | Resolve all existing open alerts for this device |
| `health.status == "unhealthy"` or `"degraded"` | Create a new alert (or update the existing one) |

A `kind: periodic` or `kind: edge_health` message **never** creates an alert.

---

## 3. Alert Lifecycle — States

```
opened  →  triaged  →  acting  →  resolved
```

| State | Meaning |
|---|---|
| `opened` | Alert just created, no one has looked at it yet |
| `triaged` | A human or agent has acknowledged the alert |
| `acting` | Auto-fix has been dispatched (e.g. cycling a PoE port) |
| `resolved` | Device came back healthy — a new `transition` with `status: healthy` arrived |

The state is stored in the `alerts` table (`state` column) and also reflected live in
`detail_json → identity → state` when the API response is built.

---

## 4. Alert Severity

Severity is derived directly from the device's new health status:

| Device status | Alert severity |
|---|---|
| `unhealthy` | `p1` (highest — page someone now) |
| `degraded` | `p2` (warning — monitor closely) |
| `unknown` | `p3` (uncertain — investigate) |
| `healthy` | `p4` (not used for alerts — resolves them) |

---

## 5. Duplicate Alert Prevention

If a device is already unhealthy and keeps sending transition messages every 60 seconds,
we do **not** want a new alert created each time. The ingestor checks:

```python
existing = await alerts.find_open_for_device(device_id, "health_transition_to_unhealthy")
if existing:
    # update the existing alert with the latest top_events
    await alerts.update_detail(existing["alert_id"], new_detail, new_summary)
    return   # no new alert created
```

So per device per status, there is always **exactly one open alert** at any time.

---

## 6. What Is Inside an Alert — Full Structure

An alert has two parts:

### 6a. The `alerts` table row (flat columns)

| Column | Description |
|---|---|
| `alert_id` | Unique ID e.g. `alr_1bac680a38f4...` |
| `provider_id` | Which service provider owns this alert |
| `property_id` | Which hotel property |
| `device_id` | Which device triggered it |
| `severity` | `p1` / `p2` / `p3` |
| `state` | `opened` / `triaged` / `acting` / `resolved` |
| `alert_kind` | e.g. `health_transition_to_unhealthy` |
| `summary` | Short human-readable description |
| `correlation_id` | Groups related alerts e.g. `corr_f269867e...` |
| `opened_at` | When the alert was first created |
| `triaged_at` | When it was acknowledged |
| `acted_at` | When auto-fix was dispatched |
| `resolved_at` | When the device came back healthy |
| `detail_json` | Full rich JSON blob (see below) |

---

### 6b. `detail_json` — The Rich Alert Payload

This is a single JSONB column that holds everything the React dashboard needs to render
the full alert detail screen. It has 6 sections:

```
detail_json
├── identity          ← who / when / what
├── signal            ← what the metric looked like (with time-series)
├── causal_chain      ← 4-tier root cause analysis
├── agent_reasoning   ← why the AI classified it this way
├── recommended_action  ← Phase 2 (null for now)
└── runbook_history   ← Phase 2 (empty for now)
```

---

#### identity

```json
{
  "severity": "p1",
  "state": "opened",
  "opened_at": "2026-05-12T07:50:18.236416Z",
  "triaged_at": null,
  "acted_at": null,
  "resolved_at": null,
  "property_id": "123",
  "property_name": "sheraton",
  "device_id": "dev-006",
  "device_label": "wifi_ap_lobby",
  "alert_kind": "health_transition_to_unhealthy",
  "correlation_id": "corr_f269867e45664e7192a82214ad3495dd",
  "on_call_user": null,
  "edge_id": "edge-box-7"
}
```

`state`, `triaged_at`, `acted_at`, `resolved_at` are **overwritten at read time** from the
live `alerts` table columns — so they are always up to date even if the alert was updated
after creation.

---

#### signal

Describes the metric that breached its threshold. The `series` array is built from
`top_events` in the transition message — one entry per event, sorted by timestamp.

```json
{
  "metric": "device_health",
  "unit": "status",
  "current_value": "unhealthy",
  "baseline_value": "healthy",
  "threshold_breached": "status_transition",
  "series": [
    {
      "t": 1746723220.0,
      "v": 1,
      "severity": "warn",
      "category": "hardware",
      "message": "PoE power recycled on Gi0/12 after brown-out event"
    },
    {
      "t": 1746724090.0,
      "v": 1,
      "severity": "err",
      "category": "connectivity",
      "message": "Access point UAP-AC-PRO unreachable — ICMP ping timeout after 30s"
    }
    ...
  ]
}
```

**More `top_events` in the transition message = more items in `series`.**
There is no hardcoded limit. If you send 30 `top_events`, `series` will have 30 items.

---

#### causal_chain

Four tiers of root cause analysis, built from the transition message:

| Tier | Status | What it shows |
|---|---|---|
| `element` | ✅ Live | The exact device that failed + reasons + top_events |
| `signal` | ✅ Live (if categories provided) | Dominant event category (e.g. "connectivity events dominant") |
| `kpi` | 🔲 Phase 2 | Business KPI impact (e.g. guest Wi-Fi score) |
| `consequence` | 🔲 Phase 2 | Revenue impact estimate |

Tier 3 and 4 always have `"stubbed_until": "phase_2_business_projections"` and contain
no real data yet.

**Tier 1 metadata** contains:
```json
{
  "device_id": "dev-006",
  "reasons": ["device_unreachable", "hardware_fault"],
  "event_count": 30,
  "error_count": 22,
  "top_events": [ ...all events... ]
}
```

---

#### agent_reasoning

```json
{
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

Currently always `confidence: 0.7` and `model: edge-rules-v1`. In Phase 2 the Claude AI
agent will populate this with real reasoning.

---

## 7. How an Alert Is Built — Step by Step

```
1.  Edge agent sends POST /v1/edge/ingest
        ↓
2.  Ingestor validates the batch and loops through messages
        ↓
3.  For kind:transition — ingestor calls materialize_alert_from_transition()
        ↓
4.  materialize_alert_from_transition() builds the full detail_json:
      - identity  ← from device_row + property_row + timestamp
      - signal    ← from top_events (sorted by ts)
      - tier 1    ← from health.reasons + metrics + top_events
      - tier 2    ← from metrics.categories (if present)
      - tier 3/4  ← always stubbed
      - agent_reasoning ← edge-rules-v1 template
        ↓
5.  Ingestor calls alerts.create() — INSERT INTO alerts
        ↓
6.  Ingestor enqueues alert.opened event → outbox → Redis pub/sub → SSE clients
```

If an open alert already exists for the same device + same status:

```
3b. alerts.update_detail() — UPDATE alerts SET detail_json = new_detail
        ↓
4b. alert.updated event enqueued → Redis → SSE
    (same alert_id, same opened_at — nothing duplicated)
```

---

## 8. How an Alert Is Resolved

The device sends a `transition` message with `health.status = "healthy"`:

```
1.  Ingestor receives kind:transition with status:"healthy"
        ↓
2.  alerts.resolve_all_for_device(device_id) runs:
    UPDATE alerts SET state='resolved', resolved_at=NOW()
    WHERE device_id=$1 AND state IN ('opened','triaged','acting')
        ↓
3.  alert.state_changed event enqueued → Redis → SSE clients
```

All open alerts for that device are resolved in one query.

---

## 9. API Endpoints

| Method | Endpoint | What it does |
|---|---|---|
| `GET` | `/v1/alerts` | List all alerts for the provider (cursor-paginated) |
| `GET` | `/v1/alerts/{alert_id}` | Full alert detail (all 6 sections) |
| `GET` | `/v1/properties/{id}/alerts` | Alerts scoped to one hotel property |
| `POST` | `/v1/alerts/{alert_id}/auto-fix` | Dispatch auto-fix action (requires `Idempotency-Key` header) |

### Filtering and pagination for GET /v1/alerts

```
?status=opened,triaged,acting   ← default (all open)
?status=resolved                ← resolved only
?severity=p1                    ← not implemented yet (Phase 2)
?limit=50                       ← max 100
?cursor=<opaque string>         ← for next page
```

Sort order is always: **severity ASC (p1 first), opened_at DESC (newest first)**.

---

## 10. Auto-Fix Flow

```
POST /v1/alerts/{alert_id}/auto-fix
  Headers: Idempotency-Key: <unique key>
  Body: { "confirm": true, "actor_note": "optional note" }
```

Steps:
1. Validates `Idempotency-Key` header exists (400 if missing)
2. Checks idempotency cache in Redis — returns cached response if already processed
3. Looks up alert — 404 if not found
4. Checks `state != resolved` — 409 if already resolved
5. Checks `auto_fix_authorized == true` — 422 if not authorized
6. Updates state to `acting`
7. Inserts `auto_fix.dispatched` event into `event_outbox`
8. Returns 202 Accepted with `expected_recovery_by` (90 seconds from now)

The actual fix (e.g. cycling a PoE port via AWS SSM) is handled by the **agent-service**
which consumes the `auto_fix.dispatched` event from Redis — outside this backend's scope.

---

## 11. Key Rules (Never Break These)

1. Unknown `property_id` → **404 not 403** (don't reveal whether a property exists)
2. All alert IDs are opaque strings — never expose DB sequence numbers
3. All timestamps are RFC 3339 UTC — `2026-05-12T07:50:18Z`
4. Pagination is cursor-based only — never offset
5. `Idempotency-Key` is required for auto-fix — reject with 400 if missing
6. `causal_chain[].stubbed_until` must be set honestly — never fake Phase 2 data
7. `recommended_action` may be `null` — no auto-fix button if null
8. Policy is re-checked at dispatch time, not just at recommendation time
