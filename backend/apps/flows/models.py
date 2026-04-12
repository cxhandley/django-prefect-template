"""
Flow execution models.
"""

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from django.conf import settings
from django.db import models


class ExecutionStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    RUNNING = "RUNNING", "Running"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"


_EXECUTION_STATUS_TRANSITIONS: dict = {
    ExecutionStatus.PENDING: {ExecutionStatus.RUNNING, ExecutionStatus.FAILED},
    ExecutionStatus.RUNNING: {ExecutionStatus.COMPLETED, ExecutionStatus.FAILED},
    ExecutionStatus.COMPLETED: set(),
    ExecutionStatus.FAILED: set(),
}


def _status_can_transition(current: ExecutionStatus, target: ExecutionStatus) -> bool:
    return target in _EXECUTION_STATUS_TRANSITIONS.get(current, set())


class InputPreset(models.Model):
    """A named set of prediction input values saved by a user for quick reuse."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="input_presets",
    )
    name = models.CharField(max_length=100)
    input_values = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("user", "name")]

    def __str__(self):
        return f"{self.name} ({self.user.email})"


class FlowExecution(models.Model):
    """
    Stores metadata about flow executions.
    Actual data is stored in S3.
    """

    flow_run_id = models.UUIDField(unique=True)
    flow_name = models.CharField(max_length=200)
    triggered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    # S3 paths - NOT the actual data
    s3_input_path = models.CharField(max_length=500, blank=True)
    s3_output_path = models.CharField(max_length=500, blank=True)

    # Metadata for quick filtering
    row_count = models.BigIntegerField(null=True, blank=True)
    file_size_mb = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    status = models.CharField(
        max_length=50,
        choices=ExecutionStatus.choices,
        default=ExecutionStatus.PENDING,
    )

    # Typed prediction inputs (populated for credit-prediction flows only)
    income = models.FloatField(null=True, blank=True)
    age = models.IntegerField(null=True, blank=True)
    credit_score = models.IntegerField(null=True, blank=True)
    employment_years = models.FloatField(null=True, blank=True)

    # Legacy schemaless blob — kept for backwards compatibility; do not add new keys
    parameters = models.JSONField(default=dict)

    # Async execution tracking
    celery_task_id = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)

    # External orchestrator run identifier — null when using the doit backend,
    # populated with the Prefect flow-run UUID when using the Prefect backend.
    external_run_id = models.CharField(max_length=64, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["triggered_by", "-created_at"]),
            models.Index(fields=["flow_name", "status"]),
            models.Index(fields=["-created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.flow_name} - {self.flow_run_id}"

    def transition(self, target_status: ExecutionStatus | str, **update_fields) -> bool:
        """
        Guard-checked status transition. Raises ValueError for invalid transitions.
        Auto-sets completed_at when moving to COMPLETED or FAILED.
        Returns True and saves if the transition is valid.
        """
        from django.utils import timezone

        current = ExecutionStatus(self.status)
        target = ExecutionStatus(target_status)

        if not _status_can_transition(current, target):
            raise ValueError(f"Invalid status transition: {current.value!r} → {target.value!r}")

        self.status = target.value
        if target in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED):
            if "completed_at" not in update_fields:
                self.completed_at = timezone.now()

        for field, value in update_fields.items():
            setattr(self, field, value)

        fields = ["status"] + list(update_fields.keys())
        if target in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED):
            fields.append("completed_at")

        self.save(update_fields=fields)
        return True

    @property
    def s3_input_url(self):
        """Full S3 URL for input."""
        if self.s3_input_path:
            return f"s3://{settings.DATA_LAKE_BUCKET}/{self.s3_input_path}"
        return None

    @property
    def s3_output_url(self):
        """Full S3 URL for output."""
        if self.s3_output_path:
            return f"s3://{settings.DATA_LAKE_BUCKET}/{self.s3_output_path}"
        return None

    def delete(self, *args, **kwargs):
        """Delete execution record and clean up associated S3 objects."""
        self._delete_s3_objects()
        super().delete(*args, **kwargs)

    def _delete_s3_objects(self):
        """Remove input and output S3 objects. Safe to call when objects are absent."""
        paths = [p for p in [self.s3_input_path, self.s3_output_path] if p]
        if not paths:
            return

        s3_client = boto3.client(
            "s3",
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
            config=Config(signature_version="s3v4"),
        )

        for path in paths:
            try:
                s3_client.delete_object(Bucket=settings.DATA_LAKE_BUCKET, Key=path)
            except ClientError:
                pass

    def generate_download_url(self, filename=None):
        """Generate presigned S3 URL for direct download of the output file.

        Args:
            filename: Optional filename for the Content-Disposition header.
                      Defaults to the basename of s3_output_path.

        Returns:
            Presigned URL string, or None if no output path is set.
        """
        if not self.s3_output_path:
            return None

        expires_in = settings.DOWNLOAD_URL_EXPIRY_SECONDS

        if filename is None:
            filename = self.s3_output_path.rsplit("/", 1)[-1]

        s3_client = boto3.client(
            "s3",
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
            config=Config(signature_version="s3v4"),
        )

        return s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.DATA_LAKE_BUCKET,
                "Key": self.s3_output_path,
                "ResponseContentDisposition": f'attachment; filename="{filename}"',
            },
            ExpiresIn=expires_in,
        )


class PredictionClassification(models.TextChoices):
    APPROVED = "Approved", "Approved"
    REVIEW = "Review", "Review"
    DECLINED = "Declined", "Declined"


class PredictionResult(models.Model):
    """
    Typed result record for a completed credit-prediction execution.
    Replaces the schemaless parameters blob for result fields.
    """

    execution = models.OneToOneField(
        FlowExecution,
        on_delete=models.CASCADE,
        related_name="prediction_result",
    )
    scoring_model = models.ForeignKey(
        "ScoringModel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="results",
    )
    score = models.FloatField()
    classification = models.CharField(
        max_length=20,
        choices=PredictionClassification.choices,
    )
    confidence = models.FloatField()
    scored_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["classification"]),
            models.Index(fields=["scored_at"]),
        ]

    def __str__(self):
        return f"{self.classification} ({self.score:.2f}) — {self.execution.flow_run_id}"


class ScoringModel(models.Model):
    """
    A versioned credit scoring algorithm. Active model is used for new predictions.
    """

    version = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    weights = models.JSONField(
        help_text="Factor weights, e.g. {'credit_score': 0.40, 'income': 0.30, ...}"
    )
    thresholds = models.JSONField(
        help_text="Classification thresholds, e.g. {'approved': 0.70, 'review': 0.50}"
    )
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scoring_models",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"ScoringModel v{self.version}{'*' if self.is_active else ''}"

    def save(self, *args, **kwargs):
        """Ensure only one active model at a time."""
        if self.is_active:
            ScoringModel.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_active(cls) -> "ScoringModel | None":
        return cls.objects.filter(is_active=True).first()


class ExecutionStep(models.Model):
    """
    Per-step record within a pipeline execution.
    Created/updated by PipelineRunner as each notebook step runs.
    """

    execution = models.ForeignKey(
        FlowExecution,
        on_delete=models.CASCADE,
        related_name="steps",
    )
    step_name = models.CharField(max_length=100)
    step_index = models.SmallIntegerField()
    status = models.CharField(
        max_length=50,
        choices=ExecutionStatus.choices,
        default=ExecutionStatus.PENDING,
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    output_s3_path = models.CharField(max_length=500, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["step_index"]
        unique_together = [("execution", "step_index")]
        indexes = [
            models.Index(fields=["execution", "step_index"]),
        ]

    def __str__(self):
        return f"{self.execution.flow_run_id} — step {self.step_index}: {self.step_name}"
