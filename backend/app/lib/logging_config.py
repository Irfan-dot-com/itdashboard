import datetime
import json
import logging
import logging.handlers
import queue
import sys
from pathlib import Path
from typing import Any

import structlog

from app.config import Settings

_listener: logging.handlers.QueueListener | None = None


def _ms_timestamp(logger: Any, method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    now = datetime.datetime.now(datetime.timezone.utc)
    ms = now.microsecond // 1000
    event_dict["time"] = now.strftime(f"%Y-%m-%d %H:%M:%S.{ms:03d}Z")
    return event_dict


def _dev_renderer(logger: Any, method: str, event_dict: dict[str, Any]) -> str:
    """Pretty-print for development stdout.

    Parses request_body / response_body back from escaped JSON strings into
    nested objects so they display as structured data, not a wall of text.
    Adds a blank line after each entry so consecutive logs are easy to scan.
    """
    for key in ("request_body", "response_body"):
        val = event_dict.get(key)
        if isinstance(val, str) and val.lstrip().startswith(("{", "[")):
            try:
                event_dict[key] = json.loads(val)
            except (json.JSONDecodeError, ValueError):
                pass
    return json.dumps(event_dict, indent=2, default=str) + "\n" + "-" * 80


# Processors shared by structlog native loggers AND stdlib foreign loggers
_SHARED_PRE_CHAIN = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    _ms_timestamp,
    structlog.processors.StackInfoRenderer(),
]

# Final processors used by every formatter (after pre-chain)
_FINAL_PROCESSORS_BASE = [
    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
    structlog.processors.ExceptionRenderer(),
]


class _RawQueueHandler(logging.handlers.QueueHandler):
    """Python 3.12+ changed QueueHandler.prepare() to pre-serialise record.msg to a
    string before enqueuing (for safe pickling across process queues). This breaks
    structlog's ProcessorFormatter, which requires record.msg to remain a dict so it
    can continue the processor chain in the QueueListener thread."""

    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        return record


def _make_formatter(dev: bool) -> structlog.stdlib.ProcessorFormatter:
    renderer = _dev_renderer if dev else structlog.processors.JSONRenderer()
    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_SHARED_PRE_CHAIN,
        processors=_FINAL_PROCESSORS_BASE + [renderer],
    )


def configure_logging(settings: Settings) -> None:
    """Set up structlog pipeline + stdlib root logger with optional rotating file output."""
    global _listener

    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    is_dev = settings.ENVIRONMENT == "development"

    structlog.configure(
        processors=_SHARED_PRE_CHAIN + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        cache_logger_on_first_use=True,
    )

    handlers: list[logging.Handler] = []

    # stdout: pretty-printed in development, compact JSON in production
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(_make_formatter(dev=is_dev))
    stream_handler.setLevel(log_level)
    handlers.append(stream_handler)

    if settings.LOG_TO_FILE:
        log_dir = Path(settings.LOG_DIR)
        log_dir.mkdir(parents=True, exist_ok=True)
        # File uses same format as stdout: pretty in dev, compact JSON in production
        file_handler = logging.handlers.TimedRotatingFileHandler(
            filename=log_dir / "app.log",
            when="h",
            interval=1,
            backupCount=settings.LOG_RETENTION_HOURS,
            encoding="utf-8",
            utc=True,
        )
        file_handler.setFormatter(_make_formatter(dev=is_dev))
        file_handler.setLevel(log_level)
        handlers.append(file_handler)

    # _RawQueueHandler + QueueListener: file writes happen in a background thread,
    # never blocking the asyncio event loop under high write volume
    log_queue: queue.Queue = queue.Queue(maxsize=0)
    queue_handler = _RawQueueHandler(log_queue)
    _listener = logging.handlers.QueueListener(log_queue, *handlers, respect_handler_level=True)
    _listener.start()

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(queue_handler)
    root.setLevel(log_level)

    # Suppress uvicorn's built-in access log — our middleware replaces it
    logging.getLogger("uvicorn.access").propagate = False
    # asyncpg is very verbose at DEBUG; keep it quiet unless explicitly escalated
    logging.getLogger("asyncpg").setLevel(max(log_level, logging.WARNING))


def shutdown_logging() -> None:
    global _listener
    if _listener:
        _listener.stop()
        _listener = None
