# Complete Data Flow — From Network Devices to Cloud

This guide shows how data flows through the system with real examples at each stage.

---

## Overview Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   NETWORK DEVICES (Real Switches/Routers/Firewalls)                        │
│   ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐        │
│   │ Cisco Switch     │  │ Juniper Router   │  │ Palo Alto FW     │        │
│   │ 192.168.1.10     │  │ 192.168.1.20     │  │ 192.168.1.30     │        │
│   └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘        │
│            │                     │                      │                   │
│            └─────────────────────┼──────────────────────┘                   │
│                         UDP Port 514/5514                                   │
│                        (Raw Syslog Packets)                                 │
│                                  │                                          │
└──────────────────────────────────┼──────────────────────────────────────────┘
                                   │
                                   ▼
        ┌─────────────────────────────────────────┐
        │   UBUNTU EDGE BOX (192.168.1.100)       │
        │                                         │
        │  ┌─────────────────────────────────┐   │
        │  │ syslog_listener.py              │   │
        │  │ • Listen on 0.0.0.0:5514/UDP    │   │
        │  │ • Parse RFC 3164/5424           │   │
        │  │ • Extract fields                │   │
        │  └────────────┬────────────────────┘   │
        │               │                        │
        │               ▼                        │
        │  ┌─────────────────────────────────┐   │
        │  │ config.py                       │   │
        │  │ • Resolve device IP/hostname    │   │
        │  │ • Lookup device_id, site, type  │   │
        │  └────────────┬────────────────────┘   │
        │               │                        │
        │               ▼                        │
        │  ┌─────────────────────────────────┐   │
        │  │ aggregator.py                   │   │
        │  │ • Classify message              │   │
        │  │ • Filter noise                  │   │
        │  │ • Deduplicate                   │   │
        │  │ • Compute health score          │   │
        │  │ • Build summary JSON            │   │
        │  └────────────┬────────────────────┘   │
        │               │                        │
        │               ▼                        │
        │  ┌─────────────────────────────────┐   │
        │  │ outbound_queue.py               │   │
        │  │ • Store JSON in SQLite          │   │
        │  │ (Survives reboots)              │   │
        │  └────────────┬────────────────────┘   │
        │               │                        │
        │               ▼                        │
        │  ┌─────────────────────────────────┐   │
        │  │ uploader.py                     │   │
        │  │ • Drain queue                   │   │
        │  │ • POST to cloud (HTTPS)         │   │
        │  │ • Retry with backoff            │   │
        │  └────────────┬────────────────────┘   │
        │               │                        │
        └───────────────┼────────────────────────┘
                        │
                        │ HTTPS POST (Batched)
                        │
                        ▼
        ┌──────────────────────────────┐
        │  CLOUD DASHBOARD SERVER      │
        │  https://dashboard.company.com│
        │                              │
        │  • Store device status       │
        │  • Display on web UI         │
        │  • Generate alerts           │
        │  • Historical trending       │
        └──────────────────────────────┘
```

---

## Stage 1: Raw Syslog from Network Devices

### What Real Devices Send

**Cisco Switch — Power Supply Failure:**
```
<131>May  4 15:30:00 switch-floor1 %SYS-3-POWER: Power supply 1 failed
```

**Juniper Router — BGP Session Down:**
```
<134>May  4 15:30:01 router-edge mrvl-pfe[2048]: OSPF adjacency lost with 10.0.0.1
```

**Palo Alto Firewall — Session Close:**
```
<165>May  4 15:30:02 palo-fw1 PA-5220: SYSTEM [session_close] 192.168.1.5:443=>10.0.0.1:52345
```

**Arista Switch (RFC 5424 format):**
```
<134>1 2026-05-04T15:30:03.123Z arista-switch01 Syslog 1234 - - BGP session established
```

### Data at this stage:
- **Format:** Plain text, over UDP
- **Size:** 100–300 bytes per message
- **Rate:** 1–10 msg/s per device
- **Protocol:** UDP port 514 or 5514
- **Structure:** `<PRI>timestamp hostname tag: message`

---

## Stage 2: Listener Receives and Parses

### Code Path
```
sock.recvfrom(8192)  → Raw bytes
      ↓
