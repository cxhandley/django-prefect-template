"""
Tests for flow run endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from main import app

client = TestClient(app)


class TestRunEndpoints:
    """Test run status and result endpoints."""
    
    @patch('api.v1.endpoints.runs.get_prefect_client')
    def test_get_run_status(self, mock_get_client, auth_headers):
        """Test getting run status."""
        mock_client = AsyncMock()
        mock_client.get_flow_run.return_value = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "flow_name": "test-flow",
            "state": "RUNNING",
            "state_type": "RUNNING",
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": None,
            "total_run_time": None,
            "parameters": {},
        }
        mock_get_client.return_value = mock_client
        
        response = client.get(
            "/api/v1/runs/550e8400-e29b-41d4-a716-446655440000",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "RUNNING"
    
    @patch('api.v1.endpoints.runs.get_prefect_client')
    def test_get_run_result_completed(self, mock_get_client, auth_headers):
        """Test getting result of completed run."""
        mock_client = AsyncMock()
        mock_client.get_flow_run.return_value = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "flow_name": "test-flow",
            "state": "COMPLETED",
            "state_type": "COMPLETED",
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": "2024-01-01T00:01:00Z",
            "total_run_time": 60.0,
            "parameters": {},
        }
        mock_client.get_flow_run_result.return_value = {
            "output_path": "s3://bucket/output.parquet",
            "row_count": 1000
        }
        mock_get_client.return_value = mock_client
        
        response = client.get(
            "/api/v1/runs/550e8400-e29b-41d4-a716-446655440000/result",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "COMPLETED"
        assert data["result"] is not None
    
    @patch('api.v1.endpoints.runs.get_prefect_client')
    def test_cancel_run(self, mock_get_client, auth_headers):
        """Test cancelling a run."""
        mock_client = AsyncMock()
        mock_client.cancel_flow_run.return_value = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "flow_name": "test-flow",
            "state": "CANCELLED",
            "state_type": "CANCELLED",
        }
        mock_get_client.return_value = mock_client
        
        response = client.delete(
            "/api/v1/runs/550e8400-e29b-41d4-a716-446655440000",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "cancelled" in data["message"].lower()


@pytest.fixture
def auth_headers():
    """Generate valid auth headers."""
    from core.security import create_service_token
    token = create_service_token("test-service")
    return {"Authorization": f"Bearer {token}"}