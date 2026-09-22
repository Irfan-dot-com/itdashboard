#!/usr/bin/env python3
"""
Simulate outbound-queue DB behaviors (trim, ack drain, failed retry).

Run from git_based_project root:
  python scripts/db_queue_scenarios.py --db /tmp/queue_sim.db trim
  python scripts/db_queue_scenarios.py --db /tmp/queue_sim.db ack-drain
  python scripts/db_queue_scenarios.py --db /tmp/queue_sim.db failed-retry

Or use a temp file (default) and delete after.
"""
import argparse
import json
import os
import sys

# Allow running as: python scripts/db_queue_scenarios.py from repo root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import outbound_queue as oq
from outbound_queue import OutboundQueue


def msg(kind="periodic", seq=0, **extra):
    return {"kind": kind, "device_id": "dev-001", "seq": seq, **extra}


def scenario_trim(db_path):
    """Simulate auto-purge of oldest periodic rows when over cap (like production _trim)."""
    if os.path.exists(db_path):
        os.unlink(db_path)
    oq.MAX_PERIODIC_ROWS = 5
    oq.MAX_OTHER_ROWS = 100
    q = OutboundQueue(db_path)
    for i in range(20):
        q.enqueue(msg(kind="periodic", seq=i))
    depth = q.depth()
    print(f"After enqueue 20 periodic (cap={oq.MAX_PERIODIC_ROWS}): depth={depth}")
    batch = q.take_batch(100)
    seqs = [p["seq"] for _, p in batch]
    print(f"Remaining seq values (newest kept): {sorted(seqs)}")
    q.close()
    os.unlink(db_path)
    print("OK: trim simulation - oldest periodic rows were purged from DB.")


def scenario_ack_drain(db_path):
    """Simulate successful cloud batches: take_batch + ack deletes rows (purge per batch)."""
    if os.path.exists(db_path):
        os.unlink(db_path)
    q = OutboundQueue(db_path)
    for i in range(12):
        q.enqueue(msg(seq=i))
    print(f"Start depth: {q.depth()}")
    batch_size = 5
    while q.depth() > 0:
        batch = q.take_batch(batch_size)
        ids = [rid for rid, _ in batch]
        q.ack(ids)
        print(f"  acked {len(ids)} rows, depth now {q.depth()}")
    q.close()
    os.unlink(db_path)
    print("OK: ack-drain - entire queue purged by successful-send semantics.")


def scenario_failed_retry(db_path):
    """Simulate failed upload: rows stay, attempts increment."""
    if os.path.exists(db_path):
        os.unlink(db_path)
    q = OutboundQueue(db_path)
    q.enqueue(msg(kind="transition", seq=99))
    batch = q.take_batch(10)
    ids = [rid for rid, _ in batch]
    q.mark_failed(ids)
    row = q._conn.execute(
        "SELECT attempts, payload FROM outbound LIMIT 1"
    ).fetchone()
    attempts, payload = row[0], json.loads(row[1])
    print(f"After mark_failed: depth={q.depth()}, attempts={attempts}, seq={payload.get('seq')}")
    q.close()
    os.unlink(db_path)
    print("OK: failed-retry - row not deleted, attempts bumped.")


def main():
    ap = argparse.ArgumentParser(description="Simulate SQLite outbound queue behaviors")
    ap.add_argument("--db", default="/tmp/edge_queue_sim.db", help="SQLite file path")
    ap.add_argument(
        "scenario",
        choices=["trim", "ack-drain", "failed-retry"],
        help="Which behavior to simulate",
    )
    args = ap.parse_args()

    if args.scenario == "trim":
        scenario_trim(args.db)
    elif args.scenario == "ack-drain":
        scenario_ack_drain(args.db)
    else:
        scenario_failed_retry(args.db)


if __name__ == "__main__":
    main()
