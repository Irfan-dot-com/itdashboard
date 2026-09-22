# Cloud Backend on AWS / Ubuntu 24.04 — Deployment Runbook

The canonical runbook for deploying the **cloud portion only** (FastAPI backend
+ dashboard UI + PostgreSQL + Redis) onto a dedicated EC2 instance.

The syslog agent and SD-LAN poller are **not** deployed here. They live on
Ubuntu boxes on the customer's network and reach this server outbound over 443.

Supersedes `CLOUD_DEPLOY.md` when deploying on AWS — that one is the generic
Ubuntu/Docker path and omits the AWS-specific parts (security groups, Elastic
IP, volume sizing) that cause most of the trouble.

---

## 0. The AWS side — get this right first

Most failed deployments here are an AWS networking problem, not a Docker one.

### Instance

| Setting | Value | Why |
|---|---|---|
| AMI | **Ubuntu Server 24.04 LTS (amd64)** | supported into 2029 |
| Type | **t3.medium** (2 vCPU / 4 GiB) | t3.micro and t3.small will OOM during the frontend build |
| Root volume | **40 GiB gp3** | the 8 GiB default is not enough for Docker images + Postgres + logs |
| Key pair | create or reuse one | you need the `.pem` to SSH |

Default login user is `ubuntu`.

### Security group — inbound rules

This is the actual firewall. `ufw` on the instance is not what gates traffic
from the internet.

| Type | Port | Source | Why |
|---|---|---|---|
| SSH | 22 | **your office/home IP only** | do not leave this open to 0.0.0.0/0 |
| HTTP | 80 | 0.0.0.0/0 | **required** — Let's Encrypt validates over port 80 |
| HTTPS | 443 | 0.0.0.0/0 | the dashboard UI, and the edge agents posting in |

Port 80 is not optional. Certificate issuance fails without it, and Caddy will
sit in a retry loop that looks like a broken deployment.

Outbound: leave the default (all allowed). The instance needs to pull Docker
images and reach Let's Encrypt.

### Elastic IP

Allocate one and associate it with the instance. Without it the public IP
changes whenever the instance stops, and your DNS record — plus every edge
agent's `cloud_endpoint` — silently points at nothing.

> AWS bills for all public IPv4 addresses (around $3.60/month per address),
> including Elastic IPs that are in use. Expected, just not free.

### DNS

Create an **A record** pointing your hostname at the Elastic IP:

```
dashboard.yourdomain.com.   A   <elastic-ip>
```

Then confirm it resolves **before** you start the stack:

```bash
dig +short dashboard.yourdomain.com
```

If that returns nothing or the wrong address, stop and fix DNS first.
Let's Encrypt resolves the name from the public internet; a stack started
before DNS propagates will fail certificate issuance and you may hit rate
limits retrying.

---

## 1. Connect and prepare the OS

```bash
ssh -i your-key.pem ubuntu@dashboard.yourdomain.com

sudo apt-get update && sudo apt-get upgrade -y
sudo timedatectl set-timezone UTC          # keeps log timestamps sane
```

### Swap — cheap insurance

The frontend build (`tsc` + `vite build`) is the most memory-hungry step in the
whole deployment. On 4 GiB it usually fits, but an OOM kill there produces a
confusing "build failed" with no clear cause. 2 GiB of swap removes the risk:

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h
```

### Optional: ufw as defence in depth

The security group already controls access. If you want a host firewall too,
**allow SSH before enabling it** or you will lock yourself out of the instance:

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
sudo ufw status verbose
```

---

## 2. Install Docker — from the apt repository

Use this, not `get.docker.com`. The convenience script swallows failures; this
fails loudly, which is what you want.

```bash
# clear anything conflicting
for p in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
    sudo apt-get remove -y "$p" 2>/dev/null
done

sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
                        docker-buildx-plugin docker-compose-plugin
```

`docker-compose-plugin` is what provides `docker compose` (with a space). The
old standalone `docker-compose` will not work with these files.

### Verify properly

```bash
getent group docker                  # must exist — created by the docker-ce package
docker --version
docker compose version
sudo docker run --rm hello-world     # must print its greeting
```

