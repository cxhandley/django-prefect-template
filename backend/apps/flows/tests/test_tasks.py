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
    assert execution.parameters["score"] == 0.82
    assert execution.parameters["classification"] == "Approved"


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
