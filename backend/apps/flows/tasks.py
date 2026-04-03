"""
Celery tasks for async pipeline execution.
"""

import uuid

from config.celery import app
from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .runner import PipelineRunner


def _get_user_and_profile(user_id: int):
    """Return (user, profile) or (None, None) if user not found."""
    from apps.accounts.models import UserProfile
    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return None, None

    profile, _ = UserProfile.objects.get_or_create(user=user)
    return user, profile


def _create_in_app_notification(user, notification_type: str, message: str, execution=None):
    """Create a Notification record and invalidate the unread-count cache."""
    from apps.accounts.models import Notification

    Notification.objects.create(
        user=user,
        notification_type=notification_type,
        message=message,
        related_execution=execution,
    )
    cache.delete(f"notification_count_{user.pk}")


def _send_failure_notification(run_id: uuid.UUID, user_id: int, flow_name: str, error: str):
    """Notify the user (in-app and/or email) that an execution failed."""
    from apps.flows.models import FlowExecution

    user, profile = _get_user_and_profile(user_id)
    if user is None or not profile.notify_on_failure:
        return

    execution = FlowExecution.objects.filter(flow_run_id=run_id).first()
    message = f"Execution of '{flow_name}' failed. Error: {error[:200] if error else 'No details.'}"

    if profile.notify_in_app:
        _create_in_app_notification(user, "EXECUTION_FAILED", message, execution)

    if profile.notify_via_email:
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


def _send_success_notification(run_id: uuid.UUID, user_id: int, flow_name: str):
    """Notify the user (in-app and/or email) that an execution completed successfully."""
    from apps.flows.models import FlowExecution

    user, profile = _get_user_and_profile(user_id)
    if user is None or not profile.notify_on_success:
        return

    execution = FlowExecution.objects.filter(flow_run_id=run_id).first()
    message = f"Execution of '{flow_name}' completed successfully."

    if profile.notify_in_app:
        _create_in_app_notification(user, "EXECUTION_COMPLETED", message, execution)

    if profile.notify_via_email:
        site_url = settings.SITE_URL
        detail_path = reverse("flows:execution_detail", kwargs={"run_id": run_id})
        send_mail(
            subject=f"Execution completed: {flow_name} ({str(run_id)[:8]})",
            message=(
                f"Hi {user.first_name or user.username},\n\n"
                f"Your execution of '{flow_name}' completed successfully.\n\n"
                f"View results: {site_url}{detail_path}\n"
            ),
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

    except Exception as exc:
        error_str = str(exc)[:2000]
        FlowExecution.objects.filter(flow_run_id=run_id).update(
            status="FAILED",
            error_message=error_str,
        )
        if self.request.retries >= self.max_retries:
            _send_failure_notification(run_id, user_id, "pipeline", error_str)
        raise self.retry(exc=exc) from exc

    _send_success_notification(run_id, user_id, "pipeline")
    return metadata


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

    except Exception as exc:
        error_str = str(exc)[:2000]
        FlowExecution.objects.filter(flow_run_id=run_id).update(
            status="FAILED",
            error_message=error_str,
        )
        if self.request.retries >= self.max_retries:
            _send_failure_notification(run_id, user_id, "predict_pipeline", error_str)
        raise self.retry(exc=exc) from exc

    _send_success_notification(run_id, user_id, "predict_pipeline")
    return metadata
