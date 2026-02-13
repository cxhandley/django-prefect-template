"""
Pytest fixtures for gateway tests.
"""
import pytest
from typing import Generator, Dict, Any
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from main import app
from core.security import create_service_token, create_access_token


@pytest.fixture(autouse = True)
def client() -> Generator[TestClient, None, None]:
    """
    FastAPI test client.
    
    Yields:
        TestClient instance
    """
    with TestClient(app) as client:
        yield client


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
def service_token():
    """Create a valid service token for testing."""
    return create_service_token("test-service")


@pytest.fixture
def user_token():
    """Create a valid user token for testing."""
    return create_access_token(subject="test-user")


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
