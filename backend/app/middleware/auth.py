from fastapi import Header

from app.lib.errors import AppError


async def get_provider_id(x_provider_id: str | None = Header(default=None)) -> str:
    """
    Phase 1: provider identity from X-Provider-Id header.
    Phase 2: replace body with JWT Bearer extraction — return type stays str, no route changes needed.
    """
    if not x_provider_id:
        raise AppError("AUTH_REQUIRED", "X-Provider-Id header is required", 401)
    return x_provider_id
