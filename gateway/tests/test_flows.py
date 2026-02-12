"""
Detailed tests for flow endpoints with proper mocking.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from main import app

client = TestClient(app)


@pytest.mark.asyncio
class TestFlowExecution:
    """Test flow execution endpoints with proper async mocking."""
    
    @patch('api.v1.endpoints.flows.get_prefect_client')
    def test_execute_flow_with_parameters(self, mock_get_client, auth_headers):
        """Test executing a flow with custom parameters."""
        # Setup mock
        mock_client = AsyncMock()
        mock_client.run_deployment.return_value = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "flow_name": "data-processing",
            "deployment_name": "data-processing/production",
            "state": "SCHEDULED",
            "state_type": "SCHEDULED",
            "parameters": {"input_s3_path": "s3://test/data.parquet"},
            "tags": ["user:test-service"],
            "created": "2024-01-01T00:00:00Z",
        }
        mock_get_client.return_value = mock_client
        
        # Execute
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
    
    @patch('api.v1.endpoints.flows.get_prefect_client')
    def test_execute_specific_deployment(self, mock_get_client, auth_headers):
        """Test executing a specific deployment."""
        mock_client = AsyncMock()
        mock_client.run_deployment.return_value = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "flow_name": "test-flow",
            "deployment_name": "test-flow/staging",
            "state": "SCHEDULED",
            "state_type": "SCHEDULED",
            "parameters": {},
            "tags": [],
            "created": "2024-01-01T00:00:00Z",
        }
        mock_get_client.return_value = mock_client
        
        response = client.post(
            "/api/v1/flows/test-flow/execute/staging",
            json={"parameters": {}},
            headers=auth_headers
        )
        
        assert response.status_code == 202
        assert response.json()["deployment_name"] == "test-flow/staging"
    
    def test_execute_flow_no_auth(self):
        """Test that execution requires authentication."""
        response = client.post(
            "/api/v1/flows/test-flow/execute",
            json={"parameters": {}}
        )
        
        assert response.status_code == 401
    
    def test_execute_flow_invalid_token(self, invalid_auth_headers):
        """Test execution with invalid token."""
        response = client.post(
            "/api/v1/flows/test-flow/execute",
            json={"parameters": {}},
            headers=invalid_auth_headers
        )
        
        assert response.status_code == 401


@pytest.fixture
def auth_headers():
    """Generate valid auth headers."""
    from core.security import create_service_token
    token = create_service_token("test-service")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def invalid_auth_headers():
    """Generate invalid auth headers."""
    return {"Authorization": "Bearer invalid-token"}