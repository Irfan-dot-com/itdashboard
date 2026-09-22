"""initial-schema

Revision ID: b4df3bf9ecf4
Revises:
Create Date: 2026-05-08 15:49:12.693304

"""
from alembic import op

revision = 'b4df3bf9ecf4'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:

    # ── service_providers ─────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS service_providers (
            provider_id  TEXT        PRIMARY KEY,
            name         TEXT        NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # ── properties ────────────────────────────────────────────────────────────
    # composite PK (provider_id, property_id) — property_id is only unique
    # within a provider's namespace, not globally.
    op.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            provider_id  TEXT        NOT NULL REFERENCES service_providers(provider_id) ON DELETE CASCADE,
            property_id  TEXT        NOT NULL,
            name         TEXT        NOT NULL,
            site_code    TEXT,
            address      TEXT,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (provider_id, property_id)
        )
    """)

    # ── edge_boxes ────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS edge_boxes (
            edge_id                  TEXT        PRIMARY KEY,
            provider_id              TEXT        NOT NULL,
            property_id              TEXT        NOT NULL,
            last_heartbeat_at        TIMESTAMPTZ,
            tracked_devices          INTEGER     NOT NULL DEFAULT 0,
            unhealthy_devices        INTEGER     NOT NULL DEFAULT 0,
            queue_depth              INTEGER     NOT NULL DEFAULT 0,
            summary_interval_seconds INTEGER     NOT NULL DEFAULT 60,
            created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            FOREIGN KEY (provider_id, property_id)
                REFERENCES properties (provider_id, property_id) ON DELETE CASCADE
        )
    """)

    # ── devices ───────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            device_id         TEXT        PRIMARY KEY,
            provider_id       TEXT        NOT NULL,
            property_id       TEXT        NOT NULL,
            edge_id           TEXT        REFERENCES edge_boxes(edge_id) ON DELETE SET NULL,
            label             TEXT,
            device_class      TEXT,
            vendor            TEXT,
            site              TEXT,
            health_status     TEXT        NOT NULL DEFAULT 'unknown'
                              CHECK (health_status IN ('healthy','degraded','unhealthy','unknown')),
            health_score      SMALLINT,
            last_seen_at      TIMESTAMPTZ,
            last_summary_json JSONB,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            FOREIGN KEY (provider_id, property_id)
                REFERENCES properties (provider_id, property_id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_devices_property
            ON devices (provider_id, property_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_devices_edge
            ON devices (edge_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_devices_health
            ON devices (health_status)
            WHERE health_status != 'healthy'
    """)

    # ── raw_events (partitioned by received_at) ───────────────────────────────
    # composite PK required by PostgreSQL for range-partitioned tables
    op.execute("""
        CREATE TABLE IF NOT EXISTS raw_events (
            event_id     TEXT        NOT NULL,
            edge_id      TEXT,
            device_id    TEXT,
            provider_id  TEXT        NOT NULL,
            property_id  TEXT        NOT NULL,
            kind         TEXT        NOT NULL,
            received_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            payload_json JSONB       NOT NULL,
            PRIMARY KEY (event_id, received_at)
        ) PARTITION BY RANGE (received_at)
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS raw_events_default PARTITION OF raw_events DEFAULT
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_raw_events_property_time
            ON raw_events (provider_id, property_id, received_at DESC)
    """)

    # ── events (append-only domain event log, partitioned by occurred_at) ─────
    op.execute("""
        CREATE TABLE IF NOT EXISTS events (
            event_id       UUID        NOT NULL DEFAULT gen_random_uuid(),
            schema_version SMALLINT    NOT NULL DEFAULT 1,
            kind           TEXT        NOT NULL,
            provider_id    TEXT        NOT NULL,
            property_id    TEXT        NOT NULL,
            correlation_id UUID        NOT NULL,
            occurred_at    TIMESTAMPTZ NOT NULL,
            ingested_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            metadata       JSONB       NOT NULL DEFAULT '{}'::jsonb,
            data           JSONB       NOT NULL,
            PRIMARY KEY (event_id, occurred_at)
        ) PARTITION BY RANGE (occurred_at)
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS events_default PARTITION OF events DEFAULT
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_events_property_occurred
            ON events (provider_id, property_id, occurred_at DESC)
    """)

    # ── event_outbox ──────────────────────────────────────────────────────────
    # events INSERT + event_outbox INSERT happen in the same transaction —
    # this is the transactional outbox guarantee.
    op.execute("""
        CREATE TABLE IF NOT EXISTS event_outbox (
            outbox_id    BIGSERIAL   PRIMARY KEY,
            event_id     TEXT        NOT NULL,
            property_id  TEXT        NOT NULL,
            event_kind   TEXT        NOT NULL,
            payload_json JSONB       NOT NULL,
            enqueued_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            published_at TIMESTAMPTZ,
            attempts     INTEGER     NOT NULL DEFAULT 0,
            last_error   TEXT
        )
    """)
    # partial index — poller only reads unpublished rows, keeps scan tiny
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_event_outbox_unpublished
            ON event_outbox (enqueued_at)
            WHERE published_at IS NULL
    """)

    # ── alerts ────────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            alert_id            TEXT        PRIMARY KEY,
            provider_id         TEXT        NOT NULL,
            property_id         TEXT        NOT NULL,
            device_id           TEXT        REFERENCES devices(device_id) ON DELETE SET NULL,
            severity            TEXT        NOT NULL
                                CHECK (severity IN ('p1','p2','p3','p4')),
            state               TEXT        NOT NULL DEFAULT 'opened'
                                CHECK (state IN ('opened','triaged','acting','resolved')),
            alert_kind          TEXT        NOT NULL,
            summary             TEXT,
            correlation_id      TEXT,
            detail_json         JSONB       NOT NULL DEFAULT '{}'::jsonb,
            causal_chain        JSONB,
            auto_fix_authorized BOOLEAN     NOT NULL DEFAULT FALSE,
            auto_fix_action_id  TEXT,
            opened_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            triaged_at          TIMESTAMPTZ,
            acted_at            TIMESTAMPTZ,
            resolved_at         TIMESTAMPTZ,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            FOREIGN KEY (provider_id, property_id)
                REFERENCES properties (provider_id, property_id) ON DELETE CASCADE
        )
    """)
    # main sort index for GET /v1/alerts — sev_rank computed inline
    # CASE expression must be wrapped in parentheses in PostgreSQL index definitions
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_alerts_open_sort
            ON alerts (
                provider_id,
                (CASE severity WHEN 'p1' THEN 1 WHEN 'p2' THEN 2
                               WHEN 'p3' THEN 3 WHEN 'p4' THEN 4 END),
                opened_at DESC,
                alert_id  DESC
            )
            WHERE state IN ('opened','triaged','acting')
    """)
    # estate view + property drill-down
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_alerts_property_state
            ON alerts (provider_id, property_id, state)
    """)
    # dedup check: is there already an open alert for this device+kind?
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_alerts_device_kind_open
            ON alerts (device_id, alert_kind)
            WHERE state IN ('opened','triaged','acting')
    """)

    # ── idempotency_keys ──────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS idempotency_keys (
            key           TEXT        PRIMARY KEY,
            provider_id   TEXT        NOT NULL,
            response_json JSONB       NOT NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_idempotency_created
            ON idempotency_keys (created_at)
    """)

    # ── updated_at auto-trigger ───────────────────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    for tbl in ("service_providers", "properties", "edge_boxes", "devices", "alerts"):
        op.execute(f"""
            DROP TRIGGER IF EXISTS trg_{tbl}_updated_at ON {tbl};
            CREATE TRIGGER trg_{tbl}_updated_at
                BEFORE UPDATE ON {tbl}
                FOR EACH ROW EXECUTE FUNCTION set_updated_at()
        """)


def downgrade() -> None:
    for tbl in ("service_providers", "properties", "edge_boxes", "devices", "alerts"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{tbl}_updated_at ON {tbl}")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at")
    op.execute("DROP TABLE IF EXISTS idempotency_keys")
    op.execute("DROP TABLE IF EXISTS alerts")
    op.execute("DROP TABLE IF EXISTS event_outbox")
    op.execute("DROP TABLE IF EXISTS events_default")
    op.execute("DROP TABLE IF EXISTS events")
    op.execute("DROP TABLE IF EXISTS raw_events_default")
    op.execute("DROP TABLE IF EXISTS raw_events")
    op.execute("DROP TABLE IF EXISTS devices")
    op.execute("DROP TABLE IF EXISTS edge_boxes")
    op.execute("DROP TABLE IF EXISTS properties")
    op.execute("DROP TABLE IF EXISTS service_providers")
