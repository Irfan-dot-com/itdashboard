"""Outbound queue tests. SQLite-backed; we verify FIFO, trim, ack/retry, persistence."""
import pytest
from outbound_queue import OutboundQueue


@pytest.fixture
def queue(tmp_db_path):
    return OutboundQueue(tmp_db_path)


def msg(kind="periodic", device_id="dev-001", **extra):
    return {"kind": kind, "device_id": device_id, **extra}


class TestEnqueueAndTake:
    def test_enqueue_then_take_returns_in_order(self, queue):
        for i in range(3):
            queue.enqueue(msg(seq=i))
        batch = queue.take_batch(10)
        assert [p["seq"] for _id, p in batch] == [0, 1, 2]

    def test_take_batch_respects_limit(self, queue):
        for i in range(20):
            queue.enqueue(msg(seq=i))
        batch = queue.take_batch(5)
        assert len(batch) == 5

    def test_take_does_not_remove(self, queue):
        queue.enqueue(msg(seq=1))
        queue.take_batch(10)
        # Still there — only ack() removes
        assert queue.depth() == 1


class TestAckAndRetry:
    def test_ack_removes_messages(self, queue):
        for i in range(3):
            queue.enqueue(msg(seq=i))
        batch = queue.take_batch(10)
        ids = [rid for rid, _ in batch]
        queue.ack(ids[:2])
        assert queue.depth() == 1

    def test_mark_failed_retains_messages(self, queue):
        queue.enqueue(msg(seq=1))
        batch = queue.take_batch(10)
        queue.mark_failed([rid for rid, _ in batch])
        assert queue.depth() == 1
        # Next take returns the same message
        batch2 = queue.take_batch(10)
        assert batch2[0][1]["seq"] == 1

    def test_ack_empty_list_is_safe(self, queue):
        queue.ack([])  # should not raise


class TestTrim:
    def test_periodic_trimmed_to_limit(self, queue, monkeypatch):
        # Lower the limit so the test is fast
        import outbound_queue as oq
        monkeypatch.setattr(oq, "MAX_PERIODIC_ROWS", 5)
        for i in range(20):
            queue.enqueue(msg(kind="periodic", seq=i))
        assert queue.depth() <= 5
        # Oldest dropped, newest kept
        batch = queue.take_batch(100)
        seqs = [p["seq"] for _id, p in batch]
        assert min(seqs) >= 15  # only the last 5 kept

    def test_transitions_kept_longer_than_periodic(self, queue, monkeypatch):
        import outbound_queue as oq
        monkeypatch.setattr(oq, "MAX_PERIODIC_ROWS", 2)
        monkeypatch.setattr(oq, "MAX_OTHER_ROWS", 100)
        # Push many periodic and a few transitions; trim should hit periodics first
        for i in range(10):
            queue.enqueue(msg(kind="periodic", seq=i))
        for i in range(5):
            queue.enqueue(msg(kind="transition", seq=100 + i))
        kinds = [p["kind"] for _id, p in queue.take_batch(100)]
        assert kinds.count("transition") == 5
        assert kinds.count("periodic") <= 2


class TestPersistence:
    def test_queue_survives_reopen(self, tmp_db_path):
        q1 = OutboundQueue(tmp_db_path)
        q1.enqueue(msg(seq=42))
        del q1
        q2 = OutboundQueue(tmp_db_path)
        batch = q2.take_batch(10)
        assert len(batch) == 1
        assert batch[0][1]["seq"] == 42
