from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.views.decorators.http import require_http_methods


@login_required
@require_http_methods(["GET"])
def user_menu(request):
    """HTMX endpoint: render user dropdown menu"""
    return render(request, 'accounts/components/user_menu.html', {
        'user': request.user,
    })


@login_required
@require_http_methods(["POST"])
def logout_user(request):
    """HTMX endpoint: logout and redirect"""
    logout(request)
    return HttpResponse(status=200, headers={'HX-Redirect': '/'})


@login_required
@require_http_methods(["GET"])
def profile(request):
    """User profile page"""
    return render(request, 'accounts/profile.html', {
        'user': request.user,
    })


@login_required
@require_http_methods(["GET"])
def settings(request):
    """User settings page"""
    return render(request, 'accounts/settings.html', {
        'user': request.user,
    })