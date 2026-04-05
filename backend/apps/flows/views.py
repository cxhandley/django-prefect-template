import csv
import datetime
import io
import json
import uuid

from apps.core.mixins import (
    build_active_filters,
    build_filter_query_string,
    build_table_config_json,
    get_filtered_queryset,
)
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import ExecutionStatus, FlowExecution, InputPreset
from .services.datalake import DataLakeAnalytics
from .tasks import run_pipeline_task, run_prediction_task

# ── DataTable configuration for the history view ──────────────────────────────

HISTORY_COLUMNS = [
    {
        "key": "created_at",
        "label": "Date / Time",
        "sortable": True,
        "sort_field": "created_at",
        "filterable": True,
        "filter_type": "datetime",
        "filter_choices": [],
        "visible": True,
        "hideable": False,
    },
    {
        "key": "input_summary",
        "label": "Input Summary",
        "sortable": False,
        "filterable": False,
        "visible": True,
        "hideable": True,
    },
    {
        "key": "classification",
        "label": "Prediction",
        "sortable": False,
        "filterable": True,
        "filter_type": "choice",
        "filter_choices": ["Approved", "Review", "Declined"],
        "visible": True,
        "hideable": True,
    },
    {
        "key": "status",
        "label": "Status",
        "sortable": True,
        "sort_field": "status",
        "filterable": True,
        "filter_type": "choice",
        "filter_choices": ["COMPLETED", "RUNNING", "FAILED", "PENDING"],
        "visible": True,
        "hideable": True,
    },
]

HISTORY_FILTER_FIELDS = {
    "created_at": {"type": "datetime", "orm_field": "created_at"},
    "classification": {"type": "choice", "orm_field": "prediction_result__classification"},
    "status": {"type": "choice", "orm_field": "status"},
}

HISTORY_BULK_ACTIONS = [
    {
        "key": "compare",
        "label": "Compare Selected",
        "method": "GET",
        "url": "/flows/comparison/",
        "id_param": "ids",
        "id_sep": ",",
        "min_select": 2,
        "max_select": 3,
        "confirm": False,
        "variant": "btn-outline btn-sm",
    },
]

# ── DataTable configuration for the admin executions view ────────────────────

ADMIN_EXEC_COLUMNS = [
    {
        "key": "created_at",
        "label": "Started",
        "sortable": True,
        "sort_field": "created_at",
        "filterable": True,
        "filter_type": "datetime",
        "filter_choices": [],
        "visible": True,
        "hideable": False,
    },
    {
        "key": "user",
        "label": "User",
        "sortable": True,
        "sort_field": "triggered_by__email",
        "filterable": True,
        "filter_type": "text",
        "filter_choices": [],
        "visible": True,
        "hideable": True,
    },
    {
        "key": "flow_name",
        "label": "Flow",
        "sortable": True,
        "sort_field": "flow_name",
        "filterable": True,
        "filter_type": "text",
        "filter_choices": [],
        "visible": True,
        "hideable": True,
    },
    {
        "key": "status",
        "label": "Status",
        "sortable": True,
        "sort_field": "status",
        "filterable": True,
        "filter_type": "choice",
        "filter_choices": ["COMPLETED", "RUNNING", "FAILED", "PENDING"],
        "visible": True,
        "hideable": True,
    },
    {
        "key": "duration",
        "label": "Duration",
        "sortable": False,
        "filterable": False,
        "visible": True,
        "hideable": True,
    },
    {
        "key": "error_message",
        "label": "Error",
        "sortable": False,
        "filterable": True,
        "filter_type": "text",
        "filter_choices": [],
        "visible": True,
        "hideable": True,
    },
]

ADMIN_EXEC_FILTER_FIELDS = {
    "created_at": {"type": "datetime", "orm_field": "created_at"},
    "user": {"type": "text", "orm_field": "triggered_by__email"},
    "flow_name": {"type": "text", "orm_field": "flow_name"},
    "status": {"type": "choice", "orm_field": "status"},
    "error_message": {"type": "text", "orm_field": "error_message"},
}

