from __future__ import annotations

import asyncpg
from datetime import datetime

from app.lib.cursor import encode_cursor, decode_cursor


# Inline severity rank expression — mirrors the idx_alerts_open_sort index
_SEV_RANK = (
    "CASE severity WHEN 'p1' THEN 1 WHEN 'p2' THEN 2 "
    "              WHEN 'p3' THEN 3 ELSE 4 END"
)

_SEV_TO_INT = {"p1": 1, "p2": 2, "p3": 3, "p4": 4}


class AlertsRepository:
    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    async def create(
        self,
        alert_id: str,
        provider_id: str,
        property_id: str,
        device_id: str | None,
        severity: str,
        alert_kind: str,
        summary: str,
        correlation_id: str | None,
        opened_at: datetime,
        detail: dict,
    ) -> None:
        # asyncpg passes dicts directly to JSONB columns
        await self.conn.execute(
            """
            INSERT INTO alerts
                (alert_id, provider_id, property_id, device_id, severity,
                 state, alert_kind, summary, correlation_id, opened_at, detail_json)
            VALUES ($1,$2,$3,$4,$5,'opened',$6,$7,$8,$9,$10)
            """,
            alert_id, provider_id, property_id, device_id, severity,
            alert_kind, summary, correlation_id, opened_at, detail,
        )

    async def update_detail(
        self, alert_id: str, detail: dict, summary: str
    ) -> None:
        """Refresh detail_json and summary for an existing open alert (e.g. new top_events)."""
        await self.conn.execute(
            "UPDATE alerts SET detail_json=$2, summary=$3 WHERE alert_id=$1",
            alert_id, detail, summary,
        )

    async def update_state(
        self, alert_id: str, new_state: str, at: datetime
    ) -> str | None:
        """Transition alert state. Returns prior state, or None if alert not found."""
        prior = await self.conn.fetchval(
            "SELECT state FROM alerts WHERE alert_id = $1",
            alert_id,
        )
        if prior is None:
            return None
        ts_col = {
            "triaged": "triaged_at",
            "acting":  "acted_at",
            "resolved": "resolved_at",
        }.get(new_state)
        if ts_col:
            await self.conn.execute(
                f"UPDATE alerts SET state=$2, {ts_col}=$3 WHERE alert_id=$1",
                alert_id, new_state, at,
            )
        else:
            await self.conn.execute(
                "UPDATE alerts SET state=$2 WHERE alert_id=$1",
                alert_id, new_state,
            )
        return prior

    async def get(self, alert_id: str, provider_id: str) -> asyncpg.Record | None:
        return await self.conn.fetchrow(
            """
            SELECT a.*, d.edge_id
              FROM alerts a
              LEFT JOIN devices d ON a.device_id = d.device_id
             WHERE a.alert_id = $1 AND a.provider_id = $2
            """,
            alert_id, provider_id,
        )

    async def find_open_for_device(
        self, device_id: str, alert_kind: str
    ) -> asyncpg.Record | None:
        return await self.conn.fetchrow(
            """
            SELECT * FROM alerts
            WHERE device_id=$1 AND alert_kind=$2
              AND state IN ('opened','triaged','acting')
            ORDER BY opened_at DESC
            LIMIT 1
            """,
            device_id, alert_kind,
        )

    async def list(
        self,
        provider_id: str,
        *,
        states: list[str],
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict:
        params: list = [provider_id, states, limit + 1]
        cursor_clause = ""

        if cursor:
            sev_rank, opened_at_str, alert_id = decode_cursor(cursor)
            opened_at_dt = datetime.fromisoformat(opened_at_str)
            cursor_clause = f"""
                AND (  {_SEV_RANK} > $4
                   OR ({_SEV_RANK} = $4 AND a.opened_at < $5::timestamptz)
                   OR ({_SEV_RANK} = $4 AND a.opened_at = $5::timestamptz AND a.alert_id < $6))
            """
            params += [sev_rank, opened_at_dt, alert_id]

        rows = await self.conn.fetch(
            f"""
            SELECT a.*, p.name AS property_name, d.device_class,
                   {_SEV_RANK} AS sev_rank
              FROM alerts a
              JOIN properties p USING (provider_id, property_id)
              LEFT JOIN devices d ON a.device_id = d.device_id
             WHERE a.provider_id = $1
               AND a.state = ANY($2::text[])
               {cursor_clause}
             ORDER BY {_SEV_RANK} ASC, a.opened_at DESC, a.alert_id DESC
             LIMIT $3
            """,
            *params,
        )

        has_more = len(rows) > limit
        items = [dict(r) for r in rows[:limit]]
        next_cursor = None
        if has_more and items:
            last = items[-1]
            sev = _SEV_TO_INT.get(last["severity"], 4)
            next_cursor = encode_cursor(sev, last["opened_at"].isoformat(), last["alert_id"])
        return {"items": items, "next_cursor": next_cursor, "has_more": has_more}

    async def list_by_property(
        self,
        provider_id: str,
        property_id: str,
        *,
        states: list[str],
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict:
        """Paginated alert rows for a single property, ordered by severity then recency."""
        params: list = [provider_id, property_id, states, limit + 1]
        cursor_clause = ""

        if cursor:
            sev_rank, opened_at_str, alert_id = decode_cursor(cursor)
            opened_at_dt = datetime.fromisoformat(opened_at_str)
            cursor_clause = f"""
                AND (  {_SEV_RANK} > $5
                   OR ({_SEV_RANK} = $5 AND a.opened_at < $6::timestamptz)
                   OR ({_SEV_RANK} = $5 AND a.opened_at = $6::timestamptz AND a.alert_id < $7))
            """
            params += [sev_rank, opened_at_dt, alert_id]

        rows = await self.conn.fetch(
            f"""
            SELECT a.*, d.edge_id, {_SEV_RANK} AS sev_rank
              FROM alerts a
              LEFT JOIN devices d ON a.device_id = d.device_id
             WHERE a.provider_id = $1
               AND a.property_id = $2
               AND a.state = ANY($3::text[])
               {cursor_clause}
             ORDER BY {_SEV_RANK} ASC, a.opened_at DESC, a.alert_id DESC
             LIMIT $4
            """,
            *params,
        )

        has_more = len(rows) > limit
        items = [dict(r) for r in rows[:limit]]
        next_cursor = None
        if has_more and items:
            last = items[-1]
            sev = _SEV_TO_INT.get(last["severity"], 4)
            next_cursor = encode_cursor(sev, last["opened_at"].isoformat(), last["alert_id"])
        return {"items": items, "next_cursor": next_cursor, "has_more": has_more}

    async def count_by_severity(
        self, provider_id: str, property_id: str | None = None
    ) -> dict:
        params: list = [provider_id]
        prop_clause = ""
        if property_id:
            prop_clause = "AND property_id = $2"
            params.append(property_id)
        rows = await self.conn.fetch(
            f"""
            SELECT severity, COUNT(*) AS c FROM alerts
             WHERE provider_id=$1 {prop_clause}
               AND state IN ('opened','triaged','acting')
             GROUP BY severity
            """,
            *params,
        )
        out: dict[str, int] = {"p1": 0, "p2": 0, "p3": 0, "p4": 0}
        for r in rows:
            out[r["severity"]] = int(r["c"])
        return out

    async def worst_open(
        self, provider_id: str, property_id: str
    ) -> asyncpg.Record | None:
        return await self.conn.fetchrow(
            f"""
            SELECT * FROM alerts
             WHERE provider_id=$1 AND property_id=$2
               AND state IN ('opened','triaged','acting')
             ORDER BY {_SEV_RANK} ASC, opened_at DESC
             LIMIT 1
            """,
            provider_id, property_id,
        )

    async def resolve_all_for_device(
        self, device_id: str, at: datetime
    ) -> list[dict]:
        """Resolve all open alerts for a device. Returns list of resolved rows."""
        rows = await self.conn.fetch(
            """
            UPDATE alerts SET state='resolved', resolved_at=$2
             WHERE device_id=$1 AND state IN ('opened','triaged','acting')
             RETURNING alert_id, property_id
            """,
            device_id, at,
        )
        return [dict(r) for r in rows]
