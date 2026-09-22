# Cloud Side on Windows / IIS — Deployment Guide

Deploying **only the cloud portion** — the FastAPI backend and the dashboard UI
— on a Windows Server running IIS.

The syslog agent and the SD-LAN poller are unaffected. They stay on Ubuntu edge
boxes on the customer network, because that is where the devices are. They just
point their `cloud_endpoint` at this server instead.

> **Read section 3 before you commit to this.** The app depends on Redis, and
> Redis has no official Windows build. That is the one genuine obstacle, and it
> needs a decision rather than a workaround.

---

## 1. Is IIS the right host? An honest assessment

The good news, from reading the code:

- **No Linux-specific code anywhere in `app/`.** No `uvloop` import, no signal
  handlers, no hardcoded `/var` or `/etc` paths. The application is portable.
- **Every dependency has Windows wheels** — `asyncpg`, `psycopg2-binary`,
  `cryptography`, `httptools`. `uvicorn[standard]` excludes `uvloop` on Windows
  via a platform marker, so it installs cleanly and falls back to the asyncio
  event loop.
- **The frontend is a static Vite build.** IIS serves static files very well;
  this half is genuinely easier on IIS than on Linux.

The costs:

| Cost | Detail |
|---|---|
| **Redis** | No official Windows build. Section 3. |
| **App pool recycling** | IIS recycles pools by default. That kills the background outbox poller and every open SSE connection. Must be turned off. |
| **SSE buffering** | IIS buffers responses by default, which silently breaks the live event stream. Must be turned off. |
| **No `gunicorn`** | Doesn't run on Windows. Single-process uvicorn under IIS, which is fine at this scale. |
| **Two extra IIS modules** | HttpPlatformHandler and URL Rewrite, both Microsoft downloads. |

