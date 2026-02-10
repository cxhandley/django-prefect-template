import pytest
import polars as pl
from flows_library.data_processing import (
    validate_and_clean,
    transform_data,
    aggregate_results
)

class TestPolarsTransforms:
    """Test Polars data transformations"""
    
    @pytest.fixture
    def sample_data(self):
        """Create sample data for testing"""
        return pl.DataFrame({
            'id': [1, 2, None, 4, 5],  # Has null
            'transaction_date': ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04', 'invalid'],
            'amount': [100.0, -50.0, 200.0, 150.0, 300.0],  # Has negative
            'quantity': [1, 2, 3, 4, 5],
            'customer_id': ['C1', 'C2', 'C3', 'C4', 'C5']
        })
    
    def test_validate_and_clean(self, sample_data):
        """Test data validation and cleaning"""
        # ARRANGE
        df_lazy = sample_data.lazy()
        
        # ACT
        result = validate_and_clean(df_lazy).collect()
        
        # ASSERT
        # Should remove null IDs
        assert result['id'].null_count() == 0
        # Should remove negative amounts
        assert (result['amount'] >= 0).all()
        # Should have 2 rows (removed null id, negative amount, invalid date)
        assert len(result) == 2
    
    def test_transform_data(self):
        """Test data transformations"""
        # ARRANGE
        df = pl.DataFrame({
            'id': [1, 2],
            'transaction_date': ['2024-01-15', '2024-02-20'],
            'amount': [100.0, 200.0],
            'quantity': [2, 3]
        }).lazy()
        
        # ACT
        result = transform_data(df).collect()
        
        # ASSERT
        assert 'date' in result.columns
        assert 'total' in result.columns
        assert 'tax' in result.columns
        assert 'year_month' in result.columns
        
        # Check calculations
        assert result['total'][0] == 200.0  # 100 * 2
        assert result['tax'][0] == 10.0     # 100 * 0.1
        assert result['year_month'][0] == '2024-01'
    
    def test_aggregate_results(self):
        """Test aggregation logic"""
        # ARRANGE
        df = pl.DataFrame({
            'year_month': ['2024-01', '2024-01', '2024-02'],
            'amount_category': ['high', 'medium', 'high'],
            'total': [1000.0, 500.0, 1500.0],
            'id': [1, 2, 3],
            'customer_id': ['C1', 'C1', 'C2']
        }).lazy()
        
        # ACT
        result = aggregate_results(df).collect()
        
        # ASSERT
        # Should group by year_month and category
        assert len(result) == 2  # 2024-01 high+medium, 2024-02 high
        
        # Check aggregations
        jan_high = result.filter(
            (pl.col('year_month') == '2024-01') & 
            (pl.col('amount_category') == 'high')
        )
        assert jan_high['total_revenue'][0] == 1000.0
        assert jan_high['transaction_count'][0] == 1

@pytest.mark.integration
class TestDataProcessingFlow:
    """Integration tests for complete flow"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_flow(self, mock_s3, tmp_path):
        """Test complete data processing pipeline"""
        from flows_library.data_processing import data_processing_flow
        
        # ARRANGE: Create input file
        input_df = pl.DataFrame({
            'id': list(range(100)),
            'transaction_date': ['2024-01-01'] * 100,
            'amount': [100.0] * 100,
            'quantity': [1] * 100,
            'customer_id': [f'C{i}' for i in range(100)]
        })
        
        input_path = tmp_path / "input.parquet"
        input_df.write_parquet(input_path)
        
        # Upload to S3
        mock_s3.upload_file(
            str(input_path),
            'test-bucket',
            'raw/input.parquet'
        )
        
        # ACT: Run flow
        result = await data_processing_flow(
            input_s3_path='s3://test-bucket/raw/input.parquet',
            run_id='test-123',
            user_id=1,
            output_bucket='test-bucket'
        )
        
        # ASSERT
        assert result['row_count'] > 0
        assert 'output.parquet' in result['output_path']
        
        # Verify output exists in S3
        objects = mock_s3.list_objects_v2(
            Bucket='test-bucket',
            Prefix='processed/'
        )
        assert len(objects.get('Contents', [])) > 0