# Why the Transition Message Does NOT Create a Duplicate Alert

## The problem this solves

The edge box sends a `transition` message every time a device is still unhealthy.
Without a guard, every message would create a **new alert** in the database.
After one hour = 60 duplicate alerts for the same broken device. The dashboard would be flooded.

---

## Real-world analogy — Hospital Emergency Room

**First visit (first POST):**
- Nurse checks: "Has this patient already been registered today?"
- **No record found.**
- Nurse creates a **new patient file** → patient admitted → `alert.opened` event fired.

**Second visit — same patient, same problem (second POST):**
- Nurse checks again: "Has this patient already been registered today?"
- **File already exists** — patient is already admitted and being treated.
- Nurse does NOT open a second file. That would be chaos.
- She just notes: "Patient checked in again, still sick" → `alert.updated` event fired.
- Then she **stops** — nothing else to do.

---

## The code

```python
# "Is this device already being tracked with an open alert?"
existing = await self.alerts.find_open_for_device(msg.device_id, kind_label)

if existing:
    # YES — alert already exists, just say "still happening"
    await self._enqueue_event(property_id, "alert.updated", {...})
    return   # STOP. Do NOT create a duplicate alert.

# NO — first time we're seeing this problem, create a brand new alert
alert_id = f"alr_{uuid.uuid4().hex}"
await self.alerts.create(...)
await self._enqueue_event(property_id, "alert.opened", {...})
```

File: `app/lib/ingestor.py`, line 184

---

## What `find_open_for_device` actually does

It queries the `alerts` table and asks:

> "Is there already an **open** alert for this device with this kind?"

```sql
SELECT * FROM alerts
WHERE device_id    = 'dev-006'
  AND alert_kind   = 'health_transition_to_unhealthy'
  AND state IN ('opened', 'triaged', 'acting')   -- not yet resolved
ORDER BY opened_at DESC
LIMIT 1
```

File: `app/repositories/alerts.py`, line 86

| Query result | What happens next |
|---|---|
| **Row found** — alert already exists | Fire `alert.updated` event → `return` (stop) |
| **Nothing found** — first time | Create new alert → fire `alert.opened` event |

---

## Full decision flow for a `transition` message

```
transition message received (status = "unhealthy")
        │
        ├── status == "healthy"?
        │       └── YES → resolve all open alerts for this device → done
        │
        └── status != "healthy"
                │
                ├── open alert already exists for this device + kind?
                │       └── YES → fire alert.updated → STOP (no duplicate)
                │
                └── NO → create brand new alert → fire alert.opened
```

---

## Key rule

> **One device problem = one alert, always.**
>
> No matter how many `transition` messages arrive for the same device,
> only one open alert will ever exist for it at a time.
> A new alert is only created after the previous one has been resolved.
