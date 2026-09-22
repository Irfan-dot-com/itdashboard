import hashlib

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Endpoints whose data changes at most every ~10 seconds (tile aggregates).
_TILE_PREFIXES = ("/v1/estate", "/v1/exec")

# Endpoints that skip caching entirely (streaming, health probes).
_NO_CACHE_PREFIXES = ("/v1/stream", "/livez", "/readyz", "/healthz")


class ETagMiddleware(BaseHTTPMiddleware):
    """Add ETag + Cache-Control headers to successful GET responses.

    max-age=10 for tile-level aggregates, max-age=2 for live-ish queries.
    Skips streaming responses and health probes.
    304 short-circuit: if client sends If-None-Match matching the ETag, return 304.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method != "GET":
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(p) for p in _NO_CACHE_PREFIXES):
            return await call_next(request)

        response = await call_next(request)

        if response.status_code != 200:
            return response

        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            return response

        body = b""
        async for chunk in response.body_iterator:
            body += chunk if isinstance(chunk, bytes) else chunk.encode()

        etag = f'"{hashlib.sha1(body).hexdigest()[:16]}"'

        if any(path.startswith(p) for p in _TILE_PREFIXES):
            cache_control = "private, max-age=10"
        else:
            cache_control = "private, max-age=2"

        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={"ETag": etag, "Cache-Control": cache_control})

        return Response(
            content=body,
            status_code=response.status_code,
            headers={**dict(response.headers), "ETag": etag, "Cache-Control": cache_control},
            media_type=response.media_type,
        )
