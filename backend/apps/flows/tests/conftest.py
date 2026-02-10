import pytest
from django.contrib.auth import get_user_model
from apps.flows.models import FlowExecution
import factory
from factory.django import DjangoModelFactory
from moto import mock_s3
import boto3

User = get_user_model()

# ============================================================================
# Factories (using factory-boy)
# ============================================================================

class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
    
    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')

class FlowExecutionFactory(DjangoModelFactory):
    class Meta:
        model = FlowExecution
    
    flow_run_id = factory.Faker('uuid4')
    flow_name = factory.Sequence(lambda n: f"flow-{n}")
    triggered_by = factory.SubFactory(UserFactory)
    s3_input_path = factory.Faker('file_path', depth=3, extension='csv')
    s3_output_path = factory.Faker('file_path', depth=3, extension='parquet')
    status = "PENDING"

# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def user_factory():
    """Factory for creating users"""
    return UserFactory

@pytest.fixture
def flow_execution_factory():
    """Factory for creating flow executions"""
    return FlowExecutionFactory

@pytest.fixture
def user(db):
    """Create a single user"""
    return UserFactory()

@pytest.fixture
def admin_user(db):
    """Create an admin user"""
    return UserFactory(is_staff=True, is_superuser=True)

@pytest.fixture
def api_client():
    """Django test client"""
    from django.test import Client
    return Client()

@pytest.fixture
def authenticated_client(user):
    """Authenticated Django test client"""
    from django.test import Client
    client = Client()
    client.force_login(user)
    return client

@pytest.fixture
def mock_s3():
    """Mock S3 for testing"""
    with mock_s3():
        # Create test bucket
        s3 = boto3.client('s3', region_name='us-east-1')
        s3.create_bucket(Bucket='test-bucket')
        yield s3

@pytest.fixture
def mock_gateway_client(mocker):
    """Mock FastAPI gateway client"""
    mock = mocker.patch('apps.flows.api_client.GatewayClient')
    mock.return_value.execute_flow.return_value = {
        'run_id': '550e8400-e29b-41d4-a716-446655440000',
        'flow_name': 'test-flow',
        'state': 'SCHEDULED'
    }
    return mock