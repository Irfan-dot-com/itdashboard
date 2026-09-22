"""Parser tests. The parser is pure — give it a string, get a dict back."""
import pytest
from syslog_listener import parse_message, parse_pri


class TestParsePri:
    def test_local0_info(self):
        # local0=16, info=6 => 16*8+6 = 134
        facility, severity = parse_pri(134)
        assert facility == "local0"
        assert severity == "info"

    def test_kern_emerg(self):
        # kern=0, emerg=0 => 0
        facility, severity = parse_pri(0)
        assert facility == "kern"
        assert severity == "emerg"

    def test_local7_debug(self):
        # local7=23, debug=7 => 23*8+7 = 191
        facility, severity = parse_pri(191)
        assert facility == "local7"
        assert severity == "debug"


class TestRFC3164:
    def test_basic_message(self):
        raw = "<134>May  3 12:00:00 sw1 ciscoios: Interface Gi0/1 changed to up"
        result = parse_message(raw, "10.0.0.1")
        assert result["rfc"] == "3164"
        assert result["host"] == "sw1"
        assert result["facility"] == "local0"
        assert result["severity"] == "info"
        assert result["tag"] == "ciscoios"
        assert "Interface Gi0/1" in result["message"]
        assert result["src_ip"] == "10.0.0.1"

    def test_tag_with_pid(self):
        raw = "<134>May  3 12:00:00 sw1 sshd[1234]: Accepted password for admin"
        result = parse_message(raw, "10.0.0.1")
        assert result["tag"] == "sshd[1234]"

    def test_error_severity(self):
        raw = "<131>May  3 12:00:00 sw1 pf: Power supply 1 fault"
        result = parse_message(raw, "10.0.0.2")
        # 131 = local0(16)*8 + err(3)
        assert result["severity"] == "err"


class TestRFC5424:
    def test_basic_message(self):
        raw = ("<134>1 2026-05-03T12:00:00.000Z router-edge "
               "junos 1234 ID47 - BGP neighbor up")
        result = parse_message(raw, "10.0.0.3")
        assert result["rfc"] == "5424"
        assert result["host"] == "router-edge"
        assert result["tag"] == "junos"
        assert "BGP neighbor up" in result["message"]


class TestMalformed:
    def test_garbage_returns_parse_error(self):
        result = parse_message("not a syslog message at all", "10.0.0.99")
        assert result.get("parse_error") is True
        assert result["src_ip"] == "10.0.0.99"

    def test_empty_string(self):
        result = parse_message("", "10.0.0.99")
        assert result.get("parse_error") is True


class TestRelayedRFC3339:
    """
    A relay rewrites the header to an RFC 3339 timestamp with NO RFC 5424
    version digit. rsyslog's DEFAULT omfwd template (RSYSLOG_ForwardFormat)
    does exactly this. Before RFC3164_RFC3339_RE existed, every one of these
    was a parse_error and main.py discarded it silently - a relay deployment
    that looked healthy and collected nothing.
    """

    def test_relayed_offset_timestamp(self):
        raw = ("<131>2026-09-21T19:00:00+00:00 HTL-SW-CORE-01 "
               "%SYS-3-POWER: Power supply 1 failed")
        result = parse_message(raw, "10.20.30.50")
        assert result.get("parse_error") is not True
        assert result["host"] == "HTL-SW-CORE-01"
        assert result["severity"] == "err"
        assert result["tag"] == "%SYS-3-POWER"
        assert result["message"] == "Power supply 1 failed"

    def test_relayed_subsecond_zulu(self):
        raw = ("<134>2026-09-21T19:00:04.123Z ARISTA-SW-01 Syslog[1234] "
               "BGP session established")
        result = parse_message(raw, "10.20.30.50")
        assert result.get("parse_error") is not True
        assert result["host"] == "ARISTA-SW-01"
        assert result["tag"] == "Syslog[1234]"
        assert result["severity"] == "info"

    def test_relayed_tag_with_pid(self):
        raw = ("<130>2026-09-21T19:00:03+00:00 PBX-ASTERISK-01 "
               "asterisk[912]: SIP registration failed for 1001")
        result = parse_message(raw, "10.20.30.50")
        assert result["host"] == "PBX-ASTERISK-01"
        assert result["tag"] == "asterisk[912]"
        assert result["severity"] == "crit"

    def test_relayed_offset_without_colon(self):
        raw = "<134>2026-09-21T19:00:05-0400 APC-UPS-LOBBY apcupsd: UPS on battery"
        result = parse_message(raw, "10.20.30.50")
        assert result.get("parse_error") is not True
        assert result["host"] == "APC-UPS-LOBBY"

    def test_relayed_form_is_labelled_distinctly(self):
        """So operators can tell relayed traffic apart in the parsed output."""
        raw = "<131>2026-09-21T19:00:00+00:00 sw1 tag: body"
        assert parse_message(raw, "10.0.0.1")["rfc"] == "3164-rfc3339"

    def test_classic_formats_still_win_over_the_new_pattern(self):
        """No regression: the original two regexes must still match first."""
        classic = parse_message(
            "<134>May  3 12:00:00 sw1 ciscoios: Interface Gi0/1 up", "10.0.0.1")
        assert classic["rfc"] == "3164"
        rfc5424 = parse_message(
            "<134>1 2026-05-03T12:00:00.000Z router-edge junos 1234 ID47 - up",
            "10.0.0.1")
        assert rfc5424["rfc"] == "5424"

    def test_garbage_with_a_date_in_it_still_fails(self):
        """The new pattern must not turn arbitrary text into a valid event."""
        assert parse_message("2026-09-21 something happened",
                             "10.0.0.1").get("parse_error") is True
        assert parse_message("<131>2026-09-21 no-T-separator host tag: x",
                             "10.0.0.1").get("parse_error") is True
