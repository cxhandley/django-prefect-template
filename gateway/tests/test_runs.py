"""
Tests for flow run endpoints.
"""
import pytest
from unittest.mock import AsyncMock, patch

from main import app


class TestRunEndpoints:
    """Test run status and result endpoints."""
    
    def test_get_run_status(self, client, setup_mock_client, auth_headers):
        """Test getting run status."""

        setup_mock_client.get_flow_run = AsyncMock(return_value={
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "flow_name": "test-flow",
            "state": "RUNNING",
            "state_type": "RUNNING",
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": None,
            "total_run_time": None,
            "parameters": {},
        })

        
        response = client.get(
            "/api/v1/runs/550e8400-e29b-41d4-a716-446655440000",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "RUNNING"

    
    def test_get_run_result_completed(self, client, setup_mock_client, auth_headers):
        """Test getting result of completed run."""
        setup_mock_client.get_flow_run = AsyncMock(return_value={
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "flow_name": "test-flow",
            "state": "COMPLETED",
            "state_type": "COMPLETED",
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": "2024-01-01T00:01:00Z",
            "total_run_time": 60.0,
            "parameters": {},
        })

        setup_mock_client.get_flow_run_result = AsyncMock(return_value={
            "output_path": "s3://bucket/output.parquet",
            "row_count": 1000
        })

        response = client.get(
            "/api/v1/runs/550e8400-e29b-41d4-a716-446655440000/result",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "COMPLETED"
        assert data["result"] is not None

    
    
    def test_cancel_run(self, client, setup_mock_client, auth_headers):
        """Test cancelling a run."""

        setup_mock_client.cancel_flow_run = AsyncMock(return_value={
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "flow_name": "test-flow",
            "state": "CANCELLED",
            "state_type": "CANCELLED",
        })

        response = client.delete(
            "/api/v1/runs/550e8400-e29b-41d4-a716-446655440000",
            headers=auth_headers
        )
    
        assert response.status_code == 200
        data = response.json()
        assert "cancelled" in data["message"].lower()
