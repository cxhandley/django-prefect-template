"""
Tests for flows views: dashboard, history, detail, comparison, upload,
prediction, status polling, stop, and delete.
"""

import uuid
from unittest.mock import MagicMock

import polars as pl
import pytest
from apps.flows.models import FlowExecution
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
# comparison
# ============================================================================


@pytest.mark.django_db
def test_comparison_view(authenticated_client, user, flow_execution_factory):
    ex1 = make_completed(flow_execution_factory, user)
    ex2 = make_completed(flow_execution_factory, user)
    response = authenticated_client.get(
        f"/flows/comparison/?ids={ex1.flow_run_id},{ex2.flow_run_id}"
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_comparison_empty(authenticated_client):
    response = authenticated_client.get("/flows/comparison/")
    assert response.status_code == 200


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
def test_download_results_parquet(authenticated_client, user, flow_execution_factory, mock_s3):
    execution = flow_execution_factory(
        triggered_by=user,
        s3_output_path="processed/output.parquet",
    )
    response = authenticated_client.get(f"/flows/results/{execution.flow_run_id}/download/parquet/")
    # Presigned URL redirect
    assert response.status_code == 302


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