# ── Comparison constants ───────────────────────────────────────────────────────

PREDICTION_INPUT_KEYS = ["income", "age", "credit_score", "employment_years"]
PREDICTION_RESULT_KEYS = ["score", "classification", "confidence"]
COMPARISON_CSV_FIELDS = PREDICTION_INPUT_KEYS + PREDICTION_RESULT_KEYS


@login_required
def index(request):
    """Main flows dashboard"""
    qs = FlowExecution.objects.filter(triggered_by=request.user).order_by("-created_at")
    executions = qs[:10]
    context = {
        "user": request.user,
        "executions": executions,
        "flows_count": qs.count(),
        "recent_runs": qs.filter(status=ExecutionStatus.COMPLETED).count(),
    }
    return render(request, "flows/index.html", context)


@login_required
def dashboard(request):
    """User dashboard with stats, prediction form, and recent executions"""
    executions = FlowExecution.objects.filter(triggered_by=request.user).order_by("-created_at")

    total = executions.count()
    completed = executions.filter(status=ExecutionStatus.COMPLETED)
    success_rate = round((completed.count() / total * 100), 1) if total > 0 else 0

    # Calculate average duration for completed executions
    avg_duration = 0
    if completed.exists():
        durations = []
        for ex in completed:
            if ex.completed_at and ex.created_at:
                diff = (ex.completed_at - ex.created_at).total_seconds()
                durations.append(diff)
        if durations:
            avg_duration = round(sum(durations) / len(durations), 1)

    # Get the most recent running execution as active prediction
    active_prediction = executions.filter(status=ExecutionStatus.RUNNING).first()

    presets = InputPreset.objects.filter(user=request.user)

    context = {
        "user": request.user,
        "active_page": "dashboard",
        "active_prediction": active_prediction,
        "total_executions": total,
        "avg_duration": f"{avg_duration}s",
        "success_rate": f"{success_rate}%",
        "recent_executions": executions[:5],
        "presets": presets,
    }
    return render(request, "flows/dashboard.html", context)


@login_required
def history(request):
    """Execution history with DataTable: advanced filtering, sorting, pagination."""
    qs = FlowExecution.objects.filter(triggered_by=request.user)
    qs, sort = get_filtered_queryset(
        request, qs, HISTORY_FILTER_FIELDS, HISTORY_COLUMNS, default_sort="-created_at"
    )

    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    # Determine if any running/pending executions exist in the filtered set
    # (not just on the current page) so the table poller registers correctly.
    has_running_rows = qs.filter(
        status__in=[ExecutionStatus.RUNNING, ExecutionStatus.PENDING]
    ).exists()

    table_config = {
        "table_id": "history",
        "hx_url": reverse("flows:history"),
        "hx_target": "#dt-history-body",
        "columns": HISTORY_COLUMNS,
        "bulk_actions": HISTORY_BULK_ACTIONS,
        "active_filters": build_active_filters(request),
        "sort_field": sort,
    }

    context = {
        "user": request.user,
        "active_page": "history",
        "page_obj": page_obj,
        "has_running_rows": has_running_rows,
        "table_config": table_config,
        "table_config_json": build_table_config_json(table_config),
        "page_row_ids_json": json.dumps([str(ex.flow_run_id) for ex in page_obj]),
        "filter_query_string": build_filter_query_string(request),
        "table_body_template": "flows/partials/history_table_body.html",
    }

    if request.headers.get("HX-Request"):
        return render(request, "flows/partials/history_table_body.html", context)

    return render(request, "flows/history.html", context)


