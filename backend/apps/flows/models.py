"""
Flow execution models.
"""

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from django.conf import settings
from django.db import models


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

    status = models.CharField(max_length=50, default="PENDING")
    parameters = models.JSONField(default=dict)

    # Async execution tracking
    celery_task_id = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)

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
