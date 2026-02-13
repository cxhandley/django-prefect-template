import pytest
from unittest.mock import AsyncMock, patch

from main import app


class TestHealthEndpoints:
    """Test health check endpoints."""
    
    def test_root_endpoint(self, client):
        """Test root endpoint returns status."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "running"
    
    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestFlowEndpoints:
    """Test FastAPI flow endpoints"""
    
    def test_execute_flow_success(self, client, setup_mock_client, auth_headers):
        """Test successful flow execution."""
        setup_mock_client.run_deployment = AsyncMock(return_value={
            "run_id": "550e8400-e29b-41d4-a716-446655440000",
            "flow_name": "test-flow",
            "deployment_name": "test-flow/production",
            "state": "SCHEDULED",
            "state_type": "SCHEDULED",
            "parameters": {"test": "value"},
            "tags": ["user:test-service"],
            "created": "2024-01-01T00:00:00Z",
        })
        
        # Make request
        response = client.post(
            "/api/v1/flows/test-flow/execute",
            json={"parameters": {"test": "value"}},
            headers=auth_headers
        )
        
        # Assert
        assert response.status_code == 202
        data = response.json()
        assert data["flow_name"] == "test-flow"
        assert data["run_id"] == "550e8400-e29b-41d4-a716-446655440000"
    
    def test_get_flow_run(self, client, setup_mock_client, auth_headers):
        """Test getting flow run details"""
        setup_mock_client.get_flow_run = AsyncMock(return_value={
            'id': '550e8400-e29b-41d4-a716-446655440000',
            'flow_name': 'test-flow',  # ADD THIS
            'state': 'COMPLETED',
            'state_type': 'COMPLETED',  # ADD THIS
            'start_time': '2024-01-01T00:00:00Z',
            'end_time': '2024-01-01T00:02:00Z',
            'total_run_time': 120.0,  # Use this instead of 'duration'
            'parameters': {}
        })
        
        response = client.get(
            '/api/v1/runs/550e8400-e29b-41d4-a716-446655440000',
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data['state'] == 'COMPLETED'
    
    # @patch('api.v1.endpoints.flows.get_prefect_client')
    # def test_rate_limiting(self, client, auth_headers):
    #     """Test rate limiting middleware"""
    #     # ACT: Make 20 requests quickly
    #     responses = []
    #     for _ in range(20):
    #         response = client.post(
    #             '/api/v1/flows/test-flow/execute',
    #             json={'parameters': {}},
    #             headers=auth_headers
    #         )
    #         responses.append(response)
        
    #     # ASSERT: Should get rate limited
    #     rate_limited = [r for r in responses if r.status_code == 429]
    #     assert len(rate_limited) > 0