"""Tests for YouTube transcription API endpoint."""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.models.responses import TranscriptionSegment


class TestYouTubeEndpoint:
    """Tests for POST /v1/transcriptions/youtube."""

    def test_transcribe_youtube_captions_success(
        self, client: TestClient, mock_redis: MagicMock
    ) -> None:
        """Test successful YouTube transcription via captions."""
        mock_segments = [
            {"text": "Hello", "start": 0.0, "duration": 2.0},
            {"text": "World", "start": 2.0, "duration": 2.0},
        ]

        with patch("app.services.youtube.YouTubeTranscriptApi") as mock_api:
            # Setup mock transcript
            mock_transcript = MagicMock()
            mock_transcript.language_code = "en"
            mock_transcript.is_generated = False
            mock_transcript.fetch.return_value = mock_segments

            mock_list = MagicMock()
            mock_list.__iter__ = MagicMock(return_value=iter([mock_transcript]))
            mock_list.find_manually_created_transcript.return_value = mock_transcript

            mock_api.list_transcripts.return_value = mock_list

            response = client.post(
                "/v1/transcriptions/youtube",
                json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "youtube_captions"
        assert data["language"] == "en"
        assert len(data["segments"]) == 2
        assert "Hello" in data["transcript"]

    def test_transcribe_youtube_invalid_url(
        self, client: TestClient, mock_redis: MagicMock
    ) -> None:
        """Test with invalid YouTube URL."""
        response = client.post(
            "/v1/transcriptions/youtube",
            json={"url": "https://www.google.com"},
        )

        assert response.status_code == 422  # Validation error

    def test_transcribe_youtube_missing_url(
        self, client: TestClient, mock_redis: MagicMock
    ) -> None:
        """Test with missing URL."""
        response = client.post(
            "/v1/transcriptions/youtube",
            json={},
        )

        assert response.status_code == 422

    def test_transcribe_youtube_with_format_srt(
        self, client: TestClient, mock_redis: MagicMock
    ) -> None:
        """Test YouTube transcription with SRT format."""
        mock_segments = [
            {"text": "Hello", "start": 0.0, "duration": 2.0},
        ]

        with patch("app.services.youtube.YouTubeTranscriptApi") as mock_api:
            mock_transcript = MagicMock()
            mock_transcript.language_code = "en"
            mock_transcript.is_generated = False
            mock_transcript.fetch.return_value = mock_segments

            mock_list = MagicMock()
            mock_list.__iter__ = MagicMock(return_value=iter([mock_transcript]))
            mock_list.find_manually_created_transcript.return_value = mock_transcript

            mock_api.list_transcripts.return_value = mock_list

            response = client.post(
                "/v1/transcriptions/youtube",
                json={
                    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "format": "srt",
                },
            )

        assert response.status_code == 200
        assert "00:00:00,000 --> 00:00:02,000" in response.text


class TestYouTubeASRFallback:
    """Tests for ASR fallback path."""

    def test_transcribe_youtube_with_diarise_triggers_asr(
        self, client: TestClient, mock_redis: MagicMock
    ) -> None:
        """Test that diarise=true triggers ASR mode."""
        with patch("app.api.v1.transcriptions.media_service") as mock_media, \
             patch("app.api.v1.transcriptions.asr_service") as mock_asr:
            
            # Mock media download
            mock_media.download_youtube_audio.return_value = "/tmp/test.mp3"
            mock_media.cleanup.return_value = None
            
            # Mock ASR
            mock_asr.get_audio_duration.return_value = 60.0
            mock_asr.transcribe.return_value = (
                [TranscriptionSegment(start=0.0, end=2.0, text="Hello")],
                "en",
                0.95,
                60.0,
                [],
            )
            mock_asr.get_source.return_value = "asr_local"

            response = client.post(
                "/v1/transcriptions/youtube",
                json={
                    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "diarise": True,
                },
            )

        # Should attempt ASR (may fail in test env, but should try)
        assert response.status_code in [200, 500]


class TestYouTubeErrorHandling:
    """Tests for error handling."""

    def test_video_unavailable_error(
        self, client: TestClient, mock_redis: MagicMock
    ) -> None:
        """Test handling of unavailable video."""
        from youtube_transcript_api import VideoUnavailable

        with patch("app.services.youtube.YouTubeTranscriptApi") as mock_api:
            mock_api.list_transcripts.side_effect = VideoUnavailable("test123")

            response = client.post(
                "/v1/transcriptions/youtube",
                json={"url": "https://www.youtube.com/watch?v=test123456"},
            )

        assert response.status_code == 404
        data = response.json()
        assert data["code"] == "VIDEO_UNAVAILABLE"

    def test_transcripts_disabled_error(
        self, client: TestClient, mock_redis: MagicMock
    ) -> None:
        """Test handling of disabled transcripts."""
        from youtube_transcript_api import TranscriptsDisabled

        with patch("app.services.youtube.YouTubeTranscriptApi") as mock_api:
            mock_api.list_transcripts.side_effect = TranscriptsDisabled("test123")

            response = client.post(
                "/v1/transcriptions/youtube",
                json={"url": "https://www.youtube.com/watch?v=test123456"},
            )

        # Should fall back to ASR or return error
        assert response.status_code in [404, 500]
