"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.api.middleware import RequestLoggingMiddleware
from app.core.config import get_settings
from app.core.exceptions import TranscriberError
from app.core.logging import setup_logging, get_logger
from app.services.jobs import close_redis

# Setup logging
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    settings = get_settings()
    logger.info(
        "Starting application",
        version=settings.app_version,
        environment=settings.environment,
        debug=settings.debug,
    )

    yield

    # Cleanup
    logger.info("Shutting down application")
    await close_redis()


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="""
# Transcriber API

Production-ready API for transcribing media files.

## Features

- **YouTube Transcription**: Two-path strategy with captions fast-path and ASR fallback
- **Media Transcription**: Support for file uploads and remote URLs
- **Multiple Formats**: JSON, Text, SRT, VTT output formats
- **Async Processing**: Queue-based processing for long media files
- **Observability**: Prometheus metrics and structured logging

## Authentication

All endpoints require an API key passed via `Authorization: Bearer <API_KEY>` header.

In development mode (`DEV_MODE=true`), authentication is bypassed.
        """,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request logging middleware
    app.add_middleware(RequestLoggingMiddleware)

    # Include API routes
    app.include_router(api_router)

    # Exception handlers
    @app.exception_handler(TranscriberError)
    async def transcriber_error_handler(
        request: Request, exc: TranscriberError
    ) -> JSONResponse:
        """Handle custom TranscriberError exceptions."""
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Handle unexpected exceptions."""
        logger.exception("Unhandled exception", error=str(exc))
        return JSONResponse(
            status_code=500,
            content={
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "details": {},
            },
        )

    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        workers=settings.workers,
    )
