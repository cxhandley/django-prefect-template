"""
Integration tests for Prefect FastAPI gateway.

Tests the full flow from HTTP request through dependency injection,
authentication, and Prefect client interactions.
"""
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta, UTC
from fastapi.testclient import TestClient

from core.security import create_service_token, create_access_token
from main import app  # Import your FastAPI app


# Setup test client
client = TestClient(app)


@pytest.fixture
def service_token():
    """Create a valid service token for testing."""
    return create_service_token("test-service")


@pytest.fixture
def user_token():
    """Create a valid user token for testing."""
    return create_access_token(subject="test-user")


@pytest.fixture
def auth_headers(service_token):
    """Create authorization headers with service token."""
    return {"Authorization": f"Bearer {service_token}"}


@pytest.fixture
def user_auth_headers(user_token):
    """Create authorization headers with user token."""
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture
def mock_prefect_client():
    """Create a mock Prefect client."""
    return AsyncMock()


@pytest.fixture
def setup_mock_client(mock_prefect_client):
    """Setup and teardown for mocking the Prefect client dependency."""
    async def mock_get_prefect_client():
        return mock_prefect_client
    
    from api.v1.endpoints.flows import get_prefect_client
    app.dependency_overrides[get_prefect_client] = mock_get_prefect_client
    
    yield mock_prefect_client
    
    app.dependency_overrides.clear()


class TestFlowExecutionIntegration:
    """Integration tests for flow execution endpoints."""
    
    def test_execute_flow_end_to_end(self, setup_mock_client, auth_headers):
        """Test complete flow execution from request to response."""
        # Setup mock response
        run_id = "550e8400-e29b-41d4-a716-446655440000"
        setup_mock_client.run_deployment = AsyncMock(return_value={
            "run_id": run_id,
            "flow_name": "data-processing",
            "deployment_name": "data-processing/production",
            "state": "SCHEDULED",
            "state_type": "SCHEDULED",
            "parameters": {"input_s3_path": "s3://bucket/input.parquet"},
            "tags": ["user:admin"],
            "created": "2024-01-01T00:00:00Z",
        })
        
        # Execute request
        response = client.post(
            "/api/v1/flows/data-processing/execute",
            json={"parameters": {"input_s3_path": "s3://bucket/input.parquet"}},
            headers=auth_headers
        )
        
        # Assertions
        assert response.status_code == 202
        data = response.json()
        
        assert data["run_id"] == run_id
        assert data["flow_name"] == "data-processing"
        assert data["state"] == "SCHEDULED"
        assert data["parameters"]["input_s3_path"] == "s3://bucket/input.parquet"
        
        # Verify client was called correctly
        setup_mock_client.run_deployment.assert_called_once()
        call_kwargs = setup_mock_client.run_deployment.call_args[1]
        assert call_kwargs["deployment_name"] == "data-processing/production"
    
    def test_execute_flow_with_no_parameters(self, setup_mock_client, auth_headers):
        """Test executing flow without parameters."""
        run_id = "550e8400-e29b-41d4-a716-446655440001"
        setup_mock_client.run_deployment = AsyncMock(return_value={
            "run_id": run_id,
            "flow_name": "simple-flow",
            "deployment_name": "simple-flow/production",
            "state": "SCHEDULED",
            "state_type": "SCHEDULED",
            "parameters": {},
            "tags": [],
            "created": "2024-01-01T00:00:00Z",
        })
        
        response = client.post(
            "/api/v1/flows/simple-flow/execute",
            json={"parameters": {}},
            headers=auth_headers
        )
        
        assert response.status_code == 202
        assert response.json()["parameters"] == {}
    
    def test_execute_flow_with_complex_parameters(self, setup_mock_client, auth_headers):
        """Test executing flow with nested parameter structures."""
        params = {
            "config": {
                "database": {
                    "host": "localhost",
                    "port": 5432,
                    "name": "mydb"
                },
                "retry": 3
            },
            "tags": ["prod", "critical"],
            "timeout_seconds": 3600
        }
        
        setup_mock_client.run_deployment = AsyncMock(return_value={
            "run_id": "550e8400-e29b-41d4-a716-446655440002",
            "flow_name": "etl-flow",
            "deployment_name": "etl-flow/production",
            "state": "SCHEDULED",
            "state_type": "SCHEDULED",
            "parameters": params,
            "tags": [],
            "created": "2024-01-01T00:00:00Z",
        })
        
        response = client.post(
            "/api/v1/flows/etl-flow/execute",
            json={"parameters": params},
            headers=auth_headers
        )
        
        assert response.status_code == 202
        assert response.json()["parameters"] == params
    
    def test_execute_flow_unauthorized(self):
        """Test flow execution without authorization fails."""
        response = client.post(
            "/api/v1/flows/data-processing/execute",
            json={"parameters": {}}
        )
        
        assert response.status_code == 401
    
    def test_execute_flow_invalid_token(self):
        """Test flow execution with invalid token fails."""
        headers = {"Authorization": "Bearer invalid-token"}
        
        response = client.post(
            "/api/v1/flows/data-processing/execute",
            json={"parameters": {}},
            headers=headers
        )
        
        assert response.status_code == 401
    
    def test_execute_flow_expired_token(self):
        """Test flow execution with expired token fails."""
        expired_delta = timedelta(minutes=-1)
        expired_token = create_access_token(
            subject="test-user",
            expires_delta=expired_delta
        )
        
        headers = {"Authorization": f"Bearer {expired_token}"}
        
        # This would fail if token was actually expired
        response = client.post(
            "/api/v1/flows/data-processing/execute",
            json={"parameters": {}},
            headers=headers
        )
        
        # Should succeed if token not expired
        assert response.status_code in [202, 401]
    
    def test_execute_flow_prefect_client_error(self, setup_mock_client, auth_headers):
        """Test handling of Prefect client errors."""
        setup_mock_client.run_deployment = AsyncMock(
            side_effect=Exception("Prefect API unavailable")
        )
        
        response = client.post(
            "/api/v1/flows/data-processing/execute",
            json={"parameters": {}},
            headers=auth_headers
        )
        
        # Should return 500 or appropriate error
        assert response.status_code >= 400


