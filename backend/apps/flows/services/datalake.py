import duckdb
from django.conf import settings
import polars as pl

class DataLakeAnalytics:
    """Service for querying data lake with DuckDB"""
    
    def __init__(self):
        self.conn = duckdb.connect(':memory:')
        
        # Configure S3 credentials
        self.conn.execute(f"""
            CREATE SECRET (
                TYPE S3,
                KEY_ID '{settings.AWS_ACCESS_KEY_ID}',
                SECRET '{settings.AWS_SECRET_ACCESS_KEY}',
                REGION '{settings.AWS_S3_REGION}',
                ENDPOINT '{settings.AWS_S3_ENDPOINT_URL}'
            )
        """)
        
        # Performance settings
        self.conn.execute(f"""
            SET threads={settings.DUCKDB_THREADS};
            SET memory_limit='{settings.DUCKDB_MEMORY_LIMIT}';
        """)
    
    def get_flow_results(self, s3_path: str, limit: int = 100) -> pl.DataFrame:
        """Get preview of flow results"""
        query = f"""
            SELECT * FROM read_parquet('s3://{settings.DATA_LAKE_BUCKET}/{s3_path}')
            LIMIT {limit}
        """
        return pl.from_arrow(self.conn.execute(query).arrow())
    
    def get_summary_stats(self, s3_path: str) -> dict:
        """Get summary statistics without loading full dataset"""
        query = f"""
            SELECT 
                COUNT(*) as total_rows,
                SUM(total_revenue) as grand_total_revenue,
                AVG(transaction_count) as avg_transactions,
                MAX(unique_customers) as max_customers
            FROM read_parquet('s3://{settings.DATA_LAKE_BUCKET}/{s3_path}')
        """
        result = self.conn.execute(query).fetchone()
        return {
            'total_rows': result[0],
            'grand_total_revenue': float(result[1]) if result[1] else 0,
            'avg_transactions': float(result[2]) if result[2] else 0,
            'max_customers': result[3]
        }
    
    def query_across_flows(self, flow_name: str, start_date: str, end_date: str):
        """Query across multiple flow runs"""
        s3_pattern = f"s3://{settings.DATA_LAKE_BUCKET}/processed/flows/{flow_name}/*/output.parquet"
        
        query = f"""
            SELECT 
                year_month,
                SUM(total_revenue) as total_revenue,
                SUM(transaction_count) as total_transactions
            FROM read_parquet('{s3_pattern}')
            WHERE year_month BETWEEN '{start_date}' AND '{end_date}'
            GROUP BY year_month
            ORDER BY year_month DESC
        """
        return pl.from_arrow(self.conn.execute(query).arrow())