@login_required
@require_http_methods(["GET"])
def export_history_csv(request):
    """Export all of the authenticated user's executions as a CSV download."""
    from django.http import HttpResponse

    executions = FlowExecution.objects.filter(triggered_by=request.user).order_by("-created_at")

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["id", "flow_name", "status", "row_count", "file_size_mb", "created_at", "completed_at"]
    )
    for ex in executions:
        writer.writerow(
            [
                ex.flow_run_id,
                ex.flow_name,
                ex.status,
                ex.row_count,
                ex.file_size_mb,
                ex.created_at.isoformat(),
                ex.completed_at.isoformat() if ex.completed_at else "",
            ]
        )

    response = HttpResponse(buffer.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="execution_history.csv"'
    return response


@login_required
def execution_detail(request, run_id):
    """Single execution detail page"""
    execution = get_object_or_404(FlowExecution, flow_run_id=run_id, triggered_by=request.user)

    duration = None
    if execution.completed_at and execution.created_at:
        duration = round((execution.completed_at - execution.created_at).total_seconds(), 2)

    prediction_result = None
    input_values = None
    if execution.flow_name == "credit-prediction":
        try:
            pr = execution.prediction_result
            prediction_result = {
                "score": pr.score,
                "classification": pr.classification,
                "confidence": pr.confidence,
            }
        except execution.__class__.prediction_result.RelatedObjectDoesNotExist:
            pass
        input_values = {
            "income": execution.income,
            "age": execution.age,
            "credit_score": execution.credit_score,
            "employment_years": execution.employment_years,
        }

    steps = list(execution.steps.all())

    context = {
        "user": request.user,
        "active_page": "history",
        "execution": execution,
        "duration": duration,
        "prediction_result": prediction_result,
        "input_values": input_values,
        "steps": steps,
        "breadcrumbs": [
            {"name": "Dashboard", "url": "/flows/dashboard/"},
            {"name": "History", "url": "/flows/history/"},
            {"name": f"Execution #{str(execution.flow_run_id)[:8]}"},
        ],
    }
    return render(request, "flows/execution_detail.html", context)


@login_required
def comparison(request):
    """Compare multiple prediction executions side-by-side using real parameters."""
    ids_param = request.GET.get("ids", "")
    run_ids = [i.strip() for i in ids_param.split(",") if i.strip()]

    executions = list(
        FlowExecution.objects.filter(
            flow_run_id__in=run_ids,
            triggered_by=request.user,
        ).order_by("-created_at")
    )

    breadcrumbs = [
        {"name": "Dashboard", "url": "/flows/dashboard/"},
        {"name": "History", "url": "/flows/history/"},
        {"name": "Compare Predictions"},
    ]

    if len(executions) < 2:
        return render(
            request,
            "flows/comparison.html",
            {
                "user": request.user,
                "active_page": "history",
                "comparison_data": [],
                "differing_fields": set(),
                "ids_param": ids_param,
                "insufficient": len(executions) == 1,
                "breadcrumbs": breadcrumbs,
            },
        )

    def _get_inputs(ex):
        return {
            "income": ex.income,
            "age": ex.age,
            "credit_score": ex.credit_score,
            "employment_years": ex.employment_years,
        }

    def _get_result(ex):
        try:
            pr = ex.prediction_result
            return {
                "score": pr.score,
                "classification": pr.classification,
                "confidence": pr.confidence,
            }
        except ex.__class__.prediction_result.RelatedObjectDoesNotExist:
            return {"score": None, "classification": None, "confidence": None}

    # Determine which input fields differ across all selected executions
    differing_fields = set()
    for key in PREDICTION_INPUT_KEYS:
        values = {str(getattr(ex, key)) for ex in executions}
        if len(values) > 1:
            differing_fields.add(key)

    comparison_data = []
    for ex in executions:
        duration = None
        if ex.completed_at and ex.created_at:
            duration = round((ex.completed_at - ex.created_at).total_seconds(), 2)
        comparison_data.append(
            {
                "execution": ex,
                "duration": duration,
                "inputs": _get_inputs(ex),
                "result": _get_result(ex),
            }
        )

    context = {
        "user": request.user,
        "active_page": "history",
        "comparison_data": comparison_data,
        "differing_fields": differing_fields,
        "ids_param": ids_param,
        "insufficient": False,
        "breadcrumbs": breadcrumbs,
    }
    return render(request, "flows/comparison.html", context)


@login_required
@require_http_methods(["GET"])
def comparison_export(request):
    """Download the comparison data as a CSV file."""
    ids_param = request.GET.get("ids", "")
    run_ids = [i.strip() for i in ids_param.split(",") if i.strip()]

    executions = list(
        FlowExecution.objects.filter(
            flow_run_id__in=run_ids,
            triggered_by=request.user,
        ).order_by("-created_at")
    )

    if len(executions) < 2:
        return redirect(f"/flows/comparison/?ids={ids_param}")

    short_ids = [str(ex.flow_run_id)[:8] for ex in executions]

    def _get_field_value(ex, field):
        # Input fields are typed columns on FlowExecution
        if field in PREDICTION_INPUT_KEYS:
            return getattr(ex, field, "") or ""
        # Result fields come from PredictionResult
        try:
            pr = ex.prediction_result
            return getattr(pr, field, "") or ""
        except ex.__class__.prediction_result.RelatedObjectDoesNotExist:
            return ""

    def _rows():
        yield ["field"] + short_ids
        for field in COMPARISON_CSV_FIELDS:
            row = [field]
            for ex in executions:
                row.append(_get_field_value(ex, field))
            yield row

    def _stream():
        buf = io.StringIO()
        writer = csv.writer(buf)
        for row in _rows():
            writer.writerow(row)
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate()

    date_str = datetime.date.today().strftime("%Y-%m-%d")
    response = StreamingHttpResponse(_stream(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="comparison_{date_str}.csv"'
    return response


@login_required
@require_http_methods(["GET"])
def flows_menu(request):
    """HTMX endpoint: render flows dropdown menu"""
    user_flows = [
        {"id": 1, "name": "Data Processing", "status": "active"},
    ]
    return render(
        request,
        "flows/components/flows_menu.html",
        {
            "flows": user_flows,
        },
    )


@login_required
@require_http_methods(["POST"])
def upload_and_process(request):
    """Handle file upload and trigger pipeline via Celery"""
    uploaded_file = request.FILES.get("datafile")
    if not uploaded_file:
        return JsonResponse({"error": "No file provided"}, status=400)

    run_id = uuid.uuid4()

    # Save to S3 raw zone via django-storages
    s3_key = f"raw/uploads/{request.user.id}/{run_id}/{uploaded_file.name}"
    file_path = default_storage.save(s3_key, uploaded_file)
    input_s3_path = f"s3://{settings.DATA_LAKE_BUCKET}/{file_path}"

    # Create execution record (RUNNING)
    execution = FlowExecution.objects.create(
        flow_run_id=run_id,
        flow_name="data-processing",
        triggered_by=request.user,
        s3_input_path=file_path,
        s3_output_path=f"processed/flows/data-processing/{run_id}/output.parquet",
        status=ExecutionStatus.RUNNING,
    )

    # Enqueue Celery task — returns immediately
    task = run_pipeline_task.delay(
        flow_run_id=str(run_id),
        input_s3_path=input_s3_path,
        user_id=request.user.id,
    )
    execution.celery_task_id = task.id
    execution.save(update_fields=["celery_task_id"])

    return JsonResponse(
        {
            "run_id": str(run_id),
            "status": ExecutionStatus.RUNNING,
            "message": "Pipeline started",
        }
    )


@login_required
@require_http_methods(["GET"])
def flow_status(request, run_id):
    """HTMX polling endpoint: return current execution status"""
    execution = get_object_or_404(FlowExecution, flow_run_id=run_id, triggered_by=request.user)
    return JsonResponse(
        {
            "status": execution.status,
            "row_count": execution.row_count,
            "error_message": execution.error_message,
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
        }
    )


@login_required
@require_http_methods(["GET"])
def view_flow_results(request, run_id):
    """Display flow results using DuckDB"""
    execution = get_object_or_404(FlowExecution, flow_run_id=run_id)

    if not execution.s3_output_path:
        return render(request, "flows/no_results.html", {"execution": execution})

    with DataLakeAnalytics() as analytics:
        preview = analytics.get_flow_results(execution.s3_output_path, limit=100)
        stats = analytics.get_summary_stats(execution.s3_output_path)

    return render(
        request,
        "flows/results.html",
        {
            "execution": execution,
            "preview": preview.to_dicts(),
            "preview_columns": preview.columns,
            "stats": stats,
        },
    )


@login_required
@require_http_methods(["GET"])
def download_results(request, run_id, format="csv"):
    """Download results in various formats.

    Parquet: redirects to a presigned S3 URL (no server-side data transfer).
    CSV/JSON: generated server-side from the output Parquet via DuckDB.
    """
    from django.http import HttpResponse
    from django.shortcuts import redirect

    execution = get_object_or_404(FlowExecution, flow_run_id=run_id, triggered_by=request.user)

    if format == "parquet":
        url = execution.generate_download_url(filename=f"results_{run_id}.parquet")
        return redirect(url)

    with DataLakeAnalytics() as analytics:
        if format == "csv":
            csv_data = analytics.export_to_csv(execution.s3_output_path)
            response = HttpResponse(csv_data, content_type="text/csv")
            response["Content-Disposition"] = f'attachment; filename="results_{run_id}.csv"'
            return response

        if format == "json":
            df = analytics.get_flow_results(execution.s3_output_path, limit=10000)
            response = JsonResponse(df.to_dicts(), safe=False)
            response["Content-Disposition"] = f'attachment; filename="results_{run_id}.json"'
            return response

    return HttpResponse("Unsupported format", status=400)


@login_required
@require_http_methods(["POST"])
def run_prediction(request):
    """Accept prediction form, create a 1-row CSV in S3, and run predict_pipeline."""
    # Parse inputs
    try:
        income = float(request.POST.get("income", ""))
        age = int(request.POST.get("age", ""))
        credit_score = int(request.POST.get("credit_score", ""))
        employment_years = float(request.POST.get("employment_years", ""))
    except (ValueError, TypeError):
        return render(
            request,
            "flows/partials/prediction_error.html",
            {"error": "All fields are required and must be valid numbers."},
        )

    # Validate ranges
    if income <= 0:
        return render(
            request,
            "flows/partials/prediction_error.html",
            {"error": "Income must be a positive number."},
        )
    if not (18 <= age <= 120):
        return render(
            request,
            "flows/partials/prediction_error.html",
            {"error": "Age must be between 18 and 120."},
        )
    if not (300 <= credit_score <= 850):
        return render(
            request,
            "flows/partials/prediction_error.html",
            {"error": "Credit score must be between 300 and 850."},
        )
    if employment_years < 0:
        return render(
            request,
            "flows/partials/prediction_error.html",
            {"error": "Employment years must be zero or greater."},
        )

    run_id = uuid.uuid4()

    # Build 1-row CSV in memory and upload to S3
    csv_buffer = io.StringIO()
    writer = csv.DictWriter(
        csv_buffer,
        fieldnames=["income", "age", "credit_score", "employment_years"],
    )
    writer.writeheader()
    writer.writerow(
        {
            "income": income,
            "age": age,
            "credit_score": credit_score,
            "employment_years": employment_years,
        }
    )
    s3_key = f"raw/predictions/{request.user.id}/{run_id}/input.csv"
    file_path = default_storage.save(s3_key, ContentFile(csv_buffer.getvalue().encode("utf-8")))
    input_s3_path = f"s3://{settings.DATA_LAKE_BUCKET}/{file_path}"

    # Create execution record — typed input fields populated directly
    execution = FlowExecution.objects.create(
        flow_run_id=run_id,
        flow_name="credit-prediction",
        triggered_by=request.user,
        s3_input_path=file_path,
        s3_output_path=f"processed/flows/credit-prediction/{run_id}/output.parquet",
        status=ExecutionStatus.RUNNING,
        income=income,
        age=age,
        credit_score=credit_score,
        employment_years=employment_years,
    )

    # Enqueue Celery task
    task = run_prediction_task.delay(
        flow_run_id=str(run_id),
        input_s3_path=input_s3_path,
        user_id=request.user.id,
    )
    execution.celery_task_id = task.id
    execution.save(update_fields=["celery_task_id"])

    return render(
        request,
        "flows/partials/prediction_running.html",
        {
            "run_id": str(run_id),
        },
    )


@login_required
@require_http_methods(["GET"])
def prediction_status(request, run_id):
    """HTMX polling endpoint: return HTML partial based on prediction execution status."""
    execution = get_object_or_404(
        FlowExecution,
        flow_run_id=run_id,
        triggered_by=request.user,
        flow_name="credit-prediction",
    )

    if execution.status == ExecutionStatus.COMPLETED:
        try:
            pr = execution.prediction_result
            score = pr.score
            classification = pr.classification
            confidence = pr.confidence
        except execution.__class__.prediction_result.RelatedObjectDoesNotExist:
            score = classification = confidence = None
        return render(
            request,
            "flows/partials/prediction_result.html",
            {
                "run_id": str(run_id),
                "score": score,
                "classification": classification,
                "confidence": confidence,
            },
        )

    if execution.status == ExecutionStatus.FAILED:
        return render(
            request,
            "flows/partials/prediction_error.html",
            {
                "error": execution.error_message
                or "The prediction pipeline failed. Please try again.",
            },
        )

    # Still RUNNING or PENDING — return spinner (HTMX will keep polling)
    return render(
        request,
        "flows/partials/prediction_running.html",
        {
            "run_id": str(run_id),
        },
    )


@login_required
@require_http_methods(["POST"])
def stop_execution(request, run_id):
    """Revoke the Celery task and mark the execution as stopped."""
    execution = get_object_or_404(FlowExecution, flow_run_id=run_id, triggered_by=request.user)

    if execution.celery_task_id:
        from config.celery import app as celery_app

        celery_app.control.revoke(execution.celery_task_id, terminate=True, signal="SIGTERM")

    FlowExecution.objects.filter(flow_run_id=run_id).update(
        status=ExecutionStatus.FAILED,
        error_message="Stopped by user.",
        completed_at=timezone.now(),
    )

    return redirect("flows:execution_detail", run_id=run_id)


@login_required
@require_http_methods(["POST"])
def delete_execution(request, run_id):
    """Revoke any running task and delete the execution record."""
    execution = get_object_or_404(FlowExecution, flow_run_id=run_id, triggered_by=request.user)

    if execution.celery_task_id:
        from config.celery import app as celery_app

        celery_app.control.revoke(execution.celery_task_id, terminate=True, signal="SIGTERM")

    execution.delete()

    return redirect("flows:history")


# ── Admin views (staff only) ──────────────────────────────────────────────────


@staff_member_required(login_url="/accounts/login/")
@require_http_methods(["GET"])
def admin_dashboard(request):
    """Staff-only monitoring dashboard with system-wide usage stats."""
    now = timezone.now()
    thirty_days_ago = now - datetime.timedelta(days=30)

    all_executions = FlowExecution.objects.all()
    recent = all_executions.filter(created_at__gte=thirty_days_ago)

    total = all_executions.count()
    total_recent = recent.count()

    completed = all_executions.filter(status=ExecutionStatus.COMPLETED)
    success_rate = round(completed.count() / total * 100, 1) if total else 0

    # Average runtime for completed executions that have both timestamps
    avg_duration = None
    durations = [
        (ex.completed_at - ex.created_at).total_seconds()
        for ex in completed.exclude(completed_at__isnull=True)
        if ex.completed_at and ex.created_at
    ]
    if durations:
        avg_duration = round(sum(durations) / len(durations), 1)

    # Breakdown by user (last 30 days)
    by_user = (
        recent.values("triggered_by__email", "triggered_by__username")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )

    # Breakdown by flow type (last 30 days) with success rate per type
    by_flow = []
    for row in recent.values("flow_name").annotate(count=Count("id")).order_by("-count"):
        flow_name = row["flow_name"]
        flow_completed = recent.filter(
            flow_name=flow_name, status=ExecutionStatus.COMPLETED
        ).count()
        flow_rate = round(flow_completed / row["count"] * 100) if row["count"] else 0
        by_flow.append({"flow_name": flow_name, "count": row["count"], "success_rate": flow_rate})

    # Daily counts for the last 30 days (for the bar chart)
    daily_raw = (
        recent.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(count=Count("id"))
        .order_by("day")
    )
    daily_map = {row["day"]: row["count"] for row in daily_raw}
    daily_counts = []
    for i in range(30):
        day = (now - datetime.timedelta(days=29 - i)).date()
        daily_counts.append({"day": day, "count": daily_map.get(day, 0)})

    max_daily = max((d["count"] for d in daily_counts), default=1) or 1

    chart_start = daily_counts[0]["day"] if daily_counts else None
    chart_end = daily_counts[-1]["day"] if daily_counts else None

    context = {
        "active_page": "admin_dashboard",
        "total": total,
        "total_recent": total_recent,
        "success_rate": f"{success_rate}%",
        "avg_duration": f"{avg_duration}s" if avg_duration is not None else "—",
        "by_user": by_user,
        "by_flow": by_flow,
        "daily_counts": daily_counts,
        "max_daily": max_daily,
        "chart_start": chart_start,
        "chart_end": chart_end,
    }
    return render(request, "flows/admin_dashboard.html", context)


@login_required
@require_http_methods(["GET"])
def prediction_compare_options(request):
    """Return a partial listing completed predictions the user can compare against."""
    exclude_id = request.GET.get("exclude", "").strip()
    qs = (
        FlowExecution.objects.filter(
            triggered_by=request.user,
            flow_name="credit-prediction",
            status=ExecutionStatus.COMPLETED,
        )
        .exclude(flow_run_id=exclude_id)
        .order_by("-created_at")[:20]
    )
    return render(
        request,
        "flows/partials/prediction_compare_options.html",
        {"executions": qs, "current_run_id": exclude_id},
    )


@login_required
@require_http_methods(["POST"])
def save_preset(request):
    """Save current prediction form values as a named preset."""
    name = request.POST.get("preset_name", "").strip()
    if not name:
        return render(
            request,
            "flows/partials/preset_save_error.html",
            {"error": "Preset name is required."},
        )

    input_values = {
        field: request.POST.get(field, "")
        for field in ("income", "age", "credit_score", "employment_years")
        if request.POST.get(field, "").strip()
    }

    preset, created = InputPreset.objects.get_or_create(
        user=request.user,
        name=name,
        defaults={"input_values": input_values},
    )
    if not created:
        preset.input_values = input_values
        preset.save(update_fields=["input_values"])

    presets = InputPreset.objects.filter(user=request.user)
    return render(
        request,
        "flows/partials/preset_controls.html",
        {"presets": presets, "saved_name": name},
    )


@login_required
@require_http_methods(["GET"])
def load_preset(request):
    """Return pre-filled prediction inputs partial for a selected preset."""
    preset_id = request.GET.get("preset_id", "").strip()
    if not preset_id:
        return render(request, "flows/partials/prediction_inputs.html", {"values": {}})

    preset = get_object_or_404(InputPreset, pk=preset_id, user=request.user)
    return render(
        request,
        "flows/partials/prediction_inputs.html",
        {"values": preset.input_values},
    )


@login_required
@require_http_methods(["POST"])
def delete_preset(request, preset_id):
    """Delete a preset and return the updated preset list partial."""
    preset = get_object_or_404(InputPreset, pk=preset_id, user=request.user)
    preset.delete()
    presets = InputPreset.objects.filter(user=request.user)
    return render(request, "flows/partials/preset_list.html", {"presets": presets})


@staff_member_required(login_url="/accounts/login/")
@require_http_methods(["GET"])
def admin_executions(request):
    """Staff-only execution log viewer with DataTable: filters across all users."""
    qs = FlowExecution.objects.select_related("triggered_by")
    qs, sort = get_filtered_queryset(
        request, qs, ADMIN_EXEC_FILTER_FIELDS, ADMIN_EXEC_COLUMNS, default_sort="-created_at"
    )

    has_running_rows = qs.filter(
        status__in=[ExecutionStatus.RUNNING, ExecutionStatus.PENDING]
    ).exists()

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    table_config = {
        "table_id": "admin-exec",
        "hx_url": reverse("flows:admin_executions"),
        "hx_target": "#dt-admin-exec-body",
        "columns": ADMIN_EXEC_COLUMNS,
        "bulk_actions": [],
        "active_filters": build_active_filters(request),
        "sort_field": sort,
    }

    context = {
        "active_page": "admin_dashboard",
        "page_obj": page_obj,
        "has_running_rows": has_running_rows,
        "table_config": table_config,
        "table_config_json": build_table_config_json(table_config),
        "page_row_ids_json": json.dumps([str(ex.flow_run_id) for ex in page_obj]),
        "filter_query_string": build_filter_query_string(request),
        "table_body_template": "flows/partials/admin_executions_table_body.html",
        "breadcrumbs": [
            {"name": "Admin Dashboard", "url": "/flows/admin/dashboard/"},
            {"name": "Execution Logs"},
        ],
    }

    if request.headers.get("HX-Request"):
        return render(request, "flows/partials/admin_executions_table_body.html", context)
    return render(request, "flows/admin_executions.html", context)


@login_required
@require_http_methods(["POST"])
def retry_execution(request, run_id):
    """Clone a FAILED execution and dispatch the same task with original parameters."""
    original = get_object_or_404(FlowExecution, flow_run_id=run_id, triggered_by=request.user)

    if original.status != ExecutionStatus.FAILED:
        return redirect("flows:execution_detail", run_id=run_id)

    new_run_id = uuid.uuid4()
    new_execution = FlowExecution.objects.create(
        flow_run_id=new_run_id,
        flow_name=original.flow_name,
        triggered_by=request.user,
        s3_input_path=original.s3_input_path,
        status=ExecutionStatus.PENDING,
        # Copy typed prediction inputs (null for non-prediction flows)
        income=original.income,
        age=original.age,
        credit_score=original.credit_score,
        employment_years=original.employment_years,
    )

    if original.flow_name == "predict_pipeline":
        task = run_prediction_task.delay(
            flow_run_id=str(new_run_id),
            input_s3_path=original.s3_input_path,
            user_id=request.user.id,
        )
    else:
        task = run_pipeline_task.delay(
            flow_run_id=str(new_run_id),
            input_s3_path=original.s3_input_path,
            user_id=request.user.id,
        )

    new_execution.celery_task_id = task.id
    new_execution.save(update_fields=["celery_task_id"])

    return redirect("flows:execution_detail", run_id=new_run_id)


@staff_member_required(login_url="/accounts/login/")
@require_http_methods(["GET"])
def admin_execution_detail(request, run_id):
    """Staff-only execution detail — can view any user's execution."""
    execution = get_object_or_404(
        FlowExecution.objects.select_related("triggered_by"), flow_run_id=run_id
    )

    duration = None
    if execution.completed_at and execution.created_at:
        duration = round((execution.completed_at - execution.created_at).total_seconds(), 2)

    flower_url = getattr(settings, "FLOWER_URL", "/flower/")

    context = {
        "active_page": "admin_dashboard",
        "execution": execution,
        "duration": duration,
        "flower_url": flower_url,
        "breadcrumbs": [
            {"name": "Admin Dashboard", "url": "/flows/admin/dashboard/"},
            {"name": "Execution Logs", "url": "/flows/admin/executions/"},
            {"name": f"Execution #{str(execution.flow_run_id)[:8]}"},
        ],
    }
    return render(request, "flows/admin_execution_detail.html", context)