parse_message()      → Parse RFC 3164 or 5424
      ↓
Extract fields       → Structured dict
```

### Raw Packet In
```
From: 192.168.1.10:59234 (switch-floor1)
Data: <131>May  4 15:30:00 switch-floor1 ciscoios: Power supply 1 fault detected
```

### Parsed Event Dict Out
```python
{
    'rfc': '3164',
    'src_ip': '192.168.1.10',
    'received_at': '2026-05-04T15:30:00Z',
    'timestamp': 'May  4 15:30:00',
    'host': 'switch-floor1',
    'facility': 'local0',
    'severity': 'err',
    'tag': 'ciscoios',
    'message': 'Power supply 1 fault detected'
}
```

### Data at this stage:
- **Format:** Python dictionary
- **Size:** ~1 KB per event
- **Structure:** Parsed syslog fields
- **Location:** In memory (RAM)
- **Action:** Print to console (for syslog_listener.py demo) OR pass to aggregator (for main.py production)

---

## Stage 3: Device Resolution

### Code Path
```
aggregator.ingest(event, device_meta)
      ↓
config.resolve_device(src_ip, hostname)
      ↓
Lookup in device_map
      ↓
Return: device_id, site, type
```

### Input
```python
event = {
    'src_ip': '192.168.1.10',
    'host': 'switch-floor1',
    'severity': 'err',
    'message': 'Power supply 1 fault detected'
}
```

### Lookup in config.py
```python
device_map = {
    "192.168.1.10|switch-floor1": {
        "device_id": "dev-001",
        "site": "hq",
        "type": "switch"
    }
}
```

### Output (device_meta)
```python
device_meta = {
    "device_id": "dev-001",
    "site": "hq",
    "type": "switch"
}
```

### Data at this stage:
- **Format:** Python dictionary
- **Purpose:** Link syslog to a canonical device ID
- **Location:** In memory
- **Action:** Pass to aggregator for health scoring

---

## Stage 4: Classification and Noise Filtering

### Code Path
```
classify(message, severity)
      ↓
Match against regex patterns
      ↓
Return: category
         ↓
is_noise(severity, category)
      ↓
Decide: Keep or Drop
```

### Example Classifications

| Message | Severity | Category | Noise? | Action |
|---------|----------|----------|--------|--------|
| `Power supply 1 fault detected` | err | `hardware` | No | **Keep** |
| `CPU utilization at 95%` | warning | `performance` | No | **Keep** |
| `User alice logged in from 10.0.5.1` | info | `auth` | No | **Keep** |
| `DHCP lease granted to client XX:XX...` | info | `other` | **Yes** | **Drop** |
| `Debug: buffer allocation failed` | debug | `other` | **Yes** | **Drop** |

### Data at this stage:
- **Format:** Same event dict + category field
- **Purpose:** Filter spam, categorize for health scoring
- **Location:** In memory
- **Action:** Keep or discard based on noise filter

---

## Stage 5: Deduplication

### Code Path
```
Create signature: normalize numbers in message
      ↓
Check if seen in last 60 seconds
      ↓
If yes: skip (already counted)
If no:  append to rolling window
```

### Example

**T=0s:** `Interface GigabitEthernet0/3 link state changed to down` → Store
**T=10s:** `Interface GigabitEthernet0/3 link state changed to down` → **Skip (duplicate)**
**T=30s:** `Interface GigabitEthernet0/47 link state changed to down` → **Skip (same signature)**
**T=70s:** `Interface GigabitEthernet0/3 link state changed to down` → Store (60s expired)

### Data at this stage:
- **Format:** Deduplicated event queue (5-minute rolling window)
- **Purpose:** Prevent event storms from inflating scores
- **Location:** In memory (DeviceState.events)
- **Size:** ~50–100 events per device in the window

---

## Stage 6: Health Scoring

### Code Path
```
Count errors and warnings in window
      ↓
Calculate score: 100 − (errors×8) − (warns×2)
      ↓
Determine status: healthy / degraded / unhealthy
      ↓
