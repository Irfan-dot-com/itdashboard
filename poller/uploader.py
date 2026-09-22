"""
Uploads queued messages to the cloud dashboard.

Differs from the syslog agent's uploader in two ways that matter in production:

  * every logged payload goes through config.redact() first, so an SD-LAN
    credential can never reach a log file on the edge box;
  * a 4xx is treated as permanent. The syslog agent retries a 422 forever and
    always retries the oldest rows first, so one malformed message blocks the
    whole queue indefinitely. Here a 4xx batch is retried a few times, then
    quarantined so the rest keeps flowing.
"""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import requests

import config as poller_config

MAX_4XX_ATTEMPTS = 3


class CloudUploader:
    def __init__(self, cfg, queue, session=None):
        self.cfg = cfg
        self.queue = queue
        self._stop = threading.Event()
        self._log_path = (cfg.get("cloud_upload_log_path") or "").strip()
        self._log_lock = threading.Lock()
        self._session = session or requests.Session()
        self._batch_attempts = {}

    # ------------------------------------------------------------------ log

    def _write_log(self, body, response=None, exception=None):
        if not self._log_path:
            return
        utc_now = datetime.now(timezone.utc)
        local_now = utc_now.astimezone()
        lines = [
            "=" * 80,
            f"timestamp (local): {local_now.strftime('%A, %d %B %Y at %I:%M:%S %p')} "
            f"({local_now.tzname() or 'local'})",
            f"timestamp (UTC):   {utc_now.strftime('%A, %d %B %Y at %I:%M:%S %p UTC')}",
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
        # Redacted even though this body should never carry SD-LAN credentials:
        # defence in depth, because this file is plaintext on a customer network.
        safe_body = poller_config.redact(body)
        for pl in json.dumps(safe_body, indent=2, ensure_ascii=False,
                             default=str).splitlines():
            lines.append(f"    {pl}")

        lines.extend(["", "RESULT"])
        if exception is not None:
            lines.append("  outcome: REQUEST_FAILED")
            lines.append(f"  exception: {type(exception).__name__}: {exception}")
        elif response is not None:
            ok = 200 <= response.status_code < 300
            lines.append(f"  outcome: {'HTTP_SUCCESS' if ok else 'HTTP_NON_SUCCESS'}")
            lines.append(f"  status_code: {response.status_code}")
            lines.append(f"  reason: {getattr(response, 'reason', '') or ''}")
            try:
                rb = response.text or ""
                if len(rb) > 8000:
                    rb = rb[:8000] + f"\n    ... (truncated, total {len(response.text)})"
                if rb.strip():
                    lines.append("  response_body:")
                    for rl in rb.splitlines():
                        lines.append(f"    {rl}")
                else:
                    lines.append("  response_body: <empty>")
            except Exception as ex:
                lines.append(f"  response_body: <could not read: {ex}>")
        else:
            lines.append("  outcome: UNKNOWN")
        lines.append("")

        try:
            with self._log_lock:
                Path(self._log_path).parent.mkdir(parents=True, exist_ok=True)
                with open(self._log_path, "a", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
                    f.flush()
        except OSError as e:
            print(f"cloud upload log write error ({self._log_path}): {e}")

    # ----------------------------------------------------------------- send

    def _envelope(self, payloads):
        return {
            "schema_version": "1.0",
            "edge_id": self.cfg["edge_id"],
            "service_provider": self.cfg["service_provider"],
            "property_id": self.cfg["property_id"],
            "property_name": self.cfg.get("property_name"),
            "messages": payloads,
        }

    def send(self, payloads):
        """
        POST one batch.

        Returns (ok, permanent, detail): ok True on 2xx; permanent True when
        the cloud rejected the content itself (4xx) and retrying cannot help.
        """
        body = self._envelope(payloads)
        response = exception = None
        try:
            response = self._session.post(
                self.cfg["cloud_endpoint"], json=body,
                headers={"X-Provider-Id": self.cfg["service_provider"]},
                timeout=self.cfg.get("cloud_timeout_seconds", 20))
        except Exception as e:
            exception = e
        finally:
            self._write_log(body, response, exception)

        if exception is not None:
            return False, False, f"{type(exception).__name__}: {exception}"
        if 200 <= response.status_code < 300:
            rejected = []
            try:
                rejected = (response.json() or {}).get("rejected") or []
            except Exception:
                pass
            if rejected:
                return True, False, f"cloud accepted batch but rejected {len(rejected)}: {rejected[:3]}"
            return True, False, f"HTTP {response.status_code}"
        permanent = 400 <= response.status_code < 500 and response.status_code != 429
        return False, permanent, f"HTTP {response.status_code}: {(response.text or '')[:300]}"

    def run(self):
        backoff = self.cfg.get("upload_retry_seconds", 30)
        while not self._stop.is_set():
            batch = self.queue.take_batch(self.cfg.get("upload_batch_size", 50))
            if not batch:
                self._stop.wait(2)
                continue

            ids = [rid for rid, _ in batch]
            payloads = [p for _, p in batch]
            ok, permanent, detail = self.send(payloads)

            if ok:
                self.queue.ack(ids)
                self._batch_attempts.clear()
                backoff = self.cfg.get("upload_retry_seconds", 30)
                if "rejected" in detail:
                    print(f"Upload warning: {detail}")
                continue

            self.queue.mark_failed(ids, detail)
            print(f"Upload failed ({'permanent' if permanent else 'retryable'}): {detail}")

            if permanent:
                key = tuple(ids)
                self._batch_attempts[key] = self._batch_attempts.get(key, 0) + 1
                if self._batch_attempts[key] >= MAX_4XX_ATTEMPTS:
                    self.queue.quarantine(ids, detail)
                    del self._batch_attempts[key]
                    print(f"Quarantined {len(ids)} message(s) the cloud will not "
                          f"accept; queue continues. Inspect with: "
                          f"sqlite3 {self.cfg['queue_db_path']} "
                          f"\"SELECT id, kind, last_error FROM outbound "
                          f"WHERE state='quarantined'\"")
                    continue

            self._stop.wait(backoff)
            backoff = min(backoff * 2, 600)

    def stop(self):
        self._stop.set()
