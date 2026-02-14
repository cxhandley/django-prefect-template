from django.shortcuts import render
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods


@login_required
def base_layout(request):
    """Base layout with navbar - extended by other templates"""
    context = {
        'user': request.user,
    }
    return render(request, 'core/base.html', context)


@login_required
@require_http_methods(["GET"])
def navbar(request):
    """Render the navbar component"""
    return render(request, 'core/components/navbar.html', {
        'user': request.user,
    })