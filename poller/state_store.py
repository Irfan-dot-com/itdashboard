"""
Remembers each device's last known health status across restarts.

The syslog agent keeps last_status in memory, so a restart makes it forget
every device's state and it cannot tell a transition from a first sighting.
Here it is on disk: restart the poller and it still knows that switch-3 was
already unhealthy, so it does not re-open an alert that is already open.
"""
import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS device_state (
    device_id   TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    score       INTEGER NOT NULL DEFAULT 0,
    first_seen  REAL NOT NULL,
    last_seen   REAL NOT NULL,
    last_change REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS poll_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


class StateStore:
    def __init__(self, db_path, clock=time.time):
        self.clock = clock
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False,
                                     isolation_level=None)
        self._conn.executescript(SCHEMA)
        self._lock = threading.Lock()

    def previous_status(self, device_id):
        """Last recorded status, or None if this device has never been seen."""
        with self._lock:
            row = self._conn.execute(
                "SELECT status FROM device_state WHERE device_id = ?",
                (device_id,)).fetchone()
        return row[0] if row else None

    def record(self, device_id, status, score):
        """
        Store the current status.

        Returns the previous status, or None for a device seen for the first
        time - which is what the caller uses to decide whether a transition
        message is warranted.
        """
        now = self.clock()
        with self._lock:
            row = self._conn.execute(
                "SELECT status, first_seen FROM device_state WHERE device_id = ?",
                (device_id,)).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO device_state "
                    "(device_id, status, score, first_seen, last_seen, last_change) "
                    "VALUES (?,?,?,?,?,?)",
                    (device_id, status, int(score), now, now, now))
                return None
            prev, first_seen = row
            changed = (prev != status)
            self._conn.execute(
                "UPDATE device_state SET status=?, score=?, last_seen=?, "
                "last_change=CASE WHEN ? THEN ? ELSE last_change END "
                "WHERE device_id=?",
                (status, int(score), now, 1 if changed else 0, now, device_id))
            return prev

    def all_states(self):
        with self._lock:
            rows = self._conn.execute(
                "SELECT device_id, status, score, last_seen FROM device_state"
            ).fetchall()
        return [{"device_id": r[0], "status": r[1], "score": r[2], "last_seen": r[3]}
                for r in rows]

    def counts(self):
        """(tracked, unhealthy) for the edge_health heartbeat."""
        with self._lock:
            total = self._conn.execute(
                "SELECT COUNT(*) FROM device_state").fetchone()[0]
            bad = self._conn.execute(
                "SELECT COUNT(*) FROM device_state WHERE status = 'unhealthy'"
            ).fetchone()[0]
        return total, bad

    def devices_not_seen_since(self, cutoff):
        """
        Devices absent from recent polls.

        A device that disappears from the networks report entirely - removed
        from the platform, or the platform stopped reporting it - would
        otherwise just go quiet and never be flagged.
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT device_id, status, last_seen FROM device_state "
                "WHERE last_seen < ?", (cutoff,)).fetchall()
        return [{"device_id": r[0], "status": r[1], "last_seen": r[2]} for r in rows]

    def forget(self, device_id):
        with self._lock:
            self._conn.execute("DELETE FROM device_state WHERE device_id = ?",
                               (device_id,))

    def set_meta(self, key, value):
        with self._lock:
            self._conn.execute(
                "INSERT INTO poll_meta (key, value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)))

    def get_meta(self, key, default=None):
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM poll_meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass
