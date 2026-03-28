import uuid
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods

from .models import FlowExecution
from .services.datalake import DataLakeAnalytics
from .tasks import run_pipeline_task


@login_required
def index(request):
    """Main flows dashboard"""
    executions = FlowExecution.objects.filter(
        triggered_by=request.user
    ).order_by('-created_at')[:10]
    context = {
        'user': request.user,
        'executions': executions,
        'flows_count': executions.count(),
        'recent_runs': executions.filter(status='COMPLETED').count(),
    }
    return render(request, 'flows/index.html', context)


@login_required
def dashboard(request):
    """User dashboard with stats, prediction form, and recent executions"""
    executions = FlowExecution.objects.filter(
        triggered_by=request.user
    ).order_by('-created_at')

    total = executions.count()
    completed = executions.filter(status='COMPLETED')
    failed = executions.filter(status='FAILED').count()
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
    active_prediction = executions.filter(status='RUNNING').first()

    context = {
        'user': request.user,
        'active_page': 'dashboard',
        'active_prediction': active_prediction,
        'total_executions': total,
        'avg_duration': f"{avg_duration}s",
        'success_rate': f"{success_rate}%",
        'recent_executions': executions[:5],
    }
    return render(request, 'flows/dashboard.html', context)


@login_required
def history(request):
    """Execution history with search, filtering, and pagination"""
    executions = FlowExecution.objects.filter(
        triggered_by=request.user
    ).order_by('-created_at')

    # Search
    q = request.GET.get('q', '')
    if q:
        executions = executions.filter(flow_name__icontains=q)

    # Status filter
    status = request.GET.get('status', '')
    if status:
        executions = executions.filter(status=status)

    paginator = Paginator(executions, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'user': request.user,
        'active_page': 'history',
        'page_obj': page_obj,
        'executions': page_obj,
        'search_query': q,
        'status_filter': status,
    }

    if request.headers.get('HX-Request'):
        return render(request, 'flows/partials/history_table_body.html', context)

    return render(request, 'flows/history.html', context)


@login_required
def execution_detail(request, run_id):
    """Single execution detail page"""
    execution = get_object_or_404(
        FlowExecution, flow_run_id=run_id, triggered_by=request.user
    )

    duration = None
    if execution.completed_at and execution.created_at:
        duration = round((execution.completed_at - execution.created_at).total_seconds(), 2)

    # Mock prediction result data for the UI
    prediction_result = {
        'value': '0.82',
        'classification': 'Approved',
        'confidence': 82,
    }

    # Mock input values
    input_values = execution.parameters or {
        'income': '$75,000',
        'age': '35',
        'credit_score': '720',
        'employment_years': '8',
    }

    context = {
        'user': request.user,
        'active_page': 'history',
        'execution': execution,
        'duration': duration,
        'prediction_result': prediction_result,
        'input_values': input_values,
        'breadcrumbs': [
            {'name': 'Dashboard', 'url': '/flows/dashboard/'},
            {'name': 'History', 'url': '/flows/history/'},
            {'name': f'Execution #{str(execution.flow_run_id)[:8]}'},
        ],
    }
    return render(request, 'flows/execution_detail.html', context)


@login_required
def comparison(request):
    """Compare multiple executions side-by-side"""
    ids_param = request.GET.get('ids', '')
    run_ids = [i.strip() for i in ids_param.split(',') if i.strip()]

    executions = FlowExecution.objects.filter(
        flow_run_id__in=run_ids,
        triggered_by=request.user,
    ).order_by('-created_at')

    comparison_data = []
    for ex in executions:
        duration = None
        if ex.completed_at and ex.created_at:
            duration = round((ex.completed_at - ex.created_at).total_seconds(), 2)
        comparison_data.append({
            'execution': ex,
            'duration': duration,
            'prediction': {
                'value': '0.82',
                'classification': 'Approved',
                'confidence': 82,
            },
            'inputs': ex.parameters or {},
        })

    context = {
        'user': request.user,
        'active_page': 'history',
        'comparison_data': comparison_data,
        'breadcrumbs': [
            {'name': 'Dashboard', 'url': '/flows/dashboard/'},
            {'name': 'History', 'url': '/flows/history/'},
            {'name': 'Compare Predictions'},
        ],
    }
    return render(request, 'flows/comparison.html', context)


