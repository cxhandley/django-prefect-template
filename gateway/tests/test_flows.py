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
    
    def test_execute_flow_with_parameters(self, auth_headers):
        """Test executing a flow with custom parameters."""
        # Setup mock
        mock_client = AsyncMock()
        mock_client.run_deployment = AsyncMock(return_value={
            "run_id":  "550e8400-e29b-41d4-a716-446655440000",
            "flow_name": "data-processing",
            "deployment_name": "data-processing/production",
            "state": "SCHEDULED",
            "state_type": "SCHEDULED",
            "parameters": {"input_s3_path": "s3://test/data.parquet"},
            "tags": ["user:test-service"],
            "created": "2024-01-01T00:00:00Z",
        })

        async def mock_get_prefect_client():
            return mock_client
        
        from api.v1.endpoints.flows import get_prefect_client
        app.dependency_overrides[get_prefect_client] = mock_get_prefect_client
        
        try:
        
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
        
        finally:
            # Clean up - remove the override
            app.dependency_overrides.clear()
    
    def test_execute_specific_deployment(self, auth_headers):
        """Test executing a specific deployment."""
        mock_client = AsyncMock()

        mock_client.run_deployment = AsyncMock(return_value={
            "run_id":  "550e8400-e29b-41d4-a716-446655440000",
            "flow_name": "test-flow",
            "deployment_name": "test-flow/staging",
            "state": "SCHEDULED",
            "state_type": "SCHEDULED",
            "parameters": {},
            "tags": [],
            "created": "2024-01-01T00:00:00Z",
        })

        async def mock_get_prefect_client():
            return mock_client
        
        from api.v1.endpoints.flows import get_prefect_client
        app.dependency_overrides[get_prefect_client] = mock_get_prefect_client
        
        try:
            response = client.post(
                "/api/v1/flows/test-flow/execute/staging",
                json={"parameters": {}},
                headers=auth_headers
            )
            
            assert response.status_code == 202
            assert response.json()["deployment_name"] == "test-flow/staging"

        finally:
            # Clean up - remove the override
            app.dependency_overrides.clear()
    
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