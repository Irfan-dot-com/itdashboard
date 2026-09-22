import sqlite3
import json
import time
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS outbound (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enqueued_at REAL NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_outbound_kind ON outbound(kind);
"""

MAX_PERIODIC_ROWS = 5000
MAX_OTHER_ROWS    = 20000


class OutboundQueue:
    def __init__(self, db_path, clock=time.time):
        self.db_path = db_path
        self.clock = clock
        self.lock = threading.Lock()
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        self._conn.executescript(SCHEMA)

    def enqueue(self, payload):
        with self.lock:
            self._conn.execute(
                "INSERT INTO outbound (enqueued_at, kind, payload) VALUES (?, ?, ?)",
                (self.clock(), payload.get("kind", "unknown"), json.dumps(payload)),
            )
            self._trim()

    def _trim(self):
        self._conn.execute("""
            DELETE FROM outbound WHERE id IN (
                SELECT id FROM outbound WHERE kind='periodic'
                ORDER BY enqueued_at ASC
                LIMIT MAX(0, (SELECT COUNT(*) FROM outbound WHERE kind='periodic') - ?)
            )
        """, (MAX_PERIODIC_ROWS,))
        self._conn.execute("""
            DELETE FROM outbound WHERE id IN (
                SELECT id FROM outbound WHERE kind!='periodic'
                ORDER BY enqueued_at ASC
                LIMIT MAX(0, (SELECT COUNT(*) FROM outbound WHERE kind!='periodic') - ?)
            )
        """, (MAX_OTHER_ROWS,))

    def take_batch(self, n):
        with self.lock:
            cur = self._conn.execute(
                "SELECT id, payload FROM outbound ORDER BY enqueued_at ASC LIMIT ?", (n,)
            )
            rows = cur.fetchall()
        return [(rid, json.loads(p)) for rid, p in rows]

    def ack(self, ids):
        if not ids:
            return
        with self.lock:
            qmarks = ",".join("?" * len(ids))
            self._conn.execute(f"DELETE FROM outbound WHERE id IN ({qmarks})", ids)

    def mark_failed(self, ids):
        if not ids:
            return
        with self.lock:
            qmarks = ",".join("?" * len(ids))
            self._conn.execute(
                f"UPDATE outbound SET attempts = attempts + 1 WHERE id IN ({qmarks})", ids
            )

    def depth(self):
        with self.lock:
            return self._conn.execute("SELECT COUNT(*) FROM outbound").fetchone()[0]

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    def __del__(self):
        self.close()
