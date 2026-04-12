"""
Tests for the pluggable pipeline backend system (BL-037).

Covers:
  - get_backend() factory respects settings.PIPELINE_BACKEND
  - DoitBackend.run() delegates to PipelineRunner._run_doit()
  - DoitBackend.cancel() is a no-op
  - PrefectBackend.cancel() calls _cancel_flow_run on external_run_id
  - PrefectBackend.cancel() is safe when external_run_id is absent
  - /internal/step-status/ endpoint: auth, missing fields, updates ExecutionStep
"""

import json
import uuid

import factory
import pytest
from apps.flows.backends.base import PipelineBackend
from apps.flows.backends.doit import DoitBackend
from apps.flows.models import ExecutionStatus, ExecutionStep, FlowExecution
from django.contrib.auth import get_user_model
from django.test import Client
from factory.django import DjangoModelFactory

User = get_user_model()


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"backend_user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")


class FlowExecutionFactory(DjangoModelFactory):
    class Meta:
        model = FlowExecution

    flow_run_id = factory.LazyFunction(uuid.uuid4)
    flow_name = "data-processing"
    triggered_by = factory.SubFactory(UserFactory)
    s3_input_path = "uploads/test.csv"
    s3_output_path = "processed/out.parquet"
    status = "PENDING"
    celery_task_id = ""
    error_message = ""
    external_run_id = None


# ─── get_backend() ───────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_get_backend_returns_doit_by_default(settings):
    settings.PIPELINE_BACKEND = "doit"
    from apps.flows.backends import get_backend

    backend = get_backend()
    assert isinstance(backend, DoitBackend)


@pytest.mark.django_db
def test_get_backend_returns_doit_when_not_set(settings):
    # Delete the attribute entirely to test default path
    if hasattr(settings, "PIPELINE_BACKEND"):
        delattr(settings, "PIPELINE_BACKEND")
    from apps.flows.backends import get_backend

    backend = get_backend()
    assert isinstance(backend, DoitBackend)


@pytest.mark.django_db
def test_get_backend_returns_prefect_backend(settings):
    settings.PIPELINE_BACKEND = "prefect"
    from apps.flows.backends import get_backend
    from apps.flows.backends.prefect import PrefectBackend

    backend = get_backend()
    assert isinstance(backend, PrefectBackend)


# ─── PipelineBackend ABC ──────────────────────────────────────────────────────


def test_pipeline_backend_is_abstract():
    """Concrete subclasses must implement run() and cancel()."""
    with pytest.raises(TypeError):
        PipelineBackend()  # type: ignore[abstract]


# ─── DoitBackend ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_doit_backend_run_delegates_to_pipeline_runner(mocker, settings, db):
    settings.DATA_LAKE_BUCKET = "test-bucket"
    settings.PIPELINE_BACKEND = "doit"

    user = UserFactory()
    execution = FlowExecutionFactory(
        flow_name="data-processing",
        s3_input_path="uploads/test.csv",
        triggered_by=user,
    )

    expected_metadata = {"row_count": 5, "s3_output_path": "processed/out.parquet"}
    mock_run_doit = mocker.patch(
        "apps.flows.runner.PipelineRunner._run_doit",
        return_value=expected_metadata,
    )

    backend = DoitBackend()
    result = backend.run(execution)

    assert result == expected_metadata
    mock_run_doit.assert_called_once()
    call_kwargs = mock_run_doit.call_args.kwargs
    assert call_kwargs["run_id"] == execution.flow_run_id
    assert call_kwargs["input_s3_path"] == f"s3://test-bucket/{execution.s3_input_path}"
    assert call_kwargs["doit_task"] == "pipeline"


@pytest.mark.django_db
def test_doit_backend_maps_credit_prediction_flow(mocker, settings, db):
    settings.DATA_LAKE_BUCKET = "test-bucket"
    settings.PIPELINE_BACKEND = "doit"

    user = UserFactory()
    execution = FlowExecutionFactory(
        flow_name="credit-prediction",
        s3_input_path="uploads/predict.csv",
        triggered_by=user,
    )

    mock_run_doit = mocker.patch(
        "apps.flows.runner.PipelineRunner._run_doit",
        return_value={},
    )

    DoitBackend().run(execution)

    assert mock_run_doit.call_args.kwargs["doit_task"] == "predict_pipeline"


