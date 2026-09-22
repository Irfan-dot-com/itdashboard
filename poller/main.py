#!/usr/bin/env python3
"""
SD-LAN poller - main service.

Every poll_interval_seconds:
  1. GET/POST query=networks       -> every switching device and its state
  2. GET/POST query=status         -> platform summary + active problems list
  3. assess each device's health from the API's own fields
  4. enqueue a periodic message per device, plus a transition for any device
     whose status changed since the last poll (remembered on disk)
  5. enqueue one edge_health heartbeat for this poller

A separate thread drains the queue to the cloud dashboard.

Run:  python3 main.py [--config /etc/sdlan-poller/config.json] [--once]
"""
import argparse
import signal
import sys
import threading
import time

import config as poller_config
import mapper
from outbound_queue import OutboundQueue
from sdlan_client import SdLanClient, SdLanError, iter_devices, iter_problems
from state_store import StateStore
from uploader import CloudUploader


def log(msg):
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}", flush=True)


class Poller:
    def __init__(self, cfg, client, queue, state, clock=time.time):
        self.cfg = cfg
        self.client = client
        self.queue = queue
        self.state = state
        self.clock = clock
        self._stop = threading.Event()
        self.last_error = None

    def poll_once(self):
        """One full poll cycle. Returns a summary dict for logging/tests."""
        now = self.clock()
        messages = []
        seen_ids = set()
        transitions = 0
        unhealthy_now = 0

        # --- devices ------------------------------------------------------
        networks = self.client.networks()
        device_count = 0
        for domain, site, device in iter_devices(networks):
            msg = mapper.device_message(self.cfg, device, domain, site,
                                        kind="periodic", now=now)
            if msg is None:
                continue
            device_count += 1
            dev_id = msg["device_id"]
            seen_ids.add(dev_id)
            status = msg["health"]["status"]
            if status == "unhealthy":
                unhealthy_now += 1

            prev = self.state.record(dev_id, status, msg["health"]["score"])
            messages.append(msg)
            if prev is not None and prev != status:
                transitions += 1
                messages.append(mapper.device_message(
                    self.cfg, device, domain, site, kind="transition", now=now))
                log(f"  transition {dev_id}: {prev} -> {status} "
                    f"{msg['health']['reasons']}")

        # --- the platform itself -----------------------------------------
        status_resp = {}
        problems = []
        try:
            status_resp = self.client.status() or {}
            problems = list(iter_problems(status_resp))
        except SdLanError as e:
            log(f"  status query failed (devices still polled): {e}")

        if self.cfg.get("report_platform_as_device", True) and status_resp:
            pmsg = mapper.platform_message(self.cfg, status_resp, problems,
                                           kind="periodic", now=now)
            pid = pmsg["device_id"]
            seen_ids.add(pid)
            pstatus = pmsg["health"]["status"]
            if pstatus == "unhealthy":
                unhealthy_now += 1
            prev = self.state.record(pid, pstatus, pmsg["health"]["score"])
            messages.append(pmsg)
            if prev is not None and prev != pstatus:
                transitions += 1
                messages.append(mapper.platform_message(
                    self.cfg, status_resp, problems, kind="transition", now=now))
                log(f"  transition {pid}: {prev} -> {pstatus} "
                    f"{pmsg['health']['reasons']}")

        # --- devices that vanished from the report ------------------------
        # Two missed polls, so one flaky response does not raise false alarms.
        cutoff = now - (self.cfg.get("poll_interval_seconds", 300) * 2.5)
        for gone in self.state.devices_not_seen_since(cutoff):
            if gone["device_id"] in seen_ids or gone["status"] == "unhealthy":
                continue
            prev = self.state.record(gone["device_id"], "unhealthy", 0)
            stale = int(now - gone["last_seen"])
            vanished = {
                "kind": "transition", "ts": now,
                "device_id": gone["device_id"],
                "health": {"status": "unhealthy", "score": 0,
                           "reasons": [f"absent_from_platform_report_{stale}s"]},
                "metrics": {"event_count": 1, "error_count": 1, "warn_count": 0},
                "top_events": [{
                    "ts": now, "severity": "crit", "category": "availability",
                    "message": f"device no longer present in the SD-LAN "
                               f"networks report ({stale}s)"}],
            }
            messages.append(vanished)
            transitions += 1
            unhealthy_now += 1
            log(f"  transition {gone['device_id']}: {gone['status']} -> unhealthy "
                f"(absent from report)")

        # --- heartbeat ----------------------------------------------------
        tracked, _ = self.state.counts()
        messages.append(mapper.edge_health_message(
            self.cfg, tracked, unhealthy_now, self.queue.depth(), now=now))

        self.queue.enqueue_many(messages)
        self.state.set_meta("last_poll_ok", now)
        self.last_error = None

        return {"devices": device_count, "messages": len(messages),
                "transitions": transitions, "unhealthy": unhealthy_now,
                "problems": len(problems), "queue_depth": self.queue.depth()}

    def run(self):
        interval = self.cfg.get("poll_interval_seconds", 300)
        while not self._stop.is_set():
            started = time.time()
            try:
                summary = self.poll_once()
                log(f"poll ok: {summary['devices']} devices, "
                    f"{summary['transitions']} transitions, "
                    f"{summary['unhealthy']} unhealthy, "
                    f"{summary['problems']} platform problems, "
                    f"queue={summary['queue_depth']} "
                    f"({time.time() - started:.1f}s)")
            except SdLanError as e:
                self.last_error = str(e)
                log(f"poll FAILED: {e}")
                self.state.set_meta("last_poll_error", str(e)[:300])
            except Exception as e:
                self.last_error = f"{type(e).__name__}: {e}"
                log(f"poll FAILED (unexpected): {type(e).__name__}: {e}")
                self.state.set_meta("last_poll_error", self.last_error[:300])

            if self._stop.wait(max(5, interval - (time.time() - started))):
                break

    def stop(self):
        self._stop.set()


