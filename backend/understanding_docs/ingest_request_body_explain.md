# Understanding the POST /v1/edge/ingest Request Body

This endpoint is how a **physical edge box** (a small computer installed at a hotel) reports
what is happening on the hotel's network. It sends a batch of messages to the cloud backend.

---

## Who sends this request?

**Person A** — the edge agent running on a Raspberry Pi / mini-PC installed at each hotel.
It watches all network devices (PoE switches, Wi-Fi APs, DECT phones, PBX) and regularly
posts what it sees to this endpoint.

---

## Top-level envelope fields

```json
{
  "schema_version": "1.0",
  "edge_id": "edge-box-7",
  "service_provider": "bluip",
  "property_id": "123",
  "property_name": "sheraton",
  "messages": [ ... ]
}
```

| Field             | Type   | Meaning |
|-------------------|--------|---------|
| `schema_version`  | string | Always `"1.0"` for now. Lets the backend reject old/incompatible messages in the future. |
| `edge_id`         | string | Unique ID of the physical edge box that is sending this batch. One hotel can have multiple edge boxes (one per floor/wing). |
| `service_provider`| string | The IT service company managing this hotel (e.g. `"bluip"`). Scopes all data so hotels from different providers never see each other's data. |
| `property_id`     | string | Unique ID of the hotel property. This is what the backend uses as the tenant key. |
| `property_name`   | string | Human-readable hotel name (e.g. `"sheraton"`). Displayed in the dashboard. |
| `messages`        | array  | A batch of 1–100 messages. Each message is one of three kinds (see below). |

---

## `ts` — what is it?

`ts` stands for **timestamp**. It is a **Unix epoch float** — the number of seconds since
1 January 1970 UTC.

```json
"ts": 1746724100.0
```

The backend converts this to a real UTC datetime:

```
1746724100.0  →  2025-05-08T20:28:20Z
```

Why use epoch floats instead of ISO strings?  
Because the edge box may be running in any timezone, and floats are unambiguous, compact,
and easy to sort. The backend always normalises them to UTC before storing.

---

## The three `kind` values

Every message in the `messages` array has a `kind` field. There are exactly three kinds.
Think of them as three different types of reports the edge box sends.

### 1. `kind: "edge_health"` — the edge box reporting on itself

```json
{
  "kind": "edge_health",
  "ts": 1746724100.0,
  "metrics": {
    "tracked_devices": 5,
    "unhealthy_devices": 2,
    "queue_depth": 5,
    "summary_interval_seconds": 60
  }
}
```

**What it means:** The edge box itself is saying "I am alive, and here is my current load."  
This is a **heartbeat**. If the backend stops receiving these, it knows the edge box went offline.

**`metrics` fields for `edge_health`:**

| Field                     | Meaning |
|---------------------------|---------|
| `tracked_devices`         | How many network devices this edge box is currently watching. |
| `unhealthy_devices`       | Of those, how many are currently in an unhealthy state. |
| `queue_depth`             | How many messages are waiting to be sent (backlog). High = the edge box is struggling to keep up. |
| `summary_interval_seconds`| How often (in seconds) the edge box sends periodic reports. Default is 60s. |

**What the backend does with it:**  
Updates the `edge_boxes` table with `last_heartbeat_at` and the metrics. Fires an
`edge.heartbeat` event onto the outbox → SSE stream.

---

### 2. `kind: "periodic"` — regular status report for one device

```json
{
  "kind": "periodic",
  "ts": 1746724095.0,
  "device_id": "dev-006",
  "device_name": "wifi_ap_lobby",
  "device_class": "wifi_ap",
  "vendor": "ubiquiti",
  "site": "lobby",
  "health": {
    "status": "unhealthy",
    "score": 15,
    "reasons": ["device_unreachable", "hardware_fault"]
  },
  "metrics": {
    "event_count": 20,
    "error_count": 18,
    "warn_count": 2
  }
}
```

**What it means:** Every `summary_interval_seconds` (60 seconds), the edge box sends a
snapshot for each device it is tracking. This is **routine polling** — even if nothing
changed, the backend gets a fresh status.

**Device identification fields:**

| Field          | Meaning |
|----------------|---------|
| `device_id`    | Unique ID for this device (set by the edge agent, stable over time). |
| `device_name`  | Human-readable label shown in the dashboard (e.g. `"wifi_ap_lobby"`). |
| `device_class` | Category of device: `wifi_ap`, `dect_base`, `poe_switch`, `pbx`, `pms`, etc. |
| `vendor`       | Hardware manufacturer (e.g. `"ubiquiti"`, `"cisco"`). |
| `site`         | Physical location within the hotel (e.g. `"lobby"`, `"floor_2"`, `"server_room"`). |

**`health` object:**

| Field     | Meaning |
|-----------|---------|
| `status`  | One of: `healthy`, `degraded`, `unhealthy`, `unknown`. Drives alert severity. |
| `score`   | 0–100. The edge agent's numeric health confidence. `100` = perfect, `0` = completely dead. |
| `reasons` | List of machine-readable reason codes explaining why the status is what it is. Examples: `device_unreachable`, `hardware_fault`, `high_error_rate`. |

**`metrics` fields for `periodic` and `transition`:**

