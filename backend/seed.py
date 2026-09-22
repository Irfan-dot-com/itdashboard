"""
Seed the database with realistic sample data for manual testing.

Run from the it-dashboard-api/ directory:
    python seed.py

What it creates:
  - 1 service provider  : bluip
  - 2 properties        : Grand Hotel London, City Inn Manchester
  - 2 edge boxes        : one per property
  - 6 devices           : 3 per property (switch, phone, pbx)
  - alerts              : property 1 has an unhealthy switch (auto-creates alert)
  - property 2          : all healthy (no alerts)
"""

import asyncio
import httpx

BASE_URL = "http://localhost:4000"
PROVIDER = "bluip"
HEADERS = {"X-Provider-Id": PROVIDER, "Content-Type": "application/json"}

# ── Ingest payloads ───────────────────────────────────────────────────────────

PROPERTY_1_INGEST = {
    "provider_id": PROVIDER,
    "property_id": "prop_grand_london",
    "property_name": "Grand Hotel London",
    "edge_id": "edge-box-london-01",
    "messages": [
        # Edge heartbeat
        {
            "schema_version": "1.0",
            "kind": "edge_health",
            "edge_id": "edge-box-london-01",
            "property_id": "prop_grand_london",
            "device_id": "_edge:edge-box-london-01",
            "reported_at": None,
            "metrics": {
                "tracked_devices": 3,
                "unhealthy_devices": 1,
                "queue_depth": 2,
                "summary_interval_seconds": 60,
            },
        },
        # Healthy PoE switch
        {
            "schema_version": "1.0",
            "kind": "periodic",
            "edge_id": "edge-box-london-01",
            "device_id": "dev-london-switch-01",
            "property_id": "prop_grand_london",
            "device_type": "switch",
            "site": "reception",
            "window_seconds": 300,
            "health": {"status": "healthy", "score": 98, "reasons": []},
            "metrics": {
                "event_count": 0,
                "msg_rate_per_min": 1.0,
                "error_count": 0,
                "warn_count": 0,
                "last_seen_seconds_ago": 5.0,
                "categories": {},
            },
            "top_events": [],
            "_device_meta": {"label": "PoE Switch — Reception", "type": "switch"},
        },
        # Unhealthy DECT phone (creates alert)
        {
            "schema_version": "1.0",
            "kind": "transition",
            "edge_id": "edge-box-london-01",
            "device_id": "dev-london-phone-02",
            "property_id": "prop_grand_london",
            "device_type": "dect_phone",
            "site": "floor_3",
            "window_seconds": 300,
            "health": {
                "status": "unhealthy",
                "score": 25,
                "reasons": ["registration_lost", "error_rate_high"],
            },
            "metrics": {
                "event_count": 12,
                "msg_rate_per_min": 2.4,
                "error_count": 10,
                "warn_count": 2,
                "last_seen_seconds_ago": 45.0,
                "categories": {"registration": 8, "link": 4},
            },
            "top_events": [
                {
                    "ts": 1_700_000_100.0,
                    "severity": "err",
                    "category": "registration",
                    "message": "DECT handset SIP registration failed — 408 Timeout",
                },
            ],
            "_device_meta": {"label": "DECT Phone — Floor 3", "type": "dect_phone"},
        },
        # Degraded PBX
        {
            "schema_version": "1.0",
            "kind": "transition",
            "edge_id": "edge-box-london-01",
            "device_id": "dev-london-pbx-01",
            "property_id": "prop_grand_london",
            "device_type": "pbx",
            "site": "server_room",
            "window_seconds": 300,
            "health": {
                "status": "degraded",
                "score": 65,
                "reasons": ["high_latency"],
            },
            "metrics": {
                "event_count": 4,
                "msg_rate_per_min": 0.8,
                "error_count": 1,
                "warn_count": 3,
                "last_seen_seconds_ago": 12.0,
                "categories": {"latency": 4},
            },
            "top_events": [
                {
                    "ts": 1_700_000_200.0,
                    "severity": "warn",
                    "category": "latency",
                    "message": "SIP response latency exceeded 2000ms threshold",
                },
            ],
            "_device_meta": {"label": "PBX — Server Room", "type": "pbx"},
        },
    ],
}

