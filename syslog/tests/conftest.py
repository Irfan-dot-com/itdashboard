"""Shared fixtures for the edge-agent test suite."""
import pytest
import tempfile
import os


class FakeClock:
    """Deterministic clock for tests. Call advance() to move time forward."""
    def __init__(self, start=1_700_000_000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds
        return self.now


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def cfg():
    """Minimal config suitable for tests."""
    return {
        "edge_id": "test-edge",
        "service_provider": "bluip",
        "property_id": "123",
        "property_name": "sheraton",
        "cloud_endpoint": "http://35.95.218.125:4000/v1/edge/ingest",
        "summary_interval_seconds": 60,
        "window_seconds": 300,
        "stale_threshold_seconds": 180,
        "upload_batch_size": 10,
        "upload_retry_seconds": 1,
        "queue_db_path": ":memory:",
        "cloud_upload_log_path": "",
        "device_map": {
            "10.0.0.1|sw1": {
                "device_id": "dev-001",
                "device_name": "switch_floor1",
                "device_class": "switch",
                "vendor": "cisco",
                "site": "hq",
            },
            "10.0.0.2|sw2": {
                "device_id": "dev-002",
                "device_name": "switch_floor2",
                "device_class": "switch",
                "vendor": "cisco",
                "site": "hq",
            },
            "*|wildcard-host": {
                "device_id": "dev-wild",
                "device_name": "wildcard_router",
                "device_class": "router",
                "vendor": "mikrotik",
                "site": "hq",
            },
        },
    }


@pytest.fixture
def tmp_db_path():
    """A temporary SQLite path that is cleaned up after the test."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except (FileNotFoundError, PermissionError):
        pass


def make_event(message, severity="info", host="sw1", src_ip="10.0.0.1"):
    """Build a parsed syslog event dict matching the listener's output shape."""
    return {
        "rfc": "3164",
        "src_ip": src_ip,
        "received_at": "2026-05-03T12:00:00Z",
        "timestamp": "May  3 12:00:00",
        "host": host,
        "facility": "local0",
        "severity": severity,
        "tag": "test",
        "message": message,
    }
