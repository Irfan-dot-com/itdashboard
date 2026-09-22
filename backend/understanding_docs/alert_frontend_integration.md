# Alert — Backend ↔ Frontend Integration Guide

## Overview

The frontend (React dashboard) never talks to the edge agent directly.
It only talks to this backend. There are two communication channels:

```
┌──────────────┐   REST (HTTP)    ┌─────────────┐
│   React UI   │ ──────────────▶  │   Backend   │
│              │ ◀──────────────  │  (FastAPI)  │
│              │                  │             │
│              │   SSE (stream)   │             │
│              │ ◀──────────────  │             │
└──────────────┘                  └─────────────┘
```

- **REST** — fetch data on page load, on user action, on navigation
- **SSE** — backend pushes real-time updates to the UI without polling

---

## Authentication

Every request must include:

```
X-Provider-Id: <provider_id>
```

Example: `X-Provider-Id: bluip`

Without this header → **401 AUTH_REQUIRED**. The frontend should store the
provider ID at login and attach it to every request automatically (e.g. via an
Axios interceptor or a fetch wrapper).

---

## Base URL

```
http://localhost:4000       ← development
https://api.yourdomain.com  ← production
```

---

## Part 1 — REST Endpoints (Pull)

### 1.1 Dashboard Home — Estate Overview

**When to call:** On initial page load to render the property grid and KPI strip.

```
GET /v1/estate
Headers: X-Provider-Id: bluip
```

**Response:**
```json
{
  "kpi_strip": {
    "estate_health_score": 62,
    "sites_online": 3,
    "sites_total": 5,
    "open_alerts": { "p1": 2, "p2": 1, "p3": 0, "p4": 0 }
  },
  "properties": [
    {
      "property_id": "123",
      "name": "Sheraton",
      "health_score": 34,
      "health_status": "unhealthy",
      "open_alerts": { "p1": 1, "p2": 0, "p3": 0, "p4": 0 },
      "worst_alert_summary": "wifi_ap_lobby: device_unreachable, hardware_fault",
      "edge_box": {
        "edge_id": "edge-box-7",
        "online": true,
        "tracked_devices": 5,
        "unhealthy_devices": 1
      }
    }
  ]
}
```

**What the frontend renders from this:**
- KPI strip at the top: estate health score, sites online/total, p1/p2 alert counts
- Property grid tiles: one tile per property showing health badge, alert counts, edge box status
- Sort: `?sort=worst_first` (default) or `?sort=name_asc`

---

### 1.2 Alert List — All Alerts Across All Properties

**When to call:** When user navigates to the global Alerts page.

```
GET /v1/alerts
Headers: X-Provider-Id: bluip
Query:
  ?status=opened,triaged,acting   ← default (all open)
  ?status=resolved                ← resolved alerts
  ?limit=50                       ← 1–100, default 50
  ?cursor=<string>                ← for next page (from previous response)
```

**Response:**
```json
{
  "items": [
    {
      "alert_id": "alr_1bac680a38f4...",
      "property_id": "123",
      "property_name": "Sheraton",
      "device_id": "dev-006",
      "device_class": "wifi_ap",
      "severity": "p1",
      "state": "opened",
      "alert_kind": "health_transition_to_unhealthy",
      "summary": "wifi_ap_lobby: device_unreachable, hardware_fault",
      "opened_at": "2026-05-12T07:50:18Z",
      "triaged_at": null,
      "acted_at": null,
      "resolved_at": null,
      "recommended_action": null
    }
  ],
  "next_cursor": "eyJyIjoxLCJvIjoiMjAy...",
  "has_more": true
}
```

**Pagination (cursor-based):**
```
First page:   GET /v1/alerts?limit=50
Next page:    GET /v1/alerts?limit=50&cursor=<next_cursor from previous response>
Stop when:    has_more == false
```

