import boto3
import factory
import pytest
from apps.flows.models import FlowExecution
from django.contrib.auth import get_user_model
from factory.django import DjangoModelFactory
from moto import mock_aws

User = get_user_model()

# ============================================================================
# Factories
# ============================================================================


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")


class FlowExecutionFactory(DjangoModelFactory):
    class Meta:
        model = FlowExecution

    flow_run_id = factory.Faker("uuid4")
    flow_name = factory.Sequence(lambda n: f"flow-{n}")
    triggered_by = factory.SubFactory(UserFactory)
    s3_input_path = factory.Faker("file_path", depth=3, extension="csv")
    s3_output_path = factory.Faker("file_path", depth=3, extension="parquet")
    status = "PENDING"
    celery_task_id = ""
    error_message = ""


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def user_factory():
    return UserFactory


@pytest.fixture
def flow_execution_factory():
    return FlowExecutionFactory


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def admin_user(db):
    return UserFactory(is_staff=True, is_superuser=True)


@pytest.fixture
def api_client():
    from django.test import Client

    return Client()


@pytest.fixture
def authenticated_client(user):
    from django.test import Client

    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def mock_s3(settings):
    """Mock AWS S3 / RustFS for testing via moto."""
    settings.AWS_ACCESS_KEY_ID = "testing"
    settings.AWS_SECRET_ACCESS_KEY = "testing"
    settings.AWS_S3_REGION_NAME = "us-east-1"
    settings.AWS_S3_ENDPOINT_URL = None
    settings.DATA_LAKE_BUCKET = "test-bucket"
    settings.AWS_STORAGE_BUCKET_NAME = "test-bucket"

    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")

        # Reset cached default_storage so it re-initialises with test bucket
        from django.core.files.storage import default_storage
        from django.utils.functional import empty

        default_storage._wrapped = empty

        yield s3

        default_storage._wrapped = empty


@pytest.fixture
def mock_pipeline_task(mocker):
    """Mock the Celery run_pipeline_task so tests don't spawn workers."""
    mock = mocker.patch("apps.flows.views.run_pipeline_task")
    mock.delay.return_value.id = "mock-celery-task-id-1234"
    return mock
