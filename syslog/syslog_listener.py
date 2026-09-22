import socket
import re
from datetime import datetime, timezone

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 5514

RFC3164_RE = re.compile(
    r"^<(?P<pri>\d+)>"
    r"(?P<ts>\w{3}\s+\d+\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<host>\S+)\s+"
    r"(?P<tag>[^:\[\s]+(?:\[\d+\])?):?\s*"
    r"(?P<msg>.*)$"
)

RFC5424_RE = re.compile(
    r"^<(?P<pri>\d+)>(?P<ver>\d+)\s+"
    r"(?P<ts>\S+)\s+(?P<host>\S+)\s+"
    r"(?P<app>\S+)\s+(?P<procid>\S+)\s+(?P<msgid>\S+)\s+"
    r"(?P<sd>-|\[.*?\])\s*(?P<msg>.*)$"
)

# A relay (rsyslog's omfwd with the RSYSLOG_ForwardFormat template, which is
# its modern default) rewrites the header to an RFC 3339 timestamp but does
# NOT add the RFC 5424 version digit:
#   <131>2026-09-21T19:00:00+00:00 HTL-SW-CORE-01 %SYS-3-POWER: Power supply 1 failed
# That form matches neither regex above, so without this pattern every relayed
# message is a parse_error and main.py discards it silently. Some devices emit
# this shape natively too.
RFC3164_RFC3339_RE = re.compile(
    r"^<(?P<pri>\d+)>"
    r"(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2}))\s+"
    r"(?P<host>\S+)\s+"
    r"(?P<tag>[^:\[\s]+(?:\[\d+\])?):?\s*"
    r"(?P<msg>.*)$"
)

SEVERITIES = ["emerg", "alert", "crit", "err", "warning", "notice", "info", "debug"]
FACILITIES = [
    "kern", "user", "mail", "daemon", "auth", "syslog", "lpr", "news",
    "uucp", "cron", "authpriv", "ftp", "ntp", "audit", "alert", "clock",
    "local0", "local1", "local2", "local3", "local4", "local5", "local6", "local7",
]


def parse_pri(pri):
    pri = int(pri)
    facility = FACILITIES[pri >> 3] if (pri >> 3) < len(FACILITIES) else "unknown"
    severity = SEVERITIES[pri & 0x07]
    return facility, severity


def parse_message(raw, src_ip):
    m = RFC5424_RE.match(raw)
    rfc = "5424"
    if not m:
        m = RFC3164_RE.match(raw)
        rfc = "3164"
    if not m:
        # relayed/RFC3339 header - no version digit (see the regex comment)
        m = RFC3164_RFC3339_RE.match(raw)
        rfc = "3164-rfc3339"
    if not m:
        return {
            "raw": raw,
            "src_ip": src_ip,
            "parse_error": True,
            "received_at": datetime.now(timezone.utc).isoformat(),
        }

    facility, severity = parse_pri(m.group("pri"))
    return {
        "rfc": rfc,
        "src_ip": src_ip,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "timestamp": m.group("ts"),
        "host": m.group("host"),
        "facility": facility,
        "severity": severity,
        "tag": m.group("tag") if rfc.startswith("3164") else m.group("app"),
        "message": m.group("msg"),
    }


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((LISTEN_HOST, LISTEN_PORT))
    print(f"Listening for syslog on {LISTEN_HOST}:{LISTEN_PORT}/udp")
    while True:
        data, addr = sock.recvfrom(8192)
        try:
            event = parse_message(data.decode("utf-8", errors="replace"), addr[0])
            print(event)
        except Exception as e:
            print(f"Error parsing from {addr}: {e}")


if __name__ == "__main__":
    main()
