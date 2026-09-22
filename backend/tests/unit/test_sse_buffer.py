"""Unit tests for SseReplayBuffer and _passes_filter."""
import time

import pytest

from app.lib.sse_buffer import BufferedEvent, SseReplayBuffer
from app.routers.stream import _passes_filter


# ── SseReplayBuffer ───────────────────────────────────────────────────────────

def _make_event(event_id: str, at: float | None = None) -> BufferedEvent:
    ev = BufferedEvent(
        event_id=event_id,
        event_kind="alert.opened",
        property_id="prop_x",
        payload=f'{{"event_id":"{event_id}"}}',
    )
    if at is not None:
        ev.at = at
    return ev


def test_events_since_unknown_id():
    buf = SseReplayBuffer()
    buf.add(_make_event("evt_1"))
    buf.add(_make_event("evt_2"))
    assert buf.events_since("evt_unknown") == []


def test_events_since_empty_buffer():
    buf = SseReplayBuffer()
    assert buf.events_since("evt_x") == []


def test_events_since_first_id():
    buf = SseReplayBuffer()
    buf.add(_make_event("evt_1"))
    buf.add(_make_event("evt_2"))
    buf.add(_make_event("evt_3"))
    result = buf.events_since("evt_1")
    assert [e.event_id for e in result] == ["evt_2", "evt_3"]


def test_events_since_middle_id():
    buf = SseReplayBuffer()
    buf.add(_make_event("evt_1"))
    buf.add(_make_event("evt_2"))
    buf.add(_make_event("evt_3"))
    result = buf.events_since("evt_2")
    assert [e.event_id for e in result] == ["evt_3"]


def test_events_since_last_id_returns_empty():
    buf = SseReplayBuffer()
    buf.add(_make_event("evt_1"))
    buf.add(_make_event("evt_2"))
    assert buf.events_since("evt_2") == []


def test_add_trims_expired_events():
    buf = SseReplayBuffer(window_seconds=10)
    old_at = time.time() - 20   # older than window
    buf.add(_make_event("evt_old", at=old_at))
    buf.add(_make_event("evt_new"))  # triggers trim
    # old event should have been trimmed
    assert all(e.event_id != "evt_old" for e in buf._events)
    assert any(e.event_id == "evt_new" for e in buf._events)


def test_add_keeps_recent_events():
    buf = SseReplayBuffer(window_seconds=300)
    buf.add(_make_event("evt_1"))
    buf.add(_make_event("evt_2"))
    assert len(buf._events) == 2


def test_window_does_not_expire_recent():
    buf = SseReplayBuffer(window_seconds=300)
    buf.add(_make_event("evt_1"))
    buf.add(_make_event("evt_2"))
    result = buf.events_since("evt_1")
    assert [e.event_id for e in result] == ["evt_2"]


# ── _passes_filter ────────────────────────────────────────────────────────────

def test_filter_no_constraints_passes():
    data = {"event_id": "x", "property_id": "prop_a", "event_kind": "alert.opened"}
    assert _passes_filter(data, None, None, None) is True


def test_filter_property_id_match():
    data = {"property_id": "prop_a"}
    assert _passes_filter(data, ["prop_a"], None, None) is True


def test_filter_property_id_mismatch():
    data = {"property_id": "prop_b"}
    assert _passes_filter(data, ["prop_a"], None, None) is False


def test_filter_multiple_property_ids():
    data = {"property_id": "prop_b"}
    assert _passes_filter(data, ["prop_a", "prop_b"], None, None) is True


def test_filter_kind_match():
    data = {"event_kind": "alert.opened"}
    assert _passes_filter(data, None, {"alert.opened"}, None) is True


def test_filter_kind_mismatch():
    data = {"event_kind": "edge.heartbeat"}
    assert _passes_filter(data, None, {"alert.opened"}, None) is False


def test_filter_min_severity_passes_equal():
    data = {"severity": "p2"}
    assert _passes_filter(data, None, None, "p2") is True


def test_filter_min_severity_passes_better():
    data = {"severity": "p1"}
    assert _passes_filter(data, None, None, "p2") is True


def test_filter_min_severity_fails_worse():
    data = {"severity": "p3"}
    assert _passes_filter(data, None, None, "p2") is False


def test_filter_min_severity_no_severity_field_passes():
    # Message without a severity field should not be filtered out
    data = {"event_kind": "edge.heartbeat"}
    assert _passes_filter(data, None, None, "p1") is True


def test_filter_combined_match():
    data = {"property_id": "prop_a", "event_kind": "alert.opened", "severity": "p1"}
    assert _passes_filter(data, ["prop_a"], {"alert.opened"}, "p2") is True


def test_filter_combined_one_fails():
    data = {"property_id": "prop_b", "event_kind": "alert.opened", "severity": "p1"}
    assert _passes_filter(data, ["prop_a"], {"alert.opened"}, "p2") is False
