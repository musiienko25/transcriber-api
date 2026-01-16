"""Runpod serverless integration for GPU-accelerated transcription."""

import asyncio
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.exceptions import TranscriptionFailedError
from app.core.logging import get_logger

logger = get_logger(__name__)


class RunpodService:
    """Service for interacting with Runpod serverless endpoints."""

    BASE_URL = "https://api.runpod.ai/v2"

    def __init__(self) -> None:
        self.settings = get_settings()
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate Runpod configuration."""
        if not self.settings.runpod_api_key:
            logger.warning("Runpod API key not configured")
        if not self.settings.runpod_endpoint_id:
            logger.warning("Runpod endpoint ID not configured")

    @property
    def is_configured(self) -> bool:
        """Check if Runpod is properly configured."""
        return bool(
            self.settings.runpod_api_key and self.settings.runpod_endpoint_id
        )

    def _get_headers(self) -> dict[str, str]:
        """Get headers for Runpod API requests."""
        return {
            "Authorization": f"Bearer {self.settings.runpod_api_key}",
            "Content-Type": "application/json",
        }

    async def submit_job(
        self,
        audio_url: str,
        language: str | None = None,
        translate_to: str | None = None,
        diarise: bool = False,
    ) -> str:
        """
        Submit a transcription job to Runpod.

        Args:
            audio_url: URL to the audio file (must be accessible by Runpod)
            language: Source language hint
            translate_to: Target translation language
            diarise: Enable speaker diarisation

        Returns:
            Runpod job ID
        """
        if not self.is_configured:
            raise TranscriptionFailedError("Runpod not configured", "runpod")

        endpoint_url = f"{self.BASE_URL}/{self.settings.runpod_endpoint_id}/run"

        payload = {
            "input": {
                "audio_url": audio_url,
                "language": language,
                "translate_to": translate_to,
                "diarise": diarise,
                "model": self.settings.whisper_model,
            }
        }

        logger.info("Submitting job to Runpod", audio_url=audio_url)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                endpoint_url,
                headers=self._get_headers(),
                json=payload,
                timeout=30.0,
            )

            if response.status_code != 200:
                logger.error(
                    "Runpod submission failed",
                    status=response.status_code,
                    response=response.text,
                )
                raise TranscriptionFailedError(
                    f"Runpod API error: {response.status_code}", "runpod"
                )

            data = response.json()
            job_id = data.get("id")

            logger.info("Runpod job submitted", runpod_job_id=job_id)
            return job_id

    async def get_job_status(self, runpod_job_id: str) -> dict[str, Any]:
        """
        Get the status of a Runpod job.

        Args:
            runpod_job_id: Runpod job ID

        Returns:
            Job status dict with 'status' and optionally 'output' or 'error'
        """
        if not self.is_configured:
            raise TranscriptionFailedError("Runpod not configured", "runpod")

        status_url = f"{self.BASE_URL}/{self.settings.runpod_endpoint_id}/status/{runpod_job_id}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                status_url,
                headers=self._get_headers(),
                timeout=30.0,
            )

            if response.status_code != 200:
                logger.error(
                    "Runpod status check failed",
                    status=response.status_code,
                    runpod_job_id=runpod_job_id,
                )
                raise TranscriptionFailedError(
                    f"Runpod API error: {response.status_code}", "runpod"
                )

            return response.json()

    async def wait_for_completion(
        self,
        runpod_job_id: str,
        timeout: int = 600,
        poll_interval: int = 5,
    ) -> dict[str, Any]:
        """
        Wait for a Runpod job to complete.

        Args:
            runpod_job_id: Runpod job ID
            timeout: Maximum time to wait in seconds
            poll_interval: Time between status checks

        Returns:
            Job output on success

        Raises:
            TranscriptionFailedError: If job fails or times out
        """
        elapsed = 0

        while elapsed < timeout:
            status = await self.get_job_status(runpod_job_id)

            job_status = status.get("status")

            if job_status == "COMPLETED":
                logger.info("Runpod job completed", runpod_job_id=runpod_job_id)
                return status.get("output", {})

            elif job_status == "FAILED":
                error = status.get("error", "Unknown error")
                logger.error(
                    "Runpod job failed",
                    runpod_job_id=runpod_job_id,
                    error=error,
                )
                raise TranscriptionFailedError(f"Runpod job failed: {error}", "runpod")

            elif job_status in ("IN_QUEUE", "IN_PROGRESS"):
                logger.debug(
                    "Runpod job in progress",
                    runpod_job_id=runpod_job_id,
                    status=job_status,
                )
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

            else:
                logger.warning(
                    "Unknown Runpod job status",
                    runpod_job_id=runpod_job_id,
                    status=job_status,
                )
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

        raise TranscriptionFailedError(
            f"Runpod job timed out after {timeout}s", "runpod"
        )

    async def cancel_job(self, runpod_job_id: str) -> bool:
        """
        Cancel a Runpod job.

        Args:
            runpod_job_id: Runpod job ID

        Returns:
            True if cancelled successfully
        """
        if not self.is_configured:
            return False

        cancel_url = f"{self.BASE_URL}/{self.settings.runpod_endpoint_id}/cancel/{runpod_job_id}"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    cancel_url,
                    headers=self._get_headers(),
                    timeout=30.0,
                )

                if response.status_code == 200:
                    logger.info("Runpod job cancelled", runpod_job_id=runpod_job_id)
                    return True
                else:
                    logger.warning(
                        "Failed to cancel Runpod job",
                        runpod_job_id=runpod_job_id,
                        status=response.status_code,
                    )
                    return False

        except Exception as e:
            logger.error("Error cancelling Runpod job", error=str(e))
            return False


# Global instance (lazy)
_runpod_service: RunpodService | None = None


def get_runpod_service() -> RunpodService:
    """Get or create Runpod service instance."""
    global _runpod_service
    if _runpod_service is None:
        _runpod_service = RunpodService()
    return _runpod_service
