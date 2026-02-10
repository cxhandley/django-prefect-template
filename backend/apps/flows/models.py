"""
Flow execution models.
"""
from django.db import models
from django.conf import settings
import boto3


class FlowExecution(models.Model):
    """
    Stores metadata about flow executions.
    Actual data is stored in S3.
    """
    flow_run_id = models.UUIDField(unique=True)
    flow_name = models.CharField(max_length=200)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )
    
    # S3 paths - NOT the actual data
    s3_input_path = models.CharField(max_length=500, blank=True)
    s3_output_path = models.CharField(max_length=500, blank=True)
    
    # Metadata for quick filtering
    row_count = models.BigIntegerField(null=True, blank=True)
    file_size_mb = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    status = models.CharField(max_length=50, default='PENDING')
    parameters = models.JSONField(default=dict)
    
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['triggered_by', '-created_at']),
            models.Index(fields=['flow_name', 'status']),
        ]
        ordering = ['-created_at']
    
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
    
    def generate_download_url(self, expires_in=3600):
        """Generate presigned S3 URL for direct download."""
        if not self.s3_output_path:
            return None
        
        s3_client = boto3.client(
            's3',
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        
        return s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': settings.DATA_LAKE_BUCKET,
                'Key': self.s3_output_path
            },
            ExpiresIn=expires_in
        )