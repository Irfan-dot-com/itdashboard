"""Device resolution: exact match wins, wildcard is fallback, unknowns return None."""
import socket
import config


def test_exact_ip_hostname_match(cfg):
    result = config.resolve_device(cfg, "10.0.0.1", "sw1")
    assert result["device_id"] == "dev-001"
    assert result["site"] == "hq"
    assert result["device_class"] == "switch"
    assert result["vendor"] == "cisco"
    assert result["device_name"] == "switch_floor1"


def test_wildcard_match_when_exact_missing(cfg):
    result = config.resolve_device(cfg, "192.168.99.99", "wildcard-host")
    assert result["device_id"] == "dev-wild"
    assert result["device_class"] == "router"


def test_exact_match_preferred_over_wildcard(cfg):
    cfg["device_map"]["10.0.0.5|wildcard-host"] = {
        "device_id": "dev-specific",
        "device_name": "specific_router",
        "device_class": "router",
        "vendor": "cisco",
        "site": "hq",
    }
    result = config.resolve_device(cfg, "10.0.0.5", "wildcard-host")
    assert result["device_id"] == "dev-specific"


def test_unknown_device_returns_none(cfg):
    assert config.resolve_device(cfg, "10.99.99.99", "rogue-device") is None


def test_load_returns_defaults_when_no_file(tmp_path):
    nonexistent = tmp_path / "does-not-exist.json"
    loaded = config.load(str(nonexistent))
    assert loaded["edge_id"] == socket.gethostname()
    assert loaded["service_provider"] == "bluip"
    assert loaded["property_id"] == "123"
    assert loaded["property_name"] == "sheraton"
    assert "device_map" in loaded


def test_default_endpoint_is_new_cloud_api(tmp_path):
    nonexistent = tmp_path / "does-not-exist.json"
    loaded = config.load(str(nonexistent))
    assert "35.95.218.125" in loaded["cloud_endpoint"]
