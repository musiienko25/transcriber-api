"""Format converters for transcript output."""

from app.models.responses import TranscriptionSegment


class FormatConverter:
    """Convert transcript segments to various output formats."""

    @staticmethod
    def to_text(segments: list[TranscriptionSegment]) -> str:
        """Convert segments to plain text."""
        return " ".join(seg.text for seg in segments)

    @staticmethod
    def to_srt(segments: list[TranscriptionSegment]) -> str:
        """
        Convert segments to SRT (SubRip) format.

        Format:
        1
        00:00:00,000 --> 00:00:02,500
        Hello, welcome to the video.

        2
        00:00:02,500 --> 00:00:05,000
        Today we'll be discussing...
        """
        lines = []
        for i, seg in enumerate(segments, 1):
            start = FormatConverter._format_srt_time(seg.start)
            end = FormatConverter._format_srt_time(seg.end)
            lines.append(str(i))
            lines.append(f"{start} --> {end}")
            lines.append(seg.text)
            lines.append("")  # Blank line between entries

        return "\n".join(lines)

    @staticmethod
    def to_vtt(segments: list[TranscriptionSegment]) -> str:
        """
        Convert segments to WebVTT format.

        Format:
        WEBVTT

        00:00:00.000 --> 00:00:02.500
        Hello, welcome to the video.

        00:00:02.500 --> 00:00:05.000
        Today we'll be discussing...
        """
        lines = ["WEBVTT", ""]
        for seg in segments:
            start = FormatConverter._format_vtt_time(seg.start)
            end = FormatConverter._format_vtt_time(seg.end)
            lines.append(f"{start} --> {end}")
            lines.append(seg.text)
            lines.append("")  # Blank line between entries

        return "\n".join(lines)

    @staticmethod
    def _format_srt_time(seconds: float) -> str:
        """Format time as SRT timestamp (HH:MM:SS,mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    @staticmethod
    def _format_vtt_time(seconds: float) -> str:
        """Format time as VTT timestamp (HH:MM:SS.mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"

    @staticmethod
    def convert(
        segments: list[TranscriptionSegment],
        format: str,
    ) -> str | list[dict]:
        """
        Convert segments to the requested format.

        Args:
            segments: List of transcript segments
            format: Output format (json, text, srt, vtt)

        Returns:
            Formatted output (string for text/srt/vtt, list of dicts for json)
        """
        format = format.lower()

        if format == "text":
            return FormatConverter.to_text(segments)
        elif format == "srt":
            return FormatConverter.to_srt(segments)
        elif format == "vtt":
            return FormatConverter.to_vtt(segments)
        else:  # json is default
            return [seg.model_dump() for seg in segments]
