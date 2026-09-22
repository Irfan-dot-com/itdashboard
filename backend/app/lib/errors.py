import uuid
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int, retryable: bool = False):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        super().__init__(message)


def _envelope(code: str, message: str, request_id: str, retryable: bool) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
            "retryable": retryable,
        }
    }


_HTTP_CODE_MAP = {
    400: "VALIDATION_FAILED",
    401: "AUTH_REQUIRED",
    403: "PERMISSION_DENIED",
    404: "NOT_FOUND",
    409: "CONFLICT",
    429: "RATE_LIMITED",
}


def register_exception_handlers(app: FastAPI) -> None:

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
        code = _HTTP_CODE_MAP.get(exc.status_code, "INTERNAL_ERROR")
        retryable = exc.status_code >= 500
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(code, str(exc.detail), request_id, retryable),
        )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, request_id, exc.retryable),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(x) for x in first.get("loc", []))
        msg = f"{loc}: {first.get('msg', str(exc))}" if loc else first.get("msg", str(exc))
        return JSONResponse(
            status_code=400,
            content=_envelope("VALIDATION_FAILED", msg, request_id, False),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
        logger.exception("unhandled error in %s %s", request.method, request.url.path, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=_envelope("INTERNAL_ERROR", "An unexpected error occurred", request_id, True),
        )
