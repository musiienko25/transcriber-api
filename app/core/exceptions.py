"""Custom exceptions for the application."""

from typing import Any


class TranscriberError(Exception):
    """Base exception for all transcriber errors."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to API response format."""
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


# YouTube Errors
class YouTubeError(TranscriberError):
    """Base exception for YouTube-related errors."""

    pass


class InvalidYouTubeURLError(YouTubeError):
    """Raised when the YouTube URL is invalid."""

    def __init__(self, url: str) -> None:
        super().__init__(
            code="INVALID_YOUTUBE_URL",
            message=f"Invalid YouTube URL: {url}",
            status_code=400,
            details={"url": url},
        )


class VideoUnavailableError(YouTubeError):
    """Raised when the video is unavailable (private, deleted, etc.)."""

    def __init__(self, video_id: str, reason: str = "Video unavailable") -> None:
        super().__init__(
            code="VIDEO_UNAVAILABLE",
            message=reason,
            status_code=404,
            details={"video_id": video_id},
        )


class CaptionsDisabledError(YouTubeError):
    """Raised when captions are disabled for the video."""

    def __init__(self, video_id: str) -> None:
        super().__init__(
            code="CAPTIONS_DISABLED",
            message="Captions are disabled for this video",
            status_code=404,
            details={"video_id": video_id},
        )


class TranscriptNotFoundError(YouTubeError):
    """Raised when no transcript is found for the video."""

    def __init__(self, video_id: str, available_languages: list[str] | None = None) -> None:
        super().__init__(
            code="TRANSCRIPT_NOT_FOUND",
            message="No transcript found for this video",
            status_code=404,
            details={
                "video_id": video_id,
                "available_languages": available_languages or [],
            },
        )


# Media Errors
class MediaError(TranscriberError):
    """Base exception for media-related errors."""

    pass


class UnsupportedMediaTypeError(MediaError):
    """Raised when the media type is not supported."""

    def __init__(self, content_type: str, allowed_types: list[str]) -> None:
        super().__init__(
            code="UNSUPPORTED_MEDIA_TYPE",
            message=f"Unsupported media type: {content_type}",
            status_code=415,
            details={
                "content_type": content_type,
                "allowed_types": allowed_types,
            },
        )


class FileTooLargeError(MediaError):
    """Raised when the file exceeds the maximum size."""

    def __init__(self, size_mb: float, max_size_mb: int) -> None:
        super().__init__(
            code="FILE_TOO_LARGE",
            message=f"File size ({size_mb:.1f}MB) exceeds maximum ({max_size_mb}MB)",
            status_code=413,
            details={
                "size_mb": size_mb,
                "max_size_mb": max_size_mb,
            },
        )


class MediaDownloadError(MediaError):
    """Raised when media download fails."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(
            code="MEDIA_DOWNLOAD_FAILED",
            message=f"Failed to download media: {reason}",
            status_code=400,
            details={"url": url, "reason": reason},
        )


# ASR Errors
class ASRError(TranscriberError):
    """Base exception for ASR-related errors."""

    pass


class TranscriptionFailedError(ASRError):
    """Raised when transcription fails."""

    def __init__(self, reason: str, provider: str = "unknown") -> None:
        super().__init__(
            code="TRANSCRIPTION_FAILED",
            message=f"Transcription failed: {reason}",
            status_code=500,
            details={"reason": reason, "provider": provider},
        )


class ModelNotAvailableError(ASRError):
    """Raised when the ASR model is not available."""

    def __init__(self, model: str) -> None:
        super().__init__(
            code="MODEL_NOT_AVAILABLE",
            message=f"ASR model not available: {model}",
            status_code=503,
            details={"model": model},
        )


# Job Errors
class JobError(TranscriberError):
    """Base exception for job-related errors."""

    pass


class JobNotFoundError(JobError):
    """Raised when a job is not found."""

    def __init__(self, job_id: str) -> None:
        super().__init__(
            code="JOB_NOT_FOUND",
            message=f"Job not found: {job_id}",
            status_code=404,
            details={"job_id": job_id},
        )


class JobExpiredError(JobError):
    """Raised when a job has expired."""

    def __init__(self, job_id: str) -> None:
        super().__init__(
            code="JOB_EXPIRED",
            message=f"Job has expired: {job_id}",
            status_code=410,
            details={"job_id": job_id},
        )


# Auth Errors
class AuthError(TranscriberError):
    """Base exception for authentication errors."""

    pass


class InvalidAPIKeyError(AuthError):
    """Raised when the API key is invalid."""

    def __init__(self) -> None:
        super().__init__(
            code="INVALID_API_KEY",
            message="Invalid or missing API key",
            status_code=401,
        )


class RateLimitExceededError(AuthError):
    """Raised when rate limit is exceeded."""

    def __init__(self, retry_after: int) -> None:
        super().__init__(
            code="RATE_LIMIT_EXCEEDED",
            message="Rate limit exceeded",
            status_code=429,
            details={"retry_after": retry_after},
        )
