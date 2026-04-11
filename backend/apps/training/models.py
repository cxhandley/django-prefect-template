import uuid

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from django.conf import settings
from django.db import models


class DatasetStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    GENERATING = "GENERATING", "Generating"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"


class OptimisationTarget(models.TextChoices):
    GINI = "GINI", "Gini Coefficient"
    KS = "KS", "KS Statistic"
    F1_REVIEW = "F1_REVIEW", "F1 (Review Class)"


class TrainingRunStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    RUNNING = "RUNNING", "Running"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"


class TrainingDataset(models.Model):
    """A labelled synthetic dataset used to train and backtest scoring models."""

    slug = models.CharField(max_length=50, unique=True, db_index=True)
    description = models.TextField(blank=True)
    row_count = models.PositiveIntegerField(
        help_text="Target number of rows requested at generation time."
    )
    seed = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Random seed for reproducibility. Leave blank for a random seed.",
    )
    s3_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="S3 key (without bucket prefix) for the generated data.parquet.",
    )
    status = models.CharField(
        max_length=20,
        choices=DatasetStatus.choices,
        default=DatasetStatus.PENDING,
    )
    celery_task_id = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="training_datasets",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"{self.slug} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = f"ds-{uuid.uuid4().hex[:12]}"
        super().save(*args, **kwargs)

    @property
    def is_terminal(self) -> bool:
        return self.status in (DatasetStatus.COMPLETED, DatasetStatus.FAILED)

    @property
    def s3_full_path(self) -> str | None:
        if not self.s3_path:
            return None
        return f"s3://{settings.DATA_LAKE_BUCKET}/{self.s3_path}"

    def delete(self, *args, **kwargs):
        self._delete_s3_file()
        super().delete(*args, **kwargs)

    def _delete_s3_file(self):
        if not self.s3_path:
            return
        s3_client = boto3.client(
            "s3",
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
            config=Config(signature_version="s3v4"),
        )
        try:
            s3_client.delete_object(Bucket=settings.DATA_LAKE_BUCKET, Key=self.s3_path)
        except ClientError:
            pass


class ModelTrainingRun(models.Model):
    """A weight-and-threshold optimisation run against a training dataset."""

    label = models.CharField(max_length=100, help_text="Human-readable label, e.g. 'round_1'.")
    dataset = models.ForeignKey(
        TrainingDataset,
        on_delete=models.CASCADE,
        related_name="training_runs",
    )
    optimisation_target = models.CharField(
        max_length=20,
        choices=OptimisationTarget.choices,
        default=OptimisationTarget.GINI,
    )
    status = models.CharField(
        max_length=20,
        choices=TrainingRunStatus.choices,
        default=TrainingRunStatus.PENDING,
    )
    candidate_weights = models.JSONField(
        null=True,
        blank=True,
        help_text="Optimal weight dict — null until run completes.",
    )
    candidate_thresholds = models.JSONField(
        null=True,
        blank=True,
        help_text="Optimal threshold dict — null until run completes.",
    )
    val_gini = models.FloatField(null=True, blank=True)
    val_ks = models.FloatField(null=True, blank=True)
    val_f1_review = models.FloatField(null=True, blank=True)
    umap_enabled = models.BooleanField(default=False)
    artefacts_s3_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="S3 prefix for run artefacts (weights.json, thresholds.json, etc.).",
    )
    celery_task_id = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="training_runs",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["dataset", "-created_at"], name="tr_run_ds_created_idx"),
        ]

    def __str__(self):
        return f"{self.label} ({self.get_status_display()})"

    @property
    def is_terminal(self) -> bool:
        return self.status in (TrainingRunStatus.COMPLETED, TrainingRunStatus.FAILED)


class BacktestStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    RUNNING = "RUNNING", "Running"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"


class ModelBacktestResult(models.Model):
    """Held-out (20 %) evaluation of a ModelTrainingRun's candidate weights and thresholds."""

    training_run = models.OneToOneField(
        ModelTrainingRun,
        on_delete=models.CASCADE,
        related_name="backtest_result",
    )
    status = models.CharField(
        max_length=20,
        choices=BacktestStatus.choices,
        default=BacktestStatus.PENDING,
    )
    # Per-class precision
    precision_approved = models.FloatField(null=True, blank=True)
    precision_review = models.FloatField(null=True, blank=True)
    precision_declined = models.FloatField(null=True, blank=True)
    # Per-class recall
    recall_approved = models.FloatField(null=True, blank=True)
    recall_review = models.FloatField(null=True, blank=True)
    recall_declined = models.FloatField(null=True, blank=True)
    # Per-class F1
    f1_approved = models.FloatField(null=True, blank=True)
    f1_review = models.FloatField(null=True, blank=True)
    f1_declined = models.FloatField(null=True, blank=True)
    # Overall metrics
    accuracy = models.FloatField(null=True, blank=True)
    gini = models.FloatField(null=True, blank=True)
    ks_statistic = models.FloatField(null=True, blank=True)
    # 3×3 confusion matrix: {actual_label: {predicted_label: count}}
    confusion_matrix = models.JSONField(null=True, blank=True)
    artefacts_s3_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="S3 prefix for backtest artefacts (test_scores.parquet).",
    )
    celery_task_id = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-training_run__created_at"]

    def __str__(self):
        return f"Backtest for {self.training_run.label} ({self.get_status_display()})"

    @property
    def is_terminal(self) -> bool:
        return self.status in (BacktestStatus.COMPLETED, BacktestStatus.FAILED)
