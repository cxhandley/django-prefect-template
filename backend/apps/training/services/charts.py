"""
Altair chart spec builders for model training diagnostics.

S3-backed charts (score distribution, UMAP) read Parquet files via polars +
s3fs — the same pattern used in Celery tasks — so no DuckDB httpfs extension
is required in the web process.  DB-backed charts build specs purely from ORM
data and are exposed as static methods (no class instantiation needed).

Usage::

    # S3-backed (needs credentials):
    with TrainingCharts() as charts:
        spec = charts.umap_scatter(run)
        return JsonResponse(spec)

    # DB-backed (no context manager needed):
    spec = TrainingCharts.confusion_matrix_heatmap(backtest)
    return JsonResponse(spec)
"""

import altair as alt
import polars as pl
import s3fs
from django.conf import settings

# Outcome palette consistent with the UI badge colours.
_LABEL_DOMAIN = ["Approved", "Review", "Declined"]
_LABEL_RANGE = ["#22c55e", "#f59e0b", "#ef4444"]

# Altair 5+ default row limit is 5 000; disable for large parquet files.
alt.data_transformers.disable_max_rows()


def _make_fs() -> s3fs.S3FileSystem:
    """Return an s3fs filesystem configured from Django settings."""
    endpoint = getattr(settings, "AWS_S3_ENDPOINT_URL", None) or ""
    return s3fs.S3FileSystem(
        key=settings.AWS_ACCESS_KEY_ID,
        secret=settings.AWS_SECRET_ACCESS_KEY,
        endpoint_url=endpoint,
        use_ssl=False,
    )


