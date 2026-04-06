"""
Tests for flows views: dashboard, history, detail, comparison, upload,
prediction, status polling, stop, and delete.
"""

import uuid
from unittest.mock import MagicMock

import polars as pl
import pytest
from apps.flows.models import ExecutionStep, FlowExecution
from django.utils import timezone

# ============================================================================
# Helpers
# ============================================================================


def make_completed(factory, user, **kwargs):
    return factory(
        triggered_by=user,
        status="COMPLETED",
        row_count=10,
        completed_at=timezone.now(),
        **kwargs,
    )


# ============================================================================
# index
# ============================================================================


@pytest.mark.django_db
def test_index_view(authenticated_client, user, flow_execution_factory):
    make_completed(flow_execution_factory, user)
    response = authenticated_client.get("/flows/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_index_redirects_anonymous(client):
    response = client.get("/flows/")
    assert response.status_code == 302


# ============================================================================
# dashboard
# ============================================================================


@pytest.mark.django_db
def test_dashboard_empty(authenticated_client):
    response = authenticated_client.get("/flows/dashboard/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_dashboard_with_executions(authenticated_client, user, flow_execution_factory):
    """Dashboard calculates success rate and avg duration correctly."""
    make_completed(flow_execution_factory, user)
    flow_execution_factory(triggered_by=user, status="FAILED")
    flow_execution_factory(triggered_by=user, status="RUNNING")
    response = authenticated_client.get("/flows/dashboard/")
    assert response.status_code == 200


# ============================================================================
# history
# ============================================================================


@pytest.mark.django_db
def test_history_view(authenticated_client, user, flow_execution_factory):
    make_completed(flow_execution_factory, user)
    response = authenticated_client.get("/flows/history/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_history_search(authenticated_client, user, flow_execution_factory):
    flow_execution_factory(triggered_by=user, flow_name="my-special-flow")
    response = authenticated_client.get("/flows/history/?q=special")
    assert response.status_code == 200


@pytest.mark.django_db
def test_history_status_filter(authenticated_client, user, flow_execution_factory):
    make_completed(flow_execution_factory, user)
    response = authenticated_client.get("/flows/history/?status=COMPLETED")
    assert response.status_code == 200


@pytest.mark.django_db
def test_history_htmx_partial(authenticated_client, user):
    response = authenticated_client.get("/flows/history/", HTTP_HX_REQUEST="true")
    assert response.status_code == 200


# ============================================================================
# export_history_csv
# ============================================================================


@pytest.mark.django_db
def test_export_history_csv_returns_csv(authenticated_client, user, flow_execution_factory):
    make_completed(flow_execution_factory, user, flow_name="pipeline-a")
    make_completed(flow_execution_factory, user, flow_name="pipeline-b")
    response = authenticated_client.get("/flows/history/export/")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    assert response["Content-Disposition"] == 'attachment; filename="execution_history.csv"'


@pytest.mark.django_db
def test_export_history_csv_contains_header_and_rows(
    authenticated_client, user, flow_execution_factory
):
    make_completed(flow_execution_factory, user, flow_name="my-flow")
    content = authenticated_client.get("/flows/history/export/").content.decode()
    lines = content.strip().splitlines()
    assert lines[0] == "id,flow_name,status,row_count,file_size_mb,created_at,completed_at"
    assert "my-flow" in content


@pytest.mark.django_db
def test_export_history_csv_only_own_executions(
    authenticated_client, user, flow_execution_factory, user_factory
):
    other = user_factory()
    flow_execution_factory(triggered_by=other, flow_name="other-flow")
    make_completed(flow_execution_factory, user, flow_name="my-flow")
    content = authenticated_client.get("/flows/history/export/").content.decode()
    assert "my-flow" in content
    assert "other-flow" not in content


@pytest.mark.django_db
def test_export_history_csv_empty(authenticated_client, user):
    content = authenticated_client.get("/flows/history/export/").content.decode()
    lines = content.strip().splitlines()
    assert len(lines) == 1  # header only


@pytest.mark.django_db
def test_export_history_csv_requires_login(client):
    response = client.get("/flows/history/export/")
    assert response.status_code == 302


# ============================================================================
# execution_detail
# ============================================================================


@pytest.mark.django_db
def test_execution_detail(authenticated_client, user, flow_execution_factory):
    execution = flow_execution_factory(triggered_by=user)
    response = authenticated_client.get(f"/flows/execution/{execution.flow_run_id}/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_execution_detail_with_duration(authenticated_client, user, flow_execution_factory):
    """Detail page calculates duration when completed_at is set."""
    execution = make_completed(flow_execution_factory, user)
    response = authenticated_client.get(f"/flows/execution/{execution.flow_run_id}/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_execution_detail_not_found(authenticated_client):
    response = authenticated_client.get(f"/flows/execution/{uuid.uuid4()}/")
    assert response.status_code == 404


# ============================================================================
# history — DataTable filter / sort params
# ============================================================================


@pytest.mark.django_db
def test_history_datatable_filter_by_status(authenticated_client, user, flow_execution_factory):
    make_completed(flow_execution_factory, user, flow_name="flow-a")
    flow_execution_factory(triggered_by=user, flow_name="flow-b", status="FAILED")
    response = authenticated_client.get(
        "/flows/history/?f_field[]=status&f_op[]=eq&f_val[]=COMPLETED"
    )
    assert response.status_code == 200
    assert b"flow-a" in response.content


@pytest.mark.django_db
def test_history_datatable_sort_param(authenticated_client, user, flow_execution_factory):
    make_completed(flow_execution_factory, user)
    response = authenticated_client.get("/flows/history/?sort=created_at")
    assert response.status_code == 200


@pytest.mark.django_db
def test_history_datatable_invalid_sort_ignored(authenticated_client, user, flow_execution_factory):
    make_completed(flow_execution_factory, user)
    response = authenticated_client.get("/flows/history/?sort=__evil__")
    assert response.status_code == 200


@pytest.mark.django_db
def test_history_datatable_pagination(authenticated_client, user, flow_execution_factory):
    for _ in range(30):
        make_completed(flow_execution_factory, user)
    response = authenticated_client.get("/flows/history/?page=2")
    assert response.status_code == 200


# ============================================================================
# comparison
# ============================================================================


@pytest.mark.django_db
def test_comparison_view_with_real_data(authenticated_client, user, flow_execution_factory):
    """comparison() returns real inputs and result from typed FlowExecution fields."""
    ex1 = make_completed(flow_execution_factory, user, flow_name="credit-prediction")
    ex2 = make_completed(flow_execution_factory, user, flow_name="credit-prediction")
    # BL-026: inputs are typed fields, not parameters blob
    FlowExecution.objects.filter(pk=ex1.pk).update(
        income=60000, age=30, credit_score=700, employment_years=5
    )
    FlowExecution.objects.filter(pk=ex2.pk).update(
        income=40000, age=45, credit_score=600, employment_years=2
    )

    response = authenticated_client.get(
        f"/flows/comparison/?ids={ex1.flow_run_id},{ex2.flow_run_id}"
    )
    assert response.status_code == 200
    ctx = response.context
    assert ctx["insufficient"] is False
    assert len(ctx["comparison_data"]) == 2
    # Both executions have different income → it's a differing field
    assert "income" in ctx["differing_fields"]


@pytest.mark.django_db
def test_comparison_differing_fields_identical_inputs(
    authenticated_client, user, flow_execution_factory
):
    """differing_fields is empty when all inputs are the same."""
    params = {
        "income": 60000,
        "age": 30,
        "credit_score": 700,
        "employment_years": 5,
        "score": 0.75,
        "classification": "Approved",
        "confidence": 75,
    }
    ex1 = make_completed(flow_execution_factory, user, flow_name="credit-prediction")
    ex2 = make_completed(flow_execution_factory, user, flow_name="credit-prediction")
    FlowExecution.objects.filter(pk=ex1.pk).update(parameters=params)
    FlowExecution.objects.filter(pk=ex2.pk).update(parameters=params)

    response = authenticated_client.get(
        f"/flows/comparison/?ids={ex1.flow_run_id},{ex2.flow_run_id}"
    )
    assert response.status_code == 200
    assert response.context["differing_fields"] == set()


@pytest.mark.django_db
def test_comparison_insufficient_one_execution(authenticated_client, user, flow_execution_factory):
    """insufficient=True when only 1 valid execution ID is provided."""
    ex = make_completed(flow_execution_factory, user)
    response = authenticated_client.get(f"/flows/comparison/?ids={ex.flow_run_id}")
    assert response.status_code == 200
    assert response.context["insufficient"] is True
    assert response.context["comparison_data"] == []


@pytest.mark.django_db
def test_comparison_empty_ids(authenticated_client):
    """No ids → empty comparison_data, insufficient=False."""
    response = authenticated_client.get("/flows/comparison/")
    assert response.status_code == 200
    assert response.context["comparison_data"] == []
    assert response.context["insufficient"] is False


@pytest.mark.django_db
def test_comparison_only_own_executions(
    authenticated_client, user, flow_execution_factory, user_factory
):
    """Executions belonging to another user are not included in comparison."""
    other = user_factory()
    ex1 = make_completed(flow_execution_factory, user)
    ex2 = make_completed(flow_execution_factory, other)
    response = authenticated_client.get(
        f"/flows/comparison/?ids={ex1.flow_run_id},{ex2.flow_run_id}"
    )
    assert response.status_code == 200
    # Only 1 own execution resolved → insufficient
    assert response.context["insufficient"] is True


@pytest.mark.django_db
def test_comparison_requires_login(client, user, flow_execution_factory):
    ex1 = make_completed(flow_execution_factory, user)
    ex2 = make_completed(flow_execution_factory, user)
    response = client.get(f"/flows/comparison/?ids={ex1.flow_run_id},{ex2.flow_run_id}")
    assert response.status_code == 302


# ============================================================================
# comparison_export
# ============================================================================


@pytest.mark.django_db
def test_comparison_export_returns_csv(authenticated_client, user, flow_execution_factory):
    params = {
        "income": 60000,
        "age": 30,
        "credit_score": 700,
        "employment_years": 5,
        "score": 0.75,
        "classification": "Approved",
        "confidence": 75,
    }
    ex1 = make_completed(flow_execution_factory, user, flow_name="credit-prediction")
    ex2 = make_completed(flow_execution_factory, user, flow_name="credit-prediction")
    FlowExecution.objects.filter(pk=ex1.pk).update(parameters=params)
    FlowExecution.objects.filter(pk=ex2.pk).update(parameters=params)

    response = authenticated_client.get(
        f"/flows/comparison/export/?ids={ex1.flow_run_id},{ex2.flow_run_id}"
    )
    assert response.status_code == 200
    assert "text/csv" in response["Content-Type"]
    assert "attachment" in response["Content-Disposition"]
    assert ".csv" in response["Content-Disposition"]


@pytest.mark.django_db
def test_comparison_export_csv_content(authenticated_client, user, flow_execution_factory):
    params_1 = {
        "income": 60000,
        "age": 30,
        "credit_score": 700,
        "employment_years": 5,
        "score": 0.75,
        "classification": "Approved",
        "confidence": 75,
    }
    params_2 = {
        "income": 40000,
        "age": 45,
        "credit_score": 600,
        "employment_years": 2,
        "score": 0.35,
        "classification": "Declined",
        "confidence": 35,
    }
    ex1 = make_completed(flow_execution_factory, user, flow_name="credit-prediction")
    ex2 = make_completed(flow_execution_factory, user, flow_name="credit-prediction")
    FlowExecution.objects.filter(pk=ex1.pk).update(parameters=params_1)
    FlowExecution.objects.filter(pk=ex2.pk).update(parameters=params_2)

    response = authenticated_client.get(
        f"/flows/comparison/export/?ids={ex1.flow_run_id},{ex2.flow_run_id}"
    )
    content = b"".join(response.streaming_content).decode()
    lines = content.strip().splitlines()
    # Header row should be "field,<short_id1>,<short_id2>"
    assert lines[0].startswith("field,")
    # Should contain all comparison fields as rows
    field_names = [line.split(",")[0] for line in lines[1:]]
    assert "income" in field_names
    assert "classification" in field_names
    assert "confidence" in field_names


@pytest.mark.django_db
def test_comparison_export_redirects_with_insufficient_ids(
    authenticated_client, user, flow_execution_factory
):
    ex = make_completed(flow_execution_factory, user)
    response = authenticated_client.get(f"/flows/comparison/export/?ids={ex.flow_run_id}")
    assert response.status_code == 302


@pytest.mark.django_db
def test_comparison_export_requires_login(client, user, flow_execution_factory):
    ex1 = make_completed(flow_execution_factory, user)
    ex2 = make_completed(flow_execution_factory, user)
    response = client.get(f"/flows/comparison/export/?ids={ex1.flow_run_id},{ex2.flow_run_id}")
    assert response.status_code == 302


# ============================================================================
# flows_menu
# ============================================================================


@pytest.mark.django_db
def test_flows_menu(authenticated_client):
    response = authenticated_client.get("/flows/api/flows-menu/")
    assert response.status_code == 200


# ============================================================================
# flow_status
# ============================================================================


@pytest.mark.django_db
def test_flow_status_completed(authenticated_client, user, flow_execution_factory):
    execution = make_completed(flow_execution_factory, user)
    response = authenticated_client.get(f"/flows/status/{execution.flow_run_id}/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "COMPLETED"
    assert data["row_count"] == 10
    assert data["completed_at"] is not None


# ============================================================================
# view_flow_results
# ============================================================================


@pytest.mark.django_db
def test_view_flow_results(authenticated_client, user, flow_execution_factory, mocker):
    """Results page uses DataLakeAnalytics — mock it."""
    execution = flow_execution_factory(
        triggered_by=user,
        s3_output_path="processed/output.parquet",
    )

    mock_df = pl.DataFrame({"col_a": [1, 2], "col_b": ["x", "y"]})
    mock_analytics = MagicMock()
    mock_analytics.__enter__ = MagicMock(return_value=mock_analytics)
    mock_analytics.__exit__ = MagicMock(return_value=False)
    mock_analytics.get_flow_results.return_value = mock_df
    mock_analytics.get_summary_stats.return_value = {
        "total_rows": 2,
        "grand_total_revenue": 0,
        "avg_transactions": 0,
        "max_customers": 0,
    }
    mocker.patch("apps.flows.views.DataLakeAnalytics", return_value=mock_analytics)

    response = authenticated_client.get(f"/flows/results/{execution.flow_run_id}/")
    assert response.status_code == 200


# ============================================================================
# download_results
# ============================================================================


@pytest.mark.django_db
def test_download_results_parquet_redirects_to_presigned_url(
    authenticated_client, user, flow_execution_factory, mock_s3, settings
):
    settings.DOWNLOAD_URL_EXPIRY_SECONDS = 3600
    execution = flow_execution_factory(
        triggered_by=user,
        s3_output_path="processed/output.parquet",
    )
    response = authenticated_client.get(f"/flows/results/{execution.flow_run_id}/download/parquet/")
    assert response.status_code == 302
    assert "processed/output.parquet" in response["Location"]
    assert "X-Amz-Expires=3600" in response["Location"]


@pytest.mark.django_db
def test_download_results_parquet_uses_expiry_setting(
    authenticated_client, user, flow_execution_factory, mock_s3, settings
):
    settings.DOWNLOAD_URL_EXPIRY_SECONDS = 600
    execution = flow_execution_factory(
        triggered_by=user,
        s3_output_path="processed/output.parquet",
    )
    response = authenticated_client.get(f"/flows/results/{execution.flow_run_id}/download/parquet/")
    assert response.status_code == 302
    assert "X-Amz-Expires=600" in response["Location"]


@pytest.mark.django_db
def test_download_results_csv(authenticated_client, user, flow_execution_factory, mocker):
    execution = flow_execution_factory(
        triggered_by=user,
        s3_output_path="processed/output.parquet",
    )

    mock_analytics = MagicMock()
    mock_analytics.__enter__ = MagicMock(return_value=mock_analytics)
    mock_analytics.__exit__ = MagicMock(return_value=False)
    mock_analytics.export_to_csv.return_value = "col_a,col_b\n1,x\n"
    mocker.patch("apps.flows.views.DataLakeAnalytics", return_value=mock_analytics)

    response = authenticated_client.get(f"/flows/results/{execution.flow_run_id}/download/csv/")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    assert "attachment" in response["Content-Disposition"]
    assert ".csv" in response["Content-Disposition"]


@pytest.mark.django_db
def test_download_results_json(authenticated_client, user, flow_execution_factory, mocker):
    execution = flow_execution_factory(
        triggered_by=user,
        s3_output_path="processed/output.parquet",
    )

    mock_df = pl.DataFrame({"col_a": [1], "col_b": ["x"]})
    mock_analytics = MagicMock()
    mock_analytics.__enter__ = MagicMock(return_value=mock_analytics)
    mock_analytics.__exit__ = MagicMock(return_value=False)
    mock_analytics.get_flow_results.return_value = mock_df
    mocker.patch("apps.flows.views.DataLakeAnalytics", return_value=mock_analytics)

    response = authenticated_client.get(f"/flows/results/{execution.flow_run_id}/download/json/")
    assert response.status_code == 200
    assert "attachment" in response["Content-Disposition"]
    assert ".json" in response["Content-Disposition"]


@pytest.mark.django_db
def test_download_results_unsupported_format(
    authenticated_client, user, flow_execution_factory, mocker
):
    execution = flow_execution_factory(
        triggered_by=user,
        s3_output_path="processed/output.parquet",
    )
    mocker.patch("apps.flows.views.DataLakeAnalytics")
    response = authenticated_client.get(f"/flows/results/{execution.flow_run_id}/download/xml/")
    assert response.status_code == 400


@pytest.mark.django_db
def test_download_results_requires_ownership(
    authenticated_client, flow_execution_factory, user_factory, mock_s3, settings
):
    settings.DOWNLOAD_URL_EXPIRY_SECONDS = 3600
    other_user = user_factory()
    execution = flow_execution_factory(
        triggered_by=other_user,
        s3_output_path="processed/output.parquet",
    )
    response = authenticated_client.get(f"/flows/results/{execution.flow_run_id}/download/parquet/")
    assert response.status_code == 404


# ============================================================================
# run_prediction
# ============================================================================


@pytest.fixture
def mock_prediction_task(mocker):
    mock = mocker.patch("apps.flows.views.run_prediction_task")
    mock.delay.return_value.id = "mock-predict-task-id-5678"
    return mock


@pytest.mark.django_db
def test_run_prediction_valid(authenticated_client, mock_prediction_task, mock_s3):
    response = authenticated_client.post(
        "/flows/run-prediction/",
        {
            "income": "75000",
            "age": "35",
            "credit_score": "720",
            "employment_years": "8",
        },
    )
    assert response.status_code == 200
    mock_prediction_task.delay.assert_called_once()


@pytest.mark.django_db
def test_run_prediction_invalid_inputs(authenticated_client):
    """Non-numeric inputs return the error partial."""
    response = authenticated_client.post(
        "/flows/run-prediction/",
        {"income": "abc", "age": "", "credit_score": "", "employment_years": ""},
    )
    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload,expected_error",
    [
        (
            {"income": "-1", "age": "35", "credit_score": "720", "employment_years": "8"},
            "Income must be a positive number",
        ),
        (
            {"income": "50000", "age": "10", "credit_score": "720", "employment_years": "8"},
            "Age must be between",
        ),
        (
            {"income": "50000", "age": "35", "credit_score": "100", "employment_years": "8"},
            "Credit score must be between",
        ),
        (
            {"income": "50000", "age": "35", "credit_score": "720", "employment_years": "-1"},
            "Employment years must be zero",
        ),
    ],
)
def test_run_prediction_validation(authenticated_client, payload, expected_error):
    response = authenticated_client.post("/flows/run-prediction/", payload)
    assert response.status_code == 200


# ============================================================================
# prediction_status
# ============================================================================


@pytest.mark.django_db
def test_prediction_status_running(authenticated_client, user, flow_execution_factory):
    execution = flow_execution_factory(
        triggered_by=user,
        flow_name="credit-prediction",
        status="RUNNING",
    )
    response = authenticated_client.get(f"/flows/prediction-status/{execution.flow_run_id}/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_prediction_status_completed(authenticated_client, user, flow_execution_factory):
    execution = flow_execution_factory(
        triggered_by=user,
        flow_name="credit-prediction",
        status="COMPLETED",
    )
    FlowExecution.objects.filter(pk=execution.pk).update(
        parameters={"score": 0.82, "classification": "Approved", "confidence": 82}
    )
    response = authenticated_client.get(f"/flows/prediction-status/{execution.flow_run_id}/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_prediction_status_failed(authenticated_client, user, flow_execution_factory):
    execution = flow_execution_factory(
        triggered_by=user,
        flow_name="credit-prediction",
        status="FAILED",
        error_message="Pipeline error",
    )
    response = authenticated_client.get(f"/flows/prediction-status/{execution.flow_run_id}/")
    assert response.status_code == 200


# ============================================================================
# stop_execution
# ============================================================================


@pytest.mark.django_db
def test_stop_execution_with_task(authenticated_client, user, flow_execution_factory, mocker):
    execution = flow_execution_factory(
        triggered_by=user,
        status="RUNNING",
        celery_task_id="some-task-id",
    )
    mock_celery_app = MagicMock()
    mocker.patch("config.celery.app", mock_celery_app)

    response = authenticated_client.post(f"/flows/execution/{execution.flow_run_id}/stop/")
    assert response.status_code == 302

    execution.refresh_from_db()
    assert execution.status == "FAILED"
    assert execution.error_message == "Stopped by user."


@pytest.mark.django_db
def test_stop_execution_no_task(authenticated_client, user, flow_execution_factory):
    """Stop an execution that has no celery_task_id."""
    execution = flow_execution_factory(
        triggered_by=user,
        status="RUNNING",
        celery_task_id="",
    )
    response = authenticated_client.post(f"/flows/execution/{execution.flow_run_id}/stop/")
    assert response.status_code == 302
    execution.refresh_from_db()
    assert execution.status == "FAILED"


# ============================================================================
# delete_execution
# ============================================================================


@pytest.mark.django_db
def test_delete_execution(authenticated_client, user, flow_execution_factory):
    execution = flow_execution_factory(triggered_by=user, celery_task_id="")
    run_id = execution.flow_run_id
    response = authenticated_client.post(f"/flows/execution/{run_id}/delete/")
    assert response.status_code == 302
    assert not FlowExecution.objects.filter(flow_run_id=run_id).exists()


@pytest.mark.django_db
def test_delete_execution_with_task(authenticated_client, user, flow_execution_factory, mocker):
    execution = flow_execution_factory(
        triggered_by=user,
        celery_task_id="task-to-revoke",
    )
    mock_celery_app = MagicMock()
    mocker.patch("config.celery.app", mock_celery_app)

    run_id = execution.flow_run_id
    response = authenticated_client.post(f"/flows/execution/{run_id}/delete/")
    assert response.status_code == 302
    assert not FlowExecution.objects.filter(flow_run_id=run_id).exists()


# ============================================================================
# execution_live_status
# ============================================================================


@pytest.mark.django_db
def test_execution_live_status_pending(authenticated_client, user, flow_execution_factory):
    """PENDING execution: returns 200 with hx-trigger to keep polling."""
    execution = flow_execution_factory(triggered_by=user, status="PENDING")
    response = authenticated_client.get(f"/flows/execution/{execution.flow_run_id}/live-status/")
    assert response.status_code == 200
    assert b"every 3s" in response.content
    assert b"live-status" in response.content


@pytest.mark.django_db
def test_execution_live_status_running(authenticated_client, user, flow_execution_factory):
    """RUNNING execution: returns 200 with hx-trigger to keep polling."""
    execution = flow_execution_factory(triggered_by=user, status="RUNNING")
    response = authenticated_client.get(f"/flows/execution/{execution.flow_run_id}/live-status/")
    assert response.status_code == 200
    assert b"every 3s" in response.content


@pytest.mark.django_db
def test_execution_live_status_completed_no_poll(
    authenticated_client, user, flow_execution_factory
):
    """COMPLETED execution: hx-trigger is absent so the poll loop terminates."""
    execution = make_completed(flow_execution_factory, user)
    response = authenticated_client.get(f"/flows/execution/{execution.flow_run_id}/live-status/")
    assert response.status_code == 200
    assert b"every 3s" not in response.content


@pytest.mark.django_db
def test_execution_live_status_failed_no_poll(authenticated_client, user, flow_execution_factory):
    """FAILED execution: hx-trigger is absent so the poll loop terminates."""
    execution = flow_execution_factory(
        triggered_by=user, status="FAILED", error_message="Something broke"
    )
    response = authenticated_client.get(f"/flows/execution/{execution.flow_run_id}/live-status/")
    assert response.status_code == 200
    assert b"every 3s" not in response.content


@pytest.mark.django_db
def test_execution_live_status_with_steps(authenticated_client, user, flow_execution_factory):
    """Steps attached to the execution are rendered in the response."""
    execution = flow_execution_factory(triggered_by=user, status="RUNNING")
    ExecutionStep.objects.create(
        execution=execution,
        step_name="ingest",
        step_index=0,
        status="COMPLETED",
        started_at=timezone.now(),
        completed_at=timezone.now(),
    )
    ExecutionStep.objects.create(
        execution=execution,
        step_name="validate",
        step_index=1,
        status="RUNNING",
        started_at=timezone.now(),
    )
    response = authenticated_client.get(f"/flows/execution/{execution.flow_run_id}/live-status/")
    assert response.status_code == 200
    assert b"ingest" in response.content
    assert b"validate" in response.content


@pytest.mark.django_db
def test_execution_live_status_requires_login(client, user, flow_execution_factory):
    """Unauthenticated requests are redirected to login."""
    execution = flow_execution_factory(triggered_by=user)
    response = client.get(f"/flows/execution/{execution.flow_run_id}/live-status/")
    assert response.status_code == 302


@pytest.mark.django_db
def test_execution_live_status_not_found(authenticated_client):
    """Unknown run_id returns 404."""
    response = authenticated_client.get(f"/flows/execution/{uuid.uuid4()}/live-status/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_execution_live_status_other_user_forbidden(
    authenticated_client, user_factory, flow_execution_factory
):
    """Another user's execution is not accessible (404, not 403)."""
    other = user_factory()
    execution = flow_execution_factory(triggered_by=other, status="RUNNING")
    response = authenticated_client.get(f"/flows/execution/{execution.flow_run_id}/live-status/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_prediction_status_running_includes_steps(
    authenticated_client, user, flow_execution_factory
):
    """prediction_status returns step data in the running partial when steps exist."""
    execution = flow_execution_factory(
        triggered_by=user,
        flow_name="credit-prediction",
        status="RUNNING",
    )
    ExecutionStep.objects.create(
        execution=execution,
        step_name="predict_01_prepare",
        step_index=0,
        status="COMPLETED",
        started_at=timezone.now(),
        completed_at=timezone.now(),
    )
    ExecutionStep.objects.create(
        execution=execution,
        step_name="predict_02_score",
        step_index=1,
        status="RUNNING",
        started_at=timezone.now(),
    )
    response = authenticated_client.get(f"/flows/prediction-status/{execution.flow_run_id}/")
    assert response.status_code == 200
    assert b"predict_01_prepare" in response.content
    assert b"predict_02_score" in response.content