If `getent group docker` is empty, the install did **not** work — do not
continue, and do not create the group by hand. That masks the real problem.

Then grant your user access:

```bash
sudo usermod -aG docker $USER
exit                                 # log out
# ssh back in, then:
docker ps                            # no sudo, no permission error
```

The group change only applies to a **new** login session.

---

## 3. Get the code

```bash
sudo apt-get install -y git
git clone <your-repo-url> ~/it-dashboard
cd ~/it-dashboard/backend
```

---

## 4. Configure

Two files.

```bash
cp CLOUD_ENV_TEMPLATE.txt .env.prod
nano .env.prod
chmod 600 .env.prod
```

Set:

| Key | Value |
|---|---|
| `PUBLIC_URL` | `https://dashboard.yourdomain.com` — must match the Caddyfile and DNS |
| `POSTGRES_PASSWORD` | generate it: `openssl rand -base64 32` |

Use `CLOUD_ENV_TEMPLATE.txt`, **not** the committed `.env.prod.example` — that
one still has `LOG_REQUEST_BODY=True` and `LOG_LEVEL=debug`, neither of which
belongs in production.

> If your generated password contains `@ : / ? # %`, percent-encode it or
> regenerate. It ends up inside a URL.

Then the domain and email:

```bash
nano infra_docker/Caddyfile
# replace dashboard.example.com  -> your real hostname
# replace admin@example.com      -> a real mailbox (Let's Encrypt expiry notices)
```

### Validate the Caddyfile before starting anything

```bash
docker run --rm -v "$PWD/infra_docker/Caddyfile":/etc/caddy/Caddyfile:ro \
    caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile
```

---

## 5. Bring it up

**Note `--env-file`.** Compose does not read `env_file:` for `${...}`
interpolation, only the shell environment or a `.env` in the project directory.
Without this flag the database password resolves to an empty string and
Postgres refuses to initialise.

```bash
cd ~/it-dashboard/backend
docker compose --env-file .env.prod -f infra_docker/docker-compose.tls.yml up -d --build
```

First run takes several minutes: it builds the API and frontend images, runs
`alembic upgrade head` via `entrypoint.sh`, and obtains a TLS certificate.

Watch the certificate being issued:

```bash
docker compose --env-file .env.prod -f infra_docker/docker-compose.tls.yml logs -f caddy
```

Look for `certificate obtained successfully`. If instead you see repeated ACME
failures, the cause is almost always one of: DNS not resolving to this
instance, port 80 closed in the security group, or a typo'd hostname in the
Caddyfile.

---

## 6. Register the service provider

The edge agents cannot ingest until this row exists — `service_provider` is a
foreign key.

```bash
docker exec hosp_api python add_provider.py
```

Inserts `bluip`, matching both agents' config. Safe to re-run.

---

## 7. Verify

```bash
# containers healthy
docker compose --env-file .env.prod -f infra_docker/docker-compose.tls.yml ps

# TLS works and the certificate is real
curl -v https://dashboard.yourdomain.com/livez      # 200 {"status":"ok"}

# dependencies, as the app sees them — this is the check that proves Redis works
curl https://dashboard.yourdomain.com/readyz        # 200 = DB + Redis ok

# the dashboard UI
curl -sI https://dashboard.yourdomain.com/ | head -3

# ingest — exactly what an edge agent does
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

| Response | Cause |
|---|---|
| `401` | `X-Provider-Id` header missing |
| `422` | payload shape — compare with `app/schemas/ingest.py` |
| `500` | provider row missing — run step 6 |
| connection refused / timeout | security group, or the stack is not up |

Also confirm Swagger is not public:

```bash
curl -o /dev/null -w '%{http_code}\n' https://dashboard.yourdomain.com/docs   # want 404
```

---

## 8. Backups — before the pilot carries real data

```bash
sudo install -m 0750 infra_docker/backup.sh /usr/local/bin/itdashboard-backup
sudo mkdir -p /var/backups/itdashboard
sudo crontab -e
#   15 2 * * * /usr/local/bin/itdashboard-backup >> /var/log/itdashboard-backup.log 2>&1

