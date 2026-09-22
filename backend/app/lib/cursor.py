"""Opaque cursor encoding for keyset pagination on the alerts list.

Cursor encodes (sev_rank, opened_at, alert_id) — the three columns used in
the ORDER BY clause of GET /v1/alerts.

Sort order: sev_rank ASC, opened_at DESC, alert_id DESC
"""
import base64
import json


def encode_cursor(sev_rank: int, opened_at: str, alert_id: str) -> str:
    """Encode three sort-key values into a URL-safe base64 cursor string."""
    raw = json.dumps({"r": sev_rank, "o": opened_at, "id": alert_id}).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[int, str, str]:
    """Decode a cursor string back to (sev_rank, opened_at, alert_id)."""
    pad = "=" * (-len(cursor) % 4)
    obj = json.loads(base64.urlsafe_b64decode(cursor + pad))
    return int(obj["r"]), str(obj["o"]), str(obj["id"])
