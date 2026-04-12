import csv
import io
import random

from django.contrib.admin.views.decorators import staff_member_required
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .models import (
    BacktestStatus,
    DatasetStatus,
    ModelBacktestResult,
    ModelTrainingRun,
    OptimisationTarget,
    TrainingDataset,
    TrainingRunStatus,
)
from .services.analytics import TrainingAnalytics
from .services.charts import TrainingCharts
from .tasks import generate_training_dataset_task, run_model_backtest_task, run_model_training_task


@staff_member_required
def dataset_list(request):
    datasets = TrainingDataset.objects.select_related("created_by").all()
    return render(
        request,
        "training/dataset_list.html",
        {"datasets": datasets, "active_page": "training_datasets"},
    )


@staff_member_required
@require_http_methods(["POST"])
def generate_dataset(request):
    errors = {}
    description = request.POST.get("description", "").strip()

    try:
        row_count = int(request.POST.get("row_count", 0))
        if not (100 <= row_count <= 1_000_000):
            errors["row_count"] = "Row count must be between 100 and 1,000,000."
    except (ValueError, TypeError):
        errors["row_count"] = "Row count must be a whole number."
        row_count = None

    seed_raw = request.POST.get("seed", "").strip()
    if seed_raw:
        try:
            seed = int(seed_raw)
            if seed < 0:
                errors["seed"] = "Seed must be a non-negative integer."
                seed = None
        except ValueError:
            errors["seed"] = "Seed must be a whole number."
            seed = None
    else:
        seed = random.randint(0, 2**31 - 1)

    if errors:
        datasets = TrainingDataset.objects.select_related("created_by").all()
        return render(
            request,
            "training/dataset_list.html",
            {
                "datasets": datasets,
                "active_page": "training_datasets",
                "form_errors": errors,
                "form_values": request.POST,
            },
            status=422,
        )

    dataset = TrainingDataset.objects.create(
        description=description,
        row_count=row_count,
        seed=seed,
        created_by=request.user,
        status=DatasetStatus.PENDING,
    )

    result = generate_training_dataset_task.apply_async(args=[dataset.pk])
    TrainingDataset.objects.filter(pk=dataset.pk).update(celery_task_id=result.id)

    return redirect("training:detail", slug=dataset.slug)


@staff_member_required
def dataset_detail(request, slug):
    dataset = get_object_or_404(TrainingDataset.objects.select_related("created_by"), slug=slug)

    stats = None
    sample_rows = None
    stats_error = None

    if dataset.status == DatasetStatus.COMPLETED and dataset.s3_path:
        try:
            with TrainingAnalytics() as analytics:
                stats = analytics.get_feature_stats(dataset.s3_path)
                sample_df = analytics.get_sample_rows(dataset.s3_path, limit=10)
                sample_rows = sample_df.to_dicts()
        except Exception as exc:
            stats_error = str(exc)

    return render(
        request,
        "training/dataset_detail.html",
        {
            "dataset": dataset,
            "stats": stats,
            "sample_rows": sample_rows,
            "stats_error": stats_error,
            "active_page": "training_datasets",
        },
    )


@staff_member_required
def dataset_status(request, slug):
    """HTMX polling endpoint — returns the status partial."""
    dataset = get_object_or_404(TrainingDataset, slug=slug)
    return render(
        request,
        "training/partials/dataset_status.html",
        {"dataset": dataset},
    )


@staff_member_required
@require_http_methods(["POST"])
def delete_dataset(request, slug):
    dataset = get_object_or_404(TrainingDataset, slug=slug)
    dataset.delete()
    return redirect("training:dataset_list")


# ── Training Run views ────────────────────────────────────────────────────────


@staff_member_required
def run_list(request, slug):
    """List all training runs for a dataset, sortable by metric."""
    dataset = get_object_or_404(TrainingDataset.objects.select_related("created_by"), slug=slug)
    sort_by = request.GET.get("sort", "-created_at")
    allowed_sorts = {
        "val_gini": "val_gini",
        "-val_gini": "-val_gini",
        "val_ks": "val_ks",
        "-val_ks": "-val_ks",
        "created_at": "created_at",
        "-created_at": "-created_at",
    }
    order_field = allowed_sorts.get(sort_by, "-created_at")
    runs = (
        ModelTrainingRun.objects.filter(dataset=dataset)
        .select_related("created_by")
        .order_by(order_field)
    )
    return render(
        request,
        "training/run_list.html",
        {
            "dataset": dataset,
            "runs": runs,
            "sort_by": sort_by,
            "optimisation_targets": OptimisationTarget,
            "active_page": "training_datasets",
        },
    )


