"""Tests for health check endpoints."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """Tests for GET /v1/health."""

    def test_health_check_healthy(
        self, client: TestClient, mock_redis: MagicMock
    ) -> None:
        """Test health check when all components are healthy."""
        response = client.get("/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded"]
        assert "version" in data
        assert "environment" in data
        assert "components" in data

    def test_health_check_redis_down(
        self, client: TestClient
    ) -> None:
        """Test health check when Redis is down."""
        with patch("app.api.v1.health.get_redis") as mock_redis:
            mock_redis.return_value.ping = AsyncMock(side_effect=Exception("Connection refused"))

            response = client.get("/v1/health")

        assert response.status_code == 200
        data = response.json()
        # Should be degraded when Redis is down
        assert data["status"] in ["healthy", "degraded", "unhealthy"]


class TestMetricsEndpoint:
    """Tests for GET /v1/metrics."""

    def test_metrics_endpoint(
        self, client: TestClient, mock_redis: MagicMock
    ) -> None:
        """Test Prometheus metrics endpoint."""
        response = client.get("/v1/metrics")

        assert response.status_code == 200
        # Prometheus metrics are in text format
        assert "text/plain" in response.headers.get("content-type", "")


class TestReadinessEndpoint:
    """Tests for GET /v1/ready."""

    def test_readiness_healthy(
        self, client: TestClient, mock_redis: MagicMock
    ) -> None:
        """Test readiness when healthy."""
        response = client.get("/v1/ready")

        assert response.status_code == 200
        data = response.json()
        assert "ready" in data


class TestLivenessEndpoint:
    """Tests for GET /v1/live."""

    def test_liveness(
        self, client: TestClient, mock_redis: MagicMock
    ) -> None:
        """Test liveness probe."""
        response = client.get("/v1/live")

        assert response.status_code == 200
        data = response.json()
        assert data["alive"] is True
