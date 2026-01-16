"""Health check endpoints."""

from fastapi import APIRouter, Response
from prometheus_client import (
    Counter,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.responses import HealthResponse
from app.services.jobs import get_redis

router = APIRouter()
logger = get_logger(__name__)

# Prometheus metrics
REQUEST_COUNT = Counter(
    "transcriber_requests_total",
    "Total number of requests",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "transcriber_request_latency_seconds",
    "Request latency in seconds",
    ["method", "endpoint"],
)
TRANSCRIPTION_COUNT = Counter(
    "transcriber_transcriptions_total",
    "Total number of transcriptions",
    ["source", "status"],
)
TRANSCRIPTION_DURATION = Histogram(
    "transcriber_transcription_duration_seconds",
    "Transcription duration in seconds",
    ["source"],
)
QUEUE_SIZE = Counter(
    "transcriber_queue_size",
    "Current queue size",
)


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Check the health status of the API and its dependencies",
)
async def health_check() -> HealthResponse:
    """
    Health check endpoint.

    Returns the status of the API and its components:
    - API server status
    - Redis connection status
    - Whisper model status
    """
    settings = get_settings()
    components = {}

    # Check Redis
    try:
        redis_client = await get_redis()
        await redis_client.ping()
        components["redis"] = {"status": "healthy", "connected": True}
    except Exception as e:
        components["redis"] = {"status": "unhealthy", "error": str(e)}

    # Check Whisper model (just config, not loading)
    components["whisper"] = {
        "status": "healthy",
        "model": settings.whisper_model,
        "device": settings.whisper_device,
        "provider": settings.asr_provider,
    }

    # Determine overall status
    all_healthy = all(
        c.get("status") == "healthy" for c in components.values()
    )
    status = "healthy" if all_healthy else "degraded"

    return HealthResponse(
        status=status,
        version=settings.app_version,
        environment=settings.environment,
        components=components,
    )


@router.get(
    "/metrics",
    summary="Prometheus metrics",
    description="Get Prometheus-formatted metrics",
    response_class=Response,
)
async def metrics() -> Response:
    """
    Prometheus metrics endpoint.

    Returns metrics in Prometheus text format.
    """
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@router.get(
    "/ready",
    summary="Readiness check",
    description="Check if the service is ready to accept requests",
)
async def readiness() -> dict:
    """Readiness probe for Kubernetes."""
    try:
        redis_client = await get_redis()
        await redis_client.ping()
        return {"ready": True}
    except Exception:
        return {"ready": False}


@router.get(
    "/live",
    summary="Liveness check",
    description="Check if the service is alive",
)
async def liveness() -> dict:
    """Liveness probe for Kubernetes."""
    return {"alive": True}
