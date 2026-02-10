import pytest
import polars as pl
from apps.flows.services.datalake import DataLakeAnalytics
from moto import mock_s3
import boto3

@pytest.mark.django_db
class TestDataLakeAnalytics:
    """Test DuckDB analytics service"""
    
    @pytest.fixture
    def analytics(self):
        """Create analytics service"""
        return DataLakeAnalytics()
    
    @pytest.fixture
    def sample_parquet(self, mock_s3, tmp_path):
        """Create sample Parquet file in mock S3"""
        # Create test data
        df = pl.DataFrame({
            'year_month': ['2024-01', '2024-02', '2024-03'],
            'total_revenue': [1000.0, 1500.0, 2000.0],
            'transaction_count': [10, 15, 20],
            'unique_customers': [5, 8, 12]
        })
        
        # Write to temp file
        parquet_path = tmp_path / "test.parquet"
        df.write_parquet(parquet_path)
        
        # Upload to mock S3
        mock_s3.upload_file(
            str(parquet_path),
            'test-bucket',
            'processed/flows/test-flow/123/output.parquet'
        )
        
        return 'processed/flows/test-flow/123/output.parquet'
    
    def test_get_flow_results(self, analytics, sample_parquet):
        """Test getting flow results preview"""
        # ACT
        result = analytics.get_flow_results(sample_parquet, limit=100)
        
        # ASSERT
        assert len(result) == 3
        assert 'year_month' in result.columns
        assert 'total_revenue' in result.columns
    
    def test_get_summary_stats(self, analytics, sample_parquet):
        """Test summary statistics calculation"""
        # ACT
        stats = analytics.get_summary_stats(sample_parquet)
        
        # ASSERT
        assert stats['total_rows'] == 3
        assert stats['grand_total_revenue'] == 4500.0
        assert stats['max_customers'] == 12
    
    def test_query_across_flows(self, analytics, mock_s3, tmp_path):
        """Test querying across multiple flow runs"""
        # ARRANGE: Create multiple Parquet files
        for i in range(3):
            df = pl.DataFrame({
                'year_month': [f'2024-0{i+1}'],
                'total_revenue': [1000.0 * (i+1)],
                'transaction_count': [10 * (i+1)]
            })
            parquet_path = tmp_path / f"test{i}.parquet"
            df.write_parquet(parquet_path)
            mock_s3.upload_file(
                str(parquet_path),
                'test-bucket',
                f'processed/flows/test-flow/{i}/output.parquet'
            )
        
        # ACT
        result = analytics.query_across_flows(
            'test-flow',
            start_date='2024-01',
            end_date='2024-12'
        )
        
        # ASSERT
        assert len(result) == 3
        total_revenue = result['total_revenue'].sum()
        assert total_revenue == 6000.0  # 1000 + 2000 + 3000