**If you have the choice**, a small Linux VM with
`infra_docker/docker-compose.tls.yml` is substantially less work — one command,
automatic TLS, Redis included, nothing to reason about. **If IIS is the
constraint** (existing server, existing certificates, Windows-only policy,
your admins' comfort), everything below works; the two settings that bite are
called out explicitly and `Test-ItDashboard.ps1` checks both.

---

## 2. Prerequisites

On the Windows Server:

| Item | Notes |
|---|---|
| Windows Server 2019 or 2022, IIS installed | |
| **Python 3.11+ (64-bit)** | python.org installer, "Add to PATH" |
| **PostgreSQL 16 for Windows** | EDB installer; runs as a Windows service |
| **A Redis-compatible server** | see section 3 |
| **HttpPlatformHandler** | https://www.iis.net/downloads/microsoft/httpplatformhandler |
| **URL Rewrite** | https://www.iis.net/downloads/microsoft/url-rewrite |
| Node 22+ | only to build the frontend; you can build elsewhere and copy `dist\` |
| A TLS certificate in the machine store | you probably already have one bound in IIS |
| A DNS name pointing at the server | |

Verify the IIS modules:

```powershell
Get-WebGlobalModule | Where-Object Name -match 'httpPlatform|Rewrite'
```

---

## 3. Redis on Windows — pick one

The app uses Redis for exactly two things, and **only four commands**:

| Command | Used for |
|---|---|
| `PUBLISH` | `outbox_poller` fans events out to SSE subscribers |
| `SUBSCRIBE` / `PSUBSCRIBE` | `/v1/stream` receives them |
| `SETEX` / `GET` | idempotency keys for `POST /v1/alerts/{id}/auto-fix`, 24h TTL |
| `PING` | the `/readyz` health probe |

That is a very small surface, which is what makes the options below realistic.

### Option A — Memurai (recommended)

A native Windows build that is Redis-compatible. Installs as a Windows service,
listens on 6379, and speaks the protocol the `redis` Python client expects.

- Developer Edition is free but **not licensed for production**.
- Production Edition is commercial. Budget for it, or pick another option.
- `REDIS_URL=redis://127.0.0.1:6379` — nothing in the app changes.

### Option B — Redis in WSL2 on the server

Windows Server 2019+ supports WSL2. Install Ubuntu, `apt install redis-server`,
bind it to 127.0.0.1, and reach it from Windows on localhost.

- Free and genuinely Redis.
- But: WSL2 on a production server is unusual, it needs its own start-on-boot
  arrangement (WSL does not autostart a service by default), and it is one more
  thing your admins have to understand. Workable for a pilot; I would not want
  it under a customer SLA.

### Option C — Replace Redis with PostgreSQL

Given only four commands are in use, this is more tractable than it sounds:

- **Pub/sub** → Postgres `LISTEN` / `NOTIFY`. `asyncpg` supports
  `add_listener()` directly, and the outbox poller already polls Postgres every
  100 ms — Redis is only the fan-out hop. Channel names are already
  `hosp:prop:<id>`.
- **Idempotency** → a small table with an expiry column, which is arguably
  better than a TTL key since it survives a restart.

Caveat: `NOTIFY` payloads are capped at 8000 bytes. Some `alert.opened` events
carry a summary and recommended action and could approach that. The safe
pattern is to `NOTIFY` with just the `outbox_id` and have the subscriber read
the row — a small change to `outbox_poller.py` and `stream.py`.

This removes a whole service from the deployment. It is maybe half a day of
work plus testing, and it is the option I would choose if this server is going
to be maintained by Windows admins for years. **Say the word and I'll implement
it** — it is a contained change to two files plus a migration.

### Not an option

The old Microsoft Redis port (`redis-64` 3.0.504, last touched 2016) still
turns up in search results. It is unsupported, years behind on security fixes,
and predates half the protocol the modern client uses. Don't.

---

## 4. Install

Copy the repo to the server, then from `backend\deploy_iis\` in an **elevated**
PowerShell:

```powershell
.\Install-ItDashboard.ps1 `
    -RepoRoot    C:\MyGIT\it-dashboard `
    -PublicUrl   https://dashboard.yourdomain.com `
    -DatabaseUrl "postgresql://hosp:YOUR_PASSWORD@127.0.0.1:5432/hosp_prod" `
    -RedisUrl    "redis://127.0.0.1:6379"
```

It creates the virtualenv, installs dependencies, runs
`alembic upgrade head`, registers the `bluip` service provider, writes
`web.config` with your real paths and connection strings, creates both
application pools and sites, grants the app pool identity write access to the
log directory, and **disables idle timeout and periodic recycling** on the API
pool.

It is idempotent and never overwrites an existing `web.config` or database.

It deliberately does **not** bind HTTPS — certificate handling is yours:

```powershell
New-WebBinding -Name ItDashboardApi -Protocol https -Port 443 `
               -HostHeader dashboard.yourdomain.com
# then assign the certificate in IIS Manager (Site Bindings -> Edit), or:
Get-ChildItem Cert:\LocalMachine\My        # find the thumbprint
New-Item IIS:\SslBindings\0.0.0.0!443 -Value <thumbprint>
```

---

## 5. Layout

Two IIS sites, one hostname:

```
https://dashboard.yourdomain.com
  │
  ├── /v1/*  /livez  /readyz  /docs   ──►  ItDashboardApi site
  │                                        HttpPlatformHandler launches
  │                                        venv\Scripts\python.exe -m uvicorn
  │                                        app.main:app on a private port
  │
  └── everything else                 ──►  ItDashboardWeb site
                                           static Vite build + SPA fallback
```

Serving both from one origin means the browser never makes a cross-origin
request, so CORS is irrelevant. (`app/main.py` currently sets
`allow_origins=["*"]`; with this layout you can tighten it to the one domain or
drop the middleware.)

If you'd rather use two hostnames, `web.frontend.config` documents the changes
— and remember `VITE_API_BASE_URL` is baked in at **build** time, so changing
the hostname later means rebuilding the frontend.

---

## 6. The two settings that will bite you

Both produce silent failures. Both are checked by `Test-ItDashboard.ps1`.

### 6a. App pool recycling kills the background worker

The API runs `run_outbox_poller` as an asyncio task for the process lifetime,
and holds SSE connections open indefinitely. IIS **by default** idles an app
pool out after 20 minutes of no requests and restarts it every 29 hours.

Symptom: events stop reaching the dashboard after a quiet period, then resume
when someone loads a page. Nothing in any log says why.

```powershell
Set-ItemProperty IIS:\AppPools\ItDashboardApi -Name processModel.idleTimeout -Value "00:00:00"
Set-ItemProperty IIS:\AppPools\ItDashboardApi -Name recycling.periodicRestart.time -Value "00:00:00"
Set-ItemProperty IIS:\AppPools\ItDashboardApi -Name recycling.periodicRestart.requests -Value 0
Set-ItemProperty IIS:\AppPools\ItDashboardApi -Name startMode -Value "AlwaysRunning"
```

### 6b. Response buffering breaks Server-Sent Events

IIS buffers responses before sending them. `GET /v1/stream` is an endless
stream, so a buffered response is **never** flushed: the browser receives
nothing, forever, with no error.

`web.config` handles this with `responseBufferLimit="0"` on the handler and
`doDynamicCompression="false"` (compression buffers too). Keep both.

If you use ARR reverse-proxying instead of HttpPlatformHandler, you must also
raise the ARR proxy timeout (default 2 minutes) and disable response buffering
in the ARR proxy settings — otherwise the stream is cut every two minutes.

`Test-ItDashboard.ps1` check 8 opens a real connection to `/v1/stream` and
fails if no bytes arrive within 25 seconds. That is the only reliable way to
know this is right.

### Also worth knowing

`processesPerApplication` stays **1**. Each process starts its own outbox
poller; `FOR UPDATE SKIP LOCKED` keeps that safe, but events published by one
process only reach SSE clients on another if Redis pub/sub is genuinely shared.
One process avoids the question entirely. Scale by adding a second server
behind a load balancer, once Redis is confirmed shared.

---

## 7. Verify

```powershell
.\Test-ItDashboard.ps1 -BaseUrl https://dashboard.yourdomain.com
```

Eleven checks: IIS modules, app pool recycling settings, buffering settings in
`web.config`, the virtualenv and its imports, Alembic at head, the
Redis-compatible server (it actually runs `SETEX`, `GET` and `PUBLISH`),
`/livez` and `/readyz` through IIS, **live SSE delivery**, the dashboard UI,
a real ingest POST, and whether `/docs` is exposed.

Exit code is non-zero if anything failed. Fix every FAIL before pointing an
edge agent at the server.

A 502 from `/livez` means the Python process failed to start. Look in
`C:\inetpub\itdashboard-api\logs\` for the uvicorn stdout log — HttpPlatformHandler
captures it there, and it is the first place to look for any startup problem.

---

## 8. Point the agents at it

In `/etc/edge-agent/config.json` (syslog) and `/etc/sdlan-poller/config.json`
(poller) on each Ubuntu box:

```json
"cloud_endpoint": "https://dashboard.yourdomain.com/v1/edge/ingest",
"service_provider": "bluip",
"property_id": "<this site's id>",
"edge_id": "<unique per box>"
```

Then run each agent's own `preflight.py`. It POSTs a synthetic batch, so a pass
there confirms the whole chain end to end.

Outbound TCP 443 from each edge box to this server is the only firewall rule
needed on the customer side.

---

## 9. Operating it

```powershell
Get-WebAppPoolState ItDashboardApi
Restart-WebAppPool  ItDashboardApi          # after any web.config change

Get-Content C:\inetpub\itdashboard-api\logs\* -Tail 50
Get-EventLog -LogName Application -Newest 20 | Where-Object Source -match 'IIS|HttpPlatform'
```

Database checks (adjust the psql path for your PostgreSQL version):

```powershell
$psql = "C:\Program Files\PostgreSQL\16\bin\psql.exe"

# is ingest landing?
& $psql -U hosp -d hosp_prod -c "SELECT kind, COUNT(*), MAX(received_at) FROM raw_events GROUP BY kind;"

# device health
& $psql -U hosp -d hosp_prod -c "SELECT device_id, health_status, health_score, last_seen_at FROM devices ORDER BY health_status;"

# edge box heartbeats (only the poller sends these; the syslog agent does not)
& $psql -U hosp -d hosp_prod -c "SELECT edge_id, property_id, last_heartbeat_at, queue_depth FROM edge_boxes;"

# open alerts
& $psql -U hosp -d hosp_prod -c "SELECT alert_id, device_id, severity, summary, opened_at FROM alerts WHERE resolved_at IS NULL;"

# is the outbox draining? a growing unpublished count means the poller is dead
& $psql -U hosp -d hosp_prod -c "SELECT COUNT(*) FROM event_outbox WHERE published_at IS NULL;"
```

That last one is the best single indicator that the app pool recycled and the
background poller never came back.

**Back up the database.** Nothing in the repo does this:

```powershell
$stamp = Get-Date -Format 'yyyy-MM-dd'
& "C:\Program Files\PostgreSQL\16\bin\pg_dump.exe" -U hosp -F c -f "D:\backups\hosp_prod_$stamp.dump" hosp_prod
```

Put it on a Scheduled Task before the pilot carries real customer data.

---

## 10. Upgrading

```powershell
git -C C:\MyGIT\it-dashboard pull
cd C:\MyGIT\it-dashboard\backend\deploy_iis
.\Install-ItDashboard.ps1 -RepoRoot C:\MyGIT\it-dashboard -PublicUrl ... -DatabaseUrl ... 
Restart-WebAppPool ItDashboardApi
.\Test-ItDashboard.ps1 -BaseUrl https://dashboard.yourdomain.com
```

Re-running the installer copies the new code, reinstalls dependencies, and runs
any new migrations. It will not touch your `web.config`, so if a release adds a
new environment variable you must add it there by hand.

---

## 11. What I could not test

I have no Windows or IIS host, so **none of this was executed** — unlike the
Linux/Docker path, where `docker compose config` validated, and unlike the
syslog lab, which ran against real rsyslog.

What I did verify: the XML parses, the app has no Linux-specific code, every
dependency has Windows wheels, and the exact set of Redis commands in use.

What to expect on first run: path and quoting adjustments in the PowerShell,
and possibly the `[TimeSpan]::Zero` app-pool assignments needing the string
form `"00:00:00"` instead depending on your WebAdministration version. Read
`Install-ItDashboard.ps1` before running it; it is written to be read.

`Test-ItDashboard.ps1` is the safety net — it independently checks the outcome
rather than trusting the installer, which is why check 8 exercises a real SSE
connection instead of just reading config.
