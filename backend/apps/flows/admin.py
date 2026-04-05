from django.contrib import admin

from .models import ExecutionStep, FlowExecution, PredictionResult, ScoringModel


@admin.register(ScoringModel)
class ScoringModelAdmin(admin.ModelAdmin):
    list_display = ("version", "is_active", "created_at", "created_by")
    list_filter = ("is_active",)
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)

    def save_model(self, request, obj, form, change):
        if not obj.pk and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(PredictionResult)
class PredictionResultAdmin(admin.ModelAdmin):
    list_display = (
        "execution",
        "classification",
        "score",
        "confidence",
        "scoring_model",
        "scored_at",
    )
    list_filter = ("classification", "scoring_model")
    readonly_fields = ("scored_at",)
    ordering = ("-scored_at",)


@admin.register(ExecutionStep)
class ExecutionStepAdmin(admin.ModelAdmin):
    list_display = ("execution", "step_index", "step_name", "status", "started_at", "completed_at")
    list_filter = ("status",)
    ordering = ("execution", "step_index")


@admin.register(FlowExecution)
class FlowExecutionAdmin(admin.ModelAdmin):
    list_display = (
        "flow_run_id",
        "flow_name",
        "triggered_by",
        "status",
        "created_at",
        "completed_at",
    )
    list_filter = ("status", "flow_name")
    readonly_fields = ("flow_run_id", "created_at", "completed_at", "celery_task_id")
    ordering = ("-created_at",)