@staff_member_required
@require_http_methods(["POST"])
def start_run(request, slug):
    """Validate form, create ModelTrainingRun, dispatch Celery task."""
    dataset = get_object_or_404(TrainingDataset, slug=slug)

    if dataset.status != DatasetStatus.COMPLETED:
        return redirect("training:run_list", slug=slug)

    errors = {}
    label = request.POST.get("label", "").strip()
    if not label:
        errors["label"] = "Label is required."
    elif len(label) > 100:
        errors["label"] = "Label must be 100 characters or fewer."

    optimisation_target = request.POST.get("optimisation_target", "")
    if optimisation_target not in OptimisationTarget.values:
        errors["optimisation_target"] = "Select a valid optimisation target."

    umap_enabled = request.POST.get("umap_enabled") == "on"

    if errors:
        runs = (
            ModelTrainingRun.objects.filter(dataset=dataset)
            .select_related("created_by")
            .order_by("-created_at")
        )
        return render(
            request,
            "training/run_list.html",
            {
                "dataset": dataset,
                "runs": runs,
                "sort_by": "-created_at",
                "optimisation_targets": OptimisationTarget,
                "form_errors": errors,
                "form_values": request.POST,
                "active_page": "training_datasets",
            },
            status=422,
        )

    run = ModelTrainingRun.objects.create(
        label=label,
        dataset=dataset,
        optimisation_target=optimisation_target,
        umap_enabled=umap_enabled,
        status=TrainingRunStatus.PENDING,
        created_by=request.user,
    )

    result = run_model_training_task.apply_async(args=[run.pk])
    ModelTrainingRun.objects.filter(pk=run.pk).update(celery_task_id=result.id)

    return redirect("training:run_detail", run_id=run.pk)


@staff_member_required
def run_detail(request, run_id):
    """Training run detail page."""
    run = get_object_or_404(
        ModelTrainingRun.objects.select_related("dataset", "created_by", "backtest_result"),
        pk=run_id,
    )
    return render(
        request,
        "training/run_detail.html",
        {
            "run": run,
            "dataset": run.dataset,
            "active_page": "training_datasets",
        },
    )


@staff_member_required
def run_status(request, run_id):
    """HTMX polling endpoint — returns the run status partial."""
    run = get_object_or_404(ModelTrainingRun, pk=run_id)
    return render(
        request,
        "training/partials/run_status.html",
        {"run": run},
    )


# ── Backtest views ────────────────────────────────────────────────────────────


@staff_member_required
@require_http_methods(["POST"])
def trigger_backtest(request, run_id):
    """
    Create (or reset) a ModelBacktestResult for the given run and dispatch the task.
    Returns the backtest section partial for HTMX swap.
    """
    run = get_object_or_404(ModelTrainingRun, pk=run_id)

    if run.status != TrainingRunStatus.COMPLETED:
        return render(
            request,
            "training/partials/backtest_section.html",
            {"run": run, "backtest": None, "error": "Training run is not yet completed."},
            status=422,
        )

    # Create fresh record (or reset an existing failed one)
    backtest, _ = ModelBacktestResult.objects.get_or_create(training_run=run)
    if backtest.status not in (BacktestStatus.PENDING, BacktestStatus.FAILED):
        # Already running or completed — just re-render the section
        return render(
            request,
            "training/partials/backtest_section.html",
            {"run": run, "backtest": backtest},
        )

    backtest.status = BacktestStatus.PENDING
    backtest.error_message = ""
    backtest.save(update_fields=["status", "error_message"])

    result = run_model_backtest_task.apply_async(args=[backtest.pk])
    ModelBacktestResult.objects.filter(pk=backtest.pk).update(celery_task_id=result.id)
    backtest.refresh_from_db()

    return render(
        request,
        "training/partials/backtest_section.html",
        {"run": run, "backtest": backtest},
    )