**Sort order is fixed:** p1 first → p2 → p3 → p4, then newest first within same severity.
The frontend cannot change this order.

---

### 1.3 Alert Detail — Single Alert Full View

**When to call:** When user clicks on an alert row to open the detail panel/modal.

```
GET /v1/alerts/{alert_id}
Headers: X-Provider-Id: bluip
```

**Response:** Full alert detail (see `alerts_explained.md` section 6 for the complete
structure). Key sections:

```json
{
  "alert_id": "alr_1bac680a38f4...",
  "identity": {
    "severity": "p1",
    "state": "opened",
    "opened_at": "2026-05-12T07:50:18Z",
    "device_label": "wifi_ap_lobby",
    "property_name": "Sheraton"
  },
  "signal": {
    "metric": "device_health",
    "current_value": "unhealthy",
    "series": [ ...30 time-series data points... ]
  },
  "causal_chain": [ ...4 tiers... ],
  "agent_reasoning": { ... },
  "recommended_action": null
}
```

---

### 1.4 Property Detail Page

**When to call:** When user clicks on a property tile to open the property drill-down.

```
GET /v1/properties/{property_id}
Headers: X-Provider-Id: bluip
```

**Response includes:**
- Property metadata (name, address, health score)
- All edge boxes with online status
- All devices with health status and score
- Open alert counts by severity
- Last 20 raw events received from the edge box

---

### 1.5 Property Alerts — Alerts Scoped to One Property

**When to call:** When user is on the property page and wants to see that property's alerts.

```
GET /v1/properties/{property_id}/alerts
Headers: X-Provider-Id: bluip
Query: ?limit=50&cursor=<string>&status=opened,triaged,acting
```

**Response:** Same alert detail shape as `GET /v1/alerts/{id}` but wrapped in a list:

```json
{
  "property_id": "123",
  "items": [ ...full alert detail objects... ],
  "next_cursor": null,
  "has_more": false,
  "total_returned": 1
}
```

---

### 1.6 Auto-Fix Action

**When to call:** When user clicks the "Auto-Fix" button on an alert detail screen.

```
POST /v1/alerts/{alert_id}/auto-fix
Headers:
  X-Provider-Id: bluip
  Idempotency-Key: <unique UUID generated by the frontend>
  Content-Type: application/json
Body:
  { "confirm": true, "actor_note": "Approved by shift manager" }
```

**Important rules:**
- `Idempotency-Key` is **required** — 400 if missing. The frontend must generate a
  fresh UUID for each button click. If the user clicks twice by accident, the second
  call returns the same response without dispatching a second fix.
- `confirm: true` is **required** — the UI must show a confirmation dialog first.
- The button should only appear when `recommended_action != null` (Phase 2).
  Currently `recommended_action` is always `null` so no button should render.

**Response (202 Accepted):**
```json
{
  "alert_id": "alr_1bac680a38f4...",
  "action_event_id": "evt_abc123...",
  "dispatched_at": "2026-05-12T08:30:00Z",
  "expected_recovery_by": "2026-05-12T08:31:30Z",
  "status_url": "/v1/alerts/alr_1bac680a38f4..."
}
```

After receiving 202, the frontend should poll `status_url` or watch the SSE stream
for `alert.state_changed` to know when the fix completes.

---

## Part 2 — SSE Stream (Push)

### What Is SSE?

Server-Sent Events is a one-way push channel. The backend sends events to the frontend
over a long-lived HTTP connection. The frontend does NOT need to poll — events arrive
automatically the moment something happens.

```
Frontend opens connection once  →  backend keeps it open  →  events flow in
```

### Connecting

```
GET /v1/stream
Headers:
  X-Provider-Id: bluip
  Accept: text/event-stream
  Last-Event-ID: <last seen event id>  ← optional, for reconnect replay
Query:
  ?property_id=123,456    ← filter to specific properties (optional)
  ?kinds=alert.opened,alert.state_changed  ← filter event kinds (optional)
  ?min_severity=p2        ← only p1 and p2 events (optional)
```

