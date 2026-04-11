import random

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .models import (
    DatasetStatus,
    ModelTrainingRun,
    OptimisationTarget,
    TrainingDataset,
    TrainingRunStatus,
)
from .services.analytics import TrainingAnalytics
from .tasks import generate_training_dataset_task, run_model_training_task


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
        ModelTrainingRun.objects.select_related("dataset", "created_by"),
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
