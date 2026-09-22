# All Scenarios That Create a New Alert

## Rule — 3 conditions must ALL be true

A new alert is created **only when all 3 conditions are met:**

1. Message kind is `transition`
2. Health status is **not** `"healthy"`
3. **No existing open alert** found for that `device_id + alert_kind` combination

There are **4 scenarios** that satisfy this.

---

## Scenario 1 — Brand new device, first time going unhealthy

No prior alert exists for this device. Backend finds nothing in `find_open_for_device()` → creates a new alert with kind `health_transition_to_unhealthy`.

```json
{
  "schema_version": "1.0",
  "edge_id": "edge-box-7",
  "service_provider": "bluip",
  "property_id": "123",
  "property_name": "sheraton",
  "messages": [
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
      "metrics": { "event_count": 20, "error_count": 18, "warn_count": 2 },
      "top_events": [
        {
          "ts": 1746724090.0,
          "severity": "error",
          "category": "connectivity",
          "message": "Access point UAP-AC-PRO unreachable — ICMP ping timeout after 30s"
        }
      ]
    }
  ]
}
```

**What the backend does:**
- `find_open_for_device("dev-006", "health_transition_to_unhealthy")` → returns nothing
- Creates new alert → fires `alert.opened` event

---

## Scenario 2 — A DIFFERENT device goes unhealthy

`dev-007` has never had an alert before. Backend creates a new alert for `dev-007`.

```json
{
  "schema_version": "1.0",
  "edge_id": "edge-box-7",
  "service_provider": "bluip",
  "property_id": "123",
  "property_name": "sheraton",
  "messages": [
    {
      "kind": "transition",
      "ts": 1746724200.0,
      "device_id": "dev-007",
      "device_name": "dect_base_floor2",
      "device_class": "dect_base",
      "vendor": "cisco",
      "site": "floor_2",
      "health": {
        "status": "unhealthy",
        "score": 10,
        "reasons": ["no_registrations", "device_unreachable"]
      },
      "metrics": { "event_count": 15, "error_count": 14, "warn_count": 1 },
      "top_events": [
        {
          "ts": 1746724190.0,
          "severity": "error",
          "category": "connectivity",
          "message": "DECT base station lost all phone registrations on floor 2"
        }
      ]
    }
  ]
}
```

**What the backend does:**
- `find_open_for_device("dev-007", "health_transition_to_unhealthy")` → returns nothing (new device)
- Creates new alert for `dev-007` → fires `alert.opened` event

---

## Scenario 3 — Same device recovered, then fails again

This is a **2-step scenario**. The device first recovers (alert resolved), then fails again (new alert created).

### Step A — Send this first (device recovers → existing alert resolved)

```json
{
  "schema_version": "1.0",
  "edge_id": "edge-box-7",
  "service_provider": "bluip",
  "property_id": "123",
  "property_name": "sheraton",
  "messages": [
    {
      "kind": "transition",
      "ts": 1746724300.0,
      "device_id": "dev-006",
      "device_name": "wifi_ap_lobby",
      "device_class": "wifi_ap",
      "vendor": "ubiquiti",
      "site": "lobby",
      "health": {
        "status": "healthy",
        "score": 95,
        "reasons": []
      },
      "metrics": { "event_count": 2, "error_count": 0, "warn_count": 0 },
      "top_events": []
    }
  ]
}
```

**What the backend does:**
- Status is `"healthy"` → calls `resolve_all_for_device("dev-006")` → marks existing alert as `resolved`
- Fires `alert.state_changed` event (opened → resolved)

### Step B — Send this after (device fails again → NEW alert created)

```json
{
  "schema_version": "1.0",
  "edge_id": "edge-box-7",
  "service_provider": "bluip",
  "property_id": "123",
  "property_name": "sheraton",
  "messages": [
    {
      "kind": "transition",
      "ts": 1746724400.0,
      "device_id": "dev-006",
      "device_name": "wifi_ap_lobby",
      "device_class": "wifi_ap",
      "vendor": "ubiquiti",
      "site": "lobby",
      "health": {
        "status": "unhealthy",
        "score": 8,
        "reasons": ["hardware_fault"]
      },
      "metrics": { "event_count": 25, "error_count": 23, "warn_count": 2 },
      "top_events": [
        {
          "ts": 1746724390.0,
          "severity": "error",
          "category": "hardware",
          "message": "AP hardware fault detected — radio module unresponsive"
        }
      ]
    }
  ]
}
```

