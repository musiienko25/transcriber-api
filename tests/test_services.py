"""Tests for service layer."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path


class TestMediaService:
    """Tests for MediaService."""

    def test_is_youtube_url(self) -> None:
        """Test YouTube URL detection."""
        from app.services.media import MediaService

        service = MediaService()

        # YouTube URLs
        assert service.is_youtube_url("https://www.youtube.com/watch?v=test")
        assert service.is_youtube_url("https://youtu.be/test")
        assert service.is_youtube_url("https://music.youtube.com/watch?v=test")

        # Not YouTube
        assert not service.is_youtube_url("https://vimeo.com/123")
        assert not service.is_youtube_url("https://example.com/video.mp4")

    def test_is_social_media_url(self) -> None:
        """Test social media URL detection."""
        from app.services.media import MediaService

        service = MediaService()

        # Social media URLs
        assert service.is_social_media_url("https://www.tiktok.com/@user/video/123")
        assert service.is_social_media_url("https://twitter.com/user/status/123")
        assert service.is_social_media_url("https://x.com/user/status/123")
        assert service.is_social_media_url("https://www.instagram.com/p/abc123")

        # Not social media
        assert not service.is_social_media_url("https://example.com/audio.mp3")
        assert not service.is_social_media_url("https://www.youtube.com/watch?v=test")

    def test_validate_content_type(self) -> None:
        """Test content type validation."""
        from app.services.media import MediaService

        service = MediaService()

        # Valid types
        assert service.validate_content_type("audio/mpeg") == ".mp3"
        assert service.validate_content_type("audio/wav") == ".wav"
        assert service.validate_content_type("video/mp4") == ".mp4"

        # With charset
        assert service.validate_content_type("audio/mpeg; charset=utf-8") == ".mp3"

    def test_validate_content_type_unsupported(self) -> None:
        """Test unsupported content type."""
        from app.services.media import MediaService
        from app.core.exceptions import UnsupportedMediaTypeError

        service = MediaService()

        with pytest.raises(UnsupportedMediaTypeError):
            service.validate_content_type("application/pdf")


class TestFormatConverter:
    """Tests for format converter edge cases."""

    def test_srt_time_formatting(self) -> None:
        """Test SRT time formatting."""
        from app.services.formatters import FormatConverter

        # Test various times
        assert FormatConverter._format_srt_time(0.0) == "00:00:00,000"
        assert FormatConverter._format_srt_time(61.5) == "00:01:01,500"
        assert FormatConverter._format_srt_time(3661.123) == "01:01:01,123"

    def test_vtt_time_formatting(self) -> None:
        """Test VTT time formatting."""
        from app.services.formatters import FormatConverter

        # VTT uses dots instead of commas
        assert FormatConverter._format_vtt_time(0.0) == "00:00:00.000"
        assert FormatConverter._format_vtt_time(61.5) == "00:01:01.500"


class TestJobService:
    """Tests for JobService."""

    @pytest.mark.asyncio
    async def test_job_lifecycle(self) -> None:
        """Test job creation and status transitions."""
        from app.services.jobs import JobService
        from app.models.jobs import JobType

        with patch("app.services.jobs.get_redis") as mock_redis:
            redis_mock = AsyncMock()
            redis_mock.setex = AsyncMock(return_value=True)
            redis_mock.lpush = AsyncMock(return_value=1)
            redis_mock.get = AsyncMock(return_value=None)
            mock_redis.return_value = redis_mock

            service = JobService()

            # Create job
            job = await service.create_job(
                job_type=JobType.YOUTUBE,
                input_url="https://youtube.com/watch?v=test",
                input_params={"format": "json"},
            )

            assert job.status == "queued"
            assert job.job_id is not None
            assert job.job_type == JobType.YOUTUBE

    @pytest.mark.asyncio
    async def test_job_mark_processing(self) -> None:
        """Test marking job as processing."""
        from app.models.jobs import JobData, JobType

        job = JobData(
            job_id="test-job",
            job_type=JobType.YOUTUBE,
            status="queued",
        )

        job.mark_processing("worker-1")

        assert job.status == "processing"
        assert job.worker_id == "worker-1"
        assert job.started_at is not None

    @pytest.mark.asyncio
    async def test_job_mark_completed(self) -> None:
        """Test marking job as completed."""
        from app.models.jobs import JobData, JobType

        job = JobData(
            job_id="test-job",
            job_type=JobType.YOUTUBE,
            status="processing",
        )

        result = {"transcript": "Hello world", "language": "en"}
        job.mark_completed(result)

        assert job.status == "completed"
        assert job.result == result
        assert job.progress == 100.0
        assert job.completed_at is not None


class TestRunpodService:
    """Tests for RunpodService."""

    def test_is_configured_false(self) -> None:
        """Test is_configured when not configured."""
        from app.services.runpod import RunpodService

        with patch("app.services.runpod.get_settings") as mock_settings:
            mock_settings.return_value.runpod_api_key = None
            mock_settings.return_value.runpod_endpoint_id = None

            service = RunpodService()
            assert not service.is_configured

    def test_is_configured_true(self) -> None:
        """Test is_configured when configured."""
        from app.services.runpod import RunpodService

        with patch("app.services.runpod.get_settings") as mock_settings:
            mock_settings.return_value.runpod_api_key = "test-key"
            mock_settings.return_value.runpod_endpoint_id = "test-endpoint"

            service = RunpodService()
            assert service.is_configured
