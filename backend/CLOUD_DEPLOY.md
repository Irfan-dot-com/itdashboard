# Cloud Side — Deployment Runbook

What has to exist in the cloud before any Ubuntu edge box can send anything,
and how to stand it up.

The edge agents need exactly **one** reachable thing: `POST /v1/edge/ingest`
over HTTPS, with a `service_provider` that exists in the database. Everything
below is in service of that, plus the dashboard UI that reads the results.

---

## 0. What you need first

| Item | Why |
|---|---|
| A cloud VM (2 vCPU / 4 GB / 40 GB is comfortable) | runs everything in Docker |
| Docker + Compose plugin on it | `curl -fsSL https://get.docker.com \| sh` |
| **A DNS name pointing at it** | required for TLS; Let's Encrypt will not issue for a bare IP |
| Inbound **80 and 443** open | 443 for traffic, 80 for certificate validation and redirect |
| A real mailbox for Let's Encrypt notices | expiry and problem warnings |

Nothing else should be open. Postgres, Redis and the API itself stay on the
internal Docker network.

---

## 1. The gap this fixes

The repo ships `infra_docker/docker-compose.prod.yml` and an `nginx.conf`, but:

- **`nginx.conf` is not referenced by any compose file.** It is orphaned, and it
  only listens on port 80 with no TLS configuration at all.
- **There is no TLS anywhere.** The API is served as plain HTTP on port 4000.
  Both edge agents' `preflight.py` deliberately FAIL on an `http://` endpoint,
  because the `X-Provider-Id` header is the only credential the ingest API has
  and it would cross the network in clear text.
- **`docker-compose.prod.yml` does not actually work as documented.** It uses
  `${POSTGRES_PASSWORD}` interpolation together with `env_file: ../.env.prod`.
  Compose does **not** read `env_file` for interpolation — only the shell
  environment or a `.env` in the project directory. Verified: running it as the
  README says produces `POSTGRES_PASSWORD: ""` for the postgres service, so
  Postgres refuses to initialise (or comes up with no password). See step 3 for
  the fix.
- **The README says to use the dev `docker-compose.yml` on the server.** Don't.
  That one publishes Postgres on 5432, Redis on 6379, pgAdmin on 5050 and Redis
  Commander on 8081 — to the internet.

`docker-compose.tls.yml` and `Caddyfile` in `infra_docker/` address all of it:
Caddy terminates TLS with automatic Let's Encrypt certs, the API is no longer
published on a host port, and the frontend is served from the same origin so
CORS stops mattering.

---

## 2. Configure

```bash
cd backend
cp .env.prod.example .env.prod
nano .env.prod
chmod 600 .env.prod
```

| Key | Set to |
|---|---|
| `PUBLIC_URL` | `https://dashboard.yourdomain.com` — must match the Caddyfile domain |
| `POSTGRES_PASSWORD` | generate it: `openssl rand -base64 32` |
| `LOG_LEVEL` | `info` — `debug` is far too chatty in production |
| `LOG_REQUEST_BODY` | `False` — see the warning below |
| `ENVIRONMENT` | `production` — also disables the public `/docs` page |

> **`LOG_REQUEST_BODY=True` is in the shipped example and should not be.** It
> logs the full body of every request, which for `/v1/edge/ingest` means every
> device health payload from every edge box on every poll. Large, and it puts
> the customer's estate detail in plaintext log files. Turn it on only while
> debugging an ingest problem.

Then the domain and email:

```bash
nano infra_docker/Caddyfile      # replace dashboard.example.com and admin@example.com
```

Validate it before starting anything — this catches typos without touching a
live service:

```bash
docker run --rm -v "$PWD/infra_docker/Caddyfile":/etc/caddy/Caddyfile:ro \
    caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile
```

---

## 3. Bring it up

**Note the `--env-file` flag.** It is required, for the interpolation reason in
section 1. Without it the database password resolves to an empty string.

```bash
cd backend
docker compose --env-file .env.prod -f infra_docker/docker-compose.tls.yml up -d --build
```

First start takes a few minutes: it builds the API and frontend images, runs
`alembic upgrade head` via `entrypoint.sh`, and obtains a certificate.

Then register the service provider — **the edge agents cannot ingest until this
exists**, because `service_provider` is a foreign key:

```bash
docker exec hosp_api python add_provider.py
```

That inserts `bluip`. It matches the `service_provider` value in both agents'
config, and is safe to re-run.

---

## 4. Verify, in the order the agents will

