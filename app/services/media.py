"""Media service for downloading and processing media files."""

import asyncio
import os
import tempfile
import uuid
from pathlib import Path
from typing import BinaryIO

import aiofiles
import aiohttp
import yt_dlp

from app.core.config import get_settings
from app.core.exceptions import MediaDownloadError, UnsupportedMediaTypeError, FileTooLargeError
from app.core.logging import get_logger

logger = get_logger(__name__)


class MediaService:
    """Service for media file operations."""

    # Supported MIME types
    AUDIO_MIME_TYPES = {
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/wave": ".wav",
        "audio/m4a": ".m4a",
        "audio/x-m4a": ".m4a",
        "audio/mp4": ".m4a",
        "audio/flac": ".flac",
        "audio/x-flac": ".flac",
        "audio/ogg": ".ogg",
        "audio/aac": ".aac",
        "audio/webm": ".webm",
    }

    VIDEO_MIME_TYPES = {
        "video/mp4": ".mp4",
        "video/x-matroska": ".mkv",
        "video/webm": ".webm",
        "video/x-msvideo": ".avi",
        "video/quicktime": ".mov",
        "video/x-ms-wmv": ".wmv",
    }

    ALL_MIME_TYPES = {**AUDIO_MIME_TYPES, **VIDEO_MIME_TYPES}

    def __init__(self) -> None:
        self.settings = get_settings()
        self.temp_dir = Path(self.settings.temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def get_temp_path(self, extension: str = ".mp3") -> Path:
        """Generate a unique temporary file path."""
        filename = f"{uuid.uuid4()}{extension}"
        return self.temp_dir / filename

    def validate_content_type(self, content_type: str | None) -> str:
        """
        Validate content type and return file extension.

        Args:
            content_type: MIME type of the file

        Returns:
            File extension including dot (e.g., ".mp3")

        Raises:
            UnsupportedMediaTypeError: If content type is not supported
        """
        if not content_type:
            # Default to mp3 if unknown
            return ".mp3"

        # Clean up content type (remove charset etc.)
        content_type = content_type.split(";")[0].strip().lower()

        if content_type in self.ALL_MIME_TYPES:
            return self.ALL_MIME_TYPES[content_type]

        # Check by extension in content type
        if "audio" in content_type or "video" in content_type:
            return ".mp3"  # Default for unknown audio/video

        raise UnsupportedMediaTypeError(
            content_type, list(self.ALL_MIME_TYPES.keys())
        )

    def validate_file_size(self, size_bytes: int) -> None:
        """
        Validate file size is within limits.

        Raises:
            FileTooLargeError: If file is too large
        """
        max_size_bytes = self.settings.max_upload_size_mb * 1024 * 1024
        if size_bytes > max_size_bytes:
            raise FileTooLargeError(
                size_mb=size_bytes / (1024 * 1024),
                max_size_mb=self.settings.max_upload_size_mb,
            )

    def get_extension_from_filename(self, filename: str) -> str:
        """Extract and validate extension from filename."""
        ext = Path(filename).suffix.lower()
        allowed = self.settings.get_allowed_extensions()
        if ext in allowed:
            return ext
        return ".mp3"  # Default

    async def save_upload(self, file: BinaryIO, filename: str) -> Path:
        """
        Save uploaded file to temporary storage.

        Args:
            file: File-like object
            filename: Original filename

        Returns:
            Path to saved file
        """
        ext = self.get_extension_from_filename(filename)
        temp_path = self.get_temp_path(ext)

        async with aiofiles.open(temp_path, "wb") as f:
            # Read and write in chunks
            chunk_size = 1024 * 1024  # 1MB chunks
            total_size = 0

            while True:
                chunk = file.read(chunk_size)
                if not chunk:
                    break

                total_size += len(chunk)
                self.validate_file_size(total_size)

                await f.write(chunk)

        logger.info(
            "Saved upload",
            path=str(temp_path),
            size_mb=total_size / (1024 * 1024),
        )

        return temp_path

    async def download_url(self, url: str) -> Path:
        """
        Download media from URL.

        Args:
            url: HTTP/S URL to media file

        Returns:
            Path to downloaded file

        Raises:
            MediaDownloadError: If download fails
        """
        logger.info("Downloading media", url=url)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=300)) as response:
                    if response.status != 200:
                        raise MediaDownloadError(
                            url, f"HTTP {response.status}: {response.reason}"
                        )

                    # Check content type
                    content_type = response.headers.get("Content-Type")
                    ext = self.validate_content_type(content_type)

                    # Check content length if available
                    content_length = response.headers.get("Content-Length")
                    if content_length:
                        self.validate_file_size(int(content_length))

                    temp_path = self.get_temp_path(ext)

                    # Stream download
                    total_size = 0
                    async with aiofiles.open(temp_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(1024 * 1024):
                            total_size += len(chunk)
                            self.validate_file_size(total_size)
                            await f.write(chunk)

                    logger.info(
                        "Downloaded media",
                        url=url,
                        path=str(temp_path),
                        size_mb=total_size / (1024 * 1024),
                    )

                    return temp_path

        except (MediaDownloadError, FileTooLargeError):
            raise
        except asyncio.TimeoutError:
            raise MediaDownloadError(url, "Download timed out")
        except Exception as e:
            logger.error("Download failed", url=url, error=str(e))
            raise MediaDownloadError(url, str(e))

    async def download_youtube_audio(self, video_id: str) -> Path:
        """
        Download audio from YouTube video using yt-dlp.

        Args:
            video_id: YouTube video ID

        Returns:
            Path to downloaded audio file
        """
        logger.info("Downloading YouTube audio", video_id=video_id)

        temp_path = self.get_temp_path(".mp3")
        output_template = str(temp_path.with_suffix(""))  # yt-dlp adds extension

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
        }

        url = f"https://www.youtube.com/watch?v={video_id}"

        try:
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, lambda: self._download_with_ytdlp(url, ydl_opts)
            )

            # Find the output file (yt-dlp might add extension)
            if temp_path.exists():
                return temp_path

            # Try with .mp3 extension
            mp3_path = temp_path.with_suffix(".mp3")
            if mp3_path.exists():
                return mp3_path

            # Look for any file with the base name
            for ext in [".mp3", ".m4a", ".webm", ".opus"]:
                check_path = temp_path.with_suffix(ext)
                if check_path.exists():
                    return check_path

            raise MediaDownloadError(url, "Downloaded file not found")

        except Exception as e:
            logger.error("YouTube download failed", video_id=video_id, error=str(e))
            raise MediaDownloadError(url, str(e))

    def _download_with_ytdlp(self, url: str, opts: dict) -> None:
        """Synchronous yt-dlp download."""
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

    async def download_social_media(self, url: str) -> Path:
        """
        Download media from social media URLs using yt-dlp.
        Supports: TikTok, Twitter/X, Instagram, Facebook, etc.

        Args:
            url: Social media URL

        Returns:
            Path to downloaded audio file
        """
        logger.info("Downloading social media", url=url)

        temp_path = self.get_temp_path(".mp3")
        output_template = str(temp_path.with_suffix(""))

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
            "quiet": True,
            "no_warnings": True,
        }

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, lambda: self._download_with_ytdlp(url, ydl_opts)
            )

            # Find the output file
            for ext in [".mp3", ".m4a", ".webm", ".opus", ""]:
                check_path = temp_path.with_suffix(ext) if ext else temp_path
                if check_path.exists():
                    return check_path

            raise MediaDownloadError(url, "Downloaded file not found")

        except Exception as e:
            logger.error("Social media download failed", url=url, error=str(e))
            raise MediaDownloadError(url, str(e))

    def cleanup(self, path: Path) -> None:
        """Remove temporary file."""
        try:
            if path.exists():
                path.unlink()
                logger.debug("Cleaned up file", path=str(path))
        except Exception as e:
            logger.warning("Cleanup failed", path=str(path), error=str(e))

    def is_social_media_url(self, url: str) -> bool:
        """Check if URL is from a supported social media platform."""
        social_domains = [
            "tiktok.com",
            "twitter.com",
            "x.com",
            "instagram.com",
            "facebook.com",
            "fb.watch",
            "vimeo.com",
            "dailymotion.com",
            "twitch.tv",
            "reddit.com",
        ]
        url_lower = url.lower()
        return any(domain in url_lower for domain in social_domains)

    def is_youtube_url(self, url: str) -> bool:
        """Check if URL is a YouTube URL."""
        youtube_domains = [
            "youtube.com",
            "youtu.be",
            "music.youtube.com",
        ]
        url_lower = url.lower()
        return any(domain in url_lower for domain in youtube_domains)
