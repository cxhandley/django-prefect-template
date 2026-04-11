"""
Celery tasks for model training dataset generation and weight/threshold optimisation.
"""

import io
import json
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


# ---------------------------------------------------------------------------
# Helper: build an s3fs filesystem from Django settings
# ---------------------------------------------------------------------------
def _make_fs() -> s3fs.S3FileSystem:
    endpoint_url = settings.AWS_S3_ENDPOINT_URL
    if endpoint_url and not endpoint_url.startswith("http"):
        endpoint_url = f"http://{endpoint_url}"
    return s3fs.S3FileSystem(
        key=settings.AWS_ACCESS_KEY_ID,
        secret=settings.AWS_SECRET_ACCESS_KEY,
        endpoint_url=endpoint_url,
        client_kwargs={"region_name": settings.AWS_S3_REGION_NAME},
    )


# ---------------------------------------------------------------------------
# Normalisation (identical to predict_02_score.ipynb and dataset generation)
# ---------------------------------------------------------------------------
def _normalise(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(
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


# ---------------------------------------------------------------------------
# Score computation
# ---------------------------------------------------------------------------
def _score(df: pl.DataFrame, weights: list[float]) -> pl.DataFrame:
    w_cs, w_in, w_ey, w_ag = weights
    return df.with_columns(
        (
            pl.col("credit_score_norm") * w_cs
            + pl.col("income_norm") * w_in
            + pl.col("employment_norm") * w_ey
            + pl.col("age_norm") * w_ag
        ).alias("score")
    )


# ---------------------------------------------------------------------------
# Classify with thresholds
# ---------------------------------------------------------------------------
def _classify(df: pl.DataFrame, t_approve: float, t_review: float) -> pl.DataFrame:
    return df.with_columns(
        pl.when(pl.col("score") >= t_approve)
        .then(pl.lit("Approved"))
        .when(pl.col("score") >= t_review)
        .then(pl.lit("Review"))
        .otherwise(pl.lit("Declined"))
        .alias("predicted_label")
    )


# ---------------------------------------------------------------------------
# Metrics (Polars + DuckDB, no sklearn)
# ---------------------------------------------------------------------------
def _compute_gini(df: pl.DataFrame) -> float:
    """Gini = 2·AUC − 1.  AUC via trapezoid rule over sorted scores."""
    import duckdb

    conn = duckdb.connect()
    conn.register("val_df", df.to_arrow())
    result = conn.execute(
        """
        WITH ranked AS (
            SELECT score,
                   (ground_truth_label = 'Approved')::INTEGER AS is_positive
            FROM val_df
            ORDER BY score DESC
        ),
        cum AS (
            SELECT is_positive,
                   SUM(is_positive) OVER (ORDER BY score DESC ROWS UNBOUNDED PRECEDING) AS cum_pos,
                   SUM(1 - is_positive) OVER (ORDER BY score DESC ROWS UNBOUNDED PRECEDING) AS cum_neg,
                   SUM(is_positive) OVER () AS total_pos,
                   SUM(1 - is_positive) OVER () AS total_neg
            FROM ranked
        )
        SELECT
            2.0 * SUM(
                (cum_pos::DOUBLE / NULLIF(total_pos, 0)) *
                (1.0 / NULLIF(total_neg, 0))
            ) - 1.0 AS gini
        FROM cum
        WHERE is_positive = 0
        """
    ).fetchone()
    conn.close()
    return float(result[0]) if result and result[0] is not None else 0.0


def _compute_ks(df: pl.DataFrame) -> float:
    """KS = max |CDF_approved − CDF_non_approved| over sorted scores."""
    sorted_df = df.sort("score", descending=True)
    is_pos = (sorted_df["ground_truth_label"] == "Approved").cast(pl.Float64)
    is_neg = (sorted_df["ground_truth_label"] != "Approved").cast(pl.Float64)
    n_pos = is_pos.sum()
    n_neg = is_neg.sum()
    if n_pos == 0 or n_neg == 0:
        return 0.0
    cdf_pos = is_pos.cum_sum() / n_pos
    cdf_neg = is_neg.cum_sum() / n_neg
    return float((cdf_pos - cdf_neg).abs().max())


def _compute_f1_review(df: pl.DataFrame, t_approve: float, t_review: float) -> float:
    """F1 for the Review class using current thresholds."""
    classified = _classify(df, t_approve, t_review)
    tp = (
        (classified["predicted_label"] == "Review") & (classified["ground_truth_label"] == "Review")
    ).sum()
    fp = (
        (classified["predicted_label"] == "Review") & (classified["ground_truth_label"] != "Review")
    ).sum()
    fn = (
        (classified["predicted_label"] != "Review") & (classified["ground_truth_label"] == "Review")
    ).sum()
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    if precision + recall == 0:
        return 0.0
    return float(2 * precision * recall / (precision + recall))


def _metric_for_target(
    df: pl.DataFrame,
    target: str,
    weights: list[float],
    t_approve: float,
    t_review: float,
) -> float:
    """Compute a single metric value for the given target on a scored DataFrame."""
    scored = _score(df, weights)
    if target == "GINI":
        return _compute_gini(scored)
    elif target == "KS":
        return _compute_ks(scored)
    else:  # F1_REVIEW
        return _compute_f1_review(scored, t_approve, t_review)


# ---------------------------------------------------------------------------
# Stratified 80/20 split (reproducible)
# ---------------------------------------------------------------------------
def _stratified_split(df: pl.DataFrame, seed: int) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Return (train_df, val_df) preserving class proportions."""
    rng = np.random.default_rng(seed)
    train_parts, val_parts = [], []
    for label in ["Approved", "Review", "Declined"]:
        subset = df.filter(pl.col("ground_truth_label") == label)
        n = len(subset)
        idx = rng.permutation(n)
        split = int(n * 0.8)
        train_parts.append(subset[idx[:split].tolist()])
        val_parts.append(subset[idx[split:].tolist()])
    return pl.concat(train_parts), pl.concat(val_parts)


# ---------------------------------------------------------------------------
# Main training task
# ---------------------------------------------------------------------------
@app.task(bind=True, max_retries=0, time_limit=3600, soft_time_limit=3500)
def run_model_training_task(self, run_id: int) -> dict:
    """
    Run weight-and-threshold optimisation against a training dataset.

    Steps:
    1. Read dataset Parquet from S3 into Polars DataFrame.
    2. Reproducible 80/20 stratified split using dataset seed.
    3. Normalise 4 features.
    4. scipy.optimize.minimize (SLSQP) to find optimal weights.
    5. Threshold grid search over approval/review cutpoints on val fold.
    6. Optionally compute 2-D UMAP embedding of training fold.
    7. Write artefacts to S3.
    8. Update ModelTrainingRun record.
    """
    from apps.training.models import ModelTrainingRun, TrainingRunStatus

    run = ModelTrainingRun.objects.select_related("dataset").get(pk=run_id)

    try:
        ModelTrainingRun.objects.filter(pk=run_id).update(status=TrainingRunStatus.RUNNING)

        dataset = run.dataset
        target = run.optimisation_target

        # ── Read dataset from S3 ─────────────────────────────────────────────
        fs = _make_fs()
        s3_full = f"{settings.DATA_LAKE_BUCKET}/{dataset.s3_path}"
        with fs.open(s3_full, "rb") as fh:
            df = pl.read_parquet(fh)

        # ── Split and normalise ──────────────────────────────────────────────
        train_df, val_df = _stratified_split(df, seed=dataset.seed)
        train_df = _normalise(train_df)
        val_df = _normalise(val_df)

        # ── Weight optimisation (SLSQP) ──────────────────────────────────────
        from scipy.optimize import minimize

        # Use a stable set of initial thresholds for the F1_REVIEW objective
        # during weight search; threshold grid search follows separately.
        _default_t_approve = 0.70
        _default_t_review = 0.50

        def objective(w: np.ndarray) -> float:
            weights = w.tolist()
            return -_metric_for_target(
                val_df, target, weights, _default_t_approve, _default_t_review
            )

        x0 = np.array([0.25, 0.25, 0.25, 0.25])
        bounds = [(0.05, 0.70)] * 4
        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

        result = minimize(
            objective,
            x0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 500, "ftol": 1e-9},
        )
        optimal_weights = result.x.tolist()

        # ── Threshold grid search ────────────────────────────────────────────
        import itertools

        approval_cutpoints = [round(v, 2) for v in np.arange(0.55, 0.86, 0.05)]
        review_cutpoints = [round(v, 2) for v in np.arange(0.30, 0.61, 0.05)]

        best_metric = -1.0
        best_t_approve = 0.70
        best_t_review = 0.50

        scored_val = _score(val_df, optimal_weights)

        for t_approve, t_review in itertools.product(approval_cutpoints, review_cutpoints):
            if t_review >= t_approve:
                continue
            m = _metric_for_target(scored_val, target, optimal_weights, t_approve, t_review)
            if m > best_metric:
                best_metric = m
                best_t_approve = t_approve
                best_t_review = t_review

        # ── Compute final validation metrics ─────────────────────────────────
        scored_final = _score(val_df, optimal_weights)
        val_gini = _compute_gini(scored_final)
        val_ks = _compute_ks(scored_final)
        val_f1_review = _compute_f1_review(scored_final, best_t_approve, best_t_review)

        # ── S3 artefact path ─────────────────────────────────────────────────
        artefacts_prefix = f"training/runs/{run_id}"

        # ── UMAP (optional) ──────────────────────────────────────────────────
        if run.umap_enabled:
            from umap import UMAP

            feature_cols = ["credit_score_norm", "income_norm", "employment_norm", "age_norm"]
            train_features = train_df.select(feature_cols).to_numpy()
            reducer = UMAP(n_neighbors=15, min_dist=0.1, n_components=2, random_state=dataset.seed)
            embedding = reducer.fit_transform(train_features)
            umap_df = pl.DataFrame(
                {
                    "umap_x": embedding[:, 0].tolist(),
                    "umap_y": embedding[:, 1].tolist(),
                    "ground_truth_label": train_df["ground_truth_label"].to_list(),
                }
            )
            buf = io.BytesIO()
            umap_df.write_parquet(buf, compression="snappy", use_pyarrow=True)
            buf.seek(0)
            with fs.open(
                f"{settings.DATA_LAKE_BUCKET}/{artefacts_prefix}/umap.parquet", "wb"
            ) as fh:
                fh.write(buf.read())

        # ── Write JSON artefacts ─────────────────────────────────────────────
        weights_dict = {
            "credit_score": round(optimal_weights[0], 6),
            "income": round(optimal_weights[1], 6),
            "employment_years": round(optimal_weights[2], 6),
            "age": round(optimal_weights[3], 6),
        }
        thresholds_dict = {
            "approved": best_t_approve,
            "review": best_t_review,
        }
        val_metrics_dict = {
            "val_gini": round(val_gini, 6),
            "val_ks": round(val_ks, 6),
            "val_f1_review": round(val_f1_review, 6),
            "optimisation_target": target,
            "converged": bool(result.success),
        }

        for filename, data in [
            ("weights.json", weights_dict),
            ("thresholds.json", thresholds_dict),
            ("val_metrics.json", val_metrics_dict),
        ]:
            content = json.dumps(data, indent=2).encode()
            with fs.open(f"{settings.DATA_LAKE_BUCKET}/{artefacts_prefix}/{filename}", "wb") as fh:
                fh.write(content)

        # ── score_distributions.parquet (val fold scores + ground truth) ─────
        score_dist_df = scored_final.select(["score", "ground_truth_label"])
        buf = io.BytesIO()
        score_dist_df.write_parquet(buf, compression="snappy", use_pyarrow=True)
        buf.seek(0)
        with fs.open(
            f"{settings.DATA_LAKE_BUCKET}/{artefacts_prefix}/score_distributions.parquet", "wb"
        ) as fh:
            fh.write(buf.read())

        # ── Update DB record ─────────────────────────────────────────────────
        ModelTrainingRun.objects.filter(pk=run_id).update(
            status=TrainingRunStatus.COMPLETED,
            candidate_weights=weights_dict,
            candidate_thresholds=thresholds_dict,
            val_gini=val_gini,
            val_ks=val_ks,
            val_f1_review=val_f1_review,
            artefacts_s3_path=artefacts_prefix,
            error_message="",
        )

        return {
            "run_id": run_id,
            "val_gini": val_gini,
            "val_ks": val_ks,
            "val_f1_review": val_f1_review,
            "artefacts_s3_path": artefacts_prefix,
        }

    except Exception as exc:
        error_str = str(exc)[:2000]
        ModelTrainingRun.objects.filter(pk=run_id).update(
            status=TrainingRunStatus.FAILED,
            error_message=error_str,
        )
        raise
