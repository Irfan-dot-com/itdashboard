# Syslog Patterns — Complete Reference

This document explains every syslog message the simulator can generate,
how each message is structured on the wire, how it is classified, and
what effect it has on device health scoring.

---

## 1. The Wire Format (What Gets Sent Over UDP)

Every simulated message follows **RFC 3164** (the classic BSD syslog format):

```
<PRI>Mmm DD HH:MM:SS hostname tag: message text
```

**Real example:**
```
<131>May  4 10:22:01 switch-floor1 ciscoios: Power supply 1 fault detected
```

Breaking it down field by field:

| Part | Example | Meaning |
|------|---------|---------|
| `<131>` | `<PRI>` | Priority byte = Facility × 8 + Severity |
| `May  4 10:22:01` | Timestamp | Month, space-padded day, time — note TWO spaces before single-digit day |
| `switch-floor1` | Hostname | The device that sent the log |
| `ciscoios` | Tag | The process/daemon name on that device |
| `Power supply 1 fault detected` | Message | The actual log text |

### How the PRI byte is calculated

```
PRI = Facility × 8 + Severity
```

The simulator always uses **Facility = local0 (16)**:

| Severity Name | Severity Code | PRI (local0) | Example |
|--------------|--------------|--------------|---------|
| critical (crit) | 2 | 130 | `<130>` |
| error (err) | 3 | 131 | `<131>` |
| warning | 4 | 132 | `<132>` |
| notice | 5 | 133 | `<133>` |
| informational (info) | 6 | 134 | `<134>` |

When the listener parses `<131>`:
- 131 ÷ 8 = 16 remainder 3
- Facility = 16 → `local0`
- Severity = 3 → `err`

---

## 2. The Six Simulated Devices

Each device has a fixed hostname, a syslog tag, and a health profile that
controls how often it sends info vs. warning vs. error messages.

| Device | Hostname | Tag | Profile | Meaning |
|--------|----------|-----|---------|---------|
| Switch Floor 1 | `switch-floor1` | `ciscoios` | healthy | Reliable switch, mostly clean traffic |
| Switch Floor 2 | `switch-floor2` | `ciscoios` | flaky | Unreliable switch, frequent warnings and errors |
| Edge Router | `router-edge` | `junos` | healthy | Juniper router, mostly clean |
| Lobby AP | `ap-lobby` | `hostapd` | healthy | Wireless access point, mostly clean |
| DMZ Firewall | `firewall-dmz` | `pf` | degraded | Firewall under stress, high error rate |
| HVAC Sensor | `sensor-hvac-01` | `modbus` | healthy | Industrial sensor, mostly clean |

### Health Profiles — Message Distribution

| Profile | % Info/Notice | % Warning | % Error |
|---------|--------------|-----------|---------|
| `healthy` | 92% | 7% | 1% |
| `flaky` | 65% | 25% | 10% |
| `degraded` | 40% | 35% | 25% |

At a rate of 5 msg/s over 60 seconds (300 messages), a **degraded** device
like `firewall-dmz` would produce roughly:
- 120 info/notice messages
- 105 warning messages
- 75 error messages

This is enough to trigger `unhealthy` status quickly.

---

## 3. Every Message Template — Complete List

The simulator has 12 message templates split into three severity classes.
Each line below shows: the template, the severity code sent, the PRI byte,
and the category assigned by `classify.py`.

---

### INFO / NOTICE messages (Severity 6 or 5)

These represent normal, expected activity.

---

#### INFO-1: Link Up
```
<134>May  4 10:22:01 switch-floor1 ciscoios: Interface GigabitEthernet0/12 link state changed to up
```
| Field | Value |
|-------|-------|
| Severity code | 6 (info) — PRI `<134>` |
| Tag | varies by device |
| Template | `Interface GigabitEthernet0/{p} link state changed to up` |
| `{p}` | Random port number 0–47 |
| Category | `link` |
| Noise? | No — `link` category info is kept |
| Effect on score | None (positive event) |

**What this means in real life:** A network port came back online. Normal after a reboot, cable reconnect, or STP convergence.

---

#### INFO-2: User Login
```
<134>May  4 10:22:01 router-edge junos: User alice logged in from 10.0.193.60
```
| Field | Value |
|-------|-------|
| Severity code | 6 (info) — PRI `<134>` |
| Template | `User {u} logged in from 10.0.{a}.{b}` |
| `{u}` | Random: `admin`, `netops`, `alice`, or `bob` |
| `{a}`, `{b}` | Random IP octets |
| Category | `auth` |
| Noise? | No — `auth` category info is kept |
| Effect on score | None |

