"""YouTube service for extracting video info and captions."""

import re
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)
from youtube_transcript_api._errors import NoTranscriptAvailable

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
            # List available transcripts
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

            # Get available languages for error messages
            available_languages = []
            try:
                for transcript in transcript_list:
                    available_languages.append(transcript.language_code)
            except Exception:
                pass

            transcript = None
            detected_language = language or "en"

            # Strategy 1: Try to get manually created transcript in preferred language
            if language:
                try:
                    transcript = transcript_list.find_manually_created_transcript([language])
                    detected_language = language
                    logger.info("Found manual transcript", language=language, video_id=video_id)
                except NoTranscriptFound:
                    pass

            # Strategy 2: Try to get auto-generated transcript in preferred language
            if transcript is None and language:
                try:
                    transcript = transcript_list.find_generated_transcript([language])
                    detected_language = language
                    warnings.append(f"Using auto-generated captions for {language}")
                    logger.info("Found auto-generated transcript", language=language, video_id=video_id)
                except NoTranscriptFound:
                    pass

            # Strategy 3: Try to get any manually created transcript
            if transcript is None:
                try:
                    transcript = transcript_list.find_manually_created_transcript(
                        ["en", "en-US", "en-GB"]
                    )
                    detected_language = transcript.language_code
                    logger.info("Found English manual transcript", video_id=video_id)
                except NoTranscriptFound:
                    pass

            # Strategy 4: Get any available transcript
            if transcript is None:
                try:
                    # Get first available transcript
                    for t in transcript_list:
                        transcript = t
                        detected_language = t.language_code
                        if t.is_generated:
                            warnings.append(f"Using auto-generated captions ({t.language_code})")
                        break
                except StopIteration:
                    pass

            if transcript is None:
                raise TranscriptNotFoundError(video_id, available_languages)

            # Handle translation if requested
            if translate_to and translate_to != detected_language:
                try:
                    transcript = transcript.translate(translate_to)
                    warnings.append(f"Translated from {detected_language} to {translate_to}")
                    detected_language = translate_to
                    logger.info(
                        "Translated transcript",
                        from_lang=detected_language,
                        to_lang=translate_to,
                        video_id=video_id,
                    )
                except Exception as e:
                    warnings.append(f"Translation to {translate_to} not available: {str(e)}")
                    logger.warning(
                        "Translation failed",
                        to_lang=translate_to,
                        error=str(e),
                        video_id=video_id,
                    )

            # Fetch the transcript data
            transcript_data = transcript.fetch()

            # Convert to segments
            segments = []
            for item in transcript_data:
                segment = TranscriptionSegment(
                    start=item["start"],
                    end=item["start"] + item["duration"],
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