@staff_member_required
def backtest_section(request, run_id):
    """HTMX polling endpoint — returns the full backtest section partial."""
    run = get_object_or_404(ModelTrainingRun, pk=run_id)
    backtest = getattr(run, "backtest_result", None)
    return render(
        request,
        "training/partials/backtest_section.html",
        {"run": run, "backtest": backtest},
    )


@staff_member_required
def backtest_export(request, run_id):
    """Stream test_scores.parquet from S3 as a CSV download."""
    import duckdb
    from apps.training.tasks import _make_fs
    from django.conf import settings

    run = get_object_or_404(ModelTrainingRun, pk=run_id)
    backtest = get_object_or_404(
        ModelBacktestResult, training_run=run, status=BacktestStatus.COMPLETED
    )

    fs = _make_fs()
    with fs.open(
        f"{settings.DATA_LAKE_BUCKET}/{backtest.artefacts_s3_path}/test_scores.parquet", "rb"
    ) as fh:
        parquet_bytes = fh.read()

    conn = duckdb.connect()
    conn.execute("CREATE TABLE scores AS SELECT * FROM read_parquet('/dev/stdin')")

    # Use in-memory parquet via BytesIO registered as arrow
    import polars as pl

    df = pl.read_parquet(io.BytesIO(parquet_bytes))
    conn.register("scores_arrow", df.to_arrow())
    rows = conn.execute("SELECT * FROM scores_arrow ORDER BY score DESC").fetchall()
    cols = [desc[0] for desc in conn.execute("DESCRIBE scores_arrow").fetchall()]
    conn.close()

    def csv_rows():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(cols)
        yield buf.getvalue()
        for row in rows:
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(row)
            yield buf.getvalue()

    filename = f"test_scores_run_{run.pk}.csv"
    response = StreamingHttpResponse(csv_rows(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# ── Chart endpoints — return Altair JSON specs ────────────────────────────────


def _json_spec(spec: dict):
    """Wrap an Altair spec (or error dict) as a JsonResponse."""
    from django.http import JsonResponse

    return JsonResponse(spec, safe=False)


@staff_member_required
def chart_umap(request, run_id):
    run = get_object_or_404(ModelTrainingRun, pk=run_id)
    with TrainingCharts() as charts:
        spec = charts.umap_scatter(run)
    return _json_spec(spec)


@staff_member_required
def chart_score_distribution(request, run_id):
    run = get_object_or_404(ModelTrainingRun.objects.select_related("backtest_result"), pk=run_id)
    backtest = getattr(run, "backtest_result", None)
    with TrainingCharts() as charts:
        spec = charts.score_distribution(run, backtest)
    return _json_spec(spec)


@staff_member_required
def chart_confusion_matrix(request, run_id):
    run = get_object_or_404(ModelTrainingRun.objects.select_related("backtest_result"), pk=run_id)
    backtest = getattr(run, "backtest_result", None)
    with TrainingCharts() as charts:
        spec = charts.confusion_matrix_heatmap(backtest)
    return _json_spec(spec)


@staff_member_required
def chart_class_metrics(request, run_id):
    run = get_object_or_404(ModelTrainingRun.objects.select_related("backtest_result"), pk=run_id)
    backtest = getattr(run, "backtest_result", None)
    with TrainingCharts() as charts:
        spec = charts.class_metrics_bar(backtest)
    return _json_spec(spec)


@staff_member_required
def chart_gini_trend(request, slug):
    dataset = get_object_or_404(TrainingDataset, slug=slug)
    spec = TrainingCharts.gini_ks_trend(dataset)
    return _json_spec(spec)


@staff_member_required
def chart_compare_metrics(request):
    raw = request.GET.get("run_ids", "")
    try:
        run_ids = [int(x) for x in raw.split(",") if x.strip()][:4]
    except ValueError:
        return _json_spec({"error": "Invalid run_ids parameter"})

    if len(run_ids) < 2:
        return _json_spec({"error": "Select 2–4 runs to compare"})

    runs = (
        ModelTrainingRun.objects.filter(pk__in=run_ids)
        .select_related("backtest_result")
        .order_by("created_at")
    )
    spec = TrainingCharts.multi_run_comparison(runs)
    return _json_spec(spec)
