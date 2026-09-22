# Understanding GET /v1/properties/{property_id} Response

This endpoint gives the **full picture of one hotel property** —
its health, all physical edge boxes, all devices, and a recent activity log.
The React dashboard calls this to build the property detail page.

---

## How the backend builds this response (step by step)

```
GET /v1/properties/123
        │
        ├── 1. Fetch property row from DB (name, site_code, address)
        ├── 2. Fetch all devices for this property → calculate health_score + health_status
        ├── 3. Count open alerts by severity (p1/p2/p3/p4)
        ├── 4. Fetch all edge boxes → calculate online/offline for each
        ├── 5. Fetch last 20 raw_events → build recent_events list
        └── 6. Return everything assembled in one response
```

---

## Section 1 — Property identity fields

```json
{
    "provider_id": "bluip",
    "property_id": "123",
    "name": "sheraton",
    "site_code": null,
    "address": null
}
```

| Field         | Where it comes from | Meaning |
|---------------|---------------------|---------|
| `provider_id` | `X-Provider-Id` request header | The IT service company managing this hotel. Used for tenant scoping — one provider can never see another's data. |
| `property_id` | URL path `{property_id}` | The hotel's unique ID. |
| `name`        | `properties` table | Human-readable hotel name sent by the edge agent in `property_name`. |
| `site_code`   | `properties` table | Optional short code (e.g. `"LHR-01"`). `null` until set manually. |
| `address`     | `properties` table | Physical address. `null` until set manually. |

---

## Section 2 — Property health

```json
{
    "health_score": 36,
    "health_status": "unhealthy"
}
```

These are **calculated on every request** — not stored in the DB.

**How `health_score` is calculated** (`app/lib/health.py`):

```
1. Collect all devices' health_score values → [15, 99, 20, 10]
2. Average them → (15 + 99 + 20 + 10) / 4 = 36
3. Find worst device status → any "unhealthy" present → property status = "unhealthy"
4. Clamp average to ceiling for that status:
       unhealthy ceiling = 40
       36 < 40 → health_score = 36
```

**Status rules:**

| Condition | Property status |
|---|---|
| Any device is `unhealthy` | `unhealthy` |
| Any device is `degraded` (no unhealthy) | `degraded` |
| All devices are `healthy` | `healthy` |
| Mix of healthy + unknown | `degraded` |

---

## Section 3 — Open alerts count

```json
"open_alerts": {
    "p1": 3,
    "p2": 0,
    "p3": 0,
    "p4": 0
}
```

A **count of all open alerts** for this property, grouped by severity.
"Open" means state is `opened`, `triaged`, or `acting` (not yet resolved).

| Severity | Meaning |
|---|---|
| `p1` | Critical — device completely unreachable / hardware failure |
| `p2` | High — device degraded, partial failure |
| `p3` | Medium — unknown state |
| `p4` | Low — minor, informational |

In your response: **3 critical alerts open**, nothing else.

---

## Section 4 — Edge boxes

```json
"edge_boxes": [
    {
        "edge_id": "edge-box-8",
        "online": false,
        "last_heartbeat_at": "2025-05-08T17:11:40Z",
        "tracked_devices": 3,
        "unhealthy_devices": 1,
        "queue_depth": 4,
        "summary_interval_seconds": 60
    },
    {
        "edge_id": "edge-box-7",
        "online": false,
        "last_heartbeat_at": "2025-05-08T17:08:20Z",
        "tracked_devices": 5,
        "unhealthy_devices": 2,
        "queue_depth": 5,
        "summary_interval_seconds": 60
    }
]
```

One entry per physical box installed at this hotel. This property has **two edge boxes**
(one per floor/wing). All data comes from the `edge_boxes` table, updated by `edge_health` messages.

| Field | Meaning |
|---|---|
| `edge_id` | Unique ID of the physical box. |
| `online` | **Calculated in the router** — `true` if `last_heartbeat_at` was within `summary_interval_seconds × 2` seconds ago. Both are `false` here because the last heartbeat was in 2025 and today is 2026. |
| `last_heartbeat_at` | When this box last sent an `edge_health` message. |
| `tracked_devices` | How many devices this box is watching. |
| `unhealthy_devices` | How many of those are currently unhealthy. |
| `queue_depth` | How many messages are in the edge box's backlog. |
| `summary_interval_seconds` | How often this box sends reports (60s = every minute). |

