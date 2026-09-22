"""Classification rules are pure functions — straightforward unit tests."""
import pytest
from classify import classify, is_noise


class TestClassify:
    @pytest.mark.parametrize("message,expected", [
        ("Interface GigabitEthernet0/1 link state changed to down", "link"),
        ("Interface GigabitEthernet0/1 link state changed to up",   "link"),
        ("Authentication failure for user admin from 10.0.5.1",     "auth"),
        ("User alice logged in from 10.0.5.1",                      "auth"),
        ("Power supply 1 fault detected",                           "hardware"),
        ("CPU utilization at 95%",                                  "performance"),
        ("Memory usage high: 88%",                                  "performance"),
        ("Temperature sensor reading 78C",                          "thermal"),
        ("BGP neighbor 10.0.5.1 state changed to Idle",             "routing"),
        ("Configuration saved by user admin",                       "config"),
    ])
    def test_known_patterns(self, message, expected):
        assert classify(message, "info") == expected

    def test_unknown_message_falls_through(self):
        assert classify("xyzzy frotz nothing matches", "info") == "other"

    def test_classification_is_case_insensitive(self):
        assert classify("INTERFACE GI0/1 LINK STATE CHANGED TO DOWN", "info") == "link"


class TestIsNoise:
    def test_debug_is_always_noise(self):
        assert is_noise("debug", "link") is True
        assert is_noise("debug", "other") is True

    def test_info_with_known_category_is_kept(self):
        assert is_noise("info", "link") is False
        assert is_noise("info", "auth") is False

    def test_info_with_unknown_category_is_dropped(self):
        # This is the "uncategorized chatter" filter
        assert is_noise("info", "other") is True

    def test_warnings_and_errors_always_kept(self):
        for sev in ["warning", "err", "error", "crit", "alert", "emerg"]:
            assert is_noise(sev, "other") is False
            assert is_noise(sev, "link") is False
