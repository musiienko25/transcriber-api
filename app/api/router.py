"""Main API router."""

from fastapi import APIRouter

from app.api.v1 import transcriptions, jobs, health

api_router = APIRouter()

# Include v1 routes
api_router.include_router(
    health.router,
    prefix="/v1",
    tags=["Health"],
)

api_router.include_router(
    transcriptions.router,
    prefix="/v1/transcriptions",
    tags=["Transcriptions"],
)

api_router.include_router(
    jobs.router,
    prefix="/v1/jobs",
    tags=["Jobs"],
)