@login_required
@require_http_methods(["GET"])
def flows_menu(request):
    """HTMX endpoint: render flows dropdown menu"""
    user_flows = [
        {'id': 1, 'name': 'Data Processing', 'status': 'active'},
    ]
    return render(request, 'flows/components/flows_menu.html', {
        'flows': user_flows,
    })


@login_required
@require_http_methods(["POST"])
def upload_and_process(request):
    """Handle file upload and trigger pipeline via Celery"""
    uploaded_file = request.FILES.get('datafile')
    if not uploaded_file:
        return JsonResponse({'error': 'No file provided'}, status=400)

    run_id = uuid.uuid4()

    # Save to S3 raw zone via django-storages
    s3_key = f"raw/uploads/{request.user.id}/{run_id}/{uploaded_file.name}"
    file_path = default_storage.save(s3_key, uploaded_file)
    input_s3_path = f"s3://{settings.DATA_LAKE_BUCKET}/{file_path}"

    # Create execution record (RUNNING)
    execution = FlowExecution.objects.create(
        flow_run_id=run_id,
        flow_name='data-processing',
        triggered_by=request.user,
        s3_input_path=file_path,
        s3_output_path=f"processed/flows/data-processing/{run_id}/output.parquet",
        status='RUNNING',
        parameters={
            'input_s3_path': input_s3_path,
            'run_id': str(run_id),
            'user_id': request.user.id,
        }
    )

    # Enqueue Celery task — returns immediately
    task = run_pipeline_task.delay(
        flow_run_id=str(run_id),
        input_s3_path=input_s3_path,
        user_id=request.user.id,
    )
    execution.celery_task_id = task.id
    execution.save(update_fields=['celery_task_id'])

    return JsonResponse({
        'run_id': str(run_id),
        'status': 'RUNNING',
        'message': 'Pipeline started',
    })


@login_required
@require_http_methods(["GET"])
def flow_status(request, run_id):
    """HTMX polling endpoint: return current execution status"""
    execution = get_object_or_404(
        FlowExecution, flow_run_id=run_id, triggered_by=request.user
    )
    return JsonResponse({
        'status': execution.status,
        'row_count': execution.row_count,
        'error_message': execution.error_message,
        'completed_at': execution.completed_at.isoformat() if execution.completed_at else None,
    })


@login_required
@require_http_methods(["GET"])
def view_flow_results(request, run_id):
    """Display flow results using DuckDB"""
    execution = get_object_or_404(FlowExecution, flow_run_id=run_id)

    if not execution.s3_output_path:
        return render(request, 'flows/no_results.html', {'execution': execution})

    with DataLakeAnalytics() as analytics:
        preview = analytics.get_flow_results(execution.s3_output_path, limit=100)
        stats = analytics.get_summary_stats(execution.s3_output_path)

    return render(request, 'flows/results.html', {
        'execution': execution,
        'preview': preview.to_dicts(),
        'preview_columns': preview.columns,
        'stats': stats,
    })


@login_required
@require_http_methods(["GET"])
def download_results(request, run_id, format='csv'):
    """Download results in various formats"""
    from django.http import HttpResponse
    from django.shortcuts import redirect

    execution = get_object_or_404(FlowExecution, flow_run_id=run_id)

    if format == 'parquet':
        url = execution.generate_download_url(expires_in=3600)
        return redirect(url)

    with DataLakeAnalytics() as analytics:
        if format == 'csv':
            csv_data = analytics.export_to_csv(execution.s3_output_path)
            response = HttpResponse(csv_data, content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="results_{run_id}.csv"'
            return response

        if format == 'json':
            df = analytics.get_flow_results(execution.s3_output_path, limit=10000)
            return JsonResponse(df.to_dicts(), safe=False)

    return HttpResponse('Unsupported format', status=400)