```bash
# 1. containers healthy
docker compose --env-file .env.prod -f infra_docker/docker-compose.tls.yml ps

# 2. TLS works and the cert is real
curl -v https://dashboard.yourdomain.com/livez          # expect 200 {"status":"ok"}

# 3. dependencies reachable from inside
curl https://dashboard.yourdomain.com/readyz            # 200 = DB + Redis ok, 503 = not

# 4. the dashboard UI loads
curl -sI https://dashboard.yourdomain.com/ | head -3

# 5. ingest accepts a batch — this is exactly what the edge agents do
curl -X POST https://dashboard.yourdomain.com/v1/edge/ingest \
  -H "Content-Type: application/json" \
  -H "X-Provider-Id: bluip" \
  -d '{
        "schema_version": "1.0",
        "edge_id": "smoke-test",
        "service_provider": "bluip",
        "property_id": "234",
        "property_name": "Smoke Test",
        "messages": [{
          "kind": "edge_health", "ts": 1790000000.0,
          "metrics": {"tracked_devices": 0, "unhealthy_devices": 0,
                      "queue_depth": 0, "summary_interval_seconds": 60}
        }]
      }'
```

Expect `{"edge_id":"smoke-test","accepted":1,"rejected":[]}`.

- `401` — the `X-Provider-Id` header is missing.
- `422` — the payload shape is wrong; compare against `app/schemas/ingest.py`.
- `500` — almost always the provider row is missing. Run `add_provider.py`.

Once that returns 200, point an edge box at it and run its `preflight.py`. It
performs this same POST, so a pass there means the whole chain works.

---

## 5. What each edge box then needs

In `/etc/edge-agent/config.json` (syslog) and `/etc/sdlan-poller/config.json`
(poller):

```json
"cloud_endpoint": "https://dashboard.yourdomain.com/v1/edge/ingest",
"service_provider": "bluip",
"property_id":      "<this site's id>",
"edge_id":          "<unique per box>"
```

Outbound TCP 443 from each edge box to this host is the only firewall rule
needed on the customer side.

---

## 6. Operating it

```bash
C="docker compose --env-file .env.prod -f infra_docker/docker-compose.tls.yml"

$C logs -f api
$C logs -f caddy            # certificate issuance and renewal happen here
$C ps
$C restart api              # after a config change
$C up -d --build api        # after a code change
$C down                     # stop, keep data
```

Useful checks:

```bash
# is ingest actually landing?
docker exec hosp_postgres psql -U hosp -d hosp_prod -c \
  "SELECT kind, COUNT(*), MAX(received_at) FROM raw_events GROUP BY kind;"

# what devices exist, and their health
docker exec hosp_postgres psql -U hosp -d hosp_prod -c \
  "SELECT device_id, health_status, health_score, last_seen_at FROM devices ORDER BY health_status;"

# edge boxes and their heartbeats (only populated by edge_health messages —
# the syslog agent does not send these; the poller does)
docker exec hosp_postgres psql -U hosp -d hosp_prod -c \
  "SELECT edge_id, property_id, last_heartbeat_at, queue_depth FROM edge_boxes;"

# open alerts
docker exec hosp_postgres psql -U hosp -d hosp_prod -c \
  "SELECT alert_id, device_id, severity, summary, opened_at FROM alerts WHERE resolved_at IS NULL;"
```

**Back up the database.** Nothing in the repo does this:

```bash
docker exec hosp_postgres pg_dump -U hosp hosp_prod | gzip > hosp_prod_$(date +%F).sql.gz
```

Put that on a schedule before the pilot carries real customer data.

---

## 7. Still open on the cloud side

1. **Auth is a single shared header.** `X-Provider-Id: bluip` is the only
   credential, it is the same for every edge box, and anyone who has it can
   post data for any property. `app/middleware/auth.py` and `app/config.py`
   both carry Phase 2 notes about replacing it with a JWT bearer token. Until
   then, treat the ingest URL as a secret and consider IP-allowlisting the
   `/v1/edge/*` path once you know the edge boxes' egress addresses — the
   `@ingest` matcher in the Caddyfile is split out for exactly that.
2. **No rate limiting.** A misconfigured or looping edge box can post as fast
   as it likes. Caddy's core has no rate limiter; it needs a plugin build or a
   limit in front.
3. **CORS is `allow_origins=["*"]`** in `app/main.py`. Harmless with the
   same-origin layout here, but it should be tightened before any other origin
   is in play.
4. **No backups, no monitoring of the cloud host itself.** The dashboard watches
   the customer's estate; nothing watches the dashboard.
5. **`/docs` is disabled only because `ENVIRONMENT=production`.** Worth
   confirming after deployment: `curl -o /dev/null -w '%{http_code}'
   https://dashboard.yourdomain.com/docs` should be 404.
