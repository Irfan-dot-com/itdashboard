"""End-to-end integration test.

Wires the real parser, real config resolver, real aggregator, real queue.
Mocks only the network.
"""
from unittest.mock import patch
import pytest

import config
from syslog_listener import parse_message
from aggregator import Aggregator
from outbound_queue import OutboundQueue
from uploader import HttpsUploader


class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code


def feed_packet(cfg, aggregator, raw_bytes, src_ip):
    event = parse_message(raw_bytes.decode("utf-8", errors="replace"), src_ip)
    if event.get("parse_error"):
        return
    device_meta = config.resolve_device(cfg, src_ip, event["host"])
    if device_meta is None:
        return
    aggregator.ingest(event, device_meta)


def test_full_pipeline_healthy_then_unhealthy(cfg, clock, tmp_db_path):
    """A healthy device starts emitting errors; cloud should receive a transition alert."""
    queue = OutboundQueue(tmp_db_path)
    aggregator = Aggregator(cfg, queue, clock=clock)

    healthy_packets = [
        b"<134>May  3 12:00:00 sw1 ciscoios: Interface Gi0/1 link state changed to up",
        b"<134>May  3 12:00:01 sw1 ciscoios: User admin logged in from 10.0.5.1",
    ]
    for pkt in healthy_packets:
        feed_packet(cfg, aggregator, pkt, "10.0.0.1")
        clock.advance(1)

    aggregator.devices["dev-001"].last_status = "healthy"

    error_packets = [
        b"<131>May  3 12:01:00 sw1 ciscoios: Power supply 1 fault detected",
        b"<131>May  3 12:01:01 sw1 ciscoios: BGP neighbor 10.0.5.1 state changed to Idle",
        b"<131>May  3 12:01:02 sw1 ciscoios: Interface Gi0/1 link state changed to down",
        b"<131>May  3 12:01:03 sw1 ciscoios: Authentication failure for user admin from 10.0.5.1",
        b"<131>May  3 12:01:04 sw1 ciscoios: Authentication failure for user bob from 10.0.5.2",
        b"<131>May  3 12:01:05 sw1 ciscoios: Authentication failure for user carol from 10.0.5.3",
        b"<131>May  3 12:01:06 sw1 ciscoios: Authentication failure for user dave from 10.0.5.4",
        b"<131>May  3 12:01:07 sw1 ciscoios: Authentication failure for user eve from 10.0.5.5",
    ]
    for pkt in error_packets:
        feed_packet(cfg, aggregator, pkt, "10.0.0.1")
        clock.advance(2)

    batch = queue.take_batch(100)
    payloads = [p for _, p in batch]
    transitions = [p for p in payloads if p.get("kind") == "transition"]

    assert len(transitions) >= 1
    last = transitions[-1]
    assert last["device_id"] == "dev-001"
    assert last["health"]["status"] in ("degraded", "unhealthy")
    assert last["device_class"] == "switch"
    assert last["vendor"] == "cisco"
    assert "top_events" in last


def test_transition_message_has_no_envelope_fields(cfg, clock, tmp_db_path):
    """Message payloads must NOT carry envelope fields — uploader adds those."""
    queue = OutboundQueue(tmp_db_path)
    aggregator = Aggregator(cfg, queue, clock=clock)

    feed_packet(cfg, aggregator,
                b"<131>May  3 12:00:00 sw1 ciscoios: Power supply 1 fault detected",
                "10.0.0.1")
    aggregator.devices["dev-001"].last_status = "healthy"
    feed_packet(cfg, aggregator,
                b"<131>May  3 12:00:01 sw1 ciscoios: BGP neighbor 10.0.5.1 state changed to Idle",
                "10.0.0.1")

    batch = queue.take_batch(100)
    for _, payload in batch:
        for field in ["schema_version", "edge_id", "service_provider",
                      "property_id", "property_name"]:
            assert field not in payload, f"'{field}' should not be in message payload"


def test_full_pipeline_uploads_to_cloud(cfg, clock, tmp_db_path):
    """Verify the data that lands at the cloud endpoint matches the new schema."""
    queue = OutboundQueue(tmp_db_path)
    aggregator = Aggregator(cfg, queue, clock=clock)
    uploader = HttpsUploader(cfg, queue)

    feed_packet(cfg, aggregator,
                b"<131>May  3 12:00:00 sw1 ciscoios: Power supply 1 fault detected",
                "10.0.0.1")
    state = aggregator.devices["dev-001"]
    queue.enqueue(aggregator._build_summary(state, clock(), kind="periodic"))

    captured = {}

    def capture_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["payload"] = json
        captured["headers"] = headers
        return FakeResponse(200)

    with patch("uploader.requests.post", side_effect=capture_post):
        batch = queue.take_batch(uploader.cfg["upload_batch_size"])
        ids = [rid for rid, _ in batch]
        payloads = [p for _, p in batch]
        assert uploader._send(payloads) is True
        queue.ack(ids)

    body = captured["payload"]
    assert body["schema_version"] == "1.0"
    assert body["edge_id"] == "test-edge"
    assert body["service_provider"] == "bluip"
    assert body["property_id"] == "123"
    assert body["property_name"] == "sheraton"
    assert captured["headers"]["X-Provider-Id"] == "bluip"
    assert len(body["messages"]) >= 1
    msg = body["messages"][0]
    assert msg["device_id"] == "dev-001"
    assert msg["device_class"] == "switch"
    assert msg["vendor"] == "cisco"
    assert "health" in msg
    assert "metrics" in msg
    assert queue.depth() == 0


