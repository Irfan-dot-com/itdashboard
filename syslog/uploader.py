import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import requests


def _resolve_upload_log_path(cfg):
    """Prefer cloud_upload_log_path; fall back to legacy cloud_payload_log_path."""
    for key in ("cloud_upload_log_path", "cloud_payload_log_path"):
        p = (cfg.get(key) or "").strip()
        if p:
            return p
    return ""


class HttpsUploader:
    def __init__(self, cfg, queue):
        self.cfg = cfg
        self.queue = queue
        self._stop = threading.Event()
        self._log_path = _resolve_upload_log_path(cfg)
        self._log_lock = threading.Lock()

    def _write_http_log(self, body, response=None, exception=None):
        """Append a human-readable text block: request, payload, result (HTTP or error)."""
        if not self._log_path:
            return
        utc_now = datetime.now(timezone.utc)
        local_now = utc_now.astimezone()
        tz_name = local_now.tzname() or "local"
        raw_off = local_now.strftime("%z")
        if raw_off and len(raw_off) >= 5:
            off_display = f", UTC offset {raw_off[:3]}:{raw_off[3:]}"
        else:
            off_display = ""
        local_readable = local_now.strftime("%A, %d %B %Y at %I:%M:%S %p")
        utc_readable = utc_now.strftime("%A, %d %B %Y at %I:%M:%S %p UTC")
        lines = [
            "=" * 80,
            f"timestamp (local): {local_readable} ({tz_name}{off_display})",
            f"timestamp (UTC):    {utc_readable}",
            "",
            "REQUEST",
            "  method: POST",
            f"  url: {self.cfg['cloud_endpoint']}",
            "  headers:",
            "    Content-Type: application/json",
            f"    X-Provider-Id: {self.cfg['service_provider']}",
            "",
            "  body (JSON):",
        ]
        pretty = json.dumps(body, indent=2, ensure_ascii=False)
        for pl in pretty.splitlines():
            lines.append(f"    {pl}")

        lines.extend(["", "RESULT"])
        if exception is not None:
            lines.append("  outcome: REQUEST_FAILED")
            lines.append(f"  exception: {type(exception).__name__}: {exception}")
        elif response is not None:
            ok = 200 <= response.status_code < 300
            lines.append(f"  outcome: {'HTTP_SUCCESS' if ok else 'HTTP_NON_SUCCESS'}")
            lines.append(f"  status_code: {response.status_code}")
            reason = getattr(response, "reason", None) or ""
            lines.append(f"  reason: {reason}")
            try:
                rb = response.text or ""
                max_len = 8000
                if len(rb) > max_len:
                    rb = rb[:max_len] + f"\n    ... (truncated, total {len(response.text)} chars)"
                if rb.strip():
                    lines.append("  response_body:")
                    for rl in rb.splitlines():
                        lines.append(f"    {rl}")
                else:
                    lines.append("  response_body: <empty>")
            except Exception as ex:
                lines.append(f"  response_body: <could not read: {ex}>")
        else:
            lines.append("  outcome: UNKNOWN (no response, no exception)")

        lines.append("")
        block = "\n".join(lines) + "\n"

        try:
            with self._log_lock:
                Path(self._log_path).parent.mkdir(parents=True, exist_ok=True)
                with open(self._log_path, "a", encoding="utf-8") as f:
                    f.write(block)
                    f.flush()
        except OSError as e:
            print(f"cloud upload log write error ({self._log_path}): {e}")

    def run(self):
        backoff = self.cfg["upload_retry_seconds"]
        while not self._stop.is_set():
            batch = self.queue.take_batch(self.cfg["upload_batch_size"])
            if not batch:
                self._stop.wait(2)
                continue

            ids = [rid for rid, _ in batch]
            payloads = [p for _, p in batch]

            try:
                ok = self._send(payloads)
            except Exception as e:
                print(f"Upload error: {e}")
                ok = False

            if ok:
                self.queue.ack(ids)
                backoff = self.cfg["upload_retry_seconds"]
            else:
                self.queue.mark_failed(ids)
                self._stop.wait(backoff)
                backoff = min(backoff * 2, 600)

    def _send(self, payloads):
        body = {
            "schema_version": "1.0",
            "edge_id": self.cfg["edge_id"],
            "service_provider": self.cfg["service_provider"],
            "property_id": self.cfg["property_id"],
            "property_name": self.cfg["property_name"],
            "messages": payloads,
        }
        response = None
        exception = None
        try:
            response = requests.post(
                self.cfg["cloud_endpoint"],
                json=body,
                headers={"X-Provider-Id": self.cfg["service_provider"]},
                timeout=10,
            )
        except Exception as e:
            exception = e
        finally:
            self._write_http_log(body, response, exception)

        if exception:
            raise exception
        return 200 <= response.status_code < 300

    def stop(self):
        self._stop.set()
