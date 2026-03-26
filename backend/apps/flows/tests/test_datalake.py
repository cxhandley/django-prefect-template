import pytest
import polars as pl
import boto3
from moto import mock_aws
from apps.flows.services.datalake import DataLakeAnalytics


@pytest.mark.django_db
class TestDataLakeAnalytics:
    """Test DuckDB analytics service against mock S3."""

    @pytest.fixture
    def analytics(self, settings):
        """Create analytics service with test S3 credentials."""
        settings.AWS_ACCESS_KEY_ID = 'testing'
        settings.AWS_SECRET_ACCESS_KEY = 'testing'
        settings.AWS_S3_REGION_NAME = 'us-east-1'
        settings.AWS_S3_ENDPOINT_URL = None
        settings.DATA_LAKE_BUCKET = 'test-bucket'
        settings.DUCKDB_THREADS = 1
        settings.DUCKDB_MEMORY_LIMIT = '512MB'
        return DataLakeAnalytics()

    @pytest.fixture
    def sample_parquet(self, mock_s3, tmp_path):
        """Create sample Parquet file in mock S3."""
        df = pl.DataFrame({
            'year_month': ['2024-01', '2024-02', '2024-03'],
            'amount_category': ['high', 'medium', 'low'],
            'total_revenue': [1000.0, 1500.0, 2000.0],
            'transaction_count': [10, 15, 20],
            'unique_customers': [5, 8, 12],
            'avg_transaction_value': [100.0, 100.0, 100.0],
        })

        parquet_path = tmp_path / "test.parquet"
        df.write_parquet(parquet_path)

        mock_s3.upload_file(
            str(parquet_path),
            'test-bucket',
            'processed/flows/test-flow/123/output.parquet',
        )

        return 'processed/flows/test-flow/123/output.parquet'

    def test_get_flow_results(self, analytics, sample_parquet):
        result = analytics.get_flow_results(sample_parquet, limit=100)

        assert len(result) == 3
        assert 'year_month' in result.columns
        assert 'total_revenue' in result.columns

    def test_get_summary_stats(self, analytics, sample_parquet):
        stats = analytics.get_summary_stats(sample_parquet)

        assert stats['total_rows'] == 3
        assert stats['grand_total_revenue'] == 4500.0
        assert stats['max_customers'] == 12

    def test_context_manager(self, settings):
        """Analytics can be used as a context manager."""
        settings.AWS_ACCESS_KEY_ID = 'testing'
        settings.AWS_SECRET_ACCESS_KEY = 'testing'
        settings.AWS_S3_REGION_NAME = 'us-east-1'
        settings.AWS_S3_ENDPOINT_URL = None
        settings.DATA_LAKE_BUCKET = 'test-bucket'
        settings.DUCKDB_THREADS = 1
        settings.DUCKDB_MEMORY_LIMIT = '512MB'

        with DataLakeAnalytics() as analytics:
            assert analytics.conn is not None

    def test_query_across_flows(self, settings, mock_s3, tmp_path):
        settings.AWS_ACCESS_KEY_ID = 'testing'
        settings.AWS_SECRET_ACCESS_KEY = 'testing'
        settings.AWS_S3_REGION_NAME = 'us-east-1'
        settings.AWS_S3_ENDPOINT_URL = None
        settings.DATA_LAKE_BUCKET = 'test-bucket'
        settings.DUCKDB_THREADS = 1
        settings.DUCKDB_MEMORY_LIMIT = '512MB'

        for i in range(3):
            df = pl.DataFrame({
                'year_month': [f'2024-0{i + 1}'],
                'total_revenue': [1000.0 * (i + 1)],
                'transaction_count': [10 * (i + 1)],
            })
            parquet_path = tmp_path / f"test{i}.parquet"
            df.write_parquet(parquet_path)
            mock_s3.upload_file(
                str(parquet_path),
                'test-bucket',
                f'processed/flows/test-flow/{i}/output.parquet',
            )

        with DataLakeAnalytics() as analytics:
            result = analytics.query_across_flows(
                'test-flow',
                start_date='2024-01',
                end_date='2024-12',
            )

        assert len(result) == 3
        assert result['total_revenue'].sum() == 6000.0
