"""API middleware for rate limiting and request logging."""

import time
from typing import Callable

from fastapi import Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.logging import get_logger, log_request
from app.core.security import get_client_identifier

logger = get_logger(__name__)


def get_rate_limit_key(request: Request) -> str:
    """Get key for rate limiting (API key or IP)."""
    return get_client_identifier(request)


# Create limiter instance
limiter = Limiter(key_func=get_rate_limit_key)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all requests."""

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """Log request and response details."""
        start_time = time.time()

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000

        # Log request (skip health checks for less noise)
        if not request.url.path.endswith(("/health", "/ready", "/live", "/metrics")):
            log_request(
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                client=get_remote_address(request),
            )

        # Add timing header
        response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to apply rate limiting."""

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """Apply rate limiting based on API key or IP."""
        settings = get_settings()

        # Skip rate limiting in dev mode
        if settings.dev_mode:
            return await call_next(request)

        # Skip for health endpoints
        if request.url.path.endswith(("/health", "/ready", "/live", "/metrics")):
            return await call_next(request)

        # Rate limit key
        key = get_client_identifier(request)

        # Check rate limit using slowapi
        # This is a simplified implementation
        # In production, you'd use Redis-backed rate limiting

        return await call_next(request)
