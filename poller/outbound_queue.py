"""
Durable outbound queue - messages survive restarts and cloud outages.

Same design as the syslog agent's queue, with one addition: a `state` column,
so a batch the cloud permanently rejects can be parked instead of sitting at
the head of the queue being retried forever and blocking everything behind it.
"""
import json
import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS outbound (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    enqueued_at REAL NOT NULL,
    kind        TEXT NOT NULL,
    payload     TEXT NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    state       TEXT NOT NULL DEFAULT 'pending',
    last_error  TEXT
);
CREATE INDEX IF NOT EXISTS idx_outbound_state ON outbound(state, enqueued_at);
CREATE INDEX IF NOT EXISTS idx_outbound_kind  ON outbound(kind);
"""

MAX_PERIODIC_ROWS = 5000
MAX_OTHER_ROWS = 20000
MAX_QUARANTINE_ROWS = 500


class OutboundQueue:
    def __init__(self, db_path, clock=time.time):
        self.db_path = db_path
        self.clock = clock
        self.lock = threading.Lock()
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False,
                                     isolation_level=None)
        self._conn.executescript(SCHEMA)

    def enqueue(self, payload):
        with self.lock:
            self._conn.execute(
                "INSERT INTO outbound (enqueued_at, kind, payload) VALUES (?,?,?)",
                (self.clock(), payload.get("kind", "unknown"), json.dumps(payload)))
            self._trim()

    def enqueue_many(self, payloads):
        if not payloads:
            return
        now = self.clock()
        rows = [(now, p.get("kind", "unknown"), json.dumps(p)) for p in payloads]
        with self.lock:
            self._conn.executemany(
                "INSERT INTO outbound (enqueued_at, kind, payload) VALUES (?,?,?)",
                rows)
            self._trim()

    def _trim(self):
        for kind_clause, cap in (("kind='periodic'", MAX_PERIODIC_ROWS),
                                 ("kind!='periodic'", MAX_OTHER_ROWS)):
            self._conn.execute(f"""
                DELETE FROM outbound WHERE id IN (
                    SELECT id FROM outbound
                    WHERE {kind_clause} AND state='pending'
                    ORDER BY enqueued_at ASC
                    LIMIT MAX(0, (SELECT COUNT(*) FROM outbound
                                  WHERE {kind_clause} AND state='pending') - ?)
                )""", (cap,))
        self._conn.execute("""
            DELETE FROM outbound WHERE id IN (
                SELECT id FROM outbound WHERE state='quarantined'
                ORDER BY enqueued_at ASC
                LIMIT MAX(0, (SELECT COUNT(*) FROM outbound
                              WHERE state='quarantined') - ?)
            )""", (MAX_QUARANTINE_ROWS,))

    def take_batch(self, n):
        with self.lock:
            rows = self._conn.execute(
                "SELECT id, payload FROM outbound WHERE state='pending' "
                "ORDER BY enqueued_at ASC LIMIT ?", (n,)).fetchall()
        return [(rid, json.loads(p)) for rid, p in rows]

    def ack(self, ids):
        if not ids:
            return
        with self.lock:
            q = ",".join("?" * len(ids))
            self._conn.execute(f"DELETE FROM outbound WHERE id IN ({q})", list(ids))

    def mark_failed(self, ids, error=None):
        if not ids:
            return
        with self.lock:
            q = ",".join("?" * len(ids))
            self._conn.execute(
                f"UPDATE outbound SET attempts = attempts + 1, last_error = ? "
                f"WHERE id IN ({q})", [str(error)[:300] if error else None, *ids])

    def quarantine(self, ids, error=None):
        """
        Park messages the cloud will never accept (a 4xx), so the queue can
        keep draining. They stay on disk for inspection rather than vanishing.
        """
        if not ids:
            return
        with self.lock:
            q = ",".join("?" * len(ids))
            self._conn.execute(
                f"UPDATE outbound SET state='quarantined', last_error=? "
                f"WHERE id IN ({q})", [str(error)[:300] if error else None, *ids])
            self._trim()

    def depth(self):
        with self.lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM outbound WHERE state='pending'").fetchone()[0]

    def stats(self):
        with self.lock:
            rows = self._conn.execute(
                "SELECT state, kind, COUNT(*), MAX(attempts) FROM outbound "
                "GROUP BY state, kind").fetchall()
        return [{"state": r[0], "kind": r[1], "count": r[2], "max_attempts": r[3]}
                for r in rows]

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass
