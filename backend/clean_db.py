"""
Delete ALL data from every table in the dev database.
Tables are kept — only the rows are removed.

Run from the it-dashboard-api/ directory:
    python clean_db.py

What gets cleared:
    service_providers  → cascades to properties → edge_boxes, devices, alerts
    raw_events         → all raw ingest event logs
    events             → all domain events
    event_outbox       → all pending outbox messages
    idempotency_keys   → all cached idempotency responses
"""

import asyncio
import os

import asyncpg

# Reads DATABASE_URL from environment (set by docker-compose).
# Falls back to localhost for running directly on the host machine.
DB_URL = os.environ.get("DATABASE_URL", "postgresql://hosp:hosp@localhost:5432/hosp_dev")


async def clean():
    print("Connecting to database...")
    conn = await asyncpg.connect(DB_URL)

    try:
        print("\nCleaning all tables...\n")

        # Count rows before deleting so we can show what was removed
        tables = [
            "service_providers",
            "properties",
            "edge_boxes",
            "devices",
            "alerts",
            "raw_events",
            "events",
            "event_outbox",
            "idempotency_keys",
        ]

        for table in tables:
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
            print(f"  {table:<25} {count} rows")

        print("\nTruncating...")

        # CASCADE handles all FK dependencies automatically:
        # service_providers → properties → edge_boxes, devices, alerts
        await conn.execute("""
            TRUNCATE
                service_providers,
                raw_events,
                events,
                event_outbox,
                idempotency_keys
            CASCADE
        """)

        print("\nVerifying...")
        for table in tables:
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
            status = "OK" if count == 0 else f"WARNING: {count} rows remain"
            print(f"  {table:<25} {status}")

        print("\nDone. Database is clean.")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(clean())