**What this means in real life:** A network engineer logged into the device management interface.

---

#### INFO-3: DHCP Lease
```
<134>May  4 10:22:01 ap-lobby hostapd: DHCP lease granted to client ab:4e:ea:f1:db:44
```
| Field | Value |
|-------|-------|
| Severity code | 6 (info) — PRI `<134>` |
| Template | `DHCP lease granted to client {mac}` |
| `{mac}` | Random 6-byte MAC address (`xx:xx:xx:xx:xx:xx`) |
| Category | `other` |
| Noise? | **Yes** — `other` + `info` = noise, dropped |
| Effect on score | None (dropped before aggregation) |

**What this means in real life:** A device (laptop, phone, printer) connected to the network and received an IP address. Very common, very noisy — correctly dropped.

---

#### NOTICE-4: Config Saved
```
<133>May  4 10:22:01 switch-floor1 ciscoios: Configuration saved by user bob
```
| Field | Value |
|-------|-------|
| Severity code | 5 (notice) — PRI `<133>` |
| Template | `Configuration saved by user {u}` |
| `{u}` | Random: `admin`, `netops`, `alice`, or `bob` |
| Category | `config` |
| Noise? | No — notice severity is kept regardless of category |
| Effect on score | None |

**What this means in real life:** A network engineer saved the running configuration to persistent memory. Important audit trail.

---

### WARNING messages (Severity 4)

These represent degraded but not failed conditions. They reduce the health score by 2 points each (up to −20 total).

---

#### WARN-1: CPU High
```
<132>May  4 10:22:01 firewall-dmz pf: CPU utilization at 86%
```
| Field | Value |
|-------|-------|
| Severity code | 4 (warning) — PRI `<132>` |
| Template | `CPU utilization at {pct}%` |
| `{pct}` | Random 70–99% |
| Category | `performance` |
| Noise? | No |
| Effect on score | −2 points per event |

**What this means in real life:** The device processor is overloaded. Could cause packet drops, slow response, or instability. Common on firewalls doing deep packet inspection.

---

#### WARN-2: Memory High
```
<132>May  4 10:22:01 switch-floor2 ciscoios: Memory usage high: 93%
```
| Field | Value |
|-------|-------|
| Severity code | 4 (warning) — PRI `<132>` |
| Template | `Memory usage high: {pct}%` |
| `{pct}` | Random 70–99% |
| Category | `performance` |
| Noise? | No |
| Effect on score | −2 points per event |

**What this means in real life:** Device is running low on RAM. Could lead to process crashes or reboots if it continues rising.

---

#### WARN-3: Temperature High
```
<132>May  4 10:22:01 router-edge junos: Temperature sensor reading 72C
```
| Field | Value |
|-------|-------|
| Severity code | 4 (warning) — PRI `<132>` |
| Template | `Temperature sensor reading {temp}C` |
| `{temp}` | Random 45–85°C |
| Category | `thermal` |
| Noise? | No |
| Effect on score | −2 points per event |

**What this means in real life:** Internal temperature is elevated. Above ~85°C most hardware starts throttling or shutting down. May indicate blocked airflow or failed cooling fan.

---

#### WARN-4: Packet Loss
```
<132>May  4 10:22:01 switch-floor2 ciscoios: Packet loss detected on interface eth7
```
| Field | Value |
|-------|-------|
| Severity code | 4 (warning) — PRI `<132>` |
| Template | `Packet loss detected on interface eth{p}` |
| `{p}` | Random port number 0–47 |
| Category | `performance` |
| Noise? | No |
| Effect on score | −2 points per event |

**What this means in real life:** The interface is dropping packets. Could be a duplex mismatch, a bad cable, or congestion. Users would experience slow or intermittent connectivity.

---

### ERROR messages (Severity 3 or 2)

These represent failures. They reduce the health score by 8 points each (up to −60 total). Multiple errors quickly push a device to `degraded` or `unhealthy`.

---

#### ERROR-1: Link Down
```
<131>May  4 10:22:01 switch-floor1 ciscoios: Interface GigabitEthernet0/3 link state changed to down
```
| Field | Value |
|-------|-------|
| Severity code | 3 (err) — PRI `<131>` |
| Template | `Interface GigabitEthernet0/{p} link state changed to down` |
| `{p}` | Random port 0–47 |
| Category | `link` |
| Noise? | No |
| Effect on score | −8 points per event |
| Special reason | Three or more link events → `link_flap` added to health reasons |

