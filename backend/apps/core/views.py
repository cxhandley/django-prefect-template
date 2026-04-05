import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods


def index(request):
    """Home page - publicly accessible"""
    if request.user.is_authenticated:
        # Redirect authenticated users to flows dashboard
        return render(request, "core/index.html", {"user": request.user})
    else:
        # Show home page for anonymous users
        return render(request, "core/index.html")


@login_required
def base_layout(request):
    """Base layout with navbar - extended by other templates"""
    context = {
        "user": request.user,
    }
    return render(request, "core/base.html", context)


@login_required
@require_http_methods(["POST"])
def poll(request):
    """
    Centralized front-end polling endpoint.

    Accepts a JSON body::

        {
            "page_path": "/flows/history/",
            "watchers": [
                {
                    "id":     "dt-history",
                    "type":   "table_refresh",
                    "target": "#dt-history-body",
                    "params": {"table_url": "/flows/history/?...", "scope": "user"}
                },
                ...
            ]
        }

    Returns::

        {
            "directives": [
                {
                    "watcher_id": "dt-history",
                    "url":        "/flows/history/?...",   // null → no fetch needed
                    "target":     "#dt-history-body",
                    "done":       false
                }
            ],
            "next_interval_ms": 2000
        }

    The frontend fetches each non-null ``url`` with an ``HX-Request`` header
    and swaps the response into ``target``.  When ``done`` is true the
    frontend stops watching that watcher after the final swap.
    """
    from apps.core.poll_handlers import dispatch

    try:
        body = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"directives": [], "next_interval_ms": 2000})

    watchers = body.get("watchers", [])
    directives = []

    for watcher in watchers:
        watcher_id = watcher.get("id", "")
        watcher_type = watcher.get("type", "")
        target = watcher.get("target", "")
        params = watcher.get("params", {})

        if not (watcher_id and watcher_type):
            continue

        directive = dispatch(watcher_type, request, watcher_id, params, target)
        if directive:
            directives.append(directive)

    return JsonResponse({"directives": directives, "next_interval_ms": 2000})


@require_http_methods(["GET"])
def health(request):
    """Load balancer health check — no authentication required."""
    return JsonResponse({"status": "ok"})


@login_required
@require_http_methods(["GET"])
def navbar(request):
    """Render the navbar component"""
    return render(
        request,
        "core/components/navbar.html",
        {
            "user": request.user,
        },
    )