### Event Format

Each SSE event looks like this (raw HTTP text):

```
id: evt_01HXY123abc
event: alert.opened
data: {"event_id":"evt_01HXY123abc","event_kind":"alert.opened","property_id":"123","alert_id":"alr_...","severity":"p1","summary":"wifi_ap_lobby: device_unreachable"}

```

The frontend's `EventSource` API parses this automatically.

### All Event Kinds

| Event kind | When it fires | What to do in the UI |
|---|---|---|
| `alert.opened` | New alert created | Show toast / increment p1 counter / add row to alert list |
| `alert.updated` | Existing alert refreshed with new top_events | Re-fetch alert detail if currently open |
| `alert.state_changed` | Alert resolved, triaged, or auto-fix completed | Update badge / remove from open list if resolved |
| `auto_fix.dispatched` | Auto-fix action sent to agent | Show "Fix in progress..." spinner |
| `device.health_changed` | Device changed status (periodic) | Update device status on property page |
| `edge.heartbeat` | Edge box sent a heartbeat | Update "last seen" timestamp |

### JavaScript / TypeScript Integration Example

```typescript
// Connect once when the app mounts
const stream = new EventSource(
  'http://localhost:4000/v1/stream?property_id=123',
  {
    // EventSource does not support custom headers natively.
    // Use a polyfill such as `event-source-polyfill` to pass X-Provider-Id.
  }
);

stream.addEventListener('alert.opened', (e) => {
  const alert = JSON.parse(e.data);
  // add alert to state, show toast
  queryClient.invalidateQueries(['alerts']);
});

stream.addEventListener('alert.state_changed', (e) => {
  const { alert_id, to } = JSON.parse(e.data);
  if (to === 'resolved') {
    // remove from open alerts list
    queryClient.invalidateQueries(['alerts']);
  }
});

stream.addEventListener('alert.updated', (e) => {
  const { alert_id } = JSON.parse(e.data);
  // if user is viewing this alert, refetch it
  queryClient.invalidateQueries(['alert', alert_id]);
});

// Keepalives arrive as comments — EventSource ignores them automatically
// Reconnect is automatic — browser retries with Last-Event-ID header
```

> **Note on headers:** The browser's native `EventSource` API does not support
> custom headers. Use the `event-source-polyfill` npm package or build the connection
> via `fetch` with `ReadableStream` to pass `X-Provider-Id`.

### Reconnect and Replay

If the connection drops (network blip, server restart), the browser automatically
reconnects and sends the `Last-Event-ID` header with the last event ID it received.

The backend keeps a **5-minute in-memory replay buffer**. On reconnect it replays
every event that happened while the client was disconnected, so the UI never misses
an alert opening or state change as long as the gap is under 5 minutes.

### Keepalive

Every 15 seconds of silence the backend sends:
```
: keepalive
```
This is a comment line — the `EventSource` API ignores it. It exists to prevent
proxies and load balancers from closing the idle connection.

---

## Part 3 — Error Handling

All errors use the same shape:

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "No alert with id alr_xxx visible to this provider",
    "request_id": "req_01HXY...",
    "retryable": false
  }
}
```

| HTTP Status | `code` | When | Frontend action |
|---|---|---|---|
| 400 | `VALIDATION_FAILED` | Bad query param or missing body field | Show field error |
| 401 | `AUTH_REQUIRED` | Missing `X-Provider-Id` | Redirect to login |
| 404 | `NOT_FOUND` | Unknown alert_id or property_id | Show "not found" state |
| 409 | `CONFLICT` | Auto-fix on already-resolved alert | Show "already resolved" message |
| 422 | `VALIDATION_FAILED` | Auto-fix not authorized | Hide the auto-fix button |
| 429 | `RATE_LIMITED` | Too many requests | Back-off and retry |
| 500 | `INTERNAL_ERROR` | Unexpected server error (`retryable: true`) | Show error toast, retry button |

---

## Part 4 — Recommended Frontend Data Flow

### Page: Dashboard (estate overview)

```
mount
  → GET /v1/estate           (render property grid + KPI strip)
  → open SSE /v1/stream      (listen for all events)

