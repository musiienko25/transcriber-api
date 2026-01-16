"""Job management service for async processing."""

import json
import uuid
from datetime import datetime
from typing import Any

import redis.asyncio as redis

from app.core.config import get_settings
from app.core.exceptions import JobNotFoundError, JobExpiredError
from app.core.logging import get_logger
from app.models.jobs import JobData, JobType
from app.models.responses import JobResponse, JobStatus

logger = get_logger(__name__)

# Global Redis client (lazy loaded)
_redis_client: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    """Get or create Redis client."""
    global _redis_client

    if _redis_client is None:
        settings = get_settings()
        _redis_client = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        logger.info("Redis client initialized", url=settings.redis_url)

    return _redis_client


class JobService:
    """Service for managing transcription jobs."""

    JOB_PREFIX = "job:"
    QUEUE_NAME = "transcription_queue"

    def __init__(self) -> None:
        self.settings = get_settings()

    def _job_key(self, job_id: str) -> str:
        """Get Redis key for a job."""
        return f"{self.JOB_PREFIX}{job_id}"

    async def create_job(
        self,
        job_type: JobType,
        input_url: str | None = None,
        input_params: dict[str, Any] | None = None,
        webhook_url: str | None = None,
        api_key: str | None = None,
    ) -> JobData:
        """
        Create a new transcription job.

        Args:
            job_type: Type of job (youtube, media_upload, media_url)
            input_url: Source URL or file reference
            input_params: Original request parameters
            webhook_url: Optional webhook for completion notification
            api_key: API key for tracking

        Returns:
            Created JobData instance
        """
        job_id = str(uuid.uuid4())

        job = JobData(
            job_id=job_id,
            job_type=job_type,
            input_url=input_url,
            input_params=input_params or {},
            webhook_url=webhook_url,
            api_key_hash=hash(api_key) if api_key else None,
        )

        # Store in Redis
        redis_client = await get_redis()
        await redis_client.setex(
            self._job_key(job_id),
            self.settings.redis_job_ttl,
            job.model_dump_json(),
        )

        # Add to queue
        await redis_client.lpush(
            self.QUEUE_NAME,
            json.dumps({"job_id": job_id, "created_at": datetime.utcnow().isoformat()}),
        )

        logger.info(
            "Job created",
            job_id=job_id,
            job_type=job_type.value,
            input_url=input_url,
        )

        return job

    async def get_job(self, job_id: str) -> JobData:
        """
        Get job by ID.

        Args:
            job_id: Job identifier

        Returns:
            JobData instance

        Raises:
            JobNotFoundError: If job doesn't exist
            JobExpiredError: If job has expired
        """
        redis_client = await get_redis()
        data = await redis_client.get(self._job_key(job_id))

        if data is None:
            # Check if key existed but expired
            exists = await redis_client.exists(self._job_key(job_id))
            if not exists:
                raise JobNotFoundError(job_id)
            raise JobExpiredError(job_id)

        return JobData.model_validate_json(data)

    async def update_job(self, job: JobData) -> None:
        """
        Update job in Redis.

        Args:
            job: JobData instance to update
        """
        job.updated_at = datetime.utcnow()

        redis_client = await get_redis()
        await redis_client.setex(
            self._job_key(job.job_id),
            self.settings.redis_job_ttl,
            job.model_dump_json(),
        )

        logger.debug("Job updated", job_id=job.job_id, status=job.status)

    async def complete_job(self, job_id: str, result: dict[str, Any]) -> JobData:
        """
        Mark job as completed with result.

        Args:
            job_id: Job identifier
            result: Transcription result

        Returns:
            Updated JobData
        """
        job = await self.get_job(job_id)
        job.mark_completed(result)
        await self.update_job(job)

        logger.info("Job completed", job_id=job_id)

        # Send webhook if configured
        if job.webhook_url and not job.webhook_sent:
            await self._send_webhook(job)

        return job

    async def fail_job(self, job_id: str, error: dict[str, Any]) -> JobData:
        """
        Mark job as failed with error.

        Args:
            job_id: Job identifier
            error: Error details

        Returns:
            Updated JobData
        """
        job = await self.get_job(job_id)
        job.mark_failed(error)
        await self.update_job(job)

        logger.error("Job failed", job_id=job_id, error=error)

        # Send webhook if configured
        if job.webhook_url and not job.webhook_sent:
            await self._send_webhook(job)

        return job

    async def update_progress(self, job_id: str, progress: float) -> None:
        """
        Update job progress.

        Args:
            job_id: Job identifier
            progress: Progress percentage (0-100)
        """
        job = await self.get_job(job_id)
        job.update_progress(progress)
        await self.update_job(job)

    async def _send_webhook(self, job: JobData) -> None:
        """Send webhook notification for job completion."""
        if not job.webhook_url:
            return

        import httpx

        try:
            payload = {
                "job_id": job.job_id,
                "status": job.status,
                "result": job.result,
                "error": job.error,
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    job.webhook_url,
                    json=payload,
                    timeout=30.0,
                )

                if response.status_code < 400:
                    job.webhook_sent = True
                    await self.update_job(job)
                    logger.info("Webhook sent", job_id=job.job_id, url=job.webhook_url)
                else:
                    logger.warning(
                        "Webhook failed",
                        job_id=job.job_id,
                        status=response.status_code,
                    )

        except Exception as e:
            logger.error("Webhook error", job_id=job.job_id, error=str(e))

    async def pop_job(self) -> dict[str, Any] | None:
        """
        Pop next job from queue for processing.

        Returns:
            Job info dict or None if queue is empty
        """
        redis_client = await get_redis()
        data = await redis_client.rpop(self.QUEUE_NAME)

        if data:
            return json.loads(data)
        return None

    async def get_queue_length(self) -> int:
        """Get number of jobs in queue."""
        redis_client = await get_redis()
        return await redis_client.llen(self.QUEUE_NAME)

    def to_response(self, job: JobData) -> JobResponse:
        """Convert JobData to API response."""
        from app.models.responses import TranscriptionResponse

        result = None
        if job.result:
            result = TranscriptionResponse(**job.result)

        return JobResponse(
            status=JobStatus(job.status),
            job_id=job.job_id,
            created_at=job.created_at,
            updated_at=job.updated_at,
            progress=job.progress,
            result=result,
            error=job.error,
        )


async def close_redis() -> None:
    """Close Redis connection."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
        logger.info("Redis connection closed")
