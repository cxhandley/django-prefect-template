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
    
    def test_get_run_status(self, auth_headers):
        """Test getting run status."""
        mock_client = AsyncMock()

        mock_client.get_flow_run = AsyncMock(return_value={
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "flow_name": "test-flow",
            "state": "RUNNING",
            "state_type": "RUNNING",
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": None,
            "total_run_time": None,
            "parameters": {},
        })

        async def mock_get_prefect_client():
            return mock_client
        
        from api.v1.endpoints.flows import get_prefect_client
        app.dependency_overrides[get_prefect_client] = mock_get_prefect_client
        
        try:
        
            response = client.get(
                "/api/v1/runs/550e8400-e29b-41d4-a716-446655440000",
                headers=auth_headers
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["state"] == "RUNNING"

        finally:
            # Clean up - remove the override
            app.dependency_overrides.clear()
    
    def test_get_run_result_completed(self, auth_headers):
        """Test getting result of completed run."""
        mock_client = AsyncMock()

        mock_client.get_flow_run = AsyncMock(return_value={
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "flow_name": "test-flow",
            "state": "COMPLETED",
            "state_type": "COMPLETED",
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": "2024-01-01T00:01:00Z",
            "total_run_time": 60.0,
            "parameters": {},
        })

        mock_client.get_flow_run_result = AsyncMock(return_value={
            "output_path": "s3://bucket/output.parquet",
            "row_count": 1000
        })

        async def mock_get_prefect_client():
            return mock_client
        
        from api.v1.endpoints.flows import get_prefect_client
        app.dependency_overrides[get_prefect_client] = mock_get_prefect_client
        
        try:
        
            response = client.get(
                "/api/v1/runs/550e8400-e29b-41d4-a716-446655440000/result",
                headers=auth_headers
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["state"] == "COMPLETED"
            assert data["result"] is not None

        finally:
            # Clean up - remove the override
            app.dependency_overrides.clear()
    
    
    def test_cancel_run(self, auth_headers):
        """Test cancelling a run."""
        mock_client = AsyncMock()

        mock_client.cancel_flow_run = AsyncMock(return_value={
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "flow_name": "test-flow",
            "state": "CANCELLED",
            "state_type": "CANCELLED",
        })

        async def mock_get_prefect_client():
            return mock_client
        
        from api.v1.endpoints.flows import get_prefect_client
        app.dependency_overrides[get_prefect_client] = mock_get_prefect_client
        
        try:
        
            response = client.delete(
                "/api/v1/runs/550e8400-e29b-41d4-a716-446655440000",
                headers=auth_headers
            )
        
            assert response.status_code == 200
            data = response.json()
            assert "cancelled" in data["message"].lower()

        finally:
            # Clean up - remove the override
            app.dependency_overrides.clear()
