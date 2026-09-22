"""
Insert the default service provider into the database.

Run from the it-dashboard-api/ directory:
    python add_provider.py
"""

import asyncio
import os

import asyncpg

# Reads DATABASE_URL from environment (set by docker-compose).
# Falls back to localhost for running directly on the host machine.
DB_URL = os.environ.get("DATABASE_URL", "postgresql://hosp:hosp@localhost:5432/hosp_dev")


async def add_provider():
    print("Connecting to database...")
    conn = await asyncpg.connect(DB_URL)

    try:
        await conn.execute("""
            INSERT INTO service_providers (provider_id, name)
            VALUES ('bluip', 'BluIP Hospitality')
            ON CONFLICT DO NOTHING
        """)

        row = await conn.fetchrow(
            "SELECT provider_id, name, created_at FROM service_providers WHERE provider_id = 'bluip'"
        )

        if row:
            print(f"\nOK — provider ready:")
            print(f"  provider_id : {row['provider_id']}")
            print(f"  name        : {row['name']}")
            print(f"  created_at  : {row['created_at']}")
        else:
            print("WARNING: insert ran but row not found.")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(add_provider())
