import uuid
from django.conf import settings
from django.core.files.storage import default_storage
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
