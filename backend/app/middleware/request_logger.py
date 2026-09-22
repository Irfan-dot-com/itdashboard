import time
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = structlog.get_logger(__name__)

_SKIP_PATHS = frozenset({"/livez", "/readyz", "/healthz"})
_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})
_MAX_BODY_LOG = 4096  # truncate logged bodies at 4 KB


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, detailed: bool = True, log_request_body: bool = True):
        super().__init__(app)
        self._detailed = detailed
        self._log_body = log_request_body

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=getattr(request.state, "request_id", "-"),
            method=request.method,
            path=request.url.path,
            provider_id=request.headers.get("x-provider-id", "-"),
        )

        start = time.perf_counter()

        if self._detailed:
            return await self._dispatch_detailed(request, call_next, start)
        else:
            return await self._dispatch_minimal(request, call_next, start)

    # ------------------------------------------------------------------
    # Detailed mode: full request body + response body + all context
    # ------------------------------------------------------------------
    async def _dispatch_detailed(self, request: Request, call_next, start: float):
        req_extra: dict[str, Any] = {}
        if request.url.query:
            req_extra["query"] = request.url.query
        if request.client:
            req_extra["client_ip"] = request.client.host
        raw_cl = request.headers.get("content-length")
        if raw_cl:
            req_extra["content_length"] = int(raw_cl)

        if self._log_body and request.method in _BODY_METHODS:
            body_bytes = await request.body()
            if body_bytes:
                req_extra["request_body"] = body_bytes.decode("utf-8", errors="replace")[:_MAX_BODY_LOG]

        logger.info("request.start", **req_extra)

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            logger.exception("request.error", duration_ms=duration_ms)
            raise

        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        resp_extra: dict[str, Any] = {"status_code": response.status_code, "duration_ms": duration_ms}

        content_type = response.headers.get("content-type", "")
        if "text/event-stream" not in content_type:
            chunks: list[bytes] = []
            async for chunk in response.body_iterator:
                chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode("utf-8"))
            body = b"".join(chunks)

            resp_extra["response_size"] = len(body)
            if body:
                resp_extra["response_body"] = body.decode("utf-8", errors="replace")[:_MAX_BODY_LOG]

            async def _replay() -> None:
                yield body  # type: ignore[misc]

            response.body_iterator = _replay()
        else:
            size_header = response.headers.get("content-length")
            if size_header:
                resp_extra["response_size"] = int(size_header)
            resp_extra["response_body"] = "<sse-stream>"

        logger.info("request.complete", **resp_extra)
        return response

    # ------------------------------------------------------------------
    # Minimal mode: one log line per request — method, path, status, duration
    # ------------------------------------------------------------------
    async def _dispatch_minimal(self, request: Request, call_next, start: float):
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            logger.exception("request.error", duration_ms=duration_ms)
            raise

        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        logger.info(
            "request",
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response
