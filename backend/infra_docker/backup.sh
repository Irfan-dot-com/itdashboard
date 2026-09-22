#!/usr/bin/env bash
#
# backup.sh — dump the IT Dashboard database to a compressed file and prune old ones.
#
# Nothing in the repo did this. Put it on a timer BEFORE the pilot carries real
# customer data.
#
# Install:
#   sudo install -m 0750 backup.sh /usr/local/bin/itdashboard-backup
#   sudo mkdir -p /var/backups/itdashboard
#   sudo crontab -e
#     # 02:15 every day
#     15 2 * * * /usr/local/bin/itdashboard-backup >> /var/log/itdashboard-backup.log 2>&1
#
# Restore (destructive — it drops and recreates the database):
#   gunzip -c /var/backups/itdashboard/hosp_prod_2026-09-22.sql.gz \
#     | docker exec -i hosp_postgres psql -U hosp -d postgres
#
# Verify a backup without restoring over the live database:
#   gunzip -c <file>.sql.gz | head -40
#   docker exec hosp_postgres psql -U hosp -c "CREATE DATABASE restore_test;"
#   gunzip -c <file>.sql.gz | docker exec -i hosp_postgres psql -U hosp -d restore_test
#   docker exec hosp_postgres psql -U hosp -d restore_test -c "SELECT COUNT(*) FROM devices;"
#   docker exec hosp_postgres psql -U hosp -c "DROP DATABASE restore_test;"
#
set -euo pipefail

CONTAINER="${ITDASH_PG_CONTAINER:-hosp_postgres}"
DB_USER="${POSTGRES_USER:-hosp}"
DB_NAME="${POSTGRES_DB:-hosp_prod}"
DEST="${ITDASH_BACKUP_DIR:-/var/backups/itdashboard}"
KEEP_DAYS="${ITDASH_BACKUP_KEEP_DAYS:-14}"
# A dump smaller than this almost certainly means the dump failed or the
# database is empty. Catching that is the whole point of having backups.
# Floor on the UNCOMPRESSED dump size. Checking the compressed size is wrong:
# SQL compresses ~10x, so a perfectly good dump of a small database can gzip
# below any sensible floor and be thrown away as "failed".
MIN_BYTES="${ITDASH_BACKUP_MIN_BYTES:-4096}"

ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "$(ts) $*"; }
die() { log "ERROR: $*"; exit 1; }

log "backup starting (container=$CONTAINER db=$DB_NAME dest=$DEST keep=${KEEP_DAYS}d)"

command -v docker >/dev/null 2>&1 || die "docker not found on PATH"

if ! docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | grep -q true; then
    die "container '$CONTAINER' is not running. Is the stack up?"
fi

mkdir -p "$DEST"
chmod 0750 "$DEST"

STAMP="$(date +%F_%H%M)"
OUT="$DEST/${DB_NAME}_${STAMP}.sql.gz"
TMP="$OUT.partial"

# Write to .partial first so a crashed run never leaves a truncated file that
# looks like a good backup.
if ! docker exec "$CONTAINER" pg_dump -U "$DB_USER" --clean --if-exists "$DB_NAME" \
     | gzip -9 > "$TMP"; then
    rm -f "$TMP"
    die "pg_dump failed"
fi

# Prove the gzip stream is complete and readable before accepting it.
if ! gzip -t "$TMP" 2>/dev/null; then
    rm -f "$TMP"
    die "gzip integrity check failed — the dump is truncated"
fi

GZ_SIZE=$(stat -c%s "$TMP" 2>/dev/null || stat -f%z "$TMP")
RAW_SIZE=$(gunzip -c "$TMP" | wc -c)

if [ "$RAW_SIZE" -lt "$MIN_BYTES" ]; then
    rm -f "$TMP"
    die "uncompressed dump is only ${RAW_SIZE} bytes (minimum ${MIN_BYTES}). Treating as failed."
fi

# Semantic check: a real pg_dump carries its header and at least one table
# definition. This catches a dump that ran but produced nothing useful —
# wrong database name, permissions problem, empty schema.
if ! gunzip -c "$TMP" | grep -q 'PostgreSQL database dump'; then
    rm -f "$TMP"
    die "dump does not contain a pg_dump header — check DB_USER/DB_NAME"
fi
TABLES=$(gunzip -c "$TMP" | grep -c '^CREATE TABLE' || true)
if [ "$TABLES" -lt 1 ]; then
    rm -f "$TMP"
    die "dump contains no CREATE TABLE statements — has alembic run?"
fi

mv "$TMP" "$OUT"
chmod 0640 "$OUT"
human() { numfmt --to=iec "$1" 2>/dev/null || echo "${1}B"; }
log "wrote $OUT — $(human "$GZ_SIZE") compressed, $(human "$RAW_SIZE") raw, ${TABLES} tables"

# Retention: only prune once a good new backup exists.
PRUNED=$(find "$DEST" -maxdepth 1 -name "${DB_NAME}_*.sql.gz" -type f \
         -mtime "+${KEEP_DAYS}" -print -delete | wc -l)
log "pruned $PRUNED backup(s) older than ${KEEP_DAYS} days"

COUNT=$(find "$DEST" -maxdepth 1 -name "${DB_NAME}_*.sql.gz" -type f | wc -l)
TOTAL=$(du -sh "$DEST" 2>/dev/null | cut -f1)
log "backup complete — $COUNT file(s), $TOTAL total in $DEST"

# A backup you have never restored is a hypothesis, not a backup. Restore one
# into a scratch database (see the header) at least once before go-live.
