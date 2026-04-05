"""
Poll handlers for the flows app.

Registered via FlowsConfig.ready() so the core poll registry stays
decoupled from domain models.

Watcher types
-------------
execution_status
    Watches a single FlowExecution and returns a directive to fetch
    the appropriate status partial (running / result / error).
    params: {"run_id": "<uuid string>"}

table_refresh
    Watches whether any RUNNING/PENDING executions exist for the
    current user (scope="user") or across all users (scope="all",
    staff only).  When active, returns a directive to refetch the
    table body URL.
    params: {"table_url": "<url>", "scope": "user"|"all"}
"""

from apps.core.poll_handlers import register
from django.urls import reverse

from .models import ExecutionStatus, FlowExecution


@register("execution_status")
def handle_execution_status(request, watcher_id, params, target):
    """Return a directive pointing at the prediction_status endpoint."""
    run_id = params.get("run_id", "")
    if not run_id:
        return {"watcher_id": watcher_id, "url": None, "target": target, "done": True}

    try:
        execution = FlowExecution.objects.get(flow_run_id=run_id, triggered_by=request.user)
    except FlowExecution.DoesNotExist:
        return {"watcher_id": watcher_id, "url": None, "target": target, "done": True}

    status_url = reverse("flows:prediction_status", kwargs={"run_id": run_id})

    still_active = execution.status in (ExecutionStatus.PENDING, ExecutionStatus.RUNNING)
    return {
        "watcher_id": watcher_id,
        "url": status_url,
        "target": target,
        "done": not still_active,
    }


@register("table_refresh")
def handle_table_refresh(request, watcher_id, params, target):
    """
    Return a directive to refetch the table body URL when there are
    RUNNING/PENDING executions relevant to the current context.
    """
    table_url = params.get("table_url", "")
    scope = params.get("scope", "user")

    if scope == "all" and not request.user.is_staff:
        # Non-staff cannot watch all-user tables
        return {"watcher_id": watcher_id, "url": None, "target": target, "done": True}

    qs = FlowExecution.objects.filter(status__in=[ExecutionStatus.PENDING, ExecutionStatus.RUNNING])
    if scope == "user":
        qs = qs.filter(triggered_by=request.user)

    still_active = qs.exists()

    return {
        "watcher_id": watcher_id,
        "url": table_url if still_active else None,
        "target": target,
        "done": not still_active,
    }
