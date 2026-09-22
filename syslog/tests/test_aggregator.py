"""Aggregator tests — stateful health engine with fake clock injection."""
import pytest
from aggregator import Aggregator
from conftest import make_event


class StubQueue:
    def __init__(self):
        self.items = []
    def enqueue(self, payload):
        self.items.append(payload)
    def depth(self):
        return len(self.items)


@pytest.fixture
def queue():
    return StubQueue()


@pytest.fixture
def agg(cfg, queue, clock):
    return Aggregator(cfg, queue, clock=clock)


@pytest.fixture
def device_meta():
    return {
        "device_id": "dev-001",
        "device_name": "switch_floor1",
        "device_class": "switch",
        "vendor": "cisco",
        "site": "hq",
    }


# ---------- Ingestion basics ----------

class TestIngest:
    def test_first_event_creates_device_state(self, agg, device_meta):
        agg.ingest(make_event("Interface GigabitEthernet0/1 link state changed to up"),
                   device_meta)
        assert "dev-001" in agg.devices
        assert len(agg.devices["dev-001"].events) == 1

    def test_noise_is_dropped(self, agg, device_meta):
        agg.ingest(make_event("some random uncategorized chatter", severity="info"),
                   device_meta)
        if "dev-001" in agg.devices:
            assert len(agg.devices["dev-001"].events) == 0

    def test_unknown_category_warning_is_kept(self, agg, device_meta):
        agg.ingest(make_event("strange unparseable problem", severity="warning"),
                   device_meta)
        assert len(agg.devices["dev-001"].events) == 1


# ---------- Deduplication (duplicate/garbage log filter) ----------

class TestDedup:
    def test_identical_messages_within_window_dedup(self, agg, device_meta, clock):
        msg = "Interface GigabitEthernet0/1 link state changed to down"
        for _ in range(5):
            agg.ingest(make_event(msg, severity="error"), device_meta)
            clock.advance(1)
        assert len(agg.devices["dev-001"].events) == 1

    def test_dedup_treats_varying_numbers_as_same(self, agg, device_meta, clock):
        agg.ingest(make_event("Interface GigabitEthernet0/1 link state changed to down",
                              severity="error"), device_meta)
        clock.advance(2)
        agg.ingest(make_event("Interface GigabitEthernet0/47 link state changed to down",
                              severity="error"), device_meta)
        assert len(agg.devices["dev-001"].events) == 1

    def test_dedup_window_expires(self, agg, device_meta, clock):
        msg = "Authentication failure for user admin from 10.0.5.1"
        agg.ingest(make_event(msg, severity="error"), device_meta)
        clock.advance(70)
        agg.ingest(make_event(msg, severity="error"), device_meta)
        assert len(agg.devices["dev-001"].events) == 2

    def test_different_categories_not_deduped(self, agg, device_meta):
        agg.ingest(make_event("Interface GigabitEthernet0/1 link state changed to down",
                              severity="error"), device_meta)
        agg.ingest(make_event("Power supply 1 fault detected", severity="error"),
                   device_meta)
        assert len(agg.devices["dev-001"].events) == 2

    def test_burst_of_identical_logs_counts_as_one(self, agg, device_meta, clock):
        """100 identical burst messages within 60s should produce only 1 event."""
        msg = "BGP neighbor 10.0.5.1 state changed to Idle"
        for i in range(100):
            agg.ingest(make_event(msg, severity="error"), device_meta)
            clock.advance(0.1)
        assert len(agg.devices["dev-001"].events) == 1


# ---------- Window eviction ----------

class TestWindow:
    def test_old_events_evicted_outside_window(self, agg, cfg, device_meta, clock):
        agg.ingest(make_event("Interface GigabitEthernet0/1 link state changed to up",
                              severity="info"), device_meta)
        clock.advance(cfg["window_seconds"] + 10)
        agg.ingest(make_event("Power supply 1 fault detected", severity="error"),
                   device_meta)
        assert len(agg.devices["dev-001"].events) == 1
        assert "Power supply" in agg.devices["dev-001"].events[0][3]


# ---------- Health computation ----------

class TestHealth:
    def test_no_events_yet_is_unknown(self, agg):
        from aggregator import DeviceState
        ds = DeviceState(device_id="dev-test", device_name="x",
                         device_class="switch", vendor="cisco", site="hq")
        status, score, reasons = agg._compute_health(ds, agg.clock())
        assert status == "unknown"
        assert "never_seen" in reasons

    def test_silent_device_marked_unhealthy(self, agg, cfg, device_meta, clock):
        agg.ingest(make_event("Interface GigabitEthernet0/1 link state changed to up",
                              severity="info"), device_meta)
        clock.advance(cfg["stale_threshold_seconds"] + 10)
        state = agg.devices["dev-001"]
        status, _score, reasons = agg._compute_health(state, clock())
        assert status == "unhealthy"
        assert any("silent_for_" in r for r in reasons)

    def test_healthy_with_only_info_events(self, agg, device_meta):
        for _ in range(3):
            agg.ingest(make_event("Configuration saved by user admin", severity="info"),
                       device_meta)
        state = agg.devices["dev-001"]
        status, score, _ = agg._compute_health(state, agg.clock())
        assert status == "healthy"
        assert score >= 85

    def test_many_errors_makes_unhealthy(self, agg, device_meta, clock):
        error_msgs = [
            "Power supply 1 fault detected",
            "BGP neighbor 10.0.5.1 state changed to Idle",
            "Authentication failure for user admin from 10.0.5.1",
            "Interface GigabitEthernet0/1 link state changed to down",
            "Authentication failure for user bob from 10.0.5.2",
            "Interface GigabitEthernet0/2 link state changed to down",
            "Power supply 2 fault detected",
        ]
        for msg in error_msgs:
            agg.ingest(make_event(msg, severity="error"), device_meta)
            clock.advance(2)
        state = agg.devices["dev-001"]
        status, score, reasons = agg._compute_health(state, clock())
        assert status in ("degraded", "unhealthy")

    def test_link_flap_reason_set(self, agg, device_meta, clock):
        for i in range(3):
            agg.ingest(make_event(
                f"Interface GigabitEthernet0/{i} link state changed to down",
                severity="error"), device_meta)
            clock.advance(70)
        state = agg.devices["dev-001"]
        _, _, reasons = agg._compute_health(state, clock())
        assert "link_flap" in reasons


