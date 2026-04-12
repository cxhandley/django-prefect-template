"""
Altair chart spec builders for model training diagnostics.

All S3-backed charts read data via DuckDB (no raw file bytes loaded into
Django memory). DB-backed charts build specs purely from ORM data.

Usage::

    with TrainingCharts() as charts:
        spec = charts.umap_scatter(run)
        return JsonResponse(spec)
"""

import altair as alt
from django.conf import settings

from .analytics import TrainingAnalytics

# Outcome palette consistent with the UI badge colours.
_LABEL_DOMAIN = ["Approved", "Review", "Declined"]
_LABEL_RANGE = ["#22c55e", "#f59e0b", "#ef4444"]

# Altair 5+ default row limit is 5 000; disable for large parquet files.
alt.data_transformers.disable_max_rows()


class TrainingCharts(TrainingAnalytics):
    """
    Extends TrainingAnalytics with Altair chart builders.

    Inherits the DuckDB connection that already has the S3 secret configured,
    so all ``read_parquet('s3://...')`` calls work without extra setup.
    """

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _s3(self, *parts: str) -> str:
        """Return a fully-qualified s3:// path for DuckDB read_parquet."""
        key = "/".join(p.strip("/") for p in parts)
        return f"s3://{settings.DATA_LAKE_BUCKET}/{key}"

    def _parquet_to_records(self, s3_path: str, query: str = "SELECT * FROM src") -> list[dict]:
        """
        Read a Parquet file from S3 via DuckDB and return a list of dicts.

        Args:
            s3_path: Full ``s3://…`` path.
            query:   SQL that references the CTE alias ``src``.
        """
        sql = f"WITH src AS (SELECT * FROM read_parquet('{s3_path}')) {query}"
        rel = self.conn.execute(sql)
        cols = [d[0] for d in rel.description]
        return [dict(zip(cols, row, strict=True)) for row in rel.fetchall()]

    # ── Chart 1: UMAP scatter ─────────────────────────────────────────────────

    def umap_scatter(self, run) -> dict:
        """
        2-D UMAP embedding scatter, coloured by ground-truth outcome.

        Returns ``{"error": "..."}`` when UMAP was not computed for this run.
        """
        if not run.umap_enabled or not run.artefacts_s3_path:
            return {"error": "UMAP not computed for this run"}

        s3_path = self._s3(run.artefacts_s3_path, "umap.parquet")
        try:
            records = self._parquet_to_records(s3_path)
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

        s3_path = self._s3(backtest.artefacts_s3_path, "test_scores.parquet")
        try:
            records = self._parquet_to_records(s3_path)
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

    def confusion_matrix_heatmap(self, backtest) -> dict:
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

    def class_metrics_bar(self, backtest) -> dict:
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
