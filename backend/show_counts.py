"""
Show row counts for every table in the dev database.
Nothing is modified — read-only.

Run from the it-dashboard-api/ directory:
    python show_counts.py
"""

import asyncio
import os

import asyncpg

DB_URL = os.environ.get("DATABASE_URL", "postgresql://hosp:hosp@localhost:5432/hosp_dev")

TABLES = [
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


async def show_counts():
    print(f"Connecting to {DB_URL}...\n")
    conn = await asyncpg.connect(DB_URL)

    try:
        print(f"{'Table':<25} {'Rows':>8}")
        print("-" * 35)
        total = 0
        for table in TABLES:
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
            print(f"  {table:<23} {count:>8,}")
            total += count
        print("-" * 35)
        print(f"  {'TOTAL':<23} {total:>8,}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(show_counts())
