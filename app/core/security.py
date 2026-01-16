"""Security utilities for authentication and authorization."""

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from app.core.config import Settings, get_settings
from app.core.exceptions import InvalidAPIKeyError

# API Key header scheme
api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


def extract_api_key(authorization: str | None) -> str | None:
    """Extract API key from Authorization header (Bearer token format)."""
    if not authorization:
        return None

    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    elif len(parts) == 1:
        # Allow raw API key without Bearer prefix
        return parts[0]

    return None


async def verify_api_key(
    request: Request,
    authorization: str | None = Security(api_key_header),
    settings: Settings = Depends(get_settings),
) -> str:
    """
    Verify the API key from the Authorization header.

    In dev mode, authentication is bypassed.
    Returns the API key if valid.
    """
    # Dev mode bypass
    if settings.dev_mode:
        return "dev-mode-key"

    api_key = extract_api_key(authorization)

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail=InvalidAPIKeyError().to_dict(),
        )

    valid_keys = settings.get_api_keys_list()

    if not valid_keys:
        # No API keys configured - allow any key in development
        if settings.environment == "development":
            return api_key
        raise HTTPException(
            status_code=500,
            detail={
                "code": "NO_API_KEYS_CONFIGURED",
                "message": "No API keys configured on server",
            },
        )

    if api_key not in valid_keys:
        raise HTTPException(
            status_code=401,
            detail=InvalidAPIKeyError().to_dict(),
        )

    # Store API key in request state for rate limiting
    request.state.api_key = api_key
    return api_key


def get_client_identifier(request: Request) -> str:
    """Get a unique identifier for the client (for rate limiting)."""
    # Use API key if available, otherwise use IP
    if hasattr(request.state, "api_key"):
        return f"key:{request.state.api_key}"

    # Get client IP (handle proxy headers)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"

    return f"ip:{client_ip}"
