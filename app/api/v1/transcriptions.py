"""Transcription endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, BackgroundTasks
from fastapi.responses import PlainTextResponse

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    TranscriberError,
    CaptionsDisabledError,
    TranscriptNotFoundError,
)
from app.core.logging import get_logger
from app.core.security import verify_api_key
from app.models.jobs import JobType
from app.models.requests import YouTubeTranscriptionRequest, MediaTranscriptionRequest
from app.models.responses import (
    ErrorResponse,
    JobResponse,
    TranscriptionResponse,
    TranscriptionSegment,
    TranscriptionSource,
)
from app.services.asr import ASRService
from app.services.formatters import FormatConverter
from app.services.jobs import JobService
from app.services.media import MediaService
from app.services.youtube import YouTubeService

router = APIRouter()
logger = get_logger(__name__)

# Service instances
youtube_service = YouTubeService()
asr_service = ASRService()
media_service = MediaService()
job_service = JobService()


async def process_youtube_asr(
    video_id: str,
    request: YouTubeTranscriptionRequest,
    settings: Settings,
) -> TranscriptionResponse:
    """Process YouTube video through ASR pipeline."""
    warnings = []

    # Download audio
    audio_path = await media_service.download_youtube_audio(video_id)

    try:
        # Get duration to decide sync vs async
        duration = await asr_service.get_audio_duration(audio_path)

        # Transcribe
        if settings.asr_provider == "openai" and settings.openai_api_key:
            segments, language, confidence, duration, asr_warnings = (
                await asr_service.transcribe_with_openai(
                    audio_path,
                    language=request.language,
                )
            )
        else:
            segments, language, confidence, duration, asr_warnings = (
                await asr_service.transcribe(
                    audio_path,
                    language=request.language,
                    translate_to=request.translate_to,
                    diarise=request.diarise,
                )
            )

        warnings.extend(asr_warnings)

        # Build response
        transcript = FormatConverter.to_text(segments)

        return TranscriptionResponse(
            source=asr_service.get_source(),
            language=language,
            confidence=confidence,
            duration=duration,
            transcript=transcript,
            segments=segments,
            warnings=warnings,
            metadata={"video_id": video_id},
        )

    finally:
        # Cleanup
        media_service.cleanup(audio_path)


@router.post(
    "/youtube",
    response_model=TranscriptionResponse | JobResponse,
    responses={
        200: {"description": "Transcription completed"},
        202: {"description": "Job queued for async processing", "model": JobResponse},
        400: {"description": "Invalid request", "model": ErrorResponse},
        404: {"description": "Video not found", "model": ErrorResponse},
        500: {"description": "Server error", "model": ErrorResponse},
    },
    summary="Transcribe YouTube video",
    description="""
    Transcribe a YouTube video using one of two paths:

    **Path A - Captions Fast-Path (preferred):**
    - Fetches existing captions from YouTube (no GPU required)
    - Returns segments with timestamps
    - Supports translation if the captions provider supports it

    **Path B - ASR Fallback:**
    - Triggered when captions are unavailable or diarisation is requested
    - Downloads audio and transcribes using Whisper
    - For videos >10 minutes, returns job ID for async processing
    """,
)
async def transcribe_youtube(
    request: YouTubeTranscriptionRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key),
    settings: Settings = Depends(get_settings),
) -> TranscriptionResponse | JobResponse:
    """
    Transcribe a YouTube video.

    Two-path strategy:
    1. Try to fetch existing captions (fast, no GPU)
    2. Fall back to ASR if captions unavailable or diarisation requested
    """
    try:
        # Extract video ID
        video_id = YouTubeService.extract_video_id(request.url)
        logger.info("Processing YouTube request", video_id=video_id, url=request.url)

        # Determine if we need ASR mode
        needs_asr = request.force_asr or request.diarise

        if not needs_asr:
            # Path A: Try captions first
            try:
                segments, language, warnings = YouTubeService.fetch_captions(
                    video_id,
                    language=request.language,
                    translate_to=request.translate_to,
                )

                # Build full transcript
                transcript = FormatConverter.to_text(segments)
                duration = YouTubeService.get_video_duration(segments)

                logger.info(
                    "Captions fetched successfully",
                    video_id=video_id,
                    segments=len(segments),
                    language=language,
                )

                response = TranscriptionResponse(
                    source=TranscriptionSource.YOUTUBE_CAPTIONS,
                    language=language,
                    duration=duration,
                    transcript=transcript,
                    segments=segments,
                    warnings=warnings,
                    metadata={"video_id": video_id},
                )

                # Handle output format
                if request.format != "json":
                    formatted = FormatConverter.convert(segments, request.format)
                    if isinstance(formatted, str):
                        return PlainTextResponse(
                            content=formatted,
                            media_type="text/plain",
                        )

                return response

            except (CaptionsDisabledError, TranscriptNotFoundError) as e:
                # Captions not available, fall back to ASR
                logger.info(
                    "Captions unavailable, falling back to ASR",
                    video_id=video_id,
                    reason=str(e),
                )
                needs_asr = True

        # Path B: ASR mode
        if needs_asr:
            # Check video duration for sync/async decision
            # For now, we'll process synchronously for simplicity
            # In production, you'd queue long videos

            response = await process_youtube_asr(video_id, request, settings)

            # Handle output format
            if request.format != "json":
                formatted = FormatConverter.convert(response.segments, request.format)
                if isinstance(formatted, str):
                    return PlainTextResponse(
                        content=formatted,
                        media_type="text/plain",
                    )

            return response

    except TranscriberError as e:
        logger.error("Transcription error", error=e.code, message=e.message)
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())

    except Exception as e:
        logger.exception("Unexpected error", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "details": {"error": str(e)},
            },
        )


@router.post(
    "/media",
    response_model=TranscriptionResponse | JobResponse,
    responses={
        200: {"description": "Transcription completed"},
        202: {"description": "Job queued for async processing", "model": JobResponse},
        400: {"description": "Invalid request", "model": ErrorResponse},
        413: {"description": "File too large", "model": ErrorResponse},
        415: {"description": "Unsupported media type", "model": ErrorResponse},
        500: {"description": "Server error", "model": ErrorResponse},
    },
    summary="Transcribe media file or URL",
    description="""
    Transcribe an audio or video file from:
    - File upload (multipart form data)
    - Remote URL (HTTP/S or S3 signed URL)
    - Social media URL (TikTok, Twitter, Instagram, etc.)

    Supported formats: MP3, WAV, M4A, MP4, MKV, WebM, etc.
    """,
)
async def transcribe_media(
    background_tasks: BackgroundTasks,
    file: UploadFile | None = File(default=None, description="Audio/video file to transcribe"),
    url: str | None = Form(default=None, description="URL to media file"),
    translate_to: str | None = Form(default=None, alias="translateTo"),
    diarise: bool = Form(default=False),
    format: str = Form(default="json"),
    language: str | None = Form(default=None),
    webhook_url: str | None = Form(default=None, alias="webhookUrl"),
    api_key: str = Depends(verify_api_key),
    settings: Settings = Depends(get_settings),
) -> TranscriptionResponse | JobResponse:
    """
    Transcribe a media file or URL.

    Accepts either:
    - A file upload (multipart/form-data)
    - A remote URL to a media file
    - A social media URL (uses yt-dlp for extraction)
    """
    if not file and not url:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "MISSING_INPUT",
                "message": "Either file or url must be provided",
            },
        )

    try:
        audio_path = None
        warnings = []
        job_type = JobType.MEDIA_URL

        # Handle file upload
        if file:
            job_type = JobType.MEDIA_UPLOAD
            logger.info("Processing file upload", filename=file.filename)

            # Save uploaded file
            audio_path = await media_service.save_upload(file.file, file.filename or "upload.mp3")

        # Handle URL
        elif url:
            logger.info("Processing media URL", url=url)

            # Check if it's a social media URL (use yt-dlp)
            if media_service.is_social_media_url(url):
                logger.info("Detected social media URL, using yt-dlp")
                audio_path = await media_service.download_social_media(url)
                warnings.append("Downloaded from social media using yt-dlp")
            elif media_service.is_youtube_url(url):
                # Redirect to YouTube endpoint
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "USE_YOUTUBE_ENDPOINT",
                        "message": "For YouTube URLs, use /v1/transcriptions/youtube",
                    },
                )
            else:
                # Direct media URL
                audio_path = await media_service.download_url(url)

        if not audio_path:
            raise HTTPException(
                status_code=500,
                detail={"code": "PROCESSING_ERROR", "message": "Failed to process media"},
            )

        try:
            # Get duration to decide sync vs async
            duration = await asr_service.get_audio_duration(audio_path)

            # For long files, queue for async processing
            if duration > settings.asr_sync_max_duration:
                logger.info(
                    "Queueing long media for async processing",
                    duration=duration,
                    threshold=settings.asr_sync_max_duration,
                )

                # Create async job
                job = await job_service.create_job(
                    job_type=job_type,
                    input_url=url,
                    input_params={
                        "translate_to": translate_to,
                        "diarise": diarise,
                        "format": format,
                        "language": language,
                    },
                    webhook_url=webhook_url,
                    api_key=api_key,
                )

                # Note: In production, a background worker would process this
                # For now, we'll process it inline
                background_tasks.add_task(
                    process_async_job,
                    job.job_id,
                    audio_path,
                    language,
                    translate_to,
                    diarise,
                )

                return job_service.to_response(job)

            # Transcribe synchronously
            if settings.asr_provider == "openai" and settings.openai_api_key:
                segments, detected_lang, confidence, duration, asr_warnings = (
                    await asr_service.transcribe_with_openai(audio_path, language=language)
                )
            else:
                segments, detected_lang, confidence, duration, asr_warnings = (
                    await asr_service.transcribe(
                        audio_path,
                        language=language,
                        translate_to=translate_to,
                        diarise=diarise,
                    )
                )

            warnings.extend(asr_warnings)

            # Build response
            transcript = FormatConverter.to_text(segments)

            response = TranscriptionResponse(
                source=asr_service.get_source(),
                language=detected_lang,
                confidence=confidence,
                duration=duration,
                transcript=transcript,
                segments=segments,
                warnings=warnings,
            )

            # Handle output format
            if format != "json":
                formatted = FormatConverter.convert(segments, format)
                if isinstance(formatted, str):
                    return PlainTextResponse(
                        content=formatted,
                        media_type="text/plain",
                    )

            return response

        finally:
            # Cleanup temp file (unless async processing)
            if audio_path and duration <= settings.asr_sync_max_duration:
                media_service.cleanup(audio_path)

    except TranscriberError as e:
        logger.error("Transcription error", error=e.code, message=e.message)
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())

    except HTTPException:
        raise

    except Exception as e:
        logger.exception("Unexpected error", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "details": {"error": str(e)},
            },
        )


async def process_async_job(
    job_id: str,
    audio_path: Any,
    language: str | None,
    translate_to: str | None,
    diarise: bool,
) -> None:
    """Background task to process async transcription job."""
    try:
        settings = get_settings()

        # Update job status
        job = await job_service.get_job(job_id)
        job.mark_processing("local-worker")
        await job_service.update_job(job)

        # Transcribe
        if settings.asr_provider == "openai" and settings.openai_api_key:
            segments, detected_lang, confidence, duration, warnings = (
                await asr_service.transcribe_with_openai(audio_path, language=language)
            )
        else:
            segments, detected_lang, confidence, duration, warnings = (
                await asr_service.transcribe(
                    audio_path,
                    language=language,
                    translate_to=translate_to,
                    diarise=diarise,
                )
            )

        # Build result
        transcript = FormatConverter.to_text(segments)
        result = {
            "source": asr_service.get_source().value,
            "language": detected_lang,
            "confidence": confidence,
            "duration": duration,
            "transcript": transcript,
            "segments": [seg.model_dump() for seg in segments],
            "warnings": warnings,
        }

        # Complete job
        await job_service.complete_job(job_id, result)

    except Exception as e:
        logger.exception("Async job failed", job_id=job_id, error=str(e))
        await job_service.fail_job(
            job_id,
            {"code": "TRANSCRIPTION_FAILED", "message": str(e)},
        )

    finally:
        # Cleanup
        media_service.cleanup(audio_path)