# run it once by hand to confirm
sudo /usr/local/bin/itdashboard-backup
ls -la /var/backups/itdashboard/
```

The script refuses a bad backup rather than overwriting a good one: it verifies
gzip integrity, the uncompressed size, the `pg_dump` header, and that at least
one `CREATE TABLE` is present. It writes to `.partial` first, so a crashed run
never leaves a truncated file looking like a valid backup.

**Restore one into a scratch database at least once** before go-live — the
how-to is in the script's header comments. A backup you have never restored is
a hypothesis.

On AWS, also consider an EBS snapshot schedule via Data Lifecycle Manager as a
second layer. It protects the whole instance, not just the database.

---

## 9. Point the agents at it

On each Ubuntu box on the customer's network, in
`/etc/edge-agent/config.json` (syslog) and/or
`/etc/sdlan-poller/config.json` (poller):

```json
"cloud_endpoint": "https://dashboard.yourdomain.com/v1/edge/ingest",
"service_provider": "bluip",
"property_id": "<this site's id>",
"edge_id": "<unique per box>"
```

Then run that agent's `preflight.py`. It POSTs a synthetic batch, so a pass
there confirms the whole chain end to end.

The only firewall rule needed on the **customer** side is outbound TCP 443 from
their edge box to this server.

---

## 10. Operating it

```bash
C="docker compose --env-file .env.prod -f infra_docker/docker-compose.tls.yml"

$C ps
$C logs -f api
$C logs -f caddy              # certificate renewal happens here
$C restart api                # after a config change
$C up -d --build api          # after a code change
$C down                       # stop, keep data
```

Useful database checks:

```bash
# is ingest landing?
docker exec hosp_postgres psql -U hosp -d hosp_prod -c \
  "SELECT kind, COUNT(*), MAX(received_at) FROM raw_events GROUP BY kind;"

# device health
docker exec hosp_postgres psql -U hosp -d hosp_prod -c \
  "SELECT device_id, health_status, health_score, last_seen_at FROM devices ORDER BY health_status;"

# edge box heartbeats — only the poller sends these; the syslog agent does not
docker exec hosp_postgres psql -U hosp -d hosp_prod -c \
  "SELECT edge_id, property_id, last_heartbeat_at, queue_depth FROM edge_boxes;"

# open alerts
docker exec hosp_postgres psql -U hosp -d hosp_prod -c \
  "SELECT alert_id, device_id, severity, summary, opened_at FROM alerts WHERE resolved_at IS NULL;"

# is the outbox draining? a growing unpublished count means the poller task died
docker exec hosp_postgres psql -U hosp -d hosp_prod -c \
  "SELECT COUNT(*) FROM event_outbox WHERE published_at IS NULL;"
```

Disk, since 40 GiB is not infinite:

```bash
df -h /
docker system df
docker system prune -f        # reclaims old build layers; safe, does not touch volumes
```

---

## 11. Upgrading

```bash
cd ~/it-dashboard && git pull
cd backend
docker compose --env-file .env.prod -f infra_docker/docker-compose.tls.yml up -d --build
```

Migrations run automatically on API start. Take a backup first
(`sudo /usr/local/bin/itdashboard-backup`) — migrations are not reversible in
practice.

---

## 12. Still open

1. **Auth is a single shared header.** `X-Provider-Id: bluip` is the only
   credential, identical on every edge box, and anyone holding it can post for
   any property. `app/middleware/auth.py` and `app/config.py` both carry Phase 2
   notes about replacing it with a JWT bearer token. Until then treat the ingest
   URL as a secret. Once you know the edge boxes' egress addresses you can also
   restrict the `/v1/edge/*` path — the `@ingest` matcher in the Caddyfile is
   split out for exactly that, and an AWS security group rule is another option.
2. **No rate limiting.** A looping edge box can post as fast as it likes.
3. **CORS is `allow_origins=["*"]`** in `app/main.py`. Harmless with the
   same-origin layout used here, but tighten it before another origin is in
   play.
4. **Nothing monitors this server.** The dashboard watches the customer's
   estate; nothing watches the dashboard. A CloudWatch alarm on instance status
   plus a simple external check on `/livez` would cover the basics.
