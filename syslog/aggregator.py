import re
import time
import threading
from collections import deque, Counter
from dataclasses import dataclass, field

from classify import classify, is_noise, SEVERITY_RANK


@dataclass
class DeviceState:
    device_id: str
    device_name: str
    device_class: str
    vendor: str
    site: str
    events: deque = field(default_factory=deque)
    last_seen: float = 0.0
    last_status: str = "unknown"
    dedup_cache: dict = field(default_factory=dict)


def _signature(category, severity, message):
    norm = re.sub(r"\b(\d+|[0-9a-f:]{11,17})\b", "#", message.lower())
    return f"{category}|{severity}|{norm[:80]}"


class Aggregator:
    def __init__(self, cfg, outbound_queue, clock=time.time):
        self.cfg = cfg
        self.outbound = outbound_queue
        self.clock = clock
        self.devices: dict = {}
        self.lock = threading.Lock()
        self._stop = threading.Event()

    def ingest(self, event, device_meta):
        category = classify(event["message"], event["severity"])
        if is_noise(event["severity"], category):
            return

        device_id = device_meta["device_id"]
        now = self.clock()

        with self.lock:
            state = self.devices.get(device_id)
            if state is None:
                state = DeviceState(
                    device_id=device_id,
                    device_name=device_meta.get("device_name", device_id),
                    device_class=device_meta.get("device_class", "unknown"),
                    vendor=device_meta.get("vendor", "unknown"),
                    site=device_meta.get("site", "unknown"),
                )
                self.devices[device_id] = state

            sig = _signature(category, event["severity"], event["message"])
            count, first_ts = state.dedup_cache.get(sig, (0, now))
            if count > 0 and (now - first_ts) < 60:
                state.dedup_cache[sig] = (count + 1, first_ts)
                state.last_seen = now
                return
            state.dedup_cache[sig] = (1, now)

            state.events.append((now, event["severity"], category, event["message"]))
            state.last_seen = now
            self._evict_old(state, now)

            new_status, _score, _reasons = self._compute_health(state, now)
            if new_status != state.last_status and state.last_status != "unknown":
                self.outbound.enqueue(self._build_summary(state, now, kind="transition"))
            state.last_status = new_status

    def _evict_old(self, state, now):
        cutoff = now - self.cfg["window_seconds"]
        while state.events and state.events[0][0] < cutoff:
            state.events.popleft()
        state.dedup_cache = {
            sig: (c, ts)
            for sig, (c, ts) in state.dedup_cache.items()
            if (now - ts) < 60
        }

    def _compute_health(self, state, now):
        if state.last_seen == 0:
            return "unknown", 0, ["never_seen"]

        silent_for = now - state.last_seen
        if silent_for > self.cfg["stale_threshold_seconds"]:
            return "unhealthy", 10, [f"silent_for_{int(silent_for)}s"]

        sev_counts = Counter()
        cat_counts = Counter()
        for _ts, sev, cat, _msg in state.events:
            sev_counts[sev] += 1
            cat_counts[cat] += 1

        errors = sum(c for s, c in sev_counts.items() if SEVERITY_RANK.get(s, 6) <= 3)
        warns  = sum(c for s, c in sev_counts.items() if SEVERITY_RANK.get(s, 6) == 4)

        score = 100
        score -= min(errors * 8, 60)
        score -= min(warns * 2, 20)
        if silent_for > self.cfg["stale_threshold_seconds"] / 2:
            score -= 15

        reasons = []
        if errors >= 5:                         reasons.append("error_rate_high")
        if warns >= 10:                         reasons.append("warn_rate_high")
        if cat_counts.get("link", 0) >= 3:     reasons.append("link_flap")
        if cat_counts.get("auth", 0) >= 5:     reasons.append("auth_failures")
        if cat_counts.get("hardware", 0) >= 1: reasons.append("hardware_fault")

        if score >= 85:   status = "healthy"
        elif score >= 60: status = "degraded"
        else:             status = "unhealthy"
        return status, max(score, 0), reasons

    def _build_summary(self, state, now, kind="periodic"):
        """Build periodic/transition summary payload with top_events."""
        status, score, reasons = self._compute_health(state, now)
        sev_counts = Counter(s for _t, s, _c, _m in state.events)
        cat_counts = Counter(c for _t, _s, c, _m in state.events)

        payload = {
            "kind": kind,
            "ts": now,
            "device_id": state.device_id,
            "device_name": state.device_name,
            "device_class": state.device_class,
            "vendor": state.vendor,
            "site": state.site,
            "health": {
                "status": status,
                "score": score,
                "reasons": reasons,
            },
            "metrics": {
                "event_count": len(state.events),
                "error_count": sum(
                    c for s, c in sev_counts.items() if SEVERITY_RANK.get(s, 6) <= 3
                ),
                "warn_count": sev_counts.get("warning", 0) + sev_counts.get("warn", 0),
            },
        }

        recent = sorted(
            state.events,
            key=lambda e: (SEVERITY_RANK.get(e[1], 6), -e[0]),
        )[:5]
        payload["top_events"] = [
            {"ts": t, "severity": s, "category": c, "message": m[:200]}
            for t, s, c, m in recent
        ]

        return payload

    def run_periodic(self):
        interval = self.cfg["summary_interval_seconds"]
        while not self._stop.is_set():
            now = self.clock()
            with self.lock:
                for state in self.devices.values():
                    self._evict_old(state, now)
                    self.outbound.enqueue(self._build_summary(state, now))
            if self._stop.wait(interval):
                break

    def stop(self):
        self._stop.set()
