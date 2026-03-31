"""
Shared fixtures for core app tests.
Provides the same factories used in flows tests.
"""

import factory
import pytest
from django.contrib.auth import get_user_model
from factory.django import DjangoModelFactory

User = get_user_model()


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"coreuser{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")


class FlowExecutionFactory(DjangoModelFactory):
    class Meta:
        model = "flows.FlowExecution"

    flow_run_id = factory.Faker("uuid4")
    flow_name = factory.Sequence(lambda n: f"flow-{n}")
    triggered_by = factory.SubFactory(UserFactory)
    s3_input_path = factory.Faker("file_path", depth=3, extension="csv")
    s3_output_path = factory.Faker("file_path", depth=3, extension="parquet")
    status = "PENDING"
    celery_task_id = ""
    error_message = ""


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def flow_execution_factory():
    return FlowExecutionFactory
