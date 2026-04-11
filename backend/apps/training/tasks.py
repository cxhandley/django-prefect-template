"""
Celery tasks for model training dataset generation.
"""

import math

import numpy as np
import polars as pl
import s3fs
from config.celery import app
from django.conf import settings


@app.task(bind=True, max_retries=2, default_retry_delay=30)
def generate_training_dataset_task(self, dataset_id: int) -> dict:
    """
    Generate a synthetic credit-applicant dataset and write it to S3 as Parquet.

    Uses numpy for random variate generation (reproducibly seeded) and Polars
    for all post-generation data manipulation.  No pandas, no scikit-learn.

    Args:
        dataset_id: PK of the TrainingDataset record to populate.

    Returns:
        Dict with s3_path and row_count.
    """
    from apps.flows.models import ScoringModel
    from apps.training.models import DatasetStatus, TrainingDataset

    dataset = TrainingDataset.objects.get(pk=dataset_id)

    try:
        TrainingDataset.objects.filter(pk=dataset_id).update(status=DatasetStatus.GENERATING)

        # ── Active scoring model ─────────────────────────────────────────────
        active_model = ScoringModel.get_active()
        if active_model is None:
            raise ValueError(
                "No active ScoringModel found. "
                "Create and activate a ScoringModel before generating training data."
            )
        weights = active_model.weights
        thresholds = active_model.thresholds

        # ── Random number generator ──────────────────────────────────────────
        # Use a resolved integer seed so the actual value is always stored.
        seed = dataset.seed
        if seed is None:
            import random

            seed = random.randint(0, 2**31 - 1)
            TrainingDataset.objects.filter(pk=dataset_id).update(seed=seed)

        rng = np.random.default_rng(seed)
        n = dataset.row_count

        # ── Feature generation ───────────────────────────────────────────────
        # income: LogNormal — median ~$45k, long right tail
        income = np.round(
            rng.lognormal(mean=math.log(45_000), sigma=0.6, size=n).clip(5_000, 500_000),
            2,
        )
        # age: Normal — peak mid-30s, clipped to working-age range
        age = rng.normal(loc=38, scale=12, size=n).clip(18, 80).round().astype(int)
        # credit_score: Normal — centred on fair-credit band
        credit_score = rng.normal(loc=650, scale=80, size=n).clip(300, 850).round().astype(int)
        # employment_years: Gamma — right-skewed, most people < 15 yrs
        employment_years = np.round(
            rng.gamma(shape=2, scale=4, size=n).clip(0, 40),
            1,
        )

        # ── Build Polars DataFrame ───────────────────────────────────────────
        df = pl.DataFrame(
            {
                "income": income.tolist(),
                "age": age.tolist(),
                "credit_score": credit_score.tolist(),
                "employment_years": employment_years.tolist(),
            }
        )

        # ── Normalise features (same ranges as predict_02_score.ipynb) ───────
        df = df.with_columns(
            [
                ((pl.col("credit_score").cast(pl.Float64) - 300) / 550)
                .clip(0.0, 1.0)
                .alias("credit_score_norm"),
                (pl.col("income") / 150_000).clip(0.0, 1.0).alias("income_norm"),
                (pl.col("employment_years") / 20).clip(0.0, 1.0).alias("employment_norm"),
                pl.when(pl.col("age").cast(pl.Int32).is_between(22, 70))
                .then(pl.lit(1.0))
                .otherwise(pl.lit(0.6))
                .alias("age_norm"),
            ]
        )

        # ── Weighted base score ──────────────────────────────────────────────
        w_cs = float(weights.get("credit_score", 0.0))
        w_in = float(weights.get("income", 0.0))
        w_ey = float(weights.get("employment_years", 0.0))
        w_ag = float(weights.get("age", 0.0))

        df = df.with_columns(
            (
                pl.col("credit_score_norm") * w_cs
                + pl.col("income_norm") * w_in
                + pl.col("employment_norm") * w_ey
                + pl.col("age_norm") * w_ag
            ).alias("base_score")
        )

        # ── Add Gaussian noise to produce ground-truth score ─────────────────
        noise = rng.normal(loc=0.0, scale=0.03, size=n)
        df = df.with_columns(
            (pl.col("base_score") + pl.Series("noise", noise))
            .clip(0.0, 1.0)
            .round(4)
            .alias("ground_truth_score")
        )

        # ── Derive ground-truth label from active thresholds ─────────────────
        t_approved = float(thresholds.get("approved", 0.70))
        t_review = float(thresholds.get("review", 0.50))

        df = df.with_columns(
            pl.when(pl.col("ground_truth_score") >= t_approved)
            .then(pl.lit("Approved"))
            .when(pl.col("ground_truth_score") >= t_review)
            .then(pl.lit("Review"))
            .otherwise(pl.lit("Declined"))
            .alias("ground_truth_label")
        )

        # ── Keep only the public columns ─────────────────────────────────────
        df = df.select(
            [
                "income",
                "age",
                "credit_score",
                "employment_years",
                "ground_truth_score",
                "ground_truth_label",
            ]
        )

        # ── Write to S3 ──────────────────────────────────────────────────────
        endpoint_url = settings.AWS_S3_ENDPOINT_URL
        if endpoint_url and not endpoint_url.startswith("http"):
            endpoint_url = f"http://{endpoint_url}"

        fs = s3fs.S3FileSystem(
            key=settings.AWS_ACCESS_KEY_ID,
            secret=settings.AWS_SECRET_ACCESS_KEY,
            endpoint_url=endpoint_url,
            client_kwargs={"region_name": settings.AWS_S3_REGION_NAME},
        )

        s3_path = f"training/datasets/{dataset.slug}/data.parquet"
        with fs.open(f"{settings.DATA_LAKE_BUCKET}/{s3_path}", "wb") as fh:
            df.write_parquet(fh, compression="snappy", use_pyarrow=True)

        # ── Mark complete ────────────────────────────────────────────────────
        TrainingDataset.objects.filter(pk=dataset_id).update(
            status=DatasetStatus.COMPLETED,
            s3_path=s3_path,
            error_message="",
        )

        return {"dataset_id": dataset_id, "s3_path": s3_path, "row_count": n}

    except Exception as exc:
        error_str = str(exc)[:2000]
        TrainingDataset.objects.filter(pk=dataset_id).update(
            status=DatasetStatus.FAILED,
            error_message=error_str,
        )
        raise self.retry(exc=exc) from exc