@pytest.mark.django_db
def test_doit_backend_cancel_is_noop(db):
    user = UserFactory()
    execution = FlowExecutionFactory(triggered_by=user)
    backend = DoitBackend()
    # Should complete without error and return None
    result = backend.cancel(execution)
    assert result is None


# ─── PrefectBackend ───────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_prefect_backend_cancel_calls_cancel_flow_run(mocker, db):
    from apps.flows.backends.prefect import PrefectBackend

    user = UserFactory()
    execution = FlowExecutionFactory(
        triggered_by=user,
        external_run_id="prefect-run-uuid-1234",
    )
    mock_cancel = mocker.patch.object(PrefectBackend, "_cancel_flow_run")

    PrefectBackend().cancel(execution)

    mock_cancel.assert_called_once_with("prefect-run-uuid-1234")


@pytest.mark.django_db
def test_prefect_backend_cancel_noop_when_no_external_run_id(mocker, db):
    from apps.flows.backends.prefect import PrefectBackend

    user = UserFactory()
    execution = FlowExecutionFactory(triggered_by=user, external_run_id=None)
    mock_cancel = mocker.patch.object(PrefectBackend, "_cancel_flow_run")

    PrefectBackend().cancel(execution)

    mock_cancel.assert_not_called()


@pytest.mark.django_db
def test_prefect_backend_cancel_swallows_errors(mocker, db):
    """A broken Prefect API call must not propagate out of cancel()."""
    from apps.flows.backends.prefect import PrefectBackend

    user = UserFactory()
    execution = FlowExecutionFactory(
        triggered_by=user,
        external_run_id="bad-id",
    )
    mocker.patch.object(PrefectBackend, "_cancel_flow_run", side_effect=Exception("network error"))

    # Must not raise
    PrefectBackend().cancel(execution)


# ─── PipelineRunner dispatching ──────────────────────────────────────────────


@pytest.mark.django_db
def test_pipeline_runner_uses_doit_backend_by_default(mocker, settings, db):
    """run_pipeline() with the doit backend calls _run_doit() directly."""
    settings.PIPELINE_BACKEND = "doit"
    settings.DATA_LAKE_BUCKET = "test-bucket"

    from apps.flows.runner import PipelineRunner

    mock_run_doit = mocker.patch.object(
        PipelineRunner,
        "_run_doit",
        return_value={"row_count": 1},
    )

    runner = PipelineRunner()
    run_id = uuid.uuid4()
    runner.run_pipeline(run_id=run_id, input_s3_path="s3://test-bucket/in.csv")

    mock_run_doit.assert_called_once()


@pytest.mark.django_db
def test_pipeline_runner_uses_prefect_backend(mocker, settings, db):
    """run_pipeline() with the Prefect backend calls backend.run() with execution."""
    settings.PIPELINE_BACKEND = "prefect"

    from apps.flows.backends.prefect import PrefectBackend
    from apps.flows.runner import PipelineRunner

    user = UserFactory()
    run_id = uuid.uuid4()
    execution = FlowExecutionFactory(
        flow_run_id=run_id,
        flow_name="data-processing",
        triggered_by=user,
    )

    mock_run = mocker.patch.object(
        PrefectBackend,
        "run",
        return_value={"row_count": 7},
    )

    runner = PipelineRunner()
    result = runner.run_pipeline(run_id=run_id, input_s3_path="s3://bucket/in.csv")

    assert result == {"row_count": 7}
    mock_run.assert_called_once_with(execution)


# ─── /internal/step-status/ endpoint ─────────────────────────────────────────


@pytest.fixture
def step_status_client(settings):
    """Client pre-configured with the bearer token."""
    settings.PREFECT_INTERNAL_SECRET = "test-secret-xyz"
    return Client()


@pytest.fixture
def execution_with_step(db):
    user = UserFactory()
    execution = FlowExecutionFactory(
        flow_run_id=uuid.uuid4(),
        flow_name="data-processing",
        triggered_by=user,
    )
    step = ExecutionStep.objects.create(
        execution=execution,
        step_index=0,
        step_name="01_ingest",
        status=ExecutionStatus.PENDING,
    )
    return execution, step


def _post_step_status(client, payload, secret="test-secret-xyz"):
    return client.post(
        "/internal/step-status/",
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {secret}",
    )


