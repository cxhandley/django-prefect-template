from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .forms import LoginForm, SignupForm

User = get_user_model()


def login_user(request):
    """Login page - GET renders form, POST authenticates"""
    if request.user.is_authenticated:
        return redirect("flows:dashboard")

    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            password = form.cleaned_data["password"]
            # Try to find user by email, then authenticate by username
            try:
                user_obj = User.objects.get(email=email)
                user = authenticate(request, username=user_obj.username, password=password)
            except User.DoesNotExist:
                user = None

            if user is not None:
                login(request, user)
                if request.headers.get("HX-Request"):
                    return HttpResponse(status=200, headers={"HX-Redirect": "/flows/dashboard/"})
                return redirect("flows:dashboard")
            else:
                form.add_error(None, "Invalid email or password.")
    else:
        form = LoginForm()

    template = (
        "accounts/partials/login_form.html"
        if request.headers.get("HX-Request")
        else "accounts/login.html"
    )
    return render(request, template, {"form": form})


def signup_user(request):
    """Signup page - GET renders form, POST creates user"""
    if request.user.is_authenticated:
        return redirect("flows:dashboard")

    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            name_parts = form.cleaned_data["full_name"].split(" ", 1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ""

            user = User.objects.create_user(
                username=form.cleaned_data["username"],
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
                first_name=first_name,
                last_name=last_name,
            )
            login(request, user)
            if request.headers.get("HX-Request"):
                return HttpResponse(status=200, headers={"HX-Redirect": "/flows/dashboard/"})
            return redirect("flows:dashboard")
    else:
        form = SignupForm()

    template = (
        "accounts/partials/signup_form.html"
        if request.headers.get("HX-Request")
        else "accounts/signup.html"
    )
    return render(request, template, {"form": form})


@login_required
@require_http_methods(["GET"])
def user_menu(request):
    """HTMX endpoint: render user dropdown menu"""
    return render(
        request,
        "accounts/components/user_menu.html",
        {
            "user": request.user,
        },
    )


@login_required
@require_http_methods(["POST"])
def logout_user(request):
    """HTMX endpoint: logout and redirect"""
    logout(request)
    return HttpResponse(status=200, headers={"HX-Redirect": "/"})


@login_required
@require_http_methods(["GET"])
def profile(request):
    """User profile page"""
    return render(
        request,
        "accounts/profile.html",
        {
            "user": request.user,
        },
    )


@login_required
@require_http_methods(["GET"])
def settings(request):
    """User settings page"""
    return render(
        request,
        "accounts/settings.html",
        {
            "user": request.user,
        },
    )