**What this means in real life:** A port lost its connection. Could be a cable pull, a connected device powering off, or a physical fault. Repeated up/down cycles (link flap) indicate a hardware problem.

---

#### ERROR-2: Authentication Failure
```
<131>May  4 10:22:01 switch-floor2 ciscoios: Authentication failure for user admin from 10.0.67.54
```
| Field | Value |
|-------|-------|
| Severity code | 3 (err) — PRI `<131>` |
| Template | `Authentication failure for user {u} from 10.0.{a}.{b}` |
| `{u}` | Random: `admin`, `netops`, `alice`, `bob` |
| `{a}`, `{b}` | Random IP octets |
| Category | `auth` |
| Noise? | No |
| Effect on score | −8 points per event |

**What this means in real life:** Someone tried and failed to log in. A few of these are normal (typos). A burst of these from the same IP is a brute-force attack attempt.

---

#### ERROR-3: Power Supply Fault
```
<131>May  4 10:22:01 firewall-dmz pf: Power supply 2 fault detected
```
| Field | Value |
|-------|-------|
| Severity code | 3 (err) — PRI `<131>` |
| Template | `Power supply {n} fault detected` |
| `{n}` | Random: 1 or 2 |
| Category | `hardware` |
| Noise? | No |
| Effect on score | −8 points per event |

**What this means in real life:** One of the redundant power supplies has failed. The device is still running on the other one but is now at risk — any further power issue would cause a full outage.

---

#### ERROR-4: BGP Down (Severity 2)
```
<130>May  4 10:22:01 router-edge junos: BGP neighbor 10.0.193.60 state changed to Idle
```
| Field | Value |
|-------|-------|
| Severity code | 2 (crit) — PRI `<130>` |
| Template | `BGP neighbor 10.0.{a}.{b} state changed to Idle` |
| `{a}`, `{b}` | Random IP octets |
| Category | `routing` |
| Noise? | No |
| Effect on score | −8 points per event |

**What this means in real life:** The BGP routing session with a neighboring router has dropped. This is a critical event — it means the router is no longer exchanging routes with that peer. Traffic may be rerouted or lost depending on redundancy.

---

## 4. Deduplication — How the Aggregator Handles Repeated Messages

The aggregator normalizes numbers before deduplication. This means:

```
Interface GigabitEthernet0/3 link state changed to down
Interface GigabitEthernet0/47 link state changed to down
```

Both produce the same signature: `link state changed to down`. Within a 60-second window, only the first is stored. This prevents a port-flap storm from flooding the health score.

After 60 seconds, the signature expires and the same type of message can be recorded again.

---

## 5. Burst Mode (`--burst` flag)

When the simulator runs with `--burst`, it occasionally picks one device and
floods it with errors for 10–25 messages in a row:

```
--- Incident starting on switch-floor2 ---
```

During a burst, only ERROR class messages are sent (ERROR-1 through ERROR-4),
chosen randomly. This simulates a real incident like a power supply failing,
a BGP session dropping, and link ports going down simultaneously.

**Effect on the aggregator:** The burst will very quickly push the device's
health score below 60, triggering a `healthy → unhealthy` transition alert
that is immediately enqueued for cloud upload — without waiting for the
60-second periodic summary.

---

## 6. What the Aggregator Does With Each Message Type

| Category | Severity | Score Impact | Reason Added |
|----------|----------|-------------|--------------|
| `link` (up) | info | none | — |
| `link` (down) | error | −8 | `link_flap` if 3+ link events |
| `auth` (login) | info | none | — |
| `auth` (failure) | error | −8 | `error_rate_high` |
| `hardware` | error | −8 | `error_rate_high` |
| `performance` | warning | −2 | `warn_rate_high` |
| `thermal` | warning | −2 | `warn_rate_high` |
| `routing` | error (crit) | −8 | `error_rate_high` |
| `config` | notice | none | — |
| `other` + info | info | **dropped** | noise filter |
| DHCP | info | **dropped** | noise filter |
| any | debug | **dropped** | noise filter |

**Health thresholds:**
- Score ≥ 85 → `healthy`
- Score 60–84 → `degraded`
- Score < 60 → `unhealthy`
- No activity past 180 seconds → `unhealthy` (silent device)
