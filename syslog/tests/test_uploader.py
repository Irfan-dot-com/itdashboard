"""Uploader tests — mock requests.post, verify new envelope structure and headers."""
from unittest.mock import patch
import pytest
from outbound_queue import OutboundQueue
from uploader import HttpsUploader


class FakeResponse:
    def __init__(self, status_code, text="", reason="OK"):
        self.status_code = status_code
        self.text = text
        self.reason = reason


@pytest.fixture
def queue(tmp_db_path):
    q = OutboundQueue(tmp_db_path)
    for i in range(3):
        q.enqueue({
            "kind": "periodic",
            "ts": 1700000000.0 + i,
            "device_id": "dev-001",
            "device_name": "switch_floor1",
            "device_class": "switch",
            "vendor": "cisco",
            "site": "hq",
            "health": {"status": "healthy", "score": 95, "reasons": []},
            "metrics": {"event_count": i, "error_count": 0, "warn_count": 0},
        })
    return q


@pytest.fixture
def uploader(cfg, queue):
    return HttpsUploader(cfg, queue)


class TestSendOnce:
    def test_2xx_returns_true(self, uploader):
        with patch("uploader.requests.post", return_value=FakeResponse(200)) as p:
            assert uploader._send([{"kind": "periodic"}]) is True
            p.assert_called_once()

    def test_5xx_returns_false(self, uploader):
        with patch("uploader.requests.post", return_value=FakeResponse(503)):
            assert uploader._send([{"kind": "periodic"}]) is False

    def test_4xx_returns_false(self, uploader):
        with patch("uploader.requests.post", return_value=FakeResponse(400)):
            assert uploader._send([{"kind": "periodic"}]) is False

    def test_uses_provider_header_not_bearer(self, uploader):
        """New API uses X-Provider-Id header, not Authorization: Bearer."""
        with patch("uploader.requests.post", return_value=FakeResponse(200)) as p:
            uploader._send([{"kind": "periodic"}])
            kwargs = p.call_args.kwargs
            assert "X-Provider-Id" in kwargs["headers"]
            assert kwargs["headers"]["X-Provider-Id"] == "bluip"
            assert "Authorization" not in kwargs["headers"]

    def test_envelope_contains_required_fields(self, uploader):
        """POST body must include schema_version, edge_id, service_provider,
        property_id, property_name at top level."""
        with patch("uploader.requests.post", return_value=FakeResponse(200)) as p:
            uploader._send([{"kind": "periodic"}, {"kind": "transition"}])
            body = p.call_args.kwargs["json"]
            assert body["schema_version"] == "1.0"
            assert body["edge_id"] == "test-edge"
            assert body["service_provider"] == "bluip"
            assert body["property_id"] == "123"
            assert body["property_name"] == "sheraton"
            assert body["messages"] == [{"kind": "periodic"}, {"kind": "transition"}]

    def test_correct_endpoint_used(self, uploader):
        with patch("uploader.requests.post", return_value=FakeResponse(200)) as p:
            uploader._send([{"kind": "periodic"}])
            url = p.call_args.kwargs["url"] if "url" in p.call_args.kwargs \
                else p.call_args.args[0] if p.call_args.args \
                else p.call_args.kwargs.get("url", p.call_args[0][0])
            assert "35.95.218.125" in str(p.call_args)

    def test_multiple_device_messages_in_one_post(self, uploader):
        """Cloud receives messages from multiple devices in a single POST."""
        messages = [
            {"kind": "periodic", "device_id": "dev-001"},
            {"kind": "transition", "device_id": "dev-002"},
            {"kind": "edge_health"},
        ]
        with patch("uploader.requests.post", return_value=FakeResponse(200)) as p:
            uploader._send(messages)
            body = p.call_args.kwargs["json"]
            assert len(body["messages"]) == 3
            kinds = [m["kind"] for m in body["messages"]]
            assert "periodic" in kinds
            assert "transition" in kinds
            assert "edge_health" in kinds


