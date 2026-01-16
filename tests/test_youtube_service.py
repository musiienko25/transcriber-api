"""Tests for YouTube service."""

import pytest
from unittest.mock import MagicMock, patch

from app.services.youtube import YouTubeService
from app.core.exceptions import InvalidYouTubeURLError, VideoUnavailableError


class TestVideoIdExtraction:
    """Tests for video ID extraction."""

    @pytest.mark.parametrize(
        "url,expected_id",
        [
            # Standard watch URLs
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("http://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            # With additional params
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=120", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLtest", "dQw4w9WgXcQ"),
            # Short URLs
            ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("http://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtu.be/dQw4w9WgXcQ?t=120", "dQw4w9WgXcQ"),
            # Embed URLs
            ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            # Shorts
            ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            # Mobile
            ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            # Music
            ("https://music.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ],
    )
    def test_extract_video_id_valid_urls(self, url: str, expected_id: str) -> None:
        """Test extracting video IDs from various valid URL formats."""
        assert YouTubeService.extract_video_id(url) == expected_id

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.google.com",
            "https://vimeo.com/123456",
            "not-a-url",
            "https://youtube.com",
            "https://youtube.com/",
            "",
        ],
    )
    def test_extract_video_id_invalid_urls(self, url: str) -> None:
        """Test that invalid URLs raise InvalidYouTubeURLError."""
        with pytest.raises(InvalidYouTubeURLError):
            YouTubeService.extract_video_id(url)


class TestFetchCaptions:
    """Tests for caption fetching."""

    def test_fetch_captions_success(
        self, mock_youtube_transcript: MagicMock, sample_transcript_data: list
    ) -> None:
        """Test successful caption fetching."""
        # Setup mock
        mock_transcript = MagicMock()
        mock_transcript.language_code = "en"
        mock_transcript.is_generated = False
        mock_transcript.fetch.return_value = sample_transcript_data

        mock_transcript_list = MagicMock()
        mock_transcript_list.__iter__ = MagicMock(return_value=iter([mock_transcript]))
        mock_transcript_list.find_manually_created_transcript.return_value = mock_transcript

        mock_youtube_transcript.list_transcripts.return_value = mock_transcript_list

        # Call
        segments, language, warnings = YouTubeService.fetch_captions("dQw4w9WgXcQ")

        # Assert
        assert len(segments) == 3
        assert language == "en"
        assert segments[0].text == "Hello everyone"
        assert segments[0].start == 0.0

    def test_fetch_captions_with_translation(
        self, mock_youtube_transcript: MagicMock, sample_transcript_data: list
    ) -> None:
        """Test caption fetching with translation."""
        # Setup mock
        mock_translated = MagicMock()
        mock_translated.language_code = "es"
        mock_translated.fetch.return_value = sample_transcript_data

        mock_transcript = MagicMock()
        mock_transcript.language_code = "en"
        mock_transcript.is_generated = False
        mock_transcript.translate.return_value = mock_translated
        mock_transcript.fetch.return_value = sample_transcript_data

        mock_transcript_list = MagicMock()
        mock_transcript_list.__iter__ = MagicMock(return_value=iter([mock_transcript]))
        mock_transcript_list.find_manually_created_transcript.return_value = mock_transcript

        mock_youtube_transcript.list_transcripts.return_value = mock_transcript_list

        # Call
        segments, language, warnings = YouTubeService.fetch_captions(
            "dQw4w9WgXcQ", translate_to="es"
        )

        # Assert
        assert language == "es"
        assert any("Translated" in w for w in warnings)


class TestTranscriptBuilding:
    """Tests for transcript building utilities."""

    def test_build_transcript(self) -> None:
        """Test building full transcript from segments."""
        from app.models.responses import TranscriptionSegment

        segments = [
            TranscriptionSegment(start=0.0, end=2.0, text="Hello"),
            TranscriptionSegment(start=2.0, end=4.0, text="World"),
        ]

        result = YouTubeService.build_transcript(segments)
        assert result == "Hello World"

    def test_get_video_duration(self) -> None:
        """Test calculating video duration from segments."""
        from app.models.responses import TranscriptionSegment

        segments = [
            TranscriptionSegment(start=0.0, end=2.0, text="Hello"),
            TranscriptionSegment(start=2.0, end=5.5, text="World"),
        ]

        result = YouTubeService.get_video_duration(segments)
        assert result == 5.5

    def test_get_video_duration_empty(self) -> None:
        """Test duration calculation with empty segments."""
        assert YouTubeService.get_video_duration([]) == 0.0