**How `online` is calculated** (`app/routers/properties.py:57`):

```python
online = (now - last_heartbeat_at).total_seconds() <= summary_interval_seconds * 2
# e.g. interval=60 → online if heartbeat arrived within the last 120 seconds
```

---

## Section 5 — Devices

```json
"devices": [
    {
        "device_id": "dev-007",
        "label": "dect_base_floor2",
        "device_class": "dect_base",
        "vendor": "cisco",
        "site": "floor_2",
        "health_status": "unhealthy",
        "health_score": 10,
        "last_seen_at": "2026-05-11T08:15:55.633751Z",
        "open_alerts": { "p1": 3, "p2": 0, "p3": 0, "p4": 0 }
    },
    ...
]
```

One entry per device registered under this property. All data comes from the `devices` table,
updated by `periodic` and `transition` messages.

| Field | Meaning |
|---|---|
| `device_id` | Stable unique ID for this device (set by the edge agent). |
| `label` | Human-readable name (e.g. `"wifi_ap_lobby"`). Set from `device_name` in ingest messages. |
| `device_class` | Type of device: `wifi_ap`, `dect_base`, `dect_phone`, `poe_switch`, `pbx`, `pms`, etc. |
| `vendor` | Hardware manufacturer (e.g. `"ubiquiti"`, `"cisco"`). |
| `site` | Physical location in the hotel (e.g. `"lobby"`, `"floor_2"`). |
| `health_status` | Latest status from the edge agent: `healthy / degraded / unhealthy / unknown`. |
| `health_score` | Latest 0–100 score from the edge agent. |
| `last_seen_at` | When the backend last received a message for this device. |
| `open_alerts` | **Important shortcut** — see note below. |

**Important note about `open_alerts` per device:**

The backend does **not** count alerts per device individually here. It uses a shortcut
(`app/routers/properties.py:80`):

```python
open_alerts = prop_alerts if d["health_status"] != "healthy" else empty_alerts
```

- Device is **not healthy** → shows the **whole property's** alert counts
- Device is **healthy** → shows zeros `{p1:0, p2:0, p3:0, p4:0}`

This is why `dev-007`, `dev-101`, and `dev-006` all show `p1: 3` — that's the property total,
not per-device. `dev-102` shows zeros because its status is `healthy`.

---

## Section 6 — Integration health

```json
"integration_health": []
```

Always empty in Phase 1. Will show external system health (Mews PMS, Broadworks PBX,
Stripe, Twilio) in Phase 2.

---

## Section 7 — Recent events

```json
"recent_events": [
    {
        "event_id": "evt_585de56e...",
        "kind": "transition",
        "received_at": "2026-05-11T08:15:57Z",
        "summary": "dev-007 → unhealthy"
    },
    {
        "event_id": "evt_c7a0fdca...",
        "kind": "periodic",
        "received_at": "2026-05-08T18:04:00Z",
        "summary": "periodic on dev-006"
    },
    ...
]
```

The **last 20 raw events** received for this property, newest first.
Comes directly from the `raw_events` table — every single ingest message is stored there.

| Field | Meaning |
|---|---|
| `event_id` | Unique ID for this raw event row. |
| `kind` | The message kind: `edge_health`, `periodic`, or `transition`. |
| `received_at` | When the backend received and stored this event. |
| `summary` | Human-readable one-liner built by `_event_summary()` in the router. |

**How `summary` is built** (`app/routers/properties.py:20`):

```python
if kind == "edge_health":
    → "edge heartbeat (queue_depth=5)"

if kind == "transition":
    → "dev-006 → unhealthy"

else (periodic):
    → "periodic on dev-006"
```

---

## Full response map

```
GET /v1/properties/123
│
├── provider_id, property_id, name, site_code, address
│       └── from: properties table
│
├── health_score, health_status
│       └── calculated from: all devices' health_score/health_status
│
├── open_alerts { p1, p2, p3, p4 }
│       └── counted from: alerts table (state = opened/triaged/acting)
│
├── edge_boxes[]
│       └── from: edge_boxes table (one row per physical box)
│           online field calculated from last_heartbeat_at vs now
│
├── devices[]
│       └── from: devices table (one row per device)
│           open_alerts = property total if unhealthy, zeros if healthy
│
├── integration_health[]
│       └── always empty (Phase 2)
│
└── recent_events[]
        └── last 20 rows from: raw_events table, newest first
```
