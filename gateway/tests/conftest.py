"""
Pytest fixtures for gateway tests.
"""
import pytest
from typing import Generator, Dict, Any
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from main import app
from core.security import create_service_token


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """
    FastAPI test client.
    
    Yields:
        TestClient instance
    """
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers() -> Dict[str, str]:
    """
    Generate valid JWT authentication headers.
    
    Returns:
        Dictionary with Authorization header
    """
    token = create_service_token("test-service")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def invalid_auth_headers() -> Dict[str, str]:
    """
    Generate invalid JWT authentication headers.
    
    Returns:
        Dictionary with invalid Authorization header
    """
    return {"Authorization": "Bearer invalid-token-here"}


@pytest.fixture
def mock_prefect_client():
    """
    Mock Prefect client for testing.
    
    Returns:
        Mock PrefectClient instance
    """
    mock_client = AsyncMock()
    
    # Mock run_deployment
    mock_client.run_deployment.return_value = {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "flow_name": "test-flow",
        "deployment_name": "test-flow/production",
        "state": "SCHEDULED",
        "state_type": "SCHEDULED",
        "parameters": {},
        "tags": [],
        "created": "2024-01-01T00:00:00Z",
    }
    
    # Mock get_flow_run
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
    
    # Mock get_flow_run_result
    mock_client.get_flow_run_result.return_value = {
        "output_path": "s3://bucket/output.parquet",
        "row_count": 1000,
    }
    
    # Mock list_deployments
    mock_client.list_deployments.return_value = [
        {
            "id": "deploy-123",
            "name": "production",
            "flow_name": "test-flow",
            "description": "Test flow deployment",
            "tags": ["test"],
            "parameters": {},
        }
    ]
    
    # Mock cancel_flow_run
    mock_client.cancel_flow_run.return_value = {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "flow_name": "test-flow",
        "state": "CANCELLED",
        "state_type": "CANCELLED",
    }
    
    return mock_client


@pytest.fixture
def sample_flow_parameters() -> Dict[str, Any]:
    """
    Sample flow parameters for testing.
    
    Returns:
        Dictionary of flow parameters
    """
    return {
        "input_s3_path": "s3://bucket/input.parquet",
        "run_id": "550e8400-e29b-41d4-a716-446655440000",
        "user_id": 1,
    }


@pytest.fixture
def sample_flow_run_id() -> str:
    """
    Sample flow run ID for testing.
    
    Returns:
        UUID string
    """
    return "550e8400-e29b-41d4-a716-446655440000"