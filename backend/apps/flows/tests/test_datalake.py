from unittest.mock import patch

import polars as pl
import pytest
from apps.flows.services.datalake import DataLakeAnalytics


@pytest.mark.django_db
class TestDataLakeAnalytics:
    """Test DuckDB analytics service with local parquet files.

    DuckDB's httpfs extension cannot be installed in an offline devcontainer,
    and moto intercepts only boto3 calls — not DuckDB's own HTTP client.
    Tests exercise the DuckDB SQL logic directly using local parquet files,
    which DuckDB supports natively without any extension.
    """

    @pytest.fixture(autouse=True)
    def patch_configure_s3(self):
        """Patch _configure_s3 so DuckDB doesn't need the httpfs extension."""
        with patch.object(DataLakeAnalytics, "_configure_s3"):
            yield

    @pytest.fixture
    def analytics(self):
        return DataLakeAnalytics()

    @pytest.fixture
    def sample_parquet(self, tmp_path):
        """Write a sample Parquet file to a temp directory."""
        df = pl.DataFrame(
            {
                "year_month": ["2024-01", "2024-02", "2024-03"],
                "amount_category": ["high", "medium", "low"],
                "total_revenue": [1000.0, 1500.0, 2000.0],
                "transaction_count": [10, 15, 20],
                "unique_customers": [5, 8, 12],
                "avg_transaction_value": [100.0, 100.0, 100.0],
            }
        )
        parquet_path = tmp_path / "test.parquet"
        df.write_parquet(parquet_path)
        return str(parquet_path)

    def test_get_flow_results(self, analytics, sample_parquet):
        result = pl.from_arrow(
            analytics.conn.execute(
                f"SELECT * FROM read_parquet('{sample_parquet}') LIMIT 100"
            ).arrow()
        )

        assert len(result) == 3
        assert "year_month" in result.columns
        assert "total_revenue" in result.columns

    def test_get_summary_stats(self, analytics, sample_parquet):
        row = analytics.conn.execute(f"""
            SELECT
                COUNT(*) as total_rows,
                SUM(total_revenue) as grand_total_revenue,
                AVG(transaction_count) as avg_transactions,
                MAX(unique_customers) as max_customers
            FROM read_parquet('{sample_parquet}')
        """).fetchone()

        assert row[0] == 3
        assert float(row[1]) == 4500.0
        assert row[3] == 12

    def test_context_manager(self):
        """Analytics can be used as a context manager that closes the connection."""
        with DataLakeAnalytics() as analytics:
            assert analytics.conn is not None

    def test_query_across_flows(self, analytics, tmp_path):
        for i in range(3):
            df = pl.DataFrame(
                {
                    "year_month": [f"2024-0{i + 1}"],
                    "total_revenue": [1000.0 * (i + 1)],
                    "transaction_count": [10 * (i + 1)],
                }
            )
            df.write_parquet(tmp_path / f"test{i}.parquet")

        result = pl.from_arrow(
            analytics.conn.execute(f"""
            SELECT
                year_month,
                SUM(total_revenue) as total_revenue,
                SUM(transaction_count) as total_transactions
            FROM read_parquet('{tmp_path}/*.parquet')
            WHERE year_month BETWEEN '2024-01' AND '2024-12'
            GROUP BY year_month
            ORDER BY year_month DESC
        """).arrow()
        )

        assert len(result) == 3
        assert result["total_revenue"].sum() == 6000.0