List reasons: error_rate_high, link_flap, etc.
```

### Example Calculation

**Window contains (last 5 minutes):**
```
Power supply fault        → error (−8)
Link down (port 3)        → error (−8)
Link down (port 5)        → error (−8)
CPU high 95%              → warning (−2)
CPU high 92%              → warning (−2) [deduped, not counted again]
Memory high 88%           → warning (−2)
Config saved              → info (0)
User login                → info (0)
```

**Score calculation:**
```
Start:                  100
−3 errors × 8:         100 − 24 = 76
−2 warnings × 2:       76 − 4 = 72
No silence penalty:    72
Final score:           72

Status: DEGRADED (60 ≤ 72 < 85)
Reasons: ["error_rate_high", "link_flap", "hardware_fault"]
```

### Data at this stage:
- **Format:** Status string, score int, reasons list
- **Purpose:** Summarize device health
- **Location:** In memory (DeviceState.last_status)
- **Frequency:** Computed every time an event arrives, and every 60 seconds

---

## Stage 7: Summary Building (JSON)

### Code Path
```
_build_summary(state, clock, kind)
      ↓
Extract health, metrics, top events
      ↓
Format as JSON
      ↓
Return dict (ready to serialize)
```

### JSON Summary (Periodic)

```json
{
  "schema_version": "1.0",
  "kind": "periodic",
  "edge_id": "edge-box-7",
  "device_id": "dev-001",
  "site": "hq",
  "device_type": "switch",
  "reported_at": 1699999999.5,
  "window_seconds": 300,
  "health": {
    "status": "degraded",
    "score": 72,
    "reasons": ["error_rate_high", "link_flap", "hardware_fault"]
  },
  "metrics": {
    "event_count": 8,
    "msg_rate_per_min": 9.6,
    "error_count": 3,
    "warn_count": 2,
    "last_seen_seconds_ago": 1.2,
    "categories": {
      "hardware": 1,
      "link": 2,
      "performance": 3,
      "config": 1,
      "auth": 1
    }
  },
  "top_events": [
    {
      "ts": 1699999980.0,
      "severity": "err",
      "category": "hardware",
      "message": "Power supply 1 fault detected"
    },
    {
      "ts": 1699999975.0,
      "severity": "err",
      "category": "link",
      "message": "Interface GigabitEthernet0/3 link state changed to down"
    }
  ]
}
```

### Data at this stage:
- **Format:** JSON-serializable Python dict
- **Size:** ~1.2 KB per message
- **Purpose:** Cloud-ready payload
- **Location:** In memory, ready to queue
- **Frequency:** Every 60 seconds (periodic) + immediately on status change (transition)

---

## Stage 8: Queue Storage (SQLite)

### Code Path
```
enqueue(payload_dict)
      ↓
json.dumps(payload)       → Convert dict to JSON string
      ↓
INSERT into SQLite        → Store row
      ↓
Check queue size
      ↓
Trim if over limit
```

### Database Schema
```sql
CREATE TABLE outbound (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enqueued_at REAL,
    kind TEXT,              -- "periodic", "transition", "edge_health"
    payload TEXT,           -- JSON string
    attempts INTEGER
);
```

### Example Rows in Queue

```
id | enqueued_at   | kind        | payload                              | attempts
───┼───────────────┼─────────────┼──────────────────────────────────────┼─────────
 1 | 1699999900.0  | periodic    | {"device_id":"dev-001","status":"..."}│ 0
 2 | 1699999920.1  | transition  | {"device_id":"dev-001","status":"..."}│ 0
 3 | 1699999960.0  | periodic    | {"device_id":"dev-002","status":"..."}│ 0
 4 | 1699999999.5  | edge_health | {"tracked_devices":6,"unhealthy":1}   │ 0
```

### Data at this stage:
- **Format:** SQLite database rows
- **Size:** ~1.2 KB per row
- **Location:** Disk file (survives power loss, restarts)
- **Retention:** Up to 5,000 periodic + 20,000 other rows
- **Purpose:** Offline resilience (queue survives cloud outages)

---

## Stage 9: Uploader Batches Messages

### Code Path
```
take_batch(10)            → Read up to 10 rows from queue
      ↓
Extract payload from each row
      ↓
Build envelope
      ↓
