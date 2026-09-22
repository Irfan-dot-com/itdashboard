import socket
import threading
import signal
import sys

import config
from aggregator import Aggregator
from outbound_queue import OutboundQueue
from uploader import HttpsUploader
from syslog_listener import parse_message

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 5514          # fallback only; override with "listen_port" in config.json


def listener_loop(cfg, aggregator):
    host = cfg.get("listen_host", LISTEN_HOST)
    port = int(cfg.get("listen_port", LISTEN_PORT))
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
    sock.bind((host, port))
    print(f"Listening on {host}:{port}/udp  (edge_id={cfg['edge_id']})")
    while True:
        data, addr = sock.recvfrom(8192)
        try:
            event = parse_message(data.decode("utf-8", errors="replace"), addr[0])
            if event.get("parse_error"):
                continue
            device_meta = config.resolve_device(cfg, addr[0], event["host"])
            if device_meta is None:
                continue
            aggregator.ingest(event, device_meta)
        except Exception as e:
            print(f"Ingest error from {addr}: {e}")


def main():
    cfg = config.load()
    import pathlib
    pathlib.Path(cfg["queue_db_path"]).parent.mkdir(parents=True, exist_ok=True)
    log_path = (
        (cfg.get("cloud_upload_log_path") or "").strip()
        or (cfg.get("cloud_payload_log_path") or "").strip()
    )
    if log_path:
        pathlib.Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        print(f"Cloud HTTP log (text): {log_path}")

    queue = OutboundQueue(cfg["queue_db_path"])
    aggregator = Aggregator(cfg, queue)
    uploader = HttpsUploader(cfg, queue)

    threads = [
        threading.Thread(target=listener_loop, args=(cfg, aggregator), daemon=True),
        threading.Thread(target=aggregator.run_periodic, daemon=True),
        threading.Thread(target=uploader.run, daemon=True),
    ]
    for t in threads:
        t.start()

    def shutdown(*_):
        print("Shutting down...")
        aggregator.stop()
        uploader.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
