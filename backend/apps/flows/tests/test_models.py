import boto3
import pytest
from apps.flows.models import FlowExecution
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestFlowExecution:
    """Test FlowExecution model"""

    def test_create_flow_execution(self, user_factory):
        user = user_factory()
        execution = FlowExecution.objects.create(
            flow_run_id="550e8400-e29b-41d4-a716-446655440000",
            flow_name="data-processing",
            triggered_by=user,
            s3_input_path="raw/uploads/1/test.csv",
            s3_output_path="processed/flows/data-processing/123/output.parquet",
        )

        assert execution.flow_name == "data-processing"
        assert execution.triggered_by == user
        assert execution.status == "PENDING"
        assert execution.celery_task_id == ""
        assert execution.error_message == ""

    def test_s3_url_properties(self, flow_execution_factory, settings):
        settings.DATA_LAKE_BUCKET = "test-bucket"
        execution = flow_execution_factory(
            s3_input_path="raw/data.csv",
            s3_output_path="processed/output.parquet",
        )

        assert execution.s3_input_url == "s3://test-bucket/raw/data.csv"
        assert execution.s3_output_url == "s3://test-bucket/processed/output.parquet"

    def test_generate_download_url(self, flow_execution_factory, mock_s3, settings):
        settings.DOWNLOAD_URL_EXPIRY_SECONDS = 3600
        execution = flow_execution_factory(s3_output_path="processed/output.parquet")

        url = execution.generate_download_url()

        assert url is not None
        assert "processed/output.parquet" in url
        assert "X-Amz-Expires=3600" in url

    def test_generate_download_url_uses_expiry_setting(
        self, flow_execution_factory, mock_s3, settings
    ):
        settings.DOWNLOAD_URL_EXPIRY_SECONDS = 900
        execution = flow_execution_factory(s3_output_path="processed/output.parquet")

        url = execution.generate_download_url()

        assert "X-Amz-Expires=900" in url

    def test_generate_download_url_sets_content_disposition(
        self, flow_execution_factory, mock_s3, settings
    ):
        settings.DOWNLOAD_URL_EXPIRY_SECONDS = 3600
        execution = flow_execution_factory(s3_output_path="processed/output.parquet")

        url = execution.generate_download_url(filename="results.parquet")

        assert "results.parquet" in url
        assert "response-content-disposition" in url

    def test_generate_download_url_default_filename(
        self, flow_execution_factory, mock_s3, settings
    ):
        settings.DOWNLOAD_URL_EXPIRY_SECONDS = 3600
        execution = flow_execution_factory(s3_output_path="processed/flows/run/output.parquet")

        url = execution.generate_download_url()

        assert "output.parquet" in url

    def test_generate_download_url_no_output_path(self, flow_execution_factory, mock_s3):
        execution = flow_execution_factory(s3_output_path="")

        assert execution.generate_download_url() is None

    def test_celery_task_id_stored(self, flow_execution_factory):
        execution = flow_execution_factory(celery_task_id="abc-123-task")
        assert execution.celery_task_id == "abc-123-task"

    def test_delete_removes_s3_objects(self, flow_execution_factory, mock_s3, settings):
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.put_object(Bucket="test-bucket", Key="raw/input.csv", Body=b"data")
        s3.put_object(Bucket="test-bucket", Key="processed/output.parquet", Body=b"data")

        execution = flow_execution_factory(
            s3_input_path="raw/input.csv",
            s3_output_path="processed/output.parquet",
        )
        execution.delete()

        objects = s3.list_objects_v2(Bucket="test-bucket").get("Contents", [])
        keys = [obj["Key"] for obj in objects]
        assert "raw/input.csv" not in keys
        assert "processed/output.parquet" not in keys
        assert not FlowExecution.objects.filter(pk=execution.pk).exists()

    def test_delete_idempotent_when_s3_objects_absent(self, flow_execution_factory, mock_s3):
        execution = flow_execution_factory(
            s3_input_path="raw/nonexistent.csv",
            s3_output_path="processed/nonexistent.parquet",
        )
        # Should not raise even though S3 objects do not exist
        execution.delete()
        assert not FlowExecution.objects.filter(pk=execution.pk).exists()

    def test_delete_with_no_s3_paths(self, flow_execution_factory, mock_s3):
        execution = flow_execution_factory(s3_input_path="", s3_output_path="")
        execution.delete()
        assert not FlowExecution.objects.filter(pk=execution.pk).exists()
