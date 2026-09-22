# IT Dashboard API

Cloud-side backend for the Hotel IT Operations Dashboard. Monitors PoE switches, DECT phones, PBX, PMS, and payments across hotel properties. Uses Claude AI to auto-diagnose and fix incidents in real time.

**Stack:** Python 3.11+ · FastAPI · asyncpg · PostgreSQL 16 · Redis 7 · Alembic · Pydantic v2

**Status:** Phase 1 complete — 188 tests passing.

---

## Prerequisites

- [Python 3.11+](https://www.python.org/downloads/)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)

---

## Quick Start (Docker — recommended)

Everything runs in Docker — API + PostgreSQL + Redis + pgAdmin + Redis Commander.

```bash
# 1. Build and start all services (run from it-dashboard-api/)
docker compose -f infra_docker/docker-compose.yml up -d --build

# 2. Add the default service provider (first time only)
docker exec hosp_api python add_provider.py

# 3. Check everything is running
docker compose -f infra_docker/docker-compose.yml ps
```

API is now running at **http://localhost:4000** · Swagger UI at **http://localhost:4000/docs**

> Migrations run automatically on startup via `entrypoint.sh` — no manual `alembic upgrade head` needed.

---

## Quick Start (Local Python — for development with hot reload)

Run Postgres + Redis in Docker, API directly on your machine with auto-reload.

```powershell
# 1. Start PostgreSQL + Redis only
docker compose -f infra_docker/docker-compose.yml up -d postgres redis

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Run migrations
python -m alembic upgrade head

# 4. Set up test database (one-time)
docker exec hosp_postgres psql -U hosp -c "CREATE DATABASE hosp_test;"
$env:DATABASE_URL="postgresql://hosp:hosp@localhost:5432/hosp_test"; python -m alembic upgrade head

# 5. Add service provider
python add_provider.py

# 6. Start the API with hot reload
python -m uvicorn app.main:app --reload --port 4000
```

API is now running at **http://localhost:4000** · Swagger UI at **http://localhost:4000/docs**

---

## Environment Variables

The `.env` file (git-ignored) must exist in `it-dashboard-api/`:

```env
DATABASE_URL=postgresql://hosp:hosp@localhost:5432/hosp_dev
TEST_DATABASE_URL=postgresql://hosp:hosp@localhost:5432/hosp_test
REDIS_URL=redis://localhost:6379
API_PORT=4000
ENVIRONMENT=development
LOG_LEVEL=debug
```

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | Dev database — used by the running API |
| `TEST_DATABASE_URL` | Yes | Test database — used by `pytest` only, never touched by the API |
| `REDIS_URL` | Yes | Redis connection |
| `API_PORT` | No | Default `4000` |
| `ENVIRONMENT` | No | `development` or `production` |
| `LOG_LEVEL` | No | `debug`, `info`, `warning` |

> `TEST_DATABASE_URL` keeps your dev data safe — running `pytest` will never truncate `hosp_dev`.

---

## Database Migrations

```powershell
# Apply all migrations (dev)
python -m alembic upgrade head

# Check current migration version
python -m alembic current

# Roll back one step
python -m alembic downgrade -1

# Generate a new migration after schema changes
python -m alembic revision --autogenerate -m "describe the change"
```

---

## Running the API

```powershell
# Development (with auto-reload)
python -m uvicorn app.main:app --reload --port 4000

# Production-style (no reload)
python -m uvicorn app.main:app --port 4000 --workers 4
```

| URL | Description |
|-----|-------------|
| http://localhost:4000/docs | Swagger UI (interactive) |
| http://localhost:4000/livez | Liveness probe |
| http://localhost:4000/readyz | Readiness probe (checks DB + Redis) |
| http://localhost:4000/healthz | Legacy health check |

---

## Docker Deployment (Ubuntu Server)

Uses the same `docker-compose.yml` as local dev. No separate prod file needed.

### 1. Install Docker on Ubuntu

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # run docker without sudo — re-login after this
```

### 2. Copy code to server

```bash
# On your local machine
scp -r it-dashboard-api/ user@<server-ip>:~/it-dashboard-api
```

### 3. Build and start

```bash
cd ~/it-dashboard-api
docker compose -f infra_docker/docker-compose.yml up -d --build
```

This will:
1. Pull PostgreSQL 16, Redis 7, pgAdmin, Redis Commander images
2. Build the API image from `Dockerfile`
3. Start Postgres + Redis, wait for them to be healthy
4. Start the API — `entrypoint.sh` runs `alembic upgrade head` then starts uvicorn

### 4. Add the default service provider (first time only)

```bash
docker exec hosp_api python add_provider.py
```

### 5. Verify everything is running

```bash
# Check all containers are up
docker compose -f infra_docker/docker-compose.yml ps

# Check API health
curl http://localhost:4000/readyz
```

API is now live at **http://\<server-ip\>:4000** · Swagger UI at **http://\<server-ip\>:4000/docs**

---

## Checking Logs

```bash
# Live API logs (follow mode)
docker logs hosp_api -f

# Last 100 lines of API logs
docker logs hosp_api --tail 100

# Last 100 lines + follow
docker logs hosp_api --tail 100 -f

# Logs from all containers at once
docker compose -f infra_docker/docker-compose.yml logs -f

# Logs from a specific service
docker compose -f infra_docker/docker-compose.yml logs -f postgres
docker compose -f infra_docker/docker-compose.yml logs -f redis
```

---

## Running Scripts in Docker

When the API runs inside Docker, scripts must be executed **inside the container**
using `docker exec` — the database is only reachable from within the Docker network.

```bash
# Add default service provider
docker exec hosp_api python add_provider.py

# Clean all data
docker exec hosp_api python clean_db.py

# Seed sample data
docker exec hosp_api python seed.py

# Open an interactive shell inside the container
docker exec -it hosp_api /bin/sh
```

### Useful Docker commands

```bash
# Check status of all containers
docker compose -f infra_docker/docker-compose.yml ps

# Rebuild and restart API only (after a code change)
docker compose -f infra_docker/docker-compose.yml up -d --build api

# Restart API without rebuilding
docker compose -f infra_docker/docker-compose.yml restart api

# Stop all containers (data volumes kept)
docker compose -f infra_docker/docker-compose.yml down

# Stop and wipe ALL data (full reset)
docker compose -f infra_docker/docker-compose.yml down -v
```

### Docker files

| File | Purpose |
|------|---------|
| `Dockerfile` | Builds the API image — installs deps, copies code |
| `entrypoint.sh` | Runs `alembic upgrade head` then starts uvicorn on container start |
| `infra_docker/docker-compose.yml` | All services — API + PostgreSQL + Redis + pgAdmin + Redis Commander |
| `infra_docker/nginx.conf` | Nginx config (optional — add when HTTPS is needed) |

---

## Seed Sample Data

Populate the database with two hotels, 6 devices, and 2 open alerts:

```bash
# Running in Docker (recommended)
docker exec hosp_api python seed.py

# Running locally (Python on host)
python seed.py
```

Safe to run multiple times (`ON CONFLICT DO NOTHING`).

---

## Clean Database

Remove all rows from every table (tables are kept, only data is deleted):

```bash
# Running in Docker (recommended)
docker exec hosp_api python clean_db.py

# Running locally (Python on host)
python clean_db.py
```

What gets cleared:

| Table | Cleared via |
|-------|-------------|
| `service_providers` | Direct truncate → cascades to all below |
| `properties` | Cascade from `service_providers` |
| `edge_boxes` | Cascade from `properties` |
| `devices` | Cascade from `properties` |
| `alerts` | Cascade from `properties` |
| `raw_events` | Direct truncate |
| `events` | Direct truncate |
| `event_outbox` | Direct truncate |
| `idempotency_keys` | Direct truncate |

The script prints row counts before and after so you can confirm everything was removed.

---

## Add Service Provider

Insert the default service provider (`bluip`) into the database:

```bash
# Running in Docker (recommended)
docker exec hosp_api python add_provider.py

# Running locally (Python on host)
python add_provider.py
```

Must be run before sending any `POST /v1/edge/ingest` requests. Safe to run multiple times (`ON CONFLICT DO NOTHING`).

Typical workflow for a fresh start:

```bash
docker exec hosp_api python clean_db.py        # 1. wipe all data
docker exec hosp_api python add_provider.py    # 2. add provider
# 3. POST /v1/edge/ingest with your requests
```

---

## Running Tests

Tests use `hosp_test` (not `hosp_dev`) — your dev data is never affected.

```powershell
# Unit tests — no database needed, very fast
python -m pytest tests/unit/ -v

# Integration tests — requires Docker running
python -m pytest tests/integration/ -v

# All 188 tests
python -m pytest -v

# With coverage report
python -m pytest --cov=app --cov-report=term-missing
```

---

## API Endpoints

All endpoints except health probes require `X-Provider-Id: <provider>` header. Missing header → `401`.

### Ingestion

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/edge/ingest` | Receive edge agent batch (edge_health / periodic / transition messages) |

### Dashboard reads

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/estate` | Property grid + KPI strip (home view) |
| `GET` | `/v1/alerts` | Paginated alert list — params: `status`, `severity`, `limit`, `cursor` |
| `GET` | `/v1/alerts/{alert_id}` | Full alert detail with causal chain + top_events |
| `POST` | `/v1/alerts/{alert_id}/auto-fix` | Dispatch auto-fix — requires `Idempotency-Key` header + `{"confirm": true}` |
| `GET` | `/v1/properties/{property_id}` | Property detail: health, all edge boxes, devices, recent events |
| `GET` | `/v1/properties/{property_id}/alerts` | Paginated full alert details for one property — params: `status`, `limit`, `cursor` |
| `GET` | `/v1/stream` | SSE live event stream — params: `property_id`, `kinds`, `min_severity` + `Last-Event-ID` header |
| `GET` | `/v1/exec` | Executive view stub (Phase 2 aggregations) |

### Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/livez` | None | Always `200 {"status":"ok"}` |
| `GET` | `/readyz` | None | `200` if DB + Redis reachable, `503` if not |
| `GET` | `/healthz` | None | Legacy alias for `/livez` |

### Pagination

All list endpoints use **cursor-based pagination** — never offset.

```
GET /v1/alerts?limit=25
→ { "items": [...], "next_cursor": "eyJyIjox...", "has_more": true }

GET /v1/alerts?limit=25&cursor=eyJyIjox...
→ next page
```

### SSE stream

```
GET /v1/stream
X-Provider-Id: bluip
Last-Event-ID: evt_abc123          ← optional: replay missed events since this ID

# Filter by property
GET /v1/stream?property_id=prop_123

# Filter by event kind
GET /v1/stream?kinds=alert.opened,alert.state_changed

# Filter by severity
GET /v1/stream?min_severity=p2
```

### Caching

GET responses include `ETag` + `Cache-Control` headers:
- `private, max-age=10` — tile/aggregate data (`/v1/estate`, `/v1/exec`)
- `private, max-age=2` — live-ish data (`/v1/alerts`, `/v1/properties/{id}`)

Send `If-None-Match: <etag>` to get a `304 Not Modified` when data hasn't changed.

---

## Ingest Payload Shape

```json
{
    "schema_version": "1.0",
    "edge_id": "edge-box-7",
    "service_provider": "bluip",
    "property_id": "123",
    "property_name": "Sheraton",
    "messages": [
        {
            "kind": "edge_health",
            "ts": 1746723715.0,
            "metrics": {
                "tracked_devices": 3,
                "unhealthy_devices": 1,
                "queue_depth": 1,
                "summary_interval_seconds": 60
            }
        },
        {
            "kind": "periodic",
            "ts": 1746723710.0,
            "device_id": "dev-001",
            "device_name": "cisco_switch_main",
            "device_class": "poe_switch",
            "vendor": "cisco",
            "site": "hq",
            "health": { "status": "healthy", "score": 92, "reasons": [] },
            "metrics": { "event_count": 1, "error_count": 0, "warn_count": 0 }
        },
        {
            "kind": "transition",
            "ts": 1746723715.0,
            "device_id": "dev-002",
            "device_name": "mikrotik_router",
            "device_class": "router",
            "vendor": "mikrotik",
            "site": "hq",
            "health": {
                "status": "unhealthy",
                "score": 30,
                "reasons": ["link_flap", "error_rate_high"]
            },
            "metrics": { "event_count": 12, "error_count": 9, "warn_count": 3 },
            "top_events": [
                {
                    "ts": 1746723711.0,
                    "severity": "error",
                    "category": "link",
                    "message": "Interface GigabitEthernet0/1 link state changed to down"
                }
            ]
        }
    ]
}
```

**Message kinds:**
- `edge_health` — edge box heartbeat (updates `edge_boxes` table)
- `periodic` — routine device health sample (updates `devices` table)
- `transition` — device crossed a health threshold (creates/resolves `alerts`)

**Multiple edge boxes per property:** the same `property_id` can be sent from different `edge_id` values (e.g. one per floor). All appear in `GET /v1/properties/{id}` → `edge_boxes[]`.

---

## Project Structure

```
it-dashboard-api/
├── app/
│   ├── main.py                  ← FastAPI app factory + lifespan (pool, Redis, outbox poller)
│   ├── config.py                ← pydantic-settings (reads .env)
│   ├── database.py              ← asyncpg pool wrapper + get_db() dependency
│   ├── redis_client.py          ← redis-py async client + get_redis() dependency
│   ├── routers/
│   │   ├── health.py            ← /livez  /readyz  /healthz
│   │   ├── ingest.py            ← POST /v1/edge/ingest
│   │   ├── estate.py            ← GET /v1/estate
│   │   ├── alerts.py            ← GET /v1/alerts + /{id} + /auto-fix
│   │   ├── properties.py        ← GET /v1/properties/{id} + /{id}/alerts
│   │   ├── stream.py            ← GET /v1/stream (SSE)
│   │   └── exec.py              ← GET /v1/exec (stub)
│   ├── repositories/
│   │   ├── alerts.py            ← all alert SQL (list, get, create, update, count)
│   │   ├── devices.py           ← device upsert + health update
│   │   └── properties.py        ← property + edge_box upsert + queries
│   ├── middleware/
│   │   ├── auth.py              ← X-Provider-Id extraction → 401 if missing
│   │   ├── idempotency.py       ← Redis get/set for Idempotency-Key (24h TTL)
│   │   ├── etag.py              ← ETag + Cache-Control on GET responses
│   │   └── request_id.py        ← X-Request-ID header injection
│   ├── lib/
│   │   ├── health.py            ← property_health_score() + materialize_alert_from_transition()
│   │   ├── cursor.py            ← base64 cursor encode/decode
│   │   ├── errors.py            ← AppError + exception handlers
│   │   ├── ingestor.py          ← message processing pipeline (3 kinds)
│   │   ├── outbox_poller.py     ← background task: event_outbox → Redis pub/sub
│   │   ├── raw_events.py        ← insert_raw_event() helper
│   │   ├── severity.py          ← severity string normalisation
│   │   └── sse_buffer.py        ← SseReplayBuffer (5-min in-memory replay window)
│   └── schemas/
│       ├── ingest.py            ← EdgeHealthMessage / PeriodicMessage / TransitionMessage
│       ├── alerts.py            ← AlertListItem / AlertDetail / AutoFixRequest / AutoFixResponse
│       ├── estate.py            ← EstateResponse / PropertySummary / EdgeBoxSummary / KpiStrip
│       └── properties.py        ← PropertyDetailResponse / DeviceSummary / RecentEvent
├── migrations/
│   ├── env.py
│   └── versions/
│       ├── 20260508_..._initial_schema.py   ← all 9 tables
│       └── 20260508_..._drop_devices_fk.py  ← edge_id FK relaxation
├── tests/
│   ├── unit/                    ← pure logic, no DB (health score, cursor, SSE buffer, filters)
│   └── integration/             ← real PostgreSQL + Redis (hosp_test database)
│       ├── conftest.py          ← pg_pool, redis_client, http_client, clean_db fixtures
│       ├── test_ingest.py
│       ├── test_estate.py
│       ├── test_alerts.py
│       ├── test_properties.py
│       ├── test_property_alerts.py
│       ├── test_auto_fix.py
│       ├── test_stream.py
│       ├── test_exec.py
│       ├── test_health_endpoints.py
│       └── test_etag.py
├── seed.py                      ← populate dev DB with sample hotels + alerts
├── clean_db.py                  ← wipe all rows from every table (fresh start)
├── add_provider.py              ← insert default service provider (run before ingest)
├── Dockerfile                   ← builds the API image for production
├── entrypoint.sh                ← runs migrations then starts uvicorn (used by Docker)
├── infra_docker/
│   ├── docker-compose.yml       ← all services: API + PostgreSQL + Redis + pgAdmin + Redis Commander
│   ├── docker-compose.prod.yml  ← alternative minimal compose (no pgAdmin/Redis Commander)
│   └── nginx.conf               ← Nginx config (optional — add when HTTPS is needed)
├── alembic.ini
├── pyproject.toml
├── .env                         ← local dev only, git-ignored
└── .env.prod                    ← production secrets, git-ignored (copy from .env.prod.example)
```

---

## Key Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Auth | `X-Provider-Id` header | Phase 1 — JWT in Phase 2, no route changes needed |
| ORM | None — raw SQL in repositories | Full control, no N+1 surprises |
| Pagination | Cursor-based only | Stable under concurrent inserts |
| Idempotency | Redis `idem:{key}` with 24h TTL | Auto-fix must be safe to retry |
| SSE testing | Direct generator calls (no HTTP) | httpx ASGITransport buffers full response — hangs on infinite streams |
| Test isolation | Separate `hosp_test` database | `clean_db` autouse fixture truncates before each test without touching dev data |
| Edge boxes | `edge_boxes[]` list per property | One property can have multiple physical edge boxes (per floor/wing) |
| ETag | SHA1[:16] of response body | Cache-Control: private, max-age=10 (tiles) or max-age=2 (live queries) |

---

## Stopping Infrastructure

Same command whether running locally or on Ubuntu — both use `docker-compose.yml`.

```bash
# Stop all containers, keep data volumes
docker compose -f infra_docker/docker-compose.yml down

# Stop and wipe ALL data (full reset)
docker compose -f infra_docker/docker-compose.yml down -v
```
