import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

class TestFlowEndpoints:
    """Test FastAPI flow endpoints"""
    
    @pytest.fixture
    def mock_prefect_client(self, mocker):
        """Mock Prefect client"""
        mock = mocker.patch('core.prefect_client.PrefectClient')
        return mock
    
    @pytest.fixture
    def auth_headers(self):
        """Generate JWT auth headers"""
        from core.security import create_service_token
        token = create_service_token('test-service')
        return {'Authorization': f'Bearer {token}'}
    
    def test_execute_flow_success(self, mock_prefect_client, auth_headers):
        """Test successful flow execution"""
        # ARRANGE
        mock_prefect_client.return_value.run_deployment.return_value = {
            'id': '550e8400-e29b-41d4-a716-446655440000',
            'state': 'SCHEDULED',
            'created': '2024-01-01T00:00:00Z'
        }
        
        # ACT
        response = client.post(
            '/api/v1/flows/test-flow/execute',
            json={'parameters': {'input': 'test'}},
            headers=auth_headers
        )
        
        # ASSERT
        assert response.status_code == 200
        data = response.json()
        assert data['flow_name'] == 'test-flow'
        assert 'run_id' in data
    
    def test_execute_flow_unauthorized(self):
        """Test flow execution without auth"""
        # ACT
        response = client.post(
            '/api/v1/flows/test-flow/execute',
            json={'parameters': {}}
        )
        
        # ASSERT
        assert response.status_code == 403  # No auth header
    
    def test_get_flow_run(self, mock_prefect_client, auth_headers):
        """Test getting flow run details"""
        # ARRANGE
        mock_prefect_client.return_value.get_flow_run.return_value = {
            'id': '550e8400-e29b-41d4-a716-446655440000',
            'state': 'COMPLETED',
            'duration': 120
        }
        
        # ACT
        response = client.get(
            '/api/v1/runs/550e8400-e29b-41d4-a716-446655440000',
            headers=auth_headers
        )
        
        # ASSERT
        assert response.status_code == 200
        data = response.json()
        assert data['state'] == 'COMPLETED'
    
    def test_rate_limiting(self, auth_headers):
        """Test rate limiting middleware"""
        # ACT: Make 20 requests quickly
        responses = []
        for _ in range(20):
            response = client.post(
                '/api/v1/flows/test-flow/execute',
                json={'parameters': {}},
                headers=auth_headers
            )
            responses.append(response)
        
        # ASSERT: Should get rate limited
        rate_limited = [r for r in responses if r.status_code == 429]
        assert len(rate_limited) > 0