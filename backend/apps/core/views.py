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