# ---------- State transitions ----------

class TestTransitions:
    def test_transition_emits_alert(self, agg, queue, device_meta, clock):
        agg.ingest(make_event("Interface GigabitEthernet0/1 link state changed to up",
                              severity="info"), device_meta)
        agg.devices["dev-001"].last_status = "healthy"
        queue.items.clear()

        error_msgs = [
            "Power supply 1 fault detected",
            "BGP neighbor 10.0.5.1 state changed to Idle",
            "Interface GigabitEthernet0/1 link state changed to down",
            "Authentication failure for user admin from 10.0.5.1",
            "Authentication failure for user bob from 10.0.5.2",
            "Authentication failure for user carol from 10.0.5.3",
            "Authentication failure for user dave from 10.0.5.4",
            "Authentication failure for user eve from 10.0.5.5",
        ]
        for msg in error_msgs:
            agg.ingest(make_event(msg, severity="error"), device_meta)
            clock.advance(2)

        transitions = [m for m in queue.items if m.get("kind") == "transition"]
        assert len(transitions) >= 1
        assert transitions[-1]["device_id"] == "dev-001"
        assert transitions[-1]["health"]["status"] != "healthy"

    def test_no_transition_emit_when_status_unchanged(self, agg, queue, device_meta, clock):
        agg.ingest(make_event("Interface GigabitEthernet0/1 link state changed to up",
                              severity="info"), device_meta)
        agg.devices["dev-001"].last_status = "healthy"
        queue.items.clear()
        clock.advance(70)
        agg.ingest(make_event("User alice logged in from 10.0.5.1", severity="info"),
                   device_meta)
        transitions = [m for m in queue.items if m.get("kind") == "transition"]
        assert len(transitions) == 0


# ---------- Summary payload shape ----------

class TestSummary:
    def test_summary_contract(self, agg, device_meta):
        agg.ingest(make_event("Interface GigabitEthernet0/1 link state changed to up",
                              severity="info"), device_meta)
        state = agg.devices["dev-001"]
        summary = agg._build_summary(state, agg.clock(), kind="periodic")

        for key in ["kind", "ts", "device_id", "device_name", "device_class",
                    "vendor", "site", "health", "metrics"]:
            assert key in summary, f"missing key: {key}"

        for key in ["status", "score", "reasons"]:
            assert key in summary["health"]

        for key in ["event_count", "error_count", "warn_count"]:
            assert key in summary["metrics"]

        assert summary["device_id"] == "dev-001"
        assert summary["device_name"] == "switch_floor1"
        assert summary["device_class"] == "switch"
        assert summary["vendor"] == "cisco"
        assert summary["kind"] == "periodic"

    def test_periodic_has_no_top_events(self, agg, device_meta):
        agg.ingest(make_event("Power supply 1 fault detected", severity="error"),
                   device_meta)
        state = agg.devices["dev-001"]
        summary = agg._build_summary(state, agg.clock(), kind="periodic")
        assert "top_events" not in summary

    def test_transition_has_top_events(self, agg, device_meta):
        agg.ingest(make_event("Power supply 1 fault detected", severity="error"),
                   device_meta)
        state = agg.devices["dev-001"]
        summary = agg._build_summary(state, agg.clock(), kind="transition")
        assert "top_events" in summary
        assert len(summary["top_events"]) <= 5

    def test_top_events_truncated_to_five(self, agg, device_meta, clock):
        msgs = [
            "Power supply 1 fault detected",
            "BGP neighbor 10.0.5.1 state changed to Idle",
            "Interface GigabitEthernet0/1 link state changed to down",
            "Authentication failure for user admin from 10.0.5.1",
            "Authentication failure for user bob from 10.0.5.2",
            "Authentication failure for user carol from 10.0.5.3",
            "CPU utilization at 95%",
        ]
        for msg in msgs:
            agg.ingest(make_event(msg, severity="error"), device_meta)
            clock.advance(2)
        state = agg.devices["dev-001"]
        summary = agg._build_summary(state, clock(), kind="transition")
        assert len(summary["top_events"]) <= 5

    def test_edge_health_summary_shape(self, agg, device_meta, clock):
        agg.ingest(make_event("Power supply 1 fault detected", severity="error"),
                   device_meta)
        now = clock()
        summary = agg._build_self_summary(now)
        assert summary["kind"] == "edge_health"
        assert summary["ts"] == now
        for key in ["tracked_devices", "unhealthy_devices",
                    "queue_depth", "summary_interval_seconds"]:
            assert key in summary["metrics"], f"missing edge_health metric: {key}"

    def test_summary_no_envelope_fields(self, agg, device_meta):
        """Message-level payloads must NOT contain envelope fields (moved to uploader)."""
        agg.ingest(make_event("Power supply 1 fault detected", severity="error"),
                   device_meta)
        state = agg.devices["dev-001"]
        summary = agg._build_summary(state, agg.clock(), kind="periodic")
        for key in ["schema_version", "edge_id", "service_provider",
                    "property_id", "property_name"]:
            assert key not in summary, f"envelope field '{key}' should not be in message"