@pytest.mark.django_db
def test_step_status_requires_bearer_token(step_status_client, execution_with_step):
    execution, _ = execution_with_step
    resp = step_status_client.post(
        "/internal/step-status/",
        data=json.dumps(
            {
                "run_id": str(execution.flow_run_id),
                "step_index": 0,
                "step_name": "01_ingest",
                "status": "RUNNING",
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_step_status_rejects_wrong_token(step_status_client, execution_with_step):
    execution, _ = execution_with_step
    resp = _post_step_status(
        step_status_client,
        {
            "run_id": str(execution.flow_run_id),
            "step_index": 0,
            "step_name": "01_ingest",
            "status": "RUNNING",
        },
        secret="wrong-token",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_step_status_marks_step_running(step_status_client, execution_with_step):
    execution, step = execution_with_step
    resp = _post_step_status(
        step_status_client,
        {
            "run_id": str(execution.flow_run_id),
            "step_index": 0,
            "step_name": "01_ingest",
            "status": "RUNNING",
        },
    )
    assert resp.status_code == 200
    step.refresh_from_db()
    assert step.status == ExecutionStatus.RUNNING
    assert step.started_at is not None


@pytest.mark.django_db
def test_step_status_marks_step_completed(step_status_client, execution_with_step):
    execution, step = execution_with_step
    resp = _post_step_status(
        step_status_client,
        {
            "run_id": str(execution.flow_run_id),
            "step_index": 0,
            "step_name": "01_ingest",
            "status": "COMPLETED",
        },
    )
    assert resp.status_code == 200
    step.refresh_from_db()
    assert step.status == ExecutionStatus.COMPLETED
    assert step.completed_at is not None


@pytest.mark.django_db
def test_step_status_marks_step_failed_with_message(step_status_client, execution_with_step):
    execution, step = execution_with_step
    resp = _post_step_status(
        step_status_client,
        {
            "run_id": str(execution.flow_run_id),
            "step_index": 0,
            "step_name": "01_ingest",
            "status": "FAILED",
            "error_message": "notebook exploded",
        },
    )
    assert resp.status_code == 200
    step.refresh_from_db()
    assert step.status == ExecutionStatus.FAILED
    assert "notebook exploded" in step.error_message


@pytest.mark.django_db
def test_step_status_creates_step_if_missing(step_status_client, db):
    """If the ExecutionStep row doesn't exist yet, it should be created."""
    user = UserFactory()
    execution = FlowExecutionFactory(flow_run_id=uuid.uuid4(), triggered_by=user)

    resp = _post_step_status(
        step_status_client,
        {
            "run_id": str(execution.flow_run_id),
            "step_index": 2,
            "step_name": "03_transform",
            "status": "RUNNING",
        },
    )
    assert resp.status_code == 200
    assert ExecutionStep.objects.filter(execution=execution, step_index=2).exists()


@pytest.mark.django_db
def test_step_status_returns_404_for_unknown_execution(step_status_client, settings, db):
    settings.PREFECT_INTERNAL_SECRET = "test-secret-xyz"
    resp = _post_step_status(
        step_status_client,
        {
            "run_id": str(uuid.uuid4()),
            "step_index": 0,
            "step_name": "01_ingest",
            "status": "RUNNING",
        },
    )
    assert resp.status_code == 404


@pytest.mark.django_db
def test_step_status_rejects_invalid_status(step_status_client, execution_with_step):
    execution, _ = execution_with_step
    resp = _post_step_status(
        step_status_client,
        {
            "run_id": str(execution.flow_run_id),
            "step_index": 0,
            "step_name": "01_ingest",
            "status": "UNKNOWN_STATE",
        },
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_step_status_disabled_when_secret_empty(settings, execution_with_step, db):
    """Endpoint returns 403 if PREFECT_INTERNAL_SECRET is not configured."""
    settings.PREFECT_INTERNAL_SECRET = ""
    execution, _ = execution_with_step
    client = Client()
    resp = client.post(
        "/internal/step-status/",
        data=json.dumps(
            {
                "run_id": str(execution.flow_run_id),
                "step_index": 0,
                "step_name": "01_ingest",
                "status": "RUNNING",
            }
        ),
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer ",
    )
    assert resp.status_code == 403