def test_unknown_device_silently_dropped(cfg, clock, tmp_db_path):
    queue = OutboundQueue(tmp_db_path)
    aggregator = Aggregator(cfg, queue, clock=clock)
    pkt = b"<134>May  3 12:00:00 rogue-device foo: hello"
    feed_packet(cfg, aggregator, pkt, "10.99.99.99")
    assert len(aggregator.devices) == 0
    assert queue.depth() == 0


def test_silent_device_detected_as_unhealthy(cfg, clock, tmp_db_path):
    queue = OutboundQueue(tmp_db_path)
    aggregator = Aggregator(cfg, queue, clock=clock)
    feed_packet(cfg, aggregator,
                b"<134>May  3 12:00:00 sw1 ciscoios: Interface Gi0/1 link state changed to up",
                "10.0.0.1")
    clock.advance(cfg["stale_threshold_seconds"] + 60)
    state = aggregator.devices["dev-001"]
    summary = aggregator._build_summary(state, clock(), kind="periodic")
    assert summary["health"]["status"] == "unhealthy"
    assert any("silent_for_" in r for r in summary["health"]["reasons"])


# ---------- Syslog data collection, filter and process ----------

class TestSyslogCollectionFilterProcess:
    """Tests that cover syslog collection → filter → process pipeline."""

    def test_garbage_syslog_never_reaches_aggregator(self, cfg, clock, tmp_db_path):
        """Malformed/garbage syslog packets must be dropped before the aggregator."""
        queue = OutboundQueue(tmp_db_path)
        aggregator = Aggregator(cfg, queue, clock=clock)
        garbage_packets = [
            b"not a syslog at all",
            b"",
            b"XXXX random binary \x00\x01\x02",
        ]
        for pkt in garbage_packets:
            feed_packet(cfg, aggregator, pkt, "10.0.0.1")
        assert len(aggregator.devices) == 0
        assert queue.depth() == 0

    def test_debug_noise_filtered_before_db(self, cfg, clock, tmp_db_path):
        """Debug-level syslog events must never reach the DB queue."""
        queue = OutboundQueue(tmp_db_path)
        aggregator = Aggregator(cfg, queue, clock=clock)
        debug_packets = [
            b"<135>May  3 12:00:00 sw1 ciscoios: debug: polling interface counters",
            b"<135>May  3 12:00:01 sw1 ciscoios: debug: heartbeat timer tick",
        ]
        for pkt in debug_packets:
            feed_packet(cfg, aggregator, pkt, "10.0.0.1")
        assert queue.depth() == 0

    def test_info_uncategorized_noise_filtered(self, cfg, clock, tmp_db_path):
        """Info-level syslog that doesn't match any category is noise and dropped."""
        queue = OutboundQueue(tmp_db_path)
        aggregator = Aggregator(cfg, queue, clock=clock)
        feed_packet(cfg, aggregator,
                    b"<134>May  3 12:00:00 sw1 ciscoios: some random chatter",
                    "10.0.0.1")
        if "dev-001" in aggregator.devices:
            assert len(aggregator.devices["dev-001"].events) == 0

    def test_duplicate_syslog_burst_not_duplicated_in_db(self, cfg, clock, tmp_db_path):
        """100 identical burst packets within 60s produce only 1 event in rolling window."""
        queue = OutboundQueue(tmp_db_path)
        aggregator = Aggregator(cfg, queue, clock=clock)
        pkt = b"<131>May  3 12:00:00 sw1 ciscoios: Power supply 1 fault detected"
        for i in range(100):
            feed_packet(cfg, aggregator, pkt, "10.0.0.1")
            clock.advance(0.1)
        assert len(aggregator.devices["dev-001"].events) == 1

    def test_error_syslog_triggers_health_degradation(self, cfg, clock, tmp_db_path):
        """Error syslogs from a known device must degrade health score."""
        queue = OutboundQueue(tmp_db_path)
        aggregator = Aggregator(cfg, queue, clock=clock)
        error_pkts = [
            b"<131>May  3 12:00:00 sw1 ciscoios: Power supply 1 fault detected",
            b"<131>May  3 12:00:02 sw1 ciscoios: BGP neighbor 10.0.5.1 state changed to Idle",
            b"<131>May  3 12:00:04 sw1 ciscoios: Interface Gi0/1 link state changed to down",
            b"<131>May  3 12:00:06 sw1 ciscoios: Authentication failure for user admin from 10.0.5.1",
            b"<131>May  3 12:00:08 sw1 ciscoios: Authentication failure for user bob from 10.0.5.2",
        ]
        for pkt in error_pkts:
            feed_packet(cfg, aggregator, pkt, "10.0.0.1")
            clock.advance(2)
        state = aggregator.devices["dev-001"]
        _status, score, _reasons = aggregator._compute_health(state, clock())
        assert score < 85

    def test_rfc3164_and_rfc5424_both_processed(self, cfg, clock, tmp_db_path):
        """Both RFC3164 and RFC5424 syslog formats must be parsed and processed."""
        queue = OutboundQueue(tmp_db_path)
        aggregator = Aggregator(cfg, queue, clock=clock)

        rfc3164 = b"<131>May  3 12:00:00 sw1 ciscoios: Power supply 1 fault detected"
        feed_packet(cfg, aggregator, rfc3164, "10.0.0.1")
        assert "dev-001" in aggregator.devices

        rfc5424 = (b"<131>1 2026-05-03T12:00:01.000Z sw2 junos 1234 ID47 - "
                   b"Interface Gi0/1 link state changed to down")
        feed_packet(cfg, aggregator, rfc5424, "10.0.0.2")
        assert "dev-002" in aggregator.devices
