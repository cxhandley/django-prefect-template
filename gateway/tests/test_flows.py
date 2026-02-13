"""
Detailed tests for flow endpoints with proper mocking.
"""
import pytest
from unittest.mock import AsyncMock, patch

from main import app


@pytest.mark.asyncio
class TestFlowExecution:
    """Test flow execution endpoints with proper async mocking."""
    
    def test_execute_flow_with_parameters(self, setup_mock_client, client, auth_headers):
        """Test executing a flow with custom parameters."""
        # Setup mock
        setup_mock_client.run_deployment = AsyncMock(return_value={
            "run_id":  "550e8400-e29b-41d4-a716-446655440000",
            "flow_name": "data-processing",
            "deployment_name": "data-processing/production",
            "state": "SCHEDULED",
            "state_type": "SCHEDULED",
            "parameters": {"input_s3_path": "s3://test/data.parquet"},
            "tags": ["user:test-service"],
            "created": "2024-01-01T00:00:00Z",
        })
        
        response = client.post(
            "/api/v1/flows/data-processing/execute",
            json={
                "parameters": {"input_s3_path": "s3://test/data.parquet"},
                "tags": ["priority:high"]
            },
            headers=auth_headers
        )
        
        # Verify
        assert response.status_code == 202
        data = response.json()
        assert data["flow_name"] == "data-processing"
        assert "user:test-service" in data["tags"]
        
    
    def test_execute_specific_deployment(self, client, setup_mock_client, auth_headers):
        """Test executing a specific deployment."""

        setup_mock_client.run_deployment = AsyncMock(return_value={
            "run_id":  "550e8400-e29b-41d4-a716-446655440000",
            "flow_name": "test-flow",
            "deployment_name": "test-flow/staging",
            "state": "SCHEDULED",
            "state_type": "SCHEDULED",
            "parameters": {},
            "tags": [],
            "created": "2024-01-01T00:00:00Z",
        })
        
        response = client.post(
            "/api/v1/flows/test-flow/execute/staging",
            json={"parameters": {}},
            headers=auth_headers
        )
        
        assert response.status_code == 202
        assert response.json()["deployment_name"] == "test-flow/staging"

    
    def test_execute_flow_no_auth(self, client):
        """Test that execution requires authentication."""
        response = client.post(
            "/api/v1/flows/test-flow/execute",
            json={"parameters": {}}
        )
        
        assert response.status_code == 401
    
    def test_execute_flow_invalid_token(self, client, invalid_auth_headers):
        """Test execution with invalid token."""
        response = client.post(
            "/api/v1/flows/test-flow/execute",
            json={"parameters": {}},
            headers=invalid_auth_headers
        )
        
        assert response.status_code == 401