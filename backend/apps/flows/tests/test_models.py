import pytest
from django.contrib.auth import get_user_model
from apps.flows.models import FlowExecution

User = get_user_model()

@pytest.mark.django_db
class TestFlowExecution:
    """Test FlowExecution model"""
    
    def test_create_flow_execution(self, user_factory):
        """Test creating a flow execution record"""
        # RED: Write test first (will fail)
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
        assert execution.status == "PENDING"  # Default status
    
    def test_s3_url_properties(self, flow_execution_factory):
        """Test S3 URL property methods"""
        execution = flow_execution_factory(
            s3_input_path="raw/data.csv",
            s3_output_path="processed/output.parquet"
        )
        
        assert execution.s3_input_url == "s3://test-bucket/raw/data.csv"
        assert execution.s3_output_url == "s3://test-bucket/processed/output.parquet"
    
    def test_generate_download_url(self, flow_execution_factory, mock_s3):
        """Test presigned URL generation"""
        execution = flow_execution_factory(
            s3_output_path="processed/output.parquet"
        )
        
        url = execution.generate_download_url(expires_in=3600)
        
        assert url is not None
        assert "processed/output.parquet" in url
        assert "X-Amz-Expires=3600" in url