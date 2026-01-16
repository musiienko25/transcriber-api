"""YouTube service for extracting video info and captions."""

import re
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)

# Backwards compatibility - NoTranscriptAvailable was removed in newer versions
try:
    from youtube_transcript_api._errors import NoTranscriptAvailable
except ImportError:
    NoTranscriptAvailable = NoTranscriptFound

from app.core.exceptions import (
    CaptionsDisabledError,
    InvalidYouTubeURLError,
    TranscriptNotFoundError,
    VideoUnavailableError,
)
from app.core.logging import get_logger
from app.models.responses import TranscriptionSegment, TranscriptionSource

logger = get_logger(__name__)


class YouTubeService:
    """Service for YouTube video operations."""

    # Regex patterns for extracting video IDs
    VIDEO_ID_PATTERNS = [
        # Standard watch URLs: youtube.com/watch?v=VIDEO_ID
        r"(?:youtube\.com/watch\?.*v=)([a-zA-Z0-9_-]{11})",
        # Short URLs: youtu.be/VIDEO_ID
        r"(?:youtu\.be/)([a-zA-Z0-9_-]{11})",
        # Embed URLs: youtube.com/embed/VIDEO_ID
        r"(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
        # Shorts URLs: youtube.com/shorts/VIDEO_ID
        r"(?:youtube\.com/shorts/)([a-zA-Z0-9_-]{11})",
        # Live URLs: youtube.com/live/VIDEO_ID
        r"(?:youtube\.com/live/)([a-zA-Z0-9_-]{11})",
        # Music URLs: music.youtube.com/watch?v=VIDEO_ID
        r"(?:music\.youtube\.com/watch\?.*v=)([a-zA-Z0-9_-]{11})",
    ]

    @classmethod
    def extract_video_id(cls, url: str) -> str:
        """
        Extract video ID from various YouTube URL formats.

        Args:
            url: YouTube video URL

        Returns:
            11-character video ID

        Raises:
            InvalidYouTubeURLError: If URL is not a valid YouTube URL
        """
        url = url.strip()

        # Try regex patterns first
        for pattern in cls.VIDEO_ID_PATTERNS:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                return match.group(1)

        # Fallback: try to extract from query params
        try:
            parsed = urlparse(url)
            if "youtube.com" in parsed.netloc or "youtu.be" in parsed.netloc:
                query_params = parse_qs(parsed.query)
                if "v" in query_params:
                    video_id = query_params["v"][0]
                    if len(video_id) == 11:
                        return video_id
        except Exception:
            pass

        logger.warning("Failed to extract video ID", url=url)
        raise InvalidYouTubeURLError(url)

    @classmethod
    def fetch_captions(
        cls,
        video_id: str,
        language: str | None = None,
        translate_to: str | None = None,
    ) -> tuple[list[TranscriptionSegment], str, list[str]]:
        """
        Fetch captions for a YouTube video.

        Args:
            video_id: YouTube video ID
            language: Preferred source language (optional)
            translate_to: Target language for translation (optional)

        Returns:
            Tuple of (segments, detected_language, warnings)

        Raises:
            VideoUnavailableError: If video is unavailable
            CaptionsDisabledError: If captions are disabled
            TranscriptNotFoundError: If no transcript found
        """
        warnings: list[str] = []

        try:
            # Use simple get_transcript method - more reliable
            languages_to_try = []
            if language:
                languages_to_try.append(language)
            languages_to_try.extend(["en", "en-US", "en-GB"])

            transcript_data = None
            detected_language = language or "en"

            # Try to get transcript directly
            try:
                transcript_data = YouTubeTranscriptApi.get_transcript(
                    video_id,
                    languages=languages_to_try if language else None,
                )
                logger.info("Fetched transcript directly", video_id=video_id)
            except Exception as direct_error:
                logger.debug("Direct fetch failed, trying list method", error=str(direct_error))

                # Fallback to list_transcripts method
                try:
                    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

                    transcript = None
                    # Try to find any available transcript
                    for t in transcript_list:
                        transcript = t
                        detected_language = t.language_code
                        if t.is_generated:
                            warnings.append(f"Using auto-generated captions ({t.language_code})")
                        break

                    if transcript:
                        transcript_data = transcript.fetch()
                except Exception as list_error:
                    logger.error("List transcripts failed", error=str(list_error))
                    raise

            if not transcript_data:
                raise TranscriptNotFoundError(video_id)

            # Convert to segments
            segments = []
            for item in transcript_data:
                segment = TranscriptionSegment(
                    start=item["start"],
                    end=item["start"] + item.get("duration", 0),
                    text=item["text"],
                )
                segments.append(segment)

            logger.info(
                "Fetched captions successfully",
                video_id=video_id,
                segments_count=len(segments),
                language=detected_language,
            )

            return segments, detected_language, warnings

        except VideoUnavailable as e:
            logger.error("Video unavailable", video_id=video_id, error=str(e))
            raise VideoUnavailableError(video_id, str(e))

        except TranscriptsDisabled:
            logger.warning("Transcripts disabled", video_id=video_id)
            raise CaptionsDisabledError(video_id)

        except NoTranscriptFound:
            logger.warning("No transcript found", video_id=video_id)
            raise TranscriptNotFoundError(video_id)

        except NoTranscriptAvailable:
            logger.warning("No transcript available", video_id=video_id)
            raise TranscriptNotFoundError(video_id)

        except (TranscriptNotFoundError, CaptionsDisabledError, VideoUnavailableError):
            raise

        except Exception as e:
            logger.error("Unexpected error fetching captions", video_id=video_id, error=str(e))
            raise TranscriptNotFoundError(video_id)

    @classmethod
    def get_video_duration(cls, segments: list[TranscriptionSegment]) -> float:
        """Calculate video duration from segments."""
        if not segments:
            return 0.0
        return max(seg.end for seg in segments)

    @classmethod
    def build_transcript(cls, segments: list[TranscriptionSegment]) -> str:
        """Build full transcript text from segments."""
        return " ".join(seg.text for seg in segments)
