"""Pytest configuration and fixtures."""

import os
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

# Set test environment
os.environ["DEV_MODE"] = "true"
os.environ["ENVIRONMENT"] = "development"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Use asyncio backend for async tests."""
    return "asyncio"


@pytest.fixture
def mock_redis() -> Generator[MagicMock, None, None]:
    """Mock Redis client."""
    with patch("app.services.jobs.get_redis") as mock:
        redis_mock = AsyncMock()
        redis_mock.ping = AsyncMock(return_value=True)
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock(return_value=True)
        redis_mock.lpush = AsyncMock(return_value=1)
        redis_mock.rpop = AsyncMock(return_value=None)
        redis_mock.llen = AsyncMock(return_value=0)
        redis_mock.exists = AsyncMock(return_value=False)
        mock.return_value = redis_mock
        yield redis_mock


@pytest.fixture
def app(mock_redis: MagicMock) -> Generator:
    """Create test application."""
    from app.main import create_app
    
    application = create_app()
    yield application


@pytest.fixture
def client(app) -> Generator[TestClient, None, None]:
    """Create test client."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
async def async_client(app) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_youtube_transcript() -> Generator[MagicMock, None, None]:
    """Mock YouTube transcript API."""
    with patch("app.services.youtube.YouTubeTranscriptApi") as mock:
        yield mock


@pytest.fixture
def mock_whisper_model() -> Generator[MagicMock, None, None]:
    """Mock Whisper model."""
    with patch("app.services.asr._whisper_model") as mock:
        mock_model = MagicMock()
        mock.return_value = mock_model
        yield mock_model


@pytest.fixture
def sample_transcript_data() -> list[dict]:
    """Sample transcript data from YouTube."""
    return [
        {"text": "Hello everyone", "start": 0.0, "duration": 2.5},
        {"text": "Welcome to this video", "start": 2.5, "duration": 2.0},
        {"text": "Today we will learn about Python", "start": 4.5, "duration": 3.0},
    ]


@pytest.fixture
def sample_segments() -> list[dict]:
    """Sample transcription segments."""
    return [
        {"start": 0.0, "end": 2.5, "text": "Hello everyone"},
        {"start": 2.5, "end": 4.5, "text": "Welcome to this video"},
        {"start": 4.5, "end": 7.5, "text": "Today we will learn about Python"},
    ]