class TrainingCharts:
    """
    Altair chart spec builders for training diagnostics.

    S3 reads use polars + s3fs (no DuckDB httpfs extension required).
    Static methods build specs from ORM data without any I/O.
    """

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _s3_key(self, *parts: str) -> str:
        """Return the S3 key (without bucket prefix) for a path."""
        return "/".join(p.strip("/") for p in parts)

    def _parquet_to_records(self, *path_parts: str) -> list[dict]:
        """
        Read a Parquet file from S3 via polars + s3fs and return a list of dicts.

        Args:
            path_parts: Path segments under the data-lake bucket.
        """
        key = self._s3_key(*path_parts)
        full_path = f"{settings.DATA_LAKE_BUCKET}/{key}"
        fs = _make_fs()
        with fs.open(full_path, "rb") as fh:
            df = pl.read_parquet(fh)
        return df.to_dicts()

    # ── Chart 1: UMAP scatter ─────────────────────────────────────────────────

    def umap_scatter(self, run) -> dict:
        """
        2-D UMAP embedding scatter, coloured by ground-truth outcome.

        Returns ``{"error": "..."}`` when UMAP was not computed for this run.
        """
        if not run.umap_enabled or not run.artefacts_s3_path:
            return {"error": "UMAP not computed for this run"}

        try:
            records = self._parquet_to_records(run.artefacts_s3_path, "umap.parquet")
        except Exception as exc:
            return {"error": f"Could not load UMAP data: {exc}"}

        chart = (
            alt.Chart(alt.Data(values=records))
            .mark_circle(size=25, opacity=0.65)
            .encode(
                x=alt.X("umap_x:Q", title="UMAP 1", axis=alt.Axis(labels=False, ticks=False)),
                y=alt.Y("umap_y:Q", title="UMAP 2", axis=alt.Axis(labels=False, ticks=False)),
                color=alt.Color(
                    "ground_truth_label:N",
                    title="Outcome",
                    scale=alt.Scale(domain=_LABEL_DOMAIN, range=_LABEL_RANGE),
                ),
                tooltip=[
                    alt.Tooltip("ground_truth_label:N", title="Outcome"),
                    alt.Tooltip("umap_x:Q", title="UMAP 1", format=".3f"),
                    alt.Tooltip("umap_y:Q", title="UMAP 2", format=".3f"),
                ],
            )
            .properties(title="UMAP Embedding — Training Fold", width="container", height=380)
        )
        return chart.to_dict()

    # ── Chart 2: Score distribution histogram ─────────────────────────────────

    def score_distribution(self, run, backtest) -> dict:
        """
        Layered histogram of scores on the test fold, one layer per outcome
        class, with vertical rules at the approval and review thresholds.

        Requires a COMPLETED backtest.
        """
        from apps.training.models import BacktestStatus

        if not backtest or backtest.status != BacktestStatus.COMPLETED:
            return {"error": "Backtest not yet completed"}

        try:
            records = self._parquet_to_records(backtest.artefacts_s3_path, "test_scores.parquet")
        except Exception as exc:
            return {"error": f"Could not load score data: {exc}"}

        t_approve = run.candidate_thresholds.get("approved", 0.70)
        t_review = run.candidate_thresholds.get("review", 0.50)

        base = alt.Chart(alt.Data(values=records))

        hist = base.mark_bar(opacity=0.45, binSpacing=1).encode(
            x=alt.X(
                "score:Q",
                bin=alt.Bin(maxbins=40),
                title="Score",
                scale=alt.Scale(domain=[0, 1]),
            ),
            y=alt.Y("count():Q", title="Count", stack=None),
            color=alt.Color(
                "ground_truth_label:N",
                title="Outcome",
                scale=alt.Scale(domain=_LABEL_DOMAIN, range=_LABEL_RANGE),
            ),
            tooltip=[
                alt.Tooltip("ground_truth_label:N", title="Outcome"),
                alt.Tooltip("count():Q", title="Count"),
            ],
        )

        threshold_data = alt.Data(
            values=[
                {"threshold": t_approve, "label": f"Approve ≥{t_approve}"},
                {"threshold": t_review, "label": f"Review ≥{t_review}"},
            ]
        )
        rules = (
            alt.Chart(threshold_data)
            .mark_rule(strokeDash=[6, 3], strokeWidth=2)
            .encode(
                x=alt.X("threshold:Q"),
                color=alt.Color(
                    "label:N",
                    scale=alt.Scale(
                        domain=[f"Approve ≥{t_approve}", f"Review ≥{t_review}"],
                        range=["#22c55e", "#f59e0b"],
                    ),
                    legend=alt.Legend(title="Threshold"),
                ),
                tooltip=[alt.Tooltip("label:N", title="Threshold")],
            )
        )

        chart = (
            (hist + rules)
            .resolve_scale(color="independent")
            .properties(title="Score Distribution — Test Fold", width="container", height=320)
        )
        return chart.to_dict()

    # ── Chart 3: Confusion matrix heatmap ────────────────────────────────────

    @staticmethod
    def confusion_matrix_heatmap(backtest) -> dict:
        """
        3×3 confusion matrix heatmap with cell count and row-normalised
        percentage text overlays.

        Built entirely from ``ModelBacktestResult.confusion_matrix`` — no S3.
        """
        from apps.training.models import BacktestStatus

        if not backtest or backtest.status != BacktestStatus.COMPLETED:
            return {"error": "Backtest not yet completed"}

        cm = backtest.confusion_matrix
        records = []
        for actual in _LABEL_DOMAIN:
            row_total = sum(cm.get(actual, {}).get(p, 0) for p in _LABEL_DOMAIN)
            for predicted in _LABEL_DOMAIN:
                count = cm.get(actual, {}).get(predicted, 0)
                pct = round(count / row_total * 100, 1) if row_total else 0.0
                records.append(
                    {
                        "actual": actual,
                        "predicted": predicted,
                        "count": count,
                        "pct": pct,
                        "label": f"{count}\n({pct}%)",
                    }
                )

        base = alt.Chart(alt.Data(values=records))

        heatmap = base.mark_rect().encode(
            x=alt.X(
                "predicted:N",
                sort=_LABEL_DOMAIN,
                title="Predicted",
                axis=alt.Axis(labelAngle=0),
            ),
            y=alt.Y("actual:N", sort=_LABEL_DOMAIN, title="Actual"),
            color=alt.Color(
                "count:Q",
                scale=alt.Scale(scheme="blues"),
                legend=alt.Legend(title="Count"),
            ),
            tooltip=[
                alt.Tooltip("actual:N", title="Actual"),
                alt.Tooltip("predicted:N", title="Predicted"),
                alt.Tooltip("count:Q", title="Count"),
                alt.Tooltip("pct:Q", title="Row %", format=".1f"),
            ],
        )

        text = base.mark_text(fontSize=12, fontWeight="bold").encode(
            x=alt.X("predicted:N", sort=_LABEL_DOMAIN),
            y=alt.Y("actual:N", sort=_LABEL_DOMAIN),
            text=alt.Text("count:Q"),
            color=alt.condition(
                alt.datum.count > 0,
                alt.value("white"),
                alt.value("#555"),
            ),
        )

        pct_text = base.mark_text(fontSize=10, dy=14).encode(
            x=alt.X("predicted:N", sort=_LABEL_DOMAIN),
            y=alt.Y("actual:N", sort=_LABEL_DOMAIN),
            text=alt.Text("pct:Q", format=".1f"),
            color=alt.condition(
                alt.datum.count > 0,
                alt.value("#ddd"),
                alt.value("#999"),
            ),
        )

        chart = (heatmap + text + pct_text).properties(
            title="Confusion Matrix", width="container", height=260
        )
        return chart.to_dict()

    # ── Chart 4: Per-class precision / recall / F1 grouped bar ───────────────

    @staticmethod
    def class_metrics_bar(backtest) -> dict:
        """
        Grouped bar chart: x=class, colour=metric type, y=value [0–1].

        Built entirely from ``ModelBacktestResult`` typed columns — no S3.
        """
        from apps.training.models import BacktestStatus

        if not backtest or backtest.status != BacktestStatus.COMPLETED:
            return {"error": "Backtest not yet completed"}

        records = []
        for cls, prec, rec, f1 in [
            (
                "Approved",
                backtest.precision_approved,
                backtest.recall_approved,
                backtest.f1_approved,
            ),
            ("Review", backtest.precision_review, backtest.recall_review, backtest.f1_review),
            (
                "Declined",
                backtest.precision_declined,
                backtest.recall_declined,
                backtest.f1_declined,
            ),
        ]:
            for metric, value in [("Precision", prec), ("Recall", rec), ("F1", f1)]:
                records.append({"class": cls, "metric": metric, "value": round(value or 0.0, 4)})

        chart = (
            alt.Chart(alt.Data(values=records))
            .mark_bar()
            .encode(
                x=alt.X("class:N", sort=_LABEL_DOMAIN, title=None, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("value:Q", scale=alt.Scale(domain=[0, 1]), title="Score"),
                color=alt.Color(
                    "metric:N",
                    scale=alt.Scale(
                        domain=["Precision", "Recall", "F1"],
                        range=["#6366f1", "#0ea5e9", "#10b981"],
                    ),
                    legend=alt.Legend(title="Metric"),
                ),
                xOffset=alt.XOffset("metric:N", sort=["Precision", "Recall", "F1"]),
                tooltip=[
                    alt.Tooltip("class:N", title="Class"),
                    alt.Tooltip("metric:N", title="Metric"),
                    alt.Tooltip("value:Q", title="Value", format=".4f"),
                ],
            )
            .properties(title="Per-Class Metrics", width="container", height=280)
        )
        return chart.to_dict()

    # ── Chart 5: Gini / KS trend across rounds ────────────────────────────────

    @staticmethod
    def gini_ks_trend(dataset) -> dict:
        """
        Dual-line chart of Gini and KS statistic across all completed training
        runs for the dataset that have a completed backtest.

        Built from Django ORM queryset — no S3 or DuckDB.
        """
        from apps.training.models import BacktestStatus, TrainingRunStatus

        runs = (
            dataset.training_runs.filter(status=TrainingRunStatus.COMPLETED)
            .prefetch_related("backtest_result")
            .order_by("created_at")
        )

        records = []
        for run in runs:
            br = getattr(run, "backtest_result", None)
            if not br or br.status != BacktestStatus.COMPLETED:
                continue
            ts = run.created_at.isoformat()
            records.append(
                {
                    "run": run.label,
                    "created_at": ts,
                    "metric": "Gini",
                    "value": round(br.gini or 0.0, 4),
                }
            )
            records.append(
                {
                    "run": run.label,
                    "created_at": ts,
                    "metric": "KS",
                    "value": round(br.ks_statistic or 0.0, 4),
                }
            )

        if not records:
            return {"error": "No completed backtests yet for this dataset"}

        chart = (
            alt.Chart(alt.Data(values=records))
            .mark_line(point=True)
            .encode(
                x=alt.X("created_at:T", title="Run Date", axis=alt.Axis(labelAngle=-30)),
                y=alt.Y("value:Q", scale=alt.Scale(domain=[0, 1]), title="Metric Value"),
                color=alt.Color(
                    "metric:N",
                    scale=alt.Scale(domain=["Gini", "KS"], range=["#6366f1", "#0ea5e9"]),
                    legend=alt.Legend(title="Metric"),
                ),
                tooltip=[
                    alt.Tooltip("run:N", title="Run"),
                    alt.Tooltip("metric:N", title="Metric"),
                    alt.Tooltip("value:Q", title="Value", format=".4f"),
                    alt.Tooltip("created_at:T", title="Date"),
                ],
            )
            .properties(title="Gini & KS Across Training Rounds", width="container", height=280)
        )
        return chart.to_dict()

    # ── Chart 6: Multi-run metric comparison ──────────────────────────────────

    @staticmethod
    def multi_run_comparison(runs) -> dict:
        """
        Grouped bar chart comparing Gini, KS, and F1_Review across 2–4 runs.

        ``runs`` is a queryset of ``ModelTrainingRun`` pre-filtered by the
        caller to only those with completed backtests.
        """
        from apps.training.models import BacktestStatus

        records = []
        for run in runs:
            br = getattr(run, "backtest_result", None)
            if not br or br.status != BacktestStatus.COMPLETED:
                continue
            for metric, value in [
                ("Gini", br.gini),
                ("KS", br.ks_statistic),
                ("F1 Review", br.f1_review),
            ]:
                records.append(
                    {"run": run.label, "metric": metric, "value": round(value or 0.0, 4)}
                )

        if not records:
            return {"error": "No runs with completed backtests in selection"}

        chart = (
            alt.Chart(alt.Data(values=records))
            .mark_bar()
            .encode(
                x=alt.X("run:N", title=None, axis=alt.Axis(labelAngle=-20)),
                y=alt.Y("value:Q", scale=alt.Scale(domain=[0, 1]), title="Metric Value"),
                color=alt.Color(
                    "metric:N",
                    scale=alt.Scale(
                        domain=["Gini", "KS", "F1 Review"],
                        range=["#6366f1", "#0ea5e9", "#10b981"],
                    ),
                    legend=alt.Legend(title="Metric"),
                ),
                xOffset=alt.XOffset("metric:N", sort=["Gini", "KS", "F1 Review"]),
                tooltip=[
                    alt.Tooltip("run:N", title="Run"),
                    alt.Tooltip("metric:N", title="Metric"),
                    alt.Tooltip("value:Q", title="Value", format=".4f"),
                ],
            )
            .properties(title="Run Comparison", width="container", height=280)
        )
        return chart.to_dict()