POST to cloud
```

### Envelope (HTTP POST Body)

```json
{
  "edge_id": "edge-box-7",
  "messages": [
    {
      "schema_version": "1.0",
      "kind": "periodic",
      "device_id": "dev-001",
      "health": {
        "status": "degraded",
        "score": 72,
        "reasons": ["error_rate_high"]
      },
      ...
    },
    {
      "schema_version": "1.0",
      "kind": "transition",
      "device_id": "dev-002",
      "health": {
        "status": "unhealthy",
        "score": 45,
        "reasons": ["silent_for_200s"]
      },
      ...
    },
    {
      "schema_version": "1.0",
      "kind": "edge_health",
      "device_id": "_edge:edge-box-7",
      "metrics": {
        "tracked_devices": 6,
        "unhealthy_devices": 2,
        "queue_depth": 42
      }
    }
  ]
}
```

### Data at this stage:
- **Format:** JSON (ready for HTTP)
- **Size:** 1–10 messages per POST (~1–12 KB)
- **Batch frequency:** Every 2 seconds (if queue has messages)
- **Purpose:** Efficient bulk upload to cloud

---

## Stage 10: HTTPS POST to Cloud

### HTTP Request

```
POST /api/v1/ingest HTTP/1.1
Host: dashboard.company.com
Authorization: Bearer YOUR-API-KEY-HERE
Content-Type: application/json
Content-Length: 8542

{
  "edge_id": "edge-box-7",
  "messages": [...]
}
```

### HTTP Response

**Success (200 OK):**
```
HTTP/1.1 200 OK
Content-Type: application/json

{"status": "accepted", "messages_processed": 3}
```

**Action:** ACK in queue (delete those 3 rows)

**Failure (503 Service Unavailable):**
```
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{"error": "database maintenance"}
```

**Action:** Keep in queue, retry with backoff (30s → 60s → 120s → ...)

### Data at this stage:
- **Format:** HTTPS JSON
- **Encryption:** TLS/SSL (encrypted in transit)
- **Authentication:** Bearer token in header
- **Location:** Network (between edge box and cloud)
- **Retry:** Automatic exponential backoff

---

## Stage 11: Cloud Dashboard Storage

### Cloud Receives POST

```json
{
  "edge_id": "edge-box-7",
  "messages": [
    {
      "device_id": "dev-001",
      "health": {
        "status": "degraded",
        "score": 72
      }
    }
  ]
}
```

### Cloud Stores in Database

```sql
INSERT INTO device_health (
    edge_id,
    device_id,
    status,
    score,
    reasons,
    payload_json,
    received_at
) VALUES (
    'edge-box-7',
    'dev-001',
    'degraded',
    72,
    '["error_rate_high"]',
    '{full json}',
    NOW()
);
```

### Cloud Dashboard Displays

```
┌─────────────────────────────────────────────────┐
│ Device Health Dashboard                          │
├─────────────────────────────────────────────────┤
│                                                  │
│ EDGE BOX: edge-box-7 (hq)                       │
│ Updated: 5 seconds ago                          │
│ Tracked devices: 6                              │
│ Unhealthy: 1                                    │
│                                                  │
├─────────────────────────────────────────────────┤
│                                                  │
│ dev-001 (switch-floor1)         [DEGRADED] 72/100
│   • error_rate_high                             │
│   • link_flap                                   │
│   • hardware_fault                              │
│   Last event: Power supply 1 fault              │
│                                                  │
│ dev-002 (switch-floor2)         [HEALTHY]  95/100
│   No issues                                      │
│                                                  │
│ dev-003 (router-edge)           [HEALTHY]  89/100
│   No issues                                      │
│                                                  │
│ dev-004 (firewall-dmz)          [UNHEALTHY] 35/100
│   • error_rate_high                             │
│   • silent_for_240s (device offline)            │
│   Last event: 4 minutes ago                     │
│                                                  │
└─────────────────────────────────────────────────┘
```

---

## Complete Timeline Example

```
T=0s
─────────────────────────────────────────────────────
[Network Device] Switch sends: <131>...Power supply fault
[Listener] Receives UDP packet, parses to dict
[Config] Resolves: 192.168.1.10|switch-floor1 → dev-001
[Aggregator] Classifies: hardware, not noise
[Aggregator] Score: 100 − 8 = 92 (still healthy)