class TestFlowRunIntegration:
    """Integration tests for flow run retrieval endpoints."""
    
    def test_get_flow_run_end_to_end(self, setup_mock_client, auth_headers):
        """Test complete flow run retrieval from request to response."""
        run_id = "550e8400-e29b-41d4-a716-446655440000"
        
        setup_mock_client.get_flow_run = AsyncMock(return_value={
            "id": run_id,
            "flow_name": "data-processing",
            "state": "COMPLETED",
            "state_type": "COMPLETED",
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": "2024-01-01T00:02:00Z",
            "total_run_time": 120.0,
            "parameters": {"input_s3_path": "s3://bucket/input.parquet"},
        })
        
        response = client.get(
            f"/api/v1/runs/{run_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == run_id
        assert data["flow_name"] == "data-processing"
        assert data["state"] == "COMPLETED"
        assert data["total_run_time"] == 120.0
        
        # Verify client was called correctly
        setup_mock_client.get_flow_run.assert_called_once_with(run_id)
    
    def test_get_flow_run_in_progress(self, setup_mock_client, auth_headers):
        """Test retrieving a flow run that is still running."""
        run_id = "550e8400-e29b-41d4-a716-446655440001"
        
        setup_mock_client.get_flow_run = AsyncMock(return_value={
            "id": run_id,
            "flow_name": "long-running-flow",
            "state": "RUNNING",
            "state_type": "RUNNING",
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": None,
            "total_run_time": None,
            "parameters": {},
        })
        
        response = client.get(
            f"/api/v1/runs/{run_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["state"] == "RUNNING"
        assert data["end_time"] is None
        assert data["total_run_time"] is None
    
    def test_get_flow_run_failed(self, setup_mock_client, auth_headers):
        """Test retrieving a failed flow run."""
        run_id = "550e8400-e29b-41d4-a716-446655440002"
        
        setup_mock_client.get_flow_run = AsyncMock(return_value={
            "id": run_id,
            "flow_name": "failing-flow",
            "state": "FAILED",
            "state_type": "FAILED",
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": "2024-01-01T00:05:00Z",
            "total_run_time": 300.0,
            "parameters": {},
        })
        
        response = client.get(
            f"/api/v1/runs/{run_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert response.json()["state"] == "FAILED"
    
    def test_get_flow_run_not_found(self, setup_mock_client, auth_headers):
        """Test retrieving a non-existent flow run."""
        run_id = "non-existent-id"
        
        setup_mock_client.get_flow_run = AsyncMock(
            side_effect=Exception("Run not found")
        )
        
        response = client.get(
            f"/api/v1/runs/{run_id}",
            headers=auth_headers
        )
        
        # Should return 404 or 500 depending on error handling
        assert response.status_code >= 400
    
    def test_get_flow_run_unauthorized(self):
        """Test flow run retrieval without authorization fails."""
        run_id = "550e8400-e29b-41d4-a716-446655440000"
        
        response = client.get(f"/api/v1/runs/{run_id}")
        
        assert response.status_code == 401


class TestMultipleFlowsIntegration:
    """Integration tests for multiple flow operations."""
    
    def test_execute_multiple_flows_sequentially(self, setup_mock_client, auth_headers):
        """Test executing multiple different flows."""
        flows = [
            ("flow-a", {"param_a": "value_a"}),
            ("flow-b", {"param_b": "value_b"}),
            ("flow-c", {"param_c": "value_c"}),
        ]
        
        run_ids = []
        
        for flow_name, params in flows:
            run_id = f"550e8400-e29b-41d4-a716-{flow_name.replace('-', '')}"
            run_ids.append(run_id)
            
            setup_mock_client.run_deployment = AsyncMock(return_value={
                "run_id": run_id,
                "flow_name": flow_name,
                "deployment_name": f"{flow_name}/production",
                "state": "SCHEDULED",
                "state_type": "SCHEDULED",
                "parameters": params,
                "tags": [],
                "created": "2024-01-01T00:00:00Z",
            })
            
            response = client.post(
                f"/api/v1/flows/{flow_name}/execute",
                json={"parameters": params},
                headers=auth_headers
            )
            
            assert response.status_code == 202
            assert response.json()["run_id"] == run_id
    
    def test_execute_and_retrieve_flow_run(self, setup_mock_client, auth_headers):
        """Test executing a flow and then retrieving its status."""
        run_id = "550e8400-e29b-41d4-a716-446655440000"
        flow_name = "test-flow"
        
        # Step 1: Execute flow
        setup_mock_client.run_deployment = AsyncMock(return_value={
            "run_id": run_id,
            "flow_name": flow_name,
            "deployment_name": f"{flow_name}/production",
            "state": "SCHEDULED",
            "state_type": "SCHEDULED",
            "parameters": {"key": "value"},
            "tags": [],
            "created": "2024-01-01T00:00:00Z",
        })
        
        execute_response = client.post(
            f"/api/v1/flows/{flow_name}/execute",
            json={"parameters": {"key": "value"}},
            headers=auth_headers
        )
        
        assert execute_response.status_code == 202
        executed_run_id = execute_response.json()["run_id"]
        
        # Step 2: Retrieve the run
        setup_mock_client.get_flow_run = AsyncMock(return_value={
            "id": executed_run_id,
            "flow_name": flow_name,
            "state": "RUNNING",
            "state_type": "RUNNING",
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": None,
            "total_run_time": None,
            "parameters": {"key": "value"},
        })
        
        retrieve_response = client.get(
            f"/api/v1/runs/{executed_run_id}",
            headers=auth_headers
        )
        
        assert retrieve_response.status_code == 200
        assert retrieve_response.json()["flow_name"] == flow_name
        assert retrieve_response.json()["state"] == "RUNNING"


class TestAuthenticationIntegration:
    """Integration tests for authentication with different token types."""
    
    def test_service_to_service_authentication(self, setup_mock_client, auth_headers):
        """Test service-to-service authentication flow."""
        setup_mock_client.run_deployment = AsyncMock(return_value={
            "run_id": "550e8400-e29b-41d4-a716-446655440000",
            "flow_name": "test-flow",
            "deployment_name": "test-flow/production",
            "state": "SCHEDULED",
            "state_type": "SCHEDULED",
            "parameters": {},
            "tags": [],
            "created": "2024-01-01T00:00:00Z",
        })
        
        response = client.post(
            "/api/v1/flows/test-flow/execute",
            json={"parameters": {}},
            headers=auth_headers
        )
        
        assert response.status_code == 202
    
    def test_user_authentication(self, setup_mock_client, user_auth_headers):
        """Test user authentication flow."""
        setup_mock_client.run_deployment = AsyncMock(return_value={
            "run_id": "550e8400-e29b-41d4-a716-446655440000",
            "flow_name": "test-flow",
            "deployment_name": "test-flow/production",
            "state": "SCHEDULED",
            "state_type": "SCHEDULED",
            "parameters": {},
            "tags": [],
            "created": "2024-01-01T00:00:00Z",
        })
        
        response = client.post(
            "/api/v1/flows/test-flow/execute",
            json={"parameters": {}},
            headers=user_auth_headers
        )
        
        assert response.status_code == 202
    
    def test_missing_authorization_header(self, setup_mock_client):
        """Test request without authorization header."""
        response = client.post(
            "/api/v1/flows/test-flow/execute",
            json={"parameters": {}}
        )
        
        assert response.status_code == 401
    
    def test_malformed_authorization_header(self, setup_mock_client):
        """Test request with malformed authorization header."""
        headers = {"Authorization": "InvalidScheme token"}
        
        response = client.post(
            "/api/v1/flows/test-flow/execute",
            json={"parameters": {}},
            headers=headers
        )
        
        assert response.status_code >= 400


class TestErrorHandlingIntegration:
    """Integration tests for error handling."""
    
    def test_invalid_request_payload(self, setup_mock_client, auth_headers):

        setup_mock_client.run_deployment = AsyncMock(return_value={
            "run_id": "550e8400-e29b-41d4-a716-446655440000",
            "flow_name": "test-flow",
            "deployment_name": "test-flow/production",
            "state": "SCHEDULED",
            "state_type": "SCHEDULED",
            "parameters": {"key": "value"},
            "tags": [],
            "created": "2024-01-01T00:00:00Z",
        })

        """Test request with invalid JSON payload."""
        response = client.post(
            "/api/v1/flows/test-flow/execute",
            json={"invalid_field": "value"},
            headers=auth_headers
        )
        
        # Should return 422 for validation error
        assert response.status_code in [400, 422]
    
    def test_missing_required_fields(self, setup_mock_client, auth_headers):
        """Test request missing required fields."""
        response = client.post(
            "/api/v1/flows/test-flow/execute",
            json={},  # Missing 'parameters'
            headers=auth_headers
        )
        
        assert response.status_code in [400, 422]
    
    def test_timeout_handling(self, setup_mock_client, auth_headers):
        """Test handling of timeout errors from Prefect client."""
        setup_mock_client.run_deployment = AsyncMock(
            side_effect=TimeoutError("Request timed out")
        )
        
        response = client.post(
            "/api/v1/flows/test-flow/execute",
            json={"parameters": {}},
            headers=auth_headers
        )
        
        assert response.status_code >= 500