from __future__ import annotations

import uuid
from datetime import datetime, timezone

import asyncpg

from app.lib.health import materialize_alert_from_transition, severity_for_transition
from app.lib.raw_events import insert_raw_event
from app.lib.severity import normalize_severity
from app.repositories.alerts import AlertsRepository
from app.repositories.devices import DevicesRepository
from app.repositories.properties import PropertiesRepository
from app.schemas.ingest import EdgeHealthMessage, PeriodicMessage, TransitionMessage


class _Reject(Exception):
    pass


class Ingestor:
    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn
        self.props = PropertiesRepository(conn)
        self.devices = DevicesRepository(conn)
        self.alerts = AlertsRepository(conn)

    async def handle_batch(
        self,
        edge_id: str,
        service_provider: str,
        property_id: str,
        property_name: str | None,
        messages: list,
    ) -> dict:
        accepted = 0
        rejected = []
        now = datetime.now(timezone.utc)

        await self.props.upsert(service_provider, property_id, name=property_name or property_id)

        for i, msg in enumerate(messages):
            try:
                async with self.conn.transaction():
                    await self._handle_one(edge_id, service_provider, property_id, msg, now)
                accepted += 1
            except _Reject as exc:
                rejected.append({
                    "index": i,
                    "kind": getattr(msg, "kind", "?"),
                    "device_id": getattr(msg, "device_id", None),
                    "reason": str(exc),
                })
            except Exception as exc:
                rejected.append({
                    "index": i,
                    "kind": getattr(msg, "kind", "?"),
                    "device_id": getattr(msg, "device_id", None),
                    "reason": f"internal: {type(exc).__name__}: {exc}",
                })
        return {"accepted": accepted, "rejected": rejected}

    async def _handle_one(
        self,
        edge_id: str,
        provider_id: str,
        property_id: str,
        msg,
        now: datetime,
    ) -> None:
        if isinstance(msg, EdgeHealthMessage):
            await self._edge_health(edge_id, provider_id, property_id, msg, now)
        elif isinstance(msg, PeriodicMessage):
            await self._periodic(edge_id, provider_id, property_id, msg, now)
        elif isinstance(msg, TransitionMessage):
            await self._transition(edge_id, provider_id, property_id, msg, now)

    async def _edge_health(
        self,
        edge_id: str,
        provider_id: str,
        property_id: str,
        msg: EdgeHealthMessage,
        now: datetime,
    ) -> None:
        ts = datetime.fromtimestamp(msg.ts, tz=timezone.utc)
        await self.props.upsert_edge_box(
            edge_id=edge_id,
            provider_id=provider_id,
            property_id=property_id,
            last_heartbeat_at=ts,
            tracked_devices=msg.metrics.tracked_devices,
            unhealthy_devices=msg.metrics.unhealthy_devices,
            queue_depth=msg.metrics.queue_depth,
            summary_interval_seconds=msg.metrics.summary_interval_seconds,
        )
        await insert_raw_event(
            self.conn, kind="edge_health", provider_id=provider_id,
            property_id=property_id, edge_id=edge_id, device_id=None,
            payload=msg.model_dump(),
        )
        await self._enqueue_event(property_id, "edge.heartbeat", {
            "edge_id": edge_id,
            "property_id": property_id,
            "queue_depth": msg.metrics.queue_depth,
        })

    async def _periodic(
        self,
        edge_id: str,
        provider_id: str,
        property_id: str,
        msg: PeriodicMessage,
        now: datetime,
    ) -> None:
        await self.devices.upsert(
            device_id=msg.device_id,
            provider_id=provider_id,
            property_id=property_id,
            edge_id=edge_id,
            label=msg.device_name,
            device_class=msg.device_class,
            vendor=msg.vendor,
            site=msg.site,
        )
        prior = await self.devices.update_health(
            msg.device_id, msg.health.status, msg.health.score, now
        )
        await insert_raw_event(
            self.conn, kind="periodic", provider_id=provider_id,
            property_id=property_id, edge_id=edge_id, device_id=msg.device_id,
            payload=msg.model_dump(),
        )
        if prior is not None:
            await self._enqueue_event(property_id, "device.health_changed", {
                "device_id": msg.device_id,
                "from_status": prior,
                "to_status": msg.health.status,
            })

    async def _transition(
        self,
        edge_id: str,
        provider_id: str,
        property_id: str,
        msg: TransitionMessage,
        now: datetime,
    ) -> None:
        await self.devices.upsert(
            device_id=msg.device_id,
            provider_id=provider_id,
            property_id=property_id,
            edge_id=edge_id,
            label=msg.device_name,
            device_class=msg.device_class,
            vendor=msg.vendor,
            site=msg.site,
        )
        await self.devices.update_health(
            msg.device_id, msg.health.status, msg.health.score, now
        )

        payload = msg.model_dump()
        for ev in payload.get("top_events", []):
            ev["severity"] = normalize_severity(ev.get("severity", ""))

        await insert_raw_event(
            self.conn, kind="transition", provider_id=provider_id,
            property_id=property_id, edge_id=edge_id, device_id=msg.device_id,
            payload=payload,
        )

        if msg.health.status == "healthy":
            resolved = await self.alerts.resolve_all_for_device(msg.device_id, now)
            for row in resolved:
                await self._enqueue_event(row["property_id"], "alert.state_changed", {
                    "alert_id": row["alert_id"],
                    "from": "opened",
                    "to": "resolved",
                })
            return

        kind_label = f"health_transition_to_{msg.health.status}"
        device_row = dict(await self.devices.get(msg.device_id))
        prop_row = dict(await self.props.get(provider_id, property_id))

        existing = await self.alerts.find_open_for_device(msg.device_id, kind_label)
        if existing:
            # Refresh the alert's detail with the latest top_events from this transition
            detail = materialize_alert_from_transition(
                edge_summary=payload,
                device_row=device_row,
                property_row=prop_row,
                opened_at=existing["opened_at"].timestamp(),
            )
            summary = (
                detail["causal_chain"][0]["description"]
                if detail["causal_chain"]
                else kind_label
            )
            await self.alerts.update_detail(existing["alert_id"], detail, summary)
            await self._enqueue_event(property_id, "alert.updated", {
                "alert_id": existing["alert_id"],
            })
            return

        detail = materialize_alert_from_transition(
            edge_summary=payload,
            device_row=device_row,
            property_row=prop_row,
            opened_at=now.timestamp(),
        )
        alert_id = f"alr_{uuid.uuid4().hex}"
        summary = (
            detail["causal_chain"][0]["description"]
            if detail["causal_chain"]
            else kind_label
        )
        await self.alerts.create(
            alert_id=alert_id,
            provider_id=provider_id,
            property_id=property_id,
            device_id=msg.device_id,
            severity=severity_for_transition(msg.health.status),
            alert_kind=kind_label,
            summary=summary,
            correlation_id=detail["identity"]["correlation_id"],
            opened_at=now,
            detail=detail,
        )
        await self._enqueue_event(property_id, "alert.opened", {
            "alert_id":           alert_id,
            "provider_id":        provider_id,
            "property_id":        property_id,
            "property_name":      prop_row.get("name"),
            "device_id":          msg.device_id,
            "device_class":       device_row.get("device_class"),
            "severity":           severity_for_transition(msg.health.status),
            "state":              "opened",
            "alert_kind":         kind_label,
            "summary":            summary,
            "opened_at":          now.isoformat(),
            "triaged_at":         None,
            "acted_at":           None,
            "resolved_at":        None,
            "auto_fix_authorized": False,
            "impact_summary":     "Impact assessment pending",
            "recommended_action": detail.get("recommended_action"),
        })

    async def _enqueue_event(self, property_id: str, event_kind: str, payload: dict) -> None:
        await self.conn.execute(
            """
            INSERT INTO event_outbox (event_id, property_id, event_kind, payload_json)
            VALUES ($1, $2, $3, $4)
            """,
            f"evt_{uuid.uuid4().hex}", property_id, event_kind, payload,
        )