T=5s
─────────────────────────────────────────────────────
[Network Device] Switch sends: <131>...Link down port 3
[Listener] Receives, parses
[Aggregator] Classifies: link, not noise
[Aggregator] Score: 92 − 8 = 84 (still healthy)

T=8s
─────────────────────────────────────────────────────
[Network Device] Switch sends: <131>...Link down port 5
[Listener] Receives, parses
[Aggregator] Classifies: link, not noise
[Aggregator] Score: 84 − 8 = 76 (DEGRADED!)
[Aggregator] Status changed: healthy → degraded
[Aggregator] BUILD TRANSITION ALERT & ENQUEUE
[Queue] INSERT row: kind=transition, status=degraded

T=8.5s
─────────────────────────────────────────────────────
[Uploader] Checks queue every 2 seconds
[Uploader] Finds 1 message: transition alert
[Uploader] POST to cloud:
  {
    "edge_id": "edge-box-7",
    "messages": [
      {
        "kind": "transition",
        "device_id": "dev-001",
        "health": {
          "status": "degraded",
          "score": 76,
          "reasons": ["error_rate_high", "link_flap", "hardware_fault"]
        }
      }
    ]
  }

T=9s
─────────────────────────────────────────────────────
[Cloud] Receives POST, stores in database
[Cloud Dashboard] INSTANTLY shows:
  ⚠️ dev-001 (switch-floor1) is DEGRADED
  🔴 Reasons: error_rate_high, link_flap, hardware_fault
  📊 Score: 76/100
  📝 Recent events: Power supply fault, Link down x2

[Uploader] Receives 200 OK from cloud
[Uploader] ACK (delete row from local queue)

T=60s (next periodic)
─────────────────────────────────────────────────────
[Aggregator] Periodic timer fires
[Aggregator] BUILD SUMMARY for all 6 devices
[Aggregator] ENQUEUE 6 periodic + 1 edge_health = 7 messages
[Queue] INSERT 7 rows

T=62s
─────────────────────────────────────────────────────
[Uploader] Checks queue, finds 7 messages
[Uploader] POST batch of 7 to cloud
[Cloud] Receives and stores
[Uploader] Gets 200 OK, ACK all 7 rows
[Queue] Empty again
```

---

## Data Summary Table

| Stage | Format | Size | Location | Frequency |
|-------|--------|------|----------|-----------|
| 1. Raw syslog | Plain text | 100–300 B | Network (UDP) | 1–10 msg/s |
| 2. Parsed event | Python dict | ~1 KB | RAM | Immediate |
| 3. Device meta | Python dict | ~200 B | RAM | Immediate |
| 4. Classified | Python dict | ~1 KB | RAM | Immediate |
| 5. Deduplicated | Event in queue | ~500 B | RAM (rolling window) | Rolling |
| 6. Health score | Status + score | ~50 B | RAM | Per-event + /60s |
| 7. Summary JSON | Python dict | ~1.2 KB | RAM | /60s + on transition |
| 8. Queue storage | SQLite row | ~1.2 KB | Disk | /60s + transitions |
| 9. Batch envelope | JSON | 1–12 KB | RAM | /2s (if messages) |
| 10. HTTPS POST | JSON | 1–12 KB | Network (TLS) | /2s (if messages) |
| 11. Cloud storage | Database row | ~1.2 KB | Cloud DB | Immediate |

---

## Key Takeaways

✅ **Raw syslog** (100–300 B) → **Aggregated summary** (1.2 KB)
- 5–12x compression through summarization

✅ **Periodic heartbeat** (every 60s) + **Transition alerts** (immediate)
- Balances constant monitoring with efficient bandwidth

✅ **Queue survives** edge box restarts and cloud outages
- Messages kept on disk in SQLite

✅ **Batch upload** (up to 10 per POST)
- Efficient use of HTTPS connections

✅ **Cloud receives** complete device status
- Status, score, reasons, metrics, top 5 events

✅ **Real-time visibility**
- From raw syslog to cloud dashboard: ~100–200ms latency