| Field         | Meaning |
|---------------|---------|
| `event_count` | Total syslog/event lines seen from this device in the last interval. |
| `error_count` | Of those, how many were error-level. |
| `warn_count`  | Of those, how many were warning-level. |

**What the backend does with it:**  
UPSERTs the device into the `devices` table and updates its `health_status` and
`health_score`. If the status changed from what was stored before, fires a
`device.health_changed` event. Does **not** create an alert (that is what `transition` is for).

---

### 3. `kind: "transition"` — a device just changed health state

```json
{
  "kind": "transition",
  "ts": 1746724100.0,
  "device_id": "dev-006",
  "device_name": "wifi_ap_lobby",
  "device_class": "wifi_ap",
  "vendor": "ubiquiti",
  "site": "lobby",
  "health": {
    "status": "unhealthy",
    "score": 15,
    "reasons": ["device_unreachable", "hardware_fault"]
  },
  "metrics": {
    "event_count": 20,
    "error_count": 18,
    "warn_count": 2
  },
  "top_events": [
    {
      "ts": 1746724090.0,
      "severity": "error",
      "category": "connectivity",
      "message": "Access point UAP-AC-PRO unreachable — ICMP ping timeout after 30s"
    },
    {
      "ts": 1746724085.0,
      "severity": "error",
      "category": "hardware",
      "message": "PoE power budget exceeded on port Gi0/12 — AP lost power"
    },
    {
      "ts": 1746724080.0,
      "severity": "error",
      "category": "connectivity",
      "message": "SSID 'Sheraton-Guest' no longer broadcasting from AP-Lobby-01"
    },
    {
      "ts": 1746724075.0,
      "severity": "warning",
      "category": "hardware",
      "message": "PoE port Gi0/12 power draw spike: 32W (normal: 18W)"
    }
  ]
}
```

**What it means:** The edge box is saying "this device just crossed a health boundary —
it went from healthy to unhealthy (or vice versa)." This is the **most important** message
kind because it triggers alert creation in the backend.

It has all the same fields as `periodic`, plus one extra: `top_events`.

**`top_events` — the evidence log:**

Each entry in `top_events` is a raw syslog line (or structured event) that the edge agent
captured and considers the most relevant to explain why the device changed state.

| Field      | Meaning |
|------------|---------|
| `ts`       | When this specific event happened (Unix epoch float). |
| `severity` | Raw severity from the log: `"error"`, `"warning"`, `"information"`. The backend normalises these to `err`, `warn`, `info`. |
| `category` | What type of problem this event belongs to: `"connectivity"`, `"hardware"`, `"software"`, `"authentication"`, etc. |
| `message`  | The human-readable log line — exactly what the device or monitoring tool reported. This text surfaces in the dashboard alert detail view. |

**What the backend does with it:**

```
transition received
    │
    ├─ status == "healthy"?
    │       └─ YES → resolve all open alerts for this device → done
    │
    └─ status != "healthy"
            │
            ├─ open alert already exists for this device+kind?
            │       └─ YES → fire alert.updated event → done
            │
            └─ NO → materialize a new alert (4-tier causal chain) → INSERT alert → fire alert.opened event
```

The `top_events` list becomes the **evidence** inside the alert's `causal_chain[tier=element].metadata.top_events`
and the `signal.series[]` timeline shown in the dashboard.

---

## Why all three kinds in one batch?

The edge box sends them together in one HTTP POST to reduce round-trips. A typical batch
contains:
- One `edge_health` (the box itself)
- Many `periodic` messages (one per device, every 60s)
- Zero or a few `transition` messages (only when a device changes state)

The backend processes each message independently inside its own database transaction.
If one message fails (e.g. invalid data), it is rejected individually and the rest still succeed.
The response tells you exactly which ones were accepted vs rejected:

```json
{
  "edge_id": "edge-box-7",
  "accepted": 3,
  "rejected": []
}
```

---

## Severity mapping (normalisation)

The edge agent may send syslog-style severity strings. The backend normalises them:

| Edge sends      | Backend stores |
|-----------------|----------------|
| `"error"`       | `"err"`        |
| `"warning"`     | `"warn"`       |
| `"information"` | `"info"`       |
| `"critical"`    | `"crit"`       |

And device health status maps to alert priority:

| Device `health.status` | Alert severity |
|------------------------|----------------|
| `unhealthy`            | `p1` (critical)|
| `degraded`             | `p2` (high)    |
| `unknown`              | `p3` (medium)  |
| `healthy`              | `p4` (low / resolves alert) |

---

## Summary flow diagram

```
Edge box at hotel
    │
    │  POST /v1/edge/ingest  (batch of messages)
    ▼
Backend ingestion pipeline
    │
    ├── edge_health  →  update edge_boxes table  →  edge.heartbeat SSE event
    │
    ├── periodic     →  upsert device + health   →  device.health_changed SSE event (if changed)
    │
    └── transition   →  upsert device + health
                          │
                          ├── if healthy  →  resolve alerts  →  alert.state_changed SSE event
                          └── if not      →  create alert    →  alert.opened SSE event
                                                  │
                                                  └── React dashboard receives SSE push
                                                      and shows the new alert to hotel IT staff
```
