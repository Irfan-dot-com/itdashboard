import pytest
from app.lib.cursor import encode_cursor, decode_cursor


def test_round_trip():
    cursor = encode_cursor(1, "2026-05-08T10:00:00Z", "alr_abc123")
    sev_rank, opened_at, alert_id = decode_cursor(cursor)
    assert sev_rank == 1
    assert opened_at == "2026-05-08T10:00:00Z"
    assert alert_id == "alr_abc123"


def test_url_safe_no_padding():
    cursor = encode_cursor(2, "2026-05-08T10:00:00Z", "alr_xyz")
    assert "+" not in cursor
    assert "/" not in cursor
    assert "=" not in cursor


def test_different_sev_ranks_produce_different_cursors():
    c1 = encode_cursor(1, "2026-05-08T10:00:00Z", "alr_001")
    c2 = encode_cursor(2, "2026-05-08T10:00:00Z", "alr_001")
    assert c1 != c2


def test_different_alert_ids_produce_different_cursors():
    c1 = encode_cursor(1, "2026-05-08T10:00:00Z", "alr_001")
    c2 = encode_cursor(1, "2026-05-08T10:00:00Z", "alr_002")
    assert c1 != c2


def test_sev_rank_returned_as_int():
    cursor = encode_cursor(3, "2026-05-08T10:00:00Z", "alr_001")
    sev_rank, _, _ = decode_cursor(cursor)
    assert isinstance(sev_rank, int)


def test_invalid_cursor_raises():
    with pytest.raises(Exception):
        decode_cursor("notavalidcursor!!")