on alert.opened event
  → update KPI strip p1/p2 counter
  → re-fetch GET /v1/estate  (or update state locally)

on alert.state_changed (resolved)
  → re-fetch GET /v1/estate
```

---

### Page: Alert List

```
mount
  → GET /v1/alerts?status=opened,triaged,acting&limit=50

user scrolls to bottom
  → GET /v1/alerts?cursor=<next_cursor>   (append to list)

on alert.opened SSE event
  → prepend new alert to the top of the list (it's p1, sorts first)

on alert.state_changed (resolved) SSE event
  → remove resolved alert from open list
```

---

### Page: Alert Detail

```
mount
  → GET /v1/alerts/{alert_id}    (render full detail)

on alert.updated SSE event (matching this alert_id)
  → re-fetch GET /v1/alerts/{alert_id}   (new top_events may have arrived)

on alert.state_changed SSE event (matching this alert_id)
  → re-fetch GET /v1/alerts/{alert_id}   (state may have changed)

user clicks Auto-Fix button
  → generate idempotency_key = crypto.randomUUID()
  → POST /v1/alerts/{alert_id}/auto-fix
  → on 202: show "Fix dispatched, expected recovery in 90s"
  → watch SSE for alert.state_changed (acting → resolved)
```

---

### Page: Property Detail

```
mount
  → GET /v1/properties/{property_id}          (devices, edge boxes, recent events)
  → GET /v1/properties/{property_id}/alerts   (alert list for this property)

on edge.heartbeat SSE event (for this property)
  → update "last seen" timestamp on edge box card

on device.health_changed SSE event (for this property)
  → update device health badge

on alert.opened SSE event (for this property)
  → prepend to alert list, increment p1 counter
```

---

## Part 5 — Complete Request/Response Reference

### Headers required on every request

| Header | Value | Required |
|---|---|---|
| `X-Provider-Id` | Your provider ID e.g. `bluip` | Yes |
| `Content-Type` | `application/json` | Only on POST |
| `Idempotency-Key` | UUID string | Only on POST /auto-fix |

### Headers the backend sets on every response

| Header | Value | Purpose |
|---|---|---|
| `X-Request-ID` | `req_<hex>` | Use in support tickets to trace a request |
| `ETag` | Hash of response body | Send back as `If-None-Match` to get 304 Not Modified |
| `Cache-Control` | `max-age=10` (tiles) or `max-age=2` (live data) | Browser caching hint |

### ETag / 304 caching

```
First request:
  GET /v1/estate
  ← 200  ETag: "abc123"

Same data, second request:
  GET /v1/estate
  If-None-Match: "abc123"
  ← 304 Not Modified  (no body, saves bandwidth)
```

---

## Part 6 — Quick Checklist for Frontend Developer

- [ ] Attach `X-Provider-Id` header on every request (Axios interceptor recommended)
- [ ] Use cursor pagination — never offset
- [ ] Generate a fresh `crypto.randomUUID()` for each auto-fix button click
- [ ] Open SSE connection once on app mount, not per page
- [ ] Use `event-source-polyfill` for custom header support
- [ ] Handle `Last-Event-ID` automatically (browser does this, polyfill also does)
- [ ] Do not show Auto-Fix button when `recommended_action == null`
- [ ] All timestamps from the API are UTC — convert to local time for display
- [ ] Read `error.code` not `error.message` for programmatic error handling
- [ ] Read `error.retryable` — if `true`, show a retry button
- [ ] On 404 for a property → show "not found", do NOT assume the property doesn't exist
