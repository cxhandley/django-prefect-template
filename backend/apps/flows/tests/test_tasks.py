"""
Tests for Celery tasks: run_pipeline_task, run_prediction_task.
Tasks are invoked via .apply() so they execute synchronously in tests.
"""

import pytest
from apps.flows.tasks import run_pipeline_task, run_prediction_task


def _make_execution(factory, user, flow_name="data-processing", **kwargs):
    return factory(
        triggered_by=user,
        flow_name=flow_name,
        status="RUNNING",
        **kwargs,
    )


# ============================================================================
# run_pipeline_task
# ============================================================================


@pytest.mark.django_db
def test_run_pipeline_task_success(flow_execution_factory, user, mocker):
    execution = _make_execution(flow_execution_factory, user)
    run_id = str(execution.flow_run_id)

    mocker.patch(
        "apps.flows.tasks.PipelineRunner.run_pipeline",
        return_value={
            "s3_output_path": "processed/output.parquet",
            "row_count": 42,
        },
    )

    result = run_pipeline_task.apply(
        kwargs={
            "flow_run_id": run_id,
            "input_s3_path": "s3://bucket/raw/input.csv",
            "user_id": user.id,
        }
    )

    assert result.successful()
    assert result.result["row_count"] == 42

    execution.refresh_from_db()
    assert execution.status == "COMPLETED"
    assert execution.row_count == 42
    assert execution.s3_output_path == "processed/output.parquet"


@pytest.mark.django_db
def test_run_pipeline_task_failure(flow_execution_factory, user, mocker):
    execution = _make_execution(flow_execution_factory, user)
    run_id = str(execution.flow_run_id)

    mocker.patch(
        "apps.flows.tasks.PipelineRunner.run_pipeline",
        side_effect=RuntimeError("doit failed"),
    )
    # Prevent actual retries
    mocker.patch.object(run_pipeline_task, "retry", side_effect=RuntimeError("doit failed"))

    with pytest.raises(RuntimeError):
        run_pipeline_task.apply(
            kwargs={
                "flow_run_id": run_id,
                "input_s3_path": "s3://bucket/raw/input.csv",
                "user_id": user.id,
            },
            throw=True,
        )

    execution.refresh_from_db()
    assert execution.status == "FAILED"
    assert "doit failed" in execution.error_message


# ============================================================================
# run_prediction_task
# ============================================================================


@pytest.mark.django_db
def test_run_prediction_task_success(flow_execution_factory, user, mocker):
    execution = _make_execution(flow_execution_factory, user, flow_name="credit-prediction")
    run_id = str(execution.flow_run_id)

    mocker.patch(
        "apps.flows.tasks.PipelineRunner.run_pipeline",
        return_value={
            "score": 0.82,
            "classification": "Approved",
            "confidence": 82,
            "s3_output_path": "processed/output.parquet",
            "row_count": 1,
        },
    )

    result = run_prediction_task.apply(
        kwargs={
            "flow_run_id": run_id,
            "input_s3_path": "s3://bucket/raw/prediction.csv",
            "user_id": user.id,
        }
    )

    assert result.successful()

    execution.refresh_from_db()
    assert execution.status == "COMPLETED"
    # BL-026: results are stored in PredictionResult, not the parameters blob
    pr = execution.prediction_result
    assert pr.score == 0.82
    assert pr.classification == "Approved"


@pytest.mark.django_db
def test_run_prediction_task_failure(flow_execution_factory, user, mocker):
    execution = _make_execution(flow_execution_factory, user, flow_name="credit-prediction")
    run_id = str(execution.flow_run_id)

    mocker.patch(
        "apps.flows.tasks.PipelineRunner.run_pipeline",
        side_effect=RuntimeError("prediction failed"),
    )
    mocker.patch.object(run_prediction_task, "retry", side_effect=RuntimeError("prediction failed"))

    with pytest.raises(RuntimeError):
        run_prediction_task.apply(
            kwargs={
                "flow_run_id": run_id,
                "input_s3_path": "s3://bucket/raw/prediction.csv",
                "user_id": user.id,
            },
            throw=True,
        )

    execution.refresh_from_db()
    assert execution.status == "FAILED"
    assert "prediction failed" in execution.error_message


# ============================================================================
# BL-011 — _send_failure_notification unit tests
# ============================================================================


@pytest.mark.django_db
def test_send_failure_notification_sends_email(user, mocker, settings):
    """Email is sent to user when notify_on_failure=True."""
    import uuid

    from apps.accounts.models import UserProfile
    from apps.flows.tasks import _send_failure_notification

    UserProfile.objects.get_or_create(user=user, defaults={"notify_on_failure": True})
    settings.SITE_URL = "http://testserver"
    mock_send = mocker.patch("apps.flows.tasks.send_mail")

    run_id = uuid.uuid4()
    _send_failure_notification(run_id, user.id, "pipeline", "Something broke")

    assert mock_send.called
    call_kwargs = mock_send.call_args[1]
    assert user.email in call_kwargs["recipient_list"]
    assert "pipeline" in call_kwargs["subject"]


@pytest.mark.django_db
def test_send_failure_notification_respects_opt_out(user, mocker, settings):
    """No email when notify_on_failure=False."""
    import uuid

    from apps.accounts.models import UserProfile
    from apps.flows.tasks import _send_failure_notification

    UserProfile.objects.update_or_create(user=user, defaults={"notify_on_failure": False})
    settings.SITE_URL = "http://testserver"
    mock_send = mocker.patch("apps.flows.tasks.send_mail")

    run_id = uuid.uuid4()
    _send_failure_notification(run_id, user.id, "pipeline", "Something broke")

    assert not mock_send.called


@pytest.mark.django_db
def test_send_failure_notification_silent_for_missing_user(mocker, settings):
    """No exception raised when user_id does not exist."""
    import uuid

    from apps.flows.tasks import _send_failure_notification

    settings.SITE_URL = "http://testserver"
    mocker.patch("apps.flows.tasks.send_mail")

    # Should not raise even if user does not exist
    _send_failure_notification(uuid.uuid4(), user_id=99999, flow_name="pipeline", error="err")
