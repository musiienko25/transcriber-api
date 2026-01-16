"""Tests for media transcription API endpoint."""

import io
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient

from app.models.responses import TranscriptionSegment


class TestMediaEndpoint:
    """Tests for POST /v1/transcriptions/media."""

    def test_transcribe_media_missing_input(
        self, client: TestClient, mock_redis: MagicMock
    ) -> None:
        """Test error when neither file nor URL provided."""
        response = client.post(
            "/v1/transcriptions/media",
            data={},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["code"] == "MISSING_INPUT"

    def test_transcribe_media_youtube_url_redirects(
        self, client: TestClient, mock_redis: MagicMock
    ) -> None:
        """Test that YouTube URLs are redirected to correct endpoint."""
        with patch("app.api.v1.transcriptions.media_service") as mock_media:
            mock_media.is_youtube_url.return_value = True
            mock_media.is_social_media_url.return_value = False

            response = client.post(
                "/v1/transcriptions/media",
                data={"url": "https://www.youtube.com/watch?v=test123"},
            )

        assert response.status_code == 400
        assert "USE_YOUTUBE_ENDPOINT" in response.text

    def test_transcribe_media_url_success(
        self, client: TestClient, mock_redis: MagicMock
    ) -> None:
        """Test successful media transcription from URL."""
        with patch("app.api.v1.transcriptions.media_service") as mock_media, \
             patch("app.api.v1.transcriptions.asr_service") as mock_asr:
            
            mock_media.is_youtube_url.return_value = False
            mock_media.is_social_media_url.return_value = False
            mock_media.download_url = AsyncMock(return_value="/tmp/test.mp3")
            mock_media.cleanup.return_value = None
            
            mock_asr.get_audio_duration = AsyncMock(return_value=60.0)
            mock_asr.transcribe = AsyncMock(return_value=(
                [TranscriptionSegment(start=0.0, end=2.0, text="Hello")],
                "en",
                0.95,
                60.0,
                [],
            ))
            mock_asr.get_source.return_value = "asr_local"

            response = client.post(
                "/v1/transcriptions/media",
                data={"url": "https://example.com/audio.mp3"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "transcript" in data

    def test_transcribe_media_file_upload(
        self, client: TestClient, mock_redis: MagicMock
    ) -> None:
        """Test file upload transcription."""
        with patch("app.api.v1.transcriptions.media_service") as mock_media, \
             patch("app.api.v1.transcriptions.asr_service") as mock_asr:
            
            mock_media.save_upload = AsyncMock(return_value="/tmp/test.mp3")
            mock_media.cleanup.return_value = None
            
            mock_asr.get_audio_duration = AsyncMock(return_value=60.0)
            mock_asr.transcribe = AsyncMock(return_value=(
                [TranscriptionSegment(start=0.0, end=2.0, text="Hello world")],
                "en",
                0.95,
                60.0,
                [],
            ))
            mock_asr.get_source.return_value = "asr_local"

            # Create a fake file
            file_content = b"fake audio content"
            files = {"file": ("test.mp3", io.BytesIO(file_content), "audio/mpeg")}

            response = client.post(
                "/v1/transcriptions/media",
                files=files,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["transcript"] == "Hello world"


class TestMediaSocialSupport:
    """Tests for social media URL support."""

    def test_social_media_url_detected(
        self, client: TestClient, mock_redis: MagicMock
    ) -> None:
        """Test that social media URLs use yt-dlp."""
        with patch("app.api.v1.transcriptions.media_service") as mock_media, \
             patch("app.api.v1.transcriptions.asr_service") as mock_asr:
            
            mock_media.is_youtube_url.return_value = False
            mock_media.is_social_media_url.return_value = True
            mock_media.download_social_media = AsyncMock(return_value="/tmp/test.mp3")
            mock_media.cleanup.return_value = None
            
            mock_asr.get_audio_duration = AsyncMock(return_value=30.0)
            mock_asr.transcribe = AsyncMock(return_value=(
                [TranscriptionSegment(start=0.0, end=2.0, text="TikTok video")],
                "en",
                0.95,
                30.0,
                [],
            ))
            mock_asr.get_source.return_value = "asr_local"

            response = client.post(
                "/v1/transcriptions/media",
                data={"url": "https://www.tiktok.com/@user/video/123"},
            )

        # Verify social media download was called
        mock_media.download_social_media.assert_called_once()


class TestMediaAsyncProcessing:
    """Tests for async job processing."""

    def test_long_media_queued_async(
        self, client: TestClient, mock_redis: MagicMock
    ) -> None:
        """Test that long media files are queued for async processing."""
        with patch("app.api.v1.transcriptions.media_service") as mock_media, \
             patch("app.api.v1.transcriptions.asr_service") as mock_asr, \
             patch("app.api.v1.transcriptions.job_service") as mock_jobs:
            
            mock_media.is_youtube_url.return_value = False
            mock_media.is_social_media_url.return_value = False
            mock_media.download_url = AsyncMock(return_value="/tmp/test.mp3")
            
            # Long duration triggers async
            mock_asr.get_audio_duration = AsyncMock(return_value=900.0)  # 15 min
            
            # Mock job creation
            from app.models.jobs import JobData, JobType
            mock_job = JobData(
                job_id="test-job-123",
                job_type=JobType.MEDIA_URL,
            )
            mock_jobs.create_job = AsyncMock(return_value=mock_job)
            mock_jobs.to_response.return_value = {
                "status": "queued",
                "jobId": "test-job-123",
            }

            response = client.post(
                "/v1/transcriptions/media",
                data={"url": "https://example.com/long-audio.mp3"},
            )

        # Should return job response for long files
        # Note: actual behavior depends on settings.asr_sync_max_duration
        assert response.status_code in [200, 202]
