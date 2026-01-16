"""Tests for job management API endpoints."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient

from app.models.jobs import JobData, JobType


class TestJobStatusEndpoint:
    """Tests for GET /v1/jobs/{job_id}."""

    def test_get_job_success(
        self, client: TestClient, mock_redis: MagicMock
    ) -> None:
        """Test successful job status retrieval."""
        with patch("app.api.v1.jobs.job_service") as mock_service:
            mock_job = JobData(
                job_id="test-job-123",
                job_type=JobType.YOUTUBE,
                status="completed",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                result={
                    "source": "asr_local",
                    "language": "en",
                    "transcript": "Hello world",
                    "segments": [],
                },
            )
            mock_service.get_job = AsyncMock(return_value=mock_job)
            mock_service.to_response.return_value = MagicMock(
                status="completed",
                job_id="test-job-123",
                model_dump=lambda: {
                    "status": "completed",
                    "jobId": "test-job-123",
                    "createdAt": mock_job.created_at.isoformat(),
                    "updatedAt": mock_job.updated_at.isoformat(),
                    "result": mock_job.result,
                }
            )

            response = client.get("/v1/jobs/test-job-123")

        assert response.status_code == 200

    def test_get_job_not_found(
        self, client: TestClient, mock_redis: MagicMock
    ) -> None:
        """Test job not found error."""
        from app.core.exceptions import JobNotFoundError

        with patch("app.api.v1.jobs.job_service") as mock_service:
            mock_service.get_job = AsyncMock(
                side_effect=JobNotFoundError("nonexistent-job")
            )

            response = client.get("/v1/jobs/nonexistent-job")

        assert response.status_code == 404
        data = response.json()
        assert data["code"] == "JOB_NOT_FOUND"

    def test_get_job_expired(
        self, client: TestClient, mock_redis: MagicMock
    ) -> None:
        """Test job expired error."""
        from app.core.exceptions import JobExpiredError

        with patch("app.api.v1.jobs.job_service") as mock_service:
            mock_service.get_job = AsyncMock(
                side_effect=JobExpiredError("expired-job")
            )

            response = client.get("/v1/jobs/expired-job")

        assert response.status_code == 410
        data = response.json()
        assert data["code"] == "JOB_EXPIRED"


class TestJobCancelEndpoint:
    """Tests for DELETE /v1/jobs/{job_id}."""

    def test_cancel_pending_job(
        self, client: TestClient, mock_redis: MagicMock
    ) -> None:
        """Test cancelling a pending job."""
        with patch("app.api.v1.jobs.job_service") as mock_service:
            mock_job = JobData(
                job_id="pending-job",
                job_type=JobType.MEDIA_URL,
                status="queued",
            )
            mock_service.get_job = AsyncMock(return_value=mock_job)
            mock_service.fail_job = AsyncMock(return_value=mock_job)

            response = client.delete("/v1/jobs/pending-job")

        assert response.status_code == 204

    def test_cancel_completed_job_fails(
        self, client: TestClient, mock_redis: MagicMock
    ) -> None:
        """Test that cancelling a completed job fails."""
        with patch("app.api.v1.jobs.job_service") as mock_service:
            mock_job = JobData(
                job_id="completed-job",
                job_type=JobType.YOUTUBE,
                status="completed",
            )
            mock_service.get_job = AsyncMock(return_value=mock_job)

            response = client.delete("/v1/jobs/completed-job")

        assert response.status_code == 400
        data = response.json()
        assert data["code"] == "JOB_ALREADY_FINISHED"


class TestJobStatusTransitions:
    """Tests for job status transitions."""

    def test_job_status_queued(
        self, client: TestClient, mock_redis: MagicMock
    ) -> None:
        """Test queued job status."""
        with patch("app.api.v1.jobs.job_service") as mock_service:
            mock_job = JobData(
                job_id="queued-job",
                job_type=JobType.MEDIA_UPLOAD,
                status="queued",
                progress=0.0,
            )
            mock_service.get_job = AsyncMock(return_value=mock_job)
            mock_service.to_response.return_value = MagicMock(
                model_dump=lambda: {
                    "status": "queued",
                    "jobId": "queued-job",
                    "progress": 0.0,
                }
            )

            response = client.get("/v1/jobs/queued-job")

        assert response.status_code == 200

    def test_job_status_processing(
        self, client: TestClient, mock_redis: MagicMock
    ) -> None:
        """Test processing job status with progress."""
        with patch("app.api.v1.jobs.job_service") as mock_service:
            mock_job = JobData(
                job_id="processing-job",
                job_type=JobType.MEDIA_URL,
                status="processing",
                progress=45.5,
                worker_id="worker-1",
            )
            mock_service.get_job = AsyncMock(return_value=mock_job)
            mock_service.to_response.return_value = MagicMock(
                model_dump=lambda: {
                    "status": "processing",
                    "jobId": "processing-job",
                    "progress": 45.5,
                }
            )

            response = client.get("/v1/jobs/processing-job")

        assert response.status_code == 200

    def test_job_status_failed(
        self, client: TestClient, mock_redis: MagicMock
    ) -> None:
        """Test failed job status with error details."""
        with patch("app.api.v1.jobs.job_service") as mock_service:
            mock_job = JobData(
                job_id="failed-job",
                job_type=JobType.YOUTUBE,
                status="failed",
                error={
                    "code": "TRANSCRIPTION_FAILED",
                    "message": "Audio processing error",
                },
            )
            mock_service.get_job = AsyncMock(return_value=mock_job)
            mock_service.to_response.return_value = MagicMock(
                model_dump=lambda: {
                    "status": "failed",
                    "jobId": "failed-job",
                    "error": mock_job.error,
                }
            )

            response = client.get("/v1/jobs/failed-job")

        assert response.status_code == 200