class TestRunLoop:
    def test_successful_batch_is_acked(self, uploader, queue):
        with patch("uploader.requests.post", return_value=FakeResponse(200)):
            batch = queue.take_batch(uploader.cfg["upload_batch_size"])
            ids = [rid for rid, _ in batch]
            payloads = [p for _, p in batch]
            assert uploader._send(payloads) is True
            queue.ack(ids)
        assert queue.depth() == 0

    def test_failed_batch_remains_in_queue(self, uploader, queue):
        with patch("uploader.requests.post", return_value=FakeResponse(500)):
            batch = queue.take_batch(uploader.cfg["upload_batch_size"])
            ids = [rid for rid, _ in batch]
            payloads = [p for _, p in batch]
            assert uploader._send(payloads) is False
            queue.mark_failed(ids)
        assert queue.depth() == 3

    def test_network_exception_treated_as_failure(self, uploader):
        with patch("uploader.requests.post", side_effect=ConnectionError("boom")):
            with pytest.raises(ConnectionError):
                uploader._send([{"kind": "periodic"}])


class TestQueuedLogProcess:
    """Tests for the full queued-log-to-cloud send lifecycle."""

    def test_queue_drains_in_batches(self, cfg, tmp_db_path):
        """Queue with many rows drains correctly across multiple batches."""
        q = OutboundQueue(tmp_db_path)
        for i in range(25):
            q.enqueue({"kind": "periodic", "device_id": f"dev-{i:03d}", "seq": i})
        assert q.depth() == 25

        uploader = HttpsUploader(cfg, q)
        with patch("uploader.requests.post", return_value=FakeResponse(200)):
            while q.depth() > 0:
                batch = q.take_batch(cfg["upload_batch_size"])
                ids = [rid for rid, _ in batch]
                payloads = [p for _, p in batch]
                assert uploader._send(payloads) is True
                q.ack(ids)

        assert q.depth() == 0

    def test_failed_send_rows_stay_for_retry(self, cfg, tmp_db_path):
        """On cloud failure, rows stay in queue for retry."""
        q = OutboundQueue(tmp_db_path)
        q.enqueue({"kind": "transition", "device_id": "dev-001"})
        uploader = HttpsUploader(cfg, q)

        with patch("uploader.requests.post", return_value=FakeResponse(503)):
            batch = q.take_batch(10)
            ids = [rid for rid, _ in batch]
            payloads = [p for _, p in batch]
            ok = uploader._send(payloads)
            assert ok is False
            q.mark_failed(ids)

        assert q.depth() == 1
        batch2 = q.take_batch(10)
        assert batch2[0][1]["kind"] == "transition"

    def test_transition_rows_survive_periodic_trim(self, tmp_db_path, monkeypatch):
        """Transition alerts must not be dropped when periodic queue is trimmed."""
        import outbound_queue as oq
        monkeypatch.setattr(oq, "MAX_PERIODIC_ROWS", 2)
        monkeypatch.setattr(oq, "MAX_OTHER_ROWS", 100)
        q = OutboundQueue(tmp_db_path)
        for i in range(10):
            q.enqueue({"kind": "periodic", "seq": i})
        for i in range(3):
            q.enqueue({"kind": "transition", "seq": 100 + i})
        kinds = [p["kind"] for _id, p in q.take_batch(100)]
        assert kinds.count("transition") == 3

    def test_envelope_sent_correctly_for_queued_rows(self, cfg, tmp_db_path):
        """Rows pulled from queue produce correct HTTP envelope to cloud."""
        q = OutboundQueue(tmp_db_path)
        q.enqueue({
            "kind": "periodic",
            "ts": 1700000001.0,
            "device_id": "dev-001",
            "device_name": "switch_floor1",
            "device_class": "switch",
            "vendor": "cisco",
            "site": "hq",
            "health": {"status": "healthy", "score": 90, "reasons": []},
            "metrics": {"event_count": 5, "error_count": 0, "warn_count": 1},
        })
        uploader = HttpsUploader(cfg, q)
        captured = {}

        def capture(url, json=None, headers=None, timeout=None):
            captured["body"] = json
            captured["headers"] = headers
            return FakeResponse(200)

        with patch("uploader.requests.post", side_effect=capture):
            batch = q.take_batch(10)
            ids = [rid for rid, _ in batch]
            payloads = [p for _, p in batch]
            uploader._send(payloads)
            q.ack(ids)

        assert captured["body"]["schema_version"] == "1.0"
        assert captured["body"]["edge_id"] == "test-edge"
        assert captured["body"]["service_provider"] == "bluip"
        assert captured["body"]["property_id"] == "123"
        assert captured["body"]["property_name"] == "sheraton"
        assert captured["headers"]["X-Provider-Id"] == "bluip"
        msg = captured["body"]["messages"][0]
        assert msg["kind"] == "periodic"
        assert msg["device_id"] == "dev-001"
        assert q.depth() == 0
