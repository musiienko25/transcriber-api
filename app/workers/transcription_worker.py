"""Transcription worker for processing jobs from the queue."""

import asyncio
import signal
import sys
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import setup_logging, get_logger
from app.models.jobs import JobType
from app.services.asr import ASRService
from app.services.formatters import FormatConverter
from app.services.jobs import JobService, get_redis, close_redis
from app.services.media import MediaService
from app.services.youtube import YouTubeService

# Setup logging
setup_logging()
logger = get_logger(__name__)


class TranscriptionWorker:
    """Worker that processes transcription jobs from Redis queue."""

    def __init__(self, worker_id: str = "worker-1") -> None:
        self.worker_id = worker_id
        self.settings = get_settings()
        self.job_service = JobService()
        self.asr_service = ASRService()
        self.media_service = MediaService()
        self.running = True

    async def start(self) -> None:
        """Start the worker loop."""
        logger.info("Worker starting", worker_id=self.worker_id)

        # Setup signal handlers
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self._handle_shutdown)

        # Main loop
        while self.running:
            try:
                await self._process_next_job()
            except Exception as e:
                logger.exception("Worker error", error=str(e))
                await asyncio.sleep(5)  # Back off on error

        logger.info("Worker stopped", worker_id=self.worker_id)

    def _handle_shutdown(self, signum, frame) -> None:
        """Handle shutdown signals gracefully."""
        logger.info("Shutdown signal received", signal=signum)
        self.running = False

    async def _process_next_job(self) -> None:
        """Pop and process the next job from the queue."""
        job_info = await self.job_service.pop_job()

        if job_info is None:
            # No jobs, wait and retry
            await asyncio.sleep(1)
            return

        job_id = job_info["job_id"]
        logger.info("Processing job", job_id=job_id, worker_id=self.worker_id)

        try:
            # Get full job data
            job = await self.job_service.get_job(job_id)

            # Mark as processing
            job.mark_processing(self.worker_id)
            await self.job_service.update_job(job)

            # Process based on job type
            if job.job_type == JobType.YOUTUBE:
                result = await self._process_youtube_job(job)
            elif job.job_type in (JobType.MEDIA_UPLOAD, JobType.MEDIA_URL):
                result = await self._process_media_job(job)
            else:
                raise ValueError(f"Unknown job type: {job.job_type}")

            # Complete job
            await self.job_service.complete_job(job_id, result)
            logger.info("Job completed", job_id=job_id)

        except Exception as e:
            logger.exception("Job failed", job_id=job_id, error=str(e))
            await self.job_service.fail_job(
                job_id,
                {"code": "PROCESSING_ERROR", "message": str(e)},
            )

    async def _process_youtube_job(self, job) -> dict:
        """Process a YouTube transcription job."""
        params = job.input_params
        video_id = YouTubeService.extract_video_id(job.input_url)

        # Download audio
        audio_path = await self.media_service.download_youtube_audio(video_id)

        try:
            # Update progress
            await self.job_service.update_progress(job.job_id, 30.0)

            # Transcribe
            segments, language, confidence, duration, warnings = (
                await self.asr_service.transcribe(
                    audio_path,
                    language=params.get("language"),
                    translate_to=params.get("translate_to"),
                    diarise=params.get("diarise", False),
                )
            )

            # Update progress
            await self.job_service.update_progress(job.job_id, 90.0)

            # Build result
            transcript = FormatConverter.to_text(segments)

            return {
                "source": self.asr_service.get_source().value,
                "language": language,
                "confidence": confidence,
                "duration": duration,
                "transcript": transcript,
                "segments": [seg.model_dump() for seg in segments],
                "warnings": warnings,
                "metadata": {"video_id": video_id},
            }

        finally:
            self.media_service.cleanup(audio_path)

    async def _process_media_job(self, job) -> dict:
        """Process a media file transcription job."""
        params = job.input_params

        # Get media path (already downloaded for uploads, download for URLs)
        if job.media_path:
            audio_path = Path(job.media_path)
        elif job.input_url:
            if self.media_service.is_social_media_url(job.input_url):
                audio_path = await self.media_service.download_social_media(job.input_url)
            else:
                audio_path = await self.media_service.download_url(job.input_url)
        else:
            raise ValueError("No media source specified")

        try:
            # Update progress
            await self.job_service.update_progress(job.job_id, 30.0)

            # Transcribe
            segments, language, confidence, duration, warnings = (
                await self.asr_service.transcribe(
                    audio_path,
                    language=params.get("language"),
                    translate_to=params.get("translate_to"),
                    diarise=params.get("diarise", False),
                )
            )

            # Update progress
            await self.job_service.update_progress(job.job_id, 90.0)

            # Build result
            transcript = FormatConverter.to_text(segments)

            return {
                "source": self.asr_service.get_source().value,
                "language": language,
                "confidence": confidence,
                "duration": duration,
                "transcript": transcript,
                "segments": [seg.model_dump() for seg in segments],
                "warnings": warnings,
            }

        finally:
            self.media_service.cleanup(audio_path)


async def main() -> None:
    """Main entry point for the worker."""
    import os

    worker_id = os.environ.get("WORKER_ID", "worker-1")
    worker = TranscriptionWorker(worker_id)

    try:
        await worker.start()
    finally:
        await close_redis()


if __name__ == "__main__":
    asyncio.run(main())
