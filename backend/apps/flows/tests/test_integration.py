import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.flows.models import FlowExecution


@pytest.mark.django_db
def test_upload_triggers_celery_task(authenticated_client, mock_pipeline_task, mock_s3, settings):
    """Upload should save to S3, create FlowExecution, and enqueue a Celery task."""
    settings.DATA_LAKE_BUCKET = 'test-bucket'

    csv_content = (
        b"id,amount,quantity,customer_id,transaction_date\n"
        b"1,100,2,cust1,2024-01-15\n"
        b"2,200,1,cust2,2024-02-20\n"
    )
    uploaded = SimpleUploadedFile("test.csv", csv_content, content_type="text/csv")

    response = authenticated_client.post(
        '/flows/upload-and-process/',
        {'datafile': uploaded},
    )

    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'RUNNING'
    run_id = data['run_id']

    # Execution record created
    execution = FlowExecution.objects.get(flow_run_id=run_id)
    assert execution.status == 'RUNNING'
    assert execution.celery_task_id == 'mock-celery-task-id-1234'

    # Celery task enqueued with correct args
    mock_pipeline_task.delay.assert_called_once_with(
        flow_run_id=run_id,
        input_s3_path=f"s3://test-bucket/raw/uploads/{execution.triggered_by.id}/{run_id}/test.csv",
        user_id=execution.triggered_by.id,
    )


@pytest.mark.django_db
def test_flow_status_endpoint(authenticated_client, flow_execution_factory, user):
    """Status endpoint should return current execution state."""
    execution = flow_execution_factory(
        triggered_by=user,
        status='COMPLETED',
        row_count=42,
    )

    response = authenticated_client.get(f'/flows/status/{execution.flow_run_id}/')

    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'COMPLETED'
    assert data['row_count'] == 42


@pytest.mark.django_db
def test_upload_requires_file(authenticated_client):
    """Upload without a file should return 400."""
    response = authenticated_client.post('/flows/upload-and-process/', {})
    assert response.status_code == 400
