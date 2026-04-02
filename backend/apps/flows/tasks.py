"""
Celery tasks for async pipeline execution.
"""

import uuid

from config.celery import app
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .runner import PipelineRunner


def _send_failure_notification(run_id: uuid.UUID, user_id: int, flow_name: str, error: str):
    """Send a failure email to the user if they have notifications enabled."""
    from apps.accounts.models import UserProfile
    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return

    try:
        notify = user.profile.notify_on_failure
    except UserProfile.DoesNotExist:
        notify = True

    if not notify:
        return

    site_url = settings.SITE_URL
    detail_path = reverse("flows:execution_detail", kwargs={"run_id": run_id})
    settings_path = reverse("accounts:settings")

    body = render_to_string(
        "flows/email/execution_failed.txt",
        {
            "first_name": user.first_name or user.username,
            "flow_name": flow_name,
            "run_id": str(run_id),
            "error_message": error[:500] if error else "No details available.",
            "detail_url": f"{site_url}{detail_path}",
            "settings_url": f"{site_url}{settings_path}",
        },
    )

    send_mail(
        subject=f"Execution failed: {flow_name} ({str(run_id)[:8]})",
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,
    )


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
        error_str = str(exc)[:2000]
        FlowExecution.objects.filter(flow_run_id=run_id).update(
            status="FAILED",
            error_message=error_str,
        )
        if self.request.retries >= self.max_retries:
            _send_failure_notification(run_id, user_id, "pipeline", error_str)
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
        error_str = str(exc)[:2000]
        FlowExecution.objects.filter(flow_run_id=run_id).update(
            status="FAILED",
            error_message=error_str,
        )
        if self.request.retries >= self.max_retries:
            _send_failure_notification(run_id, user_id, "predict_pipeline", error_str)
        raise self.retry(exc=exc) from exc
