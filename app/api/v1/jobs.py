"""Job management endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from app.core.exceptions import JobNotFoundError, JobExpiredError
from app.core.logging import get_logger
from app.core.security import verify_api_key
from app.models.responses import ErrorResponse, JobResponse
from app.services.jobs import JobService

router = APIRouter()
logger = get_logger(__name__)

job_service = JobService()


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    responses={
        200: {"description": "Job status retrieved"},
        404: {"description": "Job not found", "model": ErrorResponse},
        410: {"description": "Job expired", "model": ErrorResponse},
    },
    summary="Get job status",
    description="""
    Get the status of an async transcription job.

    Poll this endpoint to check job progress and retrieve results.

    Job statuses:
    - `queued`: Job is waiting to be processed
    - `processing`: Job is currently being transcribed
    - `completed`: Job finished successfully (result included)
    - `failed`: Job failed (error details included)
    """,
)
async def get_job_status(
    job_id: str,
    api_key: str = Depends(verify_api_key),
) -> JobResponse:
    """
    Get the status of a transcription job.

    Args:
        job_id: Unique job identifier

    Returns:
        Job status with result if completed
    """
    try:
        job = await job_service.get_job(job_id)
        return job_service.to_response(job)

    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.to_dict())

    except JobExpiredError as e:
        raise HTTPException(status_code=410, detail=e.to_dict())

    except Exception as e:
        logger.exception("Error getting job status", job_id=job_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "code": "INTERNAL_ERROR",
                "message": "Failed to get job status",
            },
        )


@router.delete(
    "/{job_id}",
    status_code=204,
    responses={
        204: {"description": "Job cancelled"},
        404: {"description": "Job not found", "model": ErrorResponse},
    },
    summary="Cancel job",
    description="Cancel a pending or processing job.",
)
async def cancel_job(
    job_id: str,
    api_key: str = Depends(verify_api_key),
) -> None:
    """
    Cancel a transcription job.

    Only pending jobs can be cancelled.
    """
    try:
        job = await job_service.get_job(job_id)

        if job.status in ["completed", "failed"]:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "JOB_ALREADY_FINISHED",
                    "message": f"Job is already {job.status}",
                },
            )

        # Mark as failed/cancelled
        await job_service.fail_job(
            job_id,
            {"code": "JOB_CANCELLED", "message": "Job was cancelled by user"},
        )

    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.to_dict())

    except HTTPException:
        raise

    except Exception as e:
        logger.exception("Error cancelling job", job_id=job_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "code": "INTERNAL_ERROR",
                "message": "Failed to cancel job",
            },
        )
