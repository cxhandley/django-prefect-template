import uuid
from django.core.files.storage import default_storage
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods

from .services.datalake import DataLakeAnalytics


@login_required
def index(request):
    """Main flows dashboard"""
    context = {
        'user': request.user,
        'flows_count': 12,  # Would query from DB
        'recent_runs': 3,
    }
    return render(request, 'flows/index.html', context)


@login_required
@require_http_methods(["GET"])
def flows_menu(request):
    """HTMX endpoint: render flows dropdown menu"""
    user_flows = [
        {'id': 1, 'name': 'Data Processing', 'status': 'active'},
        {'id': 2, 'name': 'Report Generation', 'status': 'paused'},
        {'id': 3, 'name': 'Analytics Pipeline', 'status': 'active'},
    ]
    return render(request, 'flows/components/flows_menu.html', {
        'flows': user_flows,
    })


@login_required
@require_http_methods(["POST"])
def upload_and_process(request):
    """Handle file upload and trigger Prefect flow"""
    uploaded_file = request.FILES['datafile']
    
    # Generate unique ID for this upload
    upload_id = uuid.uuid4()
    
    # Save to S3 raw zone
    s3_key = f"raw/uploads/{request.user.id}/{upload_id}/{uploaded_file.name}"
    file_path = default_storage.save(s3_key, uploaded_file)
    
    # Trigger Prefect flow via FastAPI gateway
    from .api_client import GatewayClient
    client = GatewayClient()
    
    result = client.trigger_flow(
        flow_name='data-processing',
        parameters={
            'input_s3_path': f"s3://{settings.DATA_LAKE_BUCKET}/{file_path}",
            'run_id': str(upload_id),
            'user_id': request.user.id
        }
    )
    
    # Store execution metadata in Django (not the data!)
    FlowExecution.objects.create(
        flow_run_id=result['run_id'],
        flow_name='data-processing',
        triggered_by=request.user,
        s3_input_path=file_path,
        s3_output_path=f"processed/flows/data-processing/{upload_id}/output.parquet",
        status='RUNNING'
    )
    
    return JsonResponse({
        'run_id': result['run_id'],
        'upload_id': str(upload_id),
        'message': 'Processing started'
    })


@login_required
@require_http_methods(["GET"])
def view_flow_results(request, run_id):
    """Display flow results using DuckDB"""
    execution = FlowExecution.objects.get(flow_run_id=run_id)
    
    if not execution.s3_output_path:
        return render(request, 'flows/no_results.html', {'execution': execution})
    
    analytics = DataLakeAnalytics()
    
    # Get preview (first 100 rows) - DuckDB doesn't load full file
    preview = analytics.get_flow_results(execution.s3_output_path, limit=100)
    
    # Get summary stats - DuckDB computes without loading all data
    stats = analytics.get_summary_stats(execution.s3_output_path)
    
    return render(request, 'flows/results.html', {
        'execution': execution,
        'preview': preview.to_dict('records'),
        'preview_columns': preview.columns.tolist(),
        'stats': stats
    })


@login_required
@require_http_methods(["GET"])
def download_results(request, run_id, format='parquet'):
    """Download results in various formats"""
    execution = FlowExecution.objects.get(flow_run_id=run_id)
    
    if format == 'parquet':
        # Direct S3 download (fastest - no Django processing)
        import boto3
        s3_client = boto3.client('s3')
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': settings.DATA_LAKE_BUCKET,
                'Key': execution.s3_output_path
            },
            ExpiresIn=3600  # 1 hour
        )
        return redirect(url)
    
    else:
        # Convert format on-the-fly with DuckDB
        analytics = DataLakeAnalytics()
        
        if format == 'csv':
            query = f"""
                COPY (
                    SELECT * FROM read_parquet('s3://{settings.DATA_LAKE_BUCKET}/{execution.s3_output_path}')
                ) TO '/dev/stdout' (FORMAT CSV, HEADER)
            """
            df = analytics.conn.execute(query).df()
            
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="results_{run_id}.csv"'
            df.to_csv(response, index=False)
            return response
        
        elif format == 'json':
            query = f"""
                SELECT * FROM read_parquet('s3://{settings.DATA_LAKE_BUCKET}/{execution.s3_output_path}')
            """
            df = analytics.conn.execute(query).df()
            return JsonResponse(df.to_dict('records'), safe=False)