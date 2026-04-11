from django.contrib import admin

from .models import TrainingDataset


@admin.register(TrainingDataset)
class TrainingDatasetAdmin(admin.ModelAdmin):
    list_display = ("slug", "status", "row_count", "seed", "created_by", "created_at")
    list_filter = ("status",)
    readonly_fields = ("slug", "created_at", "celery_task_id", "s3_path", "error_message")
    ordering = ("-created_at",)
    search_fields = ("slug", "description")
