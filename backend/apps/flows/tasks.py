"""
Celery tasks for async pipeline execution.
"""

import uuid

from config.celery import app
from django.utils import timezone

from .runner import PipelineRunner


@app.task(bind=True, max_retries=2, default_retry_delay=30)
def run_pipeline_task(
    self,
    flow_run_id: str,
    input_s3_path: str,
    user_id: int,
) -> dict:
    """
    Execute a doit/papermill pipeline asynchronously.

    Args:
        flow_run_id: UUID string matching a FlowExecution.flow_run_id.
        input_s3_path: S3 path to the uploaded input file.
        user_id: ID of the user who triggered the run (for logging).

    Returns:
        Metadata dict from the pipeline (row_count, s3_output_path, etc.).
    """
    from apps.flows.models import FlowExecution

    run_id = uuid.UUID(flow_run_id)

    try:
        runner = PipelineRunner()
        metadata = runner.run_pipeline(run_id=run_id, input_s3_path=input_s3_path)

        s3_output_path = metadata.get("s3_output_path", "")
        row_count = metadata.get("row_count")

        FlowExecution.objects.filter(flow_run_id=run_id).update(
            status="COMPLETED",
            s3_output_path=s3_output_path,
            row_count=row_count,
            completed_at=timezone.now(),
            error_message="",
        )

        return metadata

    except Exception as exc:
        FlowExecution.objects.filter(flow_run_id=run_id).update(
            status="FAILED",
            error_message=str(exc)[:2000],
        )
        raise self.retry(exc=exc) from exc


@app.task(bind=True, max_retries=2, default_retry_delay=30)
def run_prediction_task(
    self,
    flow_run_id: str,
    input_s3_path: str,
    user_id: int,
) -> dict:
    """
    Execute the credit-prediction pipeline (predict_ingest → predict_score)
    asynchronously via doit.

    Args:
        flow_run_id: UUID string matching a FlowExecution.flow_run_id.
        input_s3_path: S3 path to the uploaded 1-row prediction CSV.
        user_id: ID of the user who triggered the run (for logging).

    Returns:
        Metadata dict from the pipeline including score, classification, confidence.
    """
    from apps.flows.models import FlowExecution

    run_id = uuid.UUID(flow_run_id)

    try:
        runner = PipelineRunner()
        metadata = runner.run_pipeline(
            run_id=run_id,
            input_s3_path=input_s3_path,
            doit_task="predict_pipeline",
        )

        # Merge prediction results into existing parameters
        execution = FlowExecution.objects.get(flow_run_id=run_id)
        updated_params = {
            **execution.parameters,
            "score": metadata.get("score"),
            "classification": metadata.get("classification"),
            "confidence": metadata.get("confidence"),
        }

        FlowExecution.objects.filter(flow_run_id=run_id).update(
            status="COMPLETED",
            s3_output_path=metadata.get("s3_output_path", ""),
            row_count=metadata.get("row_count"),
            completed_at=timezone.now(),
            error_message="",
            parameters=updated_params,
        )

        return metadata

    except Exception as exc:
        FlowExecution.objects.filter(flow_run_id=run_id).update(
            status="FAILED",
            error_message=str(exc)[:2000],
        )
        raise self.retry(exc=exc) from exc
