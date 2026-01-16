"""Tests for format converters."""

import pytest

from app.models.responses import TranscriptionSegment
from app.services.formatters import FormatConverter


@pytest.fixture
def sample_segments() -> list[TranscriptionSegment]:
    """Sample segments for testing."""
    return [
        TranscriptionSegment(start=0.0, end=2.5, text="Hello everyone"),
        TranscriptionSegment(start=2.5, end=4.5, text="Welcome to this video"),
        TranscriptionSegment(start=4.5, end=7.5, text="Today we learn Python"),
    ]


class TestToText:
    """Tests for text format conversion."""

    def test_to_text(self, sample_segments: list[TranscriptionSegment]) -> None:
        """Test converting segments to plain text."""
        result = FormatConverter.to_text(sample_segments)
        assert result == "Hello everyone Welcome to this video Today we learn Python"

    def test_to_text_empty(self) -> None:
        """Test with empty segments."""
        result = FormatConverter.to_text([])
        assert result == ""


class TestToSRT:
    """Tests for SRT format conversion."""

    def test_to_srt(self, sample_segments: list[TranscriptionSegment]) -> None:
        """Test converting segments to SRT format."""
        result = FormatConverter.to_srt(sample_segments)

        # Check structure
        lines = result.strip().split("\n")
        
        # First entry
        assert lines[0] == "1"
        assert lines[1] == "00:00:00,000 --> 00:00:02,500"
        assert lines[2] == "Hello everyone"
        
        # Second entry (after blank line)
        assert lines[4] == "2"
        assert lines[5] == "00:00:02,500 --> 00:00:04,500"

    def test_to_srt_long_duration(self) -> None:
        """Test SRT with longer durations (hours)."""
        segments = [
            TranscriptionSegment(start=3661.5, end=3665.0, text="Over an hour in"),
        ]
        result = FormatConverter.to_srt(segments)
        assert "01:01:01,500" in result


class TestToVTT:
    """Tests for VTT format conversion."""

    def test_to_vtt(self, sample_segments: list[TranscriptionSegment]) -> None:
        """Test converting segments to VTT format."""
        result = FormatConverter.to_vtt(sample_segments)

        lines = result.strip().split("\n")
        
        # Header
        assert lines[0] == "WEBVTT"
        
        # First entry (after blank line)
        assert lines[2] == "00:00:00.000 --> 00:00:02.500"
        assert lines[3] == "Hello everyone"

    def test_vtt_uses_dots_not_commas(self) -> None:
        """Test that VTT uses dots for milliseconds, not commas."""
        segments = [TranscriptionSegment(start=0.0, end=1.5, text="Test")]
        result = FormatConverter.to_vtt(segments)
        
        assert "." in result  # VTT uses dots
        assert "00:00:00.000" in result


class TestConvert:
    """Tests for the main convert function."""

    def test_convert_json(self, sample_segments: list[TranscriptionSegment]) -> None:
        """Test converting to JSON format."""
        result = FormatConverter.convert(sample_segments, "json")
        
        assert isinstance(result, list)
        assert len(result) == 3
        assert result[0]["text"] == "Hello everyone"
        assert result[0]["start"] == 0.0

    def test_convert_text(self, sample_segments: list[TranscriptionSegment]) -> None:
        """Test converting to text format."""
        result = FormatConverter.convert(sample_segments, "text")
        
        assert isinstance(result, str)
        assert "Hello everyone" in result

    def test_convert_srt(self, sample_segments: list[TranscriptionSegment]) -> None:
        """Test converting to SRT format."""
        result = FormatConverter.convert(sample_segments, "srt")
        
        assert isinstance(result, str)
        assert "00:00:00,000 --> 00:00:02,500" in result

    def test_convert_vtt(self, sample_segments: list[TranscriptionSegment]) -> None:
        """Test converting to VTT format."""
        result = FormatConverter.convert(sample_segments, "vtt")
        
        assert isinstance(result, str)
        assert "WEBVTT" in result

    def test_convert_unknown_defaults_to_json(
        self, sample_segments: list[TranscriptionSegment]
    ) -> None:
        """Test that unknown format defaults to JSON."""
        result = FormatConverter.convert(sample_segments, "unknown")
        assert isinstance(result, list)