**What the backend does:**
- `find_open_for_device("dev-006", "health_transition_to_unhealthy")` → returns nothing (previous alert was resolved in Step A)
- Creates a **brand new alert** → fires `alert.opened` event

---

## Scenario 4 — Same device escalates from `degraded` to `unhealthy`

`alert_kind` is built as `health_transition_to_{status}`.
So `degraded` and `unhealthy` are **different kind strings** — `find_open_for_device` won't find
the degraded alert when searching for the unhealthy one → creates a second alert.

### Step A — Send this first (creates alert with kind `health_transition_to_degraded`)

```json
{
  "schema_version": "1.0",
  "edge_id": "edge-box-7",
  "service_provider": "bluip",
  "property_id": "123",
  "property_name": "sheraton",
  "messages": [
    {
      "kind": "transition",
      "ts": 1746724500.0,
      "device_id": "dev-006",
      "device_name": "wifi_ap_lobby",
      "device_class": "wifi_ap",
      "vendor": "ubiquiti",
      "site": "lobby",
      "health": {
        "status": "degraded",
        "score": 55,
        "reasons": ["high_error_rate"]
      },
      "metrics": { "event_count": 10, "error_count": 6, "warn_count": 4 },
      "top_events": [
        {
          "ts": 1746724490.0,
          "severity": "warning",
          "category": "connectivity",
          "message": "Packet loss rate 35% on AP-Lobby-01 — above threshold"
        }
      ]
    }
  ]
}
```

**What the backend does:**
- `find_open_for_device("dev-006", "health_transition_to_degraded")` → returns nothing
- Creates alert with kind `health_transition_to_degraded` (severity `p2`) → fires `alert.opened`

### Step B — Send this after (escalates to `unhealthy` → different kind → NEW alert created)

```json
{
  "schema_version": "1.0",
  "edge_id": "edge-box-7",
  "service_provider": "bluip",
  "property_id": "123",
  "property_name": "sheraton",
  "messages": [
    {
      "kind": "transition",
      "ts": 1746724600.0,
      "device_id": "dev-006",
      "device_name": "wifi_ap_lobby",
      "device_class": "wifi_ap",
      "vendor": "ubiquiti",
      "site": "lobby",
      "health": {
        "status": "unhealthy",
        "score": 12,
        "reasons": ["device_unreachable", "high_error_rate"]
      },
      "metrics": { "event_count": 20, "error_count": 19, "warn_count": 1 },
      "top_events": [
        {
          "ts": 1746724590.0,
          "severity": "error",
          "category": "connectivity",
          "message": "AP-Lobby-01 completely unreachable — total connectivity loss"
        }
      ]
    }
  ]
}
```

**What the backend does:**
- `find_open_for_device("dev-006", "health_transition_to_unhealthy")` → returns nothing (only `health_transition_to_degraded` exists, not `health_transition_to_unhealthy`)
- Creates a **new alert** with kind `health_transition_to_unhealthy` (severity `p1`) → fires `alert.opened`

---

## Summary of all 4 scenarios

| # | Scenario | Condition that allows new alert | Alert kind created |
|---|---|---|---|
| 1 | First transition for a new device | No prior alert exists at all | `health_transition_to_unhealthy` |
| 2 | Different `device_id` transitions | Different device — no alert for it | `health_transition_to_unhealthy` |
| 3 | Same device recovered → fails again | Previous alert was resolved (status was `healthy`) | `health_transition_to_unhealthy` |
| 4 | Same device escalates degraded → unhealthy | Different `alert_kind` string — no match found | `health_transition_to_unhealthy` |

---

## What NEVER creates a new alert

| Situation | Why |
|---|---|
| Sending the same `transition` body again | Open alert already exists → `alert.updated` only |
| Sending a `periodic` message | `periodic` never creates alerts — only updates device health |
| Sending an `edge_health` message | Only updates the edge box heartbeat |
| Sending `transition` with `status: "healthy"` | Resolves existing alerts — never opens new ones |