def main():
    ap = argparse.ArgumentParser(description="Corning SD-LAN poller")
    ap.add_argument("--config", default="/etc/sdlan-poller/config.json")
    ap.add_argument("--once", action="store_true",
                    help="run a single poll, upload it, then exit (for testing)")
    args = ap.parse_args()

    cfg = poller_config.load(args.config)
    missing = poller_config.missing_keys(cfg)
    if missing:
        sys.exit(f"config {args.config} is incomplete - set: {', '.join(missing)}\n"
                 f"Run preflight.py for a full check.")

    log(f"SD-LAN poller starting (edge_id={cfg['edge_id']}, "
        f"property_id={cfg['property_id']})")
    log(f"  platform : {poller_config.safe_url(cfg)}")
    log(f"  cloud    : {cfg['cloud_endpoint']}")
    log(f"  interval : {cfg['poll_interval_seconds']}s")
    if cfg.get("cloud_upload_log_path"):
        log(f"  http log : {cfg['cloud_upload_log_path']}")

    queue = OutboundQueue(cfg["queue_db_path"])
    state = StateStore(cfg["state_db_path"])
    client = SdLanClient(cfg)
    poller = Poller(cfg, client, queue, state)
    uploader = CloudUploader(cfg, queue)

    if args.once:
        summary = poller.poll_once()
        log(f"single poll: {summary}")
        batch = queue.take_batch(cfg.get("upload_batch_size", 50))
        if batch:
            ok, permanent, detail = uploader.send([p for _i, p in batch])
            log(f"upload: ok={ok} permanent={permanent} {detail}")
            if ok:
                queue.ack([i for i, _p in batch])
        log(f"queue now: {queue.stats()}")
        return

    threads = [
        threading.Thread(target=poller.run, daemon=True, name="poller"),
        threading.Thread(target=uploader.run, daemon=True, name="uploader"),
    ]
    for t in threads:
        t.start()

    def shutdown(*_):
        log("shutting down...")
        poller.stop()
        uploader.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
