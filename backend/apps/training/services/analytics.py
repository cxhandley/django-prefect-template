import duckdb
import polars as pl
from django.conf import settings


class TrainingAnalytics:
    """DuckDB-backed analytics service for training dataset Parquet files in S3."""

    def __init__(self):
        self.conn = duckdb.connect(":memory:")
        self._configure_s3()

    def _configure_s3(self):
        endpoint = getattr(settings, "AWS_S3_ENDPOINT_URL", None) or ""
        if endpoint.startswith("http://"):
            endpoint = endpoint[len("http://") :]
        elif endpoint.startswith("https://"):
            endpoint = endpoint[len("https://") :]

        # Known limitation: DuckDB CREATE SECRET does not support parameterised
        # queries; credentials are interpolated from Django settings (environment
        # variables only — never user input). Do not replicate elsewhere.
        self.conn.execute(f"""
            CREATE SECRET training_s3 (
                TYPE S3,
                KEY_ID '{settings.AWS_ACCESS_KEY_ID}',
                SECRET '{settings.AWS_SECRET_ACCESS_KEY}',
                REGION '{settings.AWS_S3_REGION_NAME}',
                ENDPOINT '{endpoint}',
                USE_SSL false,
                URL_STYLE 'path'
            )
        """)
        self.conn.execute(f"""
            SET threads={settings.DUCKDB_THREADS};
            SET memory_limit='{settings.DUCKDB_MEMORY_LIMIT}';
        """)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.conn.close()

    def get_feature_stats(self, s3_path: str) -> dict:
        """
        Return feature distribution stats and label counts for a training dataset.

        Args:
            s3_path: S3 key (without bucket prefix) for the dataset Parquet file.

        Returns:
            Dict with keys: total_rows, features (list of dicts), label_counts (dict).
        """
        full_path = f"s3://{settings.DATA_LAKE_BUCKET}/{s3_path}"

        # Feature distribution stats
        stats_query = f"""
            SELECT
                COUNT(*) AS total_rows,
                ROUND(AVG(income), 2)               AS income_mean,
                ROUND(STDDEV_POP(income), 2)         AS income_std,
                ROUND(MIN(income), 2)               AS income_min,
                ROUND(MAX(income), 2)               AS income_max,
                ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY income), 2) AS income_p25,
                ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY income), 2) AS income_p50,
                ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY income), 2) AS income_p75,

                ROUND(AVG(age), 1)                  AS age_mean,
                ROUND(STDDEV_POP(age), 1)            AS age_std,
                MIN(age)                            AS age_min,
                MAX(age)                            AS age_max,
                PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY age) AS age_p25,
                PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY age) AS age_p50,
                PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY age) AS age_p75,

                ROUND(AVG(credit_score), 1)         AS credit_score_mean,
                ROUND(STDDEV_POP(credit_score), 1)   AS credit_score_std,
                MIN(credit_score)                   AS credit_score_min,
                MAX(credit_score)                   AS credit_score_max,
                PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY credit_score) AS credit_score_p25,
                PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY credit_score) AS credit_score_p50,
                PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY credit_score) AS credit_score_p75,

                ROUND(AVG(employment_years), 2)     AS employment_years_mean,
                ROUND(STDDEV_POP(employment_years), 2) AS employment_years_std,
                ROUND(MIN(employment_years), 1)     AS employment_years_min,
                ROUND(MAX(employment_years), 1)     AS employment_years_max,
                ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY employment_years), 1) AS employment_years_p25,
                ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY employment_years), 1) AS employment_years_p50,
                ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY employment_years), 1) AS employment_years_p75
            FROM read_parquet('{full_path}')
        """
        row = self.conn.execute(stats_query).fetchone()
        total_rows = row[0]

        features = [
            {
                "name": "Income ($)",
                "key": "income",
                "mean": row[1],
                "std": row[2],
                "min": row[3],
                "max": row[4],
                "p25": row[5],
                "p50": row[6],
                "p75": row[7],
            },
            {
                "name": "Age",
                "key": "age",
                "mean": row[8],
                "std": row[9],
                "min": row[10],
                "max": row[11],
                "p25": row[12],
                "p50": row[13],
                "p75": row[14],
            },
            {
                "name": "Credit Score",
                "key": "credit_score",
                "mean": row[15],
                "std": row[16],
                "min": row[17],
                "max": row[18],
                "p25": row[19],
                "p50": row[20],
                "p75": row[21],
            },
            {
                "name": "Employment Years",
                "key": "employment_years",
                "mean": row[22],
                "std": row[23],
                "min": row[24],
                "max": row[25],
                "p25": row[26],
                "p50": row[27],
                "p75": row[28],
            },
        ]

        # Label distribution
        label_query = f"""
            SELECT ground_truth_label, COUNT(*) AS cnt
            FROM read_parquet('{full_path}')
            GROUP BY ground_truth_label
            ORDER BY ground_truth_label
        """
        label_rows = self.conn.execute(label_query).fetchall()
        label_counts = {r[0]: r[1] for r in label_rows}

        return {
            "total_rows": total_rows,
            "features": features,
            "label_counts": {
                "Approved": label_counts.get("Approved", 0),
                "Review": label_counts.get("Review", 0),
                "Declined": label_counts.get("Declined", 0),
            },
        }

    def get_sample_rows(self, s3_path: str, limit: int = 10) -> pl.DataFrame:
        """Return a sample of rows from the dataset for preview."""
        full_path = f"s3://{settings.DATA_LAKE_BUCKET}/{s3_path}"
        query = f"""
            SELECT income, age, credit_score, employment_years,
                   ROUND(ground_truth_score, 4) AS ground_truth_score,
                   ground_truth_label
            FROM read_parquet('{full_path}')
            LIMIT {limit}
        """
        return pl.from_arrow(self.conn.execute(query).arrow())