PROPERTY_2_INGEST = {
    "provider_id": PROVIDER,
    "property_id": "prop_city_manchester",
    "property_name": "City Inn Manchester",
    "edge_id": "edge-box-manchester-01",
    "messages": [
        # Edge heartbeat
        {
            "schema_version": "1.0",
            "kind": "edge_health",
            "edge_id": "edge-box-manchester-01",
            "property_id": "prop_city_manchester",
            "device_id": "_edge:edge-box-manchester-01",
            "reported_at": None,
            "metrics": {
                "tracked_devices": 3,
                "unhealthy_devices": 0,
                "queue_depth": 0,
                "summary_interval_seconds": 60,
            },
        },
        # All 3 devices healthy
        {
            "schema_version": "1.0",
            "kind": "periodic",
            "edge_id": "edge-box-manchester-01",
            "device_id": "dev-man-switch-01",
            "property_id": "prop_city_manchester",
            "device_type": "switch",
            "site": "lobby",
            "window_seconds": 300,
            "health": {"status": "healthy", "score": 96, "reasons": []},
            "metrics": {
                "event_count": 0,
                "msg_rate_per_min": 1.0,
                "error_count": 0,
                "warn_count": 0,
                "last_seen_seconds_ago": 3.0,
                "categories": {},
            },
            "top_events": [],
            "_device_meta": {"label": "Core Switch — Lobby", "type": "switch"},
        },
        {
            "schema_version": "1.0",
            "kind": "periodic",
            "edge_id": "edge-box-manchester-01",
            "device_id": "dev-man-phone-01",
            "property_id": "prop_city_manchester",
            "device_type": "dect_phone",
            "site": "floor_1",
            "window_seconds": 300,
            "health": {"status": "healthy", "score": 100, "reasons": []},
            "metrics": {
                "event_count": 0,
                "msg_rate_per_min": 0.5,
                "error_count": 0,
                "warn_count": 0,
                "last_seen_seconds_ago": 8.0,
                "categories": {},
            },
            "top_events": [],
            "_device_meta": {"label": "DECT Phone — Floor 1", "type": "dect_phone"},
        },
        {
            "schema_version": "1.0",
            "kind": "periodic",
            "edge_id": "edge-box-manchester-01",
            "device_id": "dev-man-pbx-01",
            "property_id": "prop_city_manchester",
            "device_type": "pbx",
            "site": "server_room",
            "window_seconds": 300,
            "health": {"status": "healthy", "score": 92, "reasons": []},
            "metrics": {
                "event_count": 0,
                "msg_rate_per_min": 0.3,
                "error_count": 0,
                "warn_count": 0,
                "last_seen_seconds_ago": 20.0,
                "categories": {},
            },
            "top_events": [],
            "_device_meta": {"label": "PBX — Server Room", "type": "pbx"},
        },
    ],
}


async def seed():
    import asyncpg

    # ── Step 1: Insert service_providers (no API endpoint for this) ───────────
    print("1. Seeding service_providers...")
    conn = await asyncpg.connect("postgresql://hosp:hosp@localhost:5432/hosp_dev")
    await conn.execute("""
        INSERT INTO service_providers (provider_id, name)
        VALUES ('bluip', 'BluIP Hospitality')
        ON CONFLICT DO NOTHING
    """)
    await conn.close()
    print("   OK — provider 'bluip' ready")

    # ── Step 2: Ingest sample data via the API ────────────────────────────────
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:

        print("\n2. Ingesting Property 1 — Grand Hotel London...")
        r = await client.post("/v1/edge/ingest", json=PROPERTY_1_INGEST, headers=HEADERS)
        r.raise_for_status()
        result = r.json()
        print(f"   accepted={result['accepted']}  rejected={result['rejected']}")

        print("\n3. Ingesting Property 2 — City Inn Manchester...")
        r = await client.post("/v1/edge/ingest", json=PROPERTY_2_INGEST, headers=HEADERS)
        r.raise_for_status()
        result = r.json()
        print(f"   accepted={result['accepted']}  rejected={result['rejected']}")

        # ── Step 3: Print a summary of what's now in the system ──────────────
        print("\n── What's in the system now ─────────────────────────────────")

        r = await client.get("/v1/estate", headers=HEADERS)
        estate = r.json()
        print(f"\n  GET /v1/estate")
        for p in estate.get("properties", []):
            print(f"    {p['property_id']:30s}  {p['health_status']:10s}  score={p['health_score']}")

        r = await client.get("/v1/alerts", headers=HEADERS)
        alerts = r.json()
        items = alerts.get("items", [])
        print(f"\n  GET /v1/alerts  ({len(items)} open)")
        for a in items:
            print(f"    {a['alert_id']}  {a['severity']}  {a['summary'][:60]}")

        print("\n── Done. API is ready for testing at http://localhost:4000/docs ──")


if __name__ == "__main__":
    asyncio.run(seed())
