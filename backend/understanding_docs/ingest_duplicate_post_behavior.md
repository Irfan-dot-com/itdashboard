# What Happens When You POST the Same Request Body Twice?

The system is designed to be **safe for duplicate messages**.  
Each of the 3 message kinds behaves differently on a second POST.

---

## Message 1: `edge_health` (second time)

**Code path:** `ingestor.py → _edge_health() → props.upsert_edge_box()`

| Step | What happens |
|------|-------------|
| `edge_boxes` table | UPSERT runs again — overwrites the same row with the same values. No duplicate row created. |
| `last_heartbeat_at` | Updated to the new server time. |
| `raw_events` table | A new row is always inserted (full audit log). |
| SSE event | A new `edge.heartbeat` event is pushed to the stream. |

**Result:** Safe. The edge box is simply treated as "still alive."

---

## Message 2: `periodic` (second time)

**Code path:** `ingestor.py → _periodic() → devices.update_health()`

The key logic is in `repositories/devices.py:56`:

```python
return prior if prior != health_status else None
```

| Step | What happens |
|------|-------------|
| `devices` table | UPSERT runs — same row, same values. No duplicate. |
| `update_health()` | Reads current `health_status` from DB → already `"unhealthy"`. New status is also `"unhealthy"` → **they match** → returns `None`. |
| `device.health_changed` event | **NOT fired** — because return was `None` (status did not change). |
| `raw_events` table | New row inserted (audit log). |

**Result:** Safe. No false "device changed" event is triggered just because the same message arrived twice.

---

## Message 3: `transition` (second time) — the most important one

**Code path:** `ingestor.py → _transition() → alerts.find_open_for_device()`

The key logic is in `ingestor.py:184`:

```python
existing = await self.alerts.find_open_for_device(msg.device_id, kind_label)
if existing:
    await self._enqueue_event(property_id, "alert.updated", {"alert_id": existing["alert_id"]})
    return   # stops here — does NOT create a new alert
```

| Step | What happens |
|------|-------------|
| `devices` table | UPSERT → same values. |
| `update_health()` | Status still `"unhealthy"` → no change. |
| Resolve check | Status is not `"healthy"` → no alerts resolved. |
| `find_open_for_device()` | Searches for an existing open alert for `device_id="dev-006"` with `alert_kind="health_transition_to_unhealthy"` → **finds the alert created in the first POST**. |
| New alert | **NOT created.** System sees the device is already being tracked. |
| SSE event | Only `alert.updated` is fired (not `alert.opened`). |

**Result:** Safe. You will never get 10 duplicate alerts just because the edge box sent 10 identical transition messages.

---

## Summary

| Message kind | DB write | New alert created? | SSE event fired |
|---|---|---|---|
| `edge_health` (2nd time) | Updates `edge_boxes` row | No | `edge.heartbeat` (fires again) |
| `periodic` (2nd time) | Updates `devices` row | No | Nothing (status unchanged) |
| `transition` (2nd time) | Updates `devices` row | **No** — existing open alert found | `alert.updated` only |

---

## API Response (same both times)

```json
{
  "edge_id": "edge-box-7",
  "accepted": 3,
  "rejected": []
}
```

All 3 messages are accepted with no errors.  
The backend does not reject duplicates — it silently handles them safely.

---

## Key design principle

> **UPSERT everywhere, deduplication by state check.**
>
> - Device and edge box rows use `ON CONFLICT DO UPDATE` — safe to call any number of times.
> - Alerts use `find_open_for_device()` before creating — one open alert per device per kind, always.
> - Raw events are always appended — full audit trail is preserved.
