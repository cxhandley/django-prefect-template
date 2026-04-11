from django.contrib import admin

from .models import ModelTrainingRun, TrainingDataset


@admin.register(TrainingDataset)
class TrainingDatasetAdmin(admin.ModelAdmin):
    list_display = ("slug", "status", "row_count", "seed", "created_by", "created_at")
    list_filter = ("status",)
    readonly_fields = ("slug", "created_at", "celery_task_id", "s3_path", "error_message")
    ordering = ("-created_at",)
    search_fields = ("slug", "description")


@admin.register(ModelTrainingRun)
class ModelTrainingRunAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "dataset",
        "optimisation_target",
        "status",
        "val_gini",
        "val_ks",
        "val_f1_review",
        "umap_enabled",
        "created_by",
        "created_at",
    )
    list_filter = ("status", "optimisation_target", "umap_enabled")
    readonly_fields = (
        "created_at",
        "celery_task_id",
        "artefacts_s3_path",
        "candidate_weights",
        "candidate_thresholds",
        "val_gini",
        "val_ks",
        "val_f1_review",
        "error_message",
    )
    ordering = ("-created_at",)
    search_fields = ("label",)
    raw_id_fields = ("dataset", "created_by")
