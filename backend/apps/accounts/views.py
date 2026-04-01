from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.tokens import default_token_generator
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms import LoginForm, SignupForm
from .services import send_confirmation_email

User = get_user_model()

# ── helpers ──────────────────────────────────────────────────────────────────

_superuser_required = user_passes_test(
    lambda u: u.is_active and u.is_superuser,
    login_url="/accounts/login/",
)


# ── public views ──────────────────────────────────────────────────────────────


def login_user(request):
    """Login page - GET renders form, POST authenticates"""
    if request.user.is_authenticated:
        return redirect("flows:dashboard")

    confirmed = request.GET.get("confirmed") == "1"

    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            password = form.cleaned_data["password"]
            user_obj = User.objects.filter(email=email, is_active=True).first()
            if user_obj is None:
                user_obj = User.objects.filter(email=email).first()
            user = (
                authenticate(request, username=user_obj.username, password=password)
                if user_obj
                else None
            )

            if user is not None:
                login(request, user)
                if request.headers.get("HX-Request"):
                    return HttpResponse(status=200, headers={"HX-Redirect": "/flows/dashboard/"})
                return redirect("flows:dashboard")
            else:
                # Distinguish unconfirmed accounts from wrong credentials
                unconfirmed = User.objects.filter(email=email, is_active=False).first()
                if unconfirmed and unconfirmed.check_password(password):
                    form.add_error(
                        None,
                        "Please confirm your email address before logging in.",
                    )
                else:
                    form.add_error(None, "Invalid email or password.")
    else:
        form = LoginForm()

    context = {"form": form, "confirmed": confirmed}
    template = (
        "accounts/partials/login_form.html"
        if request.headers.get("HX-Request")
        else "accounts/login.html"
    )
    return render(request, template, context)


def signup_user(request):
    """Signup page - GET renders form, POST creates inactive user and sends confirmation email"""
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
                is_active=False,  # requires email confirmation
            )
            send_confirmation_email(request, user)

            if request.headers.get("HX-Request"):
                return HttpResponse(
                    status=200,
                    headers={"HX-Redirect": "/accounts/email-confirmation-sent/"},
                )
            return redirect("accounts:email_confirmation_sent")
    else:
        form = SignupForm()

    template = (
        "accounts/partials/signup_form.html"
        if request.headers.get("HX-Request")
        else "accounts/signup.html"
    )
    return render(request, template, {"form": form})


def email_confirmation_sent(request):
    """Informational page shown after signup — tells user to check their inbox."""
    return render(request, "accounts/email_confirmation_sent.html")


def confirm_email(request, token):
    """Activate a user account via a signed token from the confirmation email."""
    signer = TimestampSigner()
    try:
        user_pk = signer.unsign(token, max_age=86400)  # 24 hours
        user = get_object_or_404(User, pk=user_pk)
        user.is_active = True
        user.save(update_fields=["is_active"])
        return redirect("/accounts/login/?confirmed=1")
    except SignatureExpired:
        return render(request, "accounts/confirm_email_invalid.html", {"reason": "expired"})
    except (BadSignature, Exception):
        return render(request, "accounts/confirm_email_invalid.html", {"reason": "invalid"})


# ── authenticated views ───────────────────────────────────────────────────────


@login_required
@require_http_methods(["GET"])
def user_menu(request):
    """HTMX endpoint: render user dropdown menu"""
    return render(
        request,
        "accounts/components/user_menu.html",
        {"user": request.user},
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
    return render(request, "accounts/profile.html", {"user": request.user})


@login_required
@require_http_methods(["GET"])
def settings(request):
    """User settings page"""
    return render(request, "accounts/settings.html", {"user": request.user})


# ── superuser views ───────────────────────────────────────────────────────────


@_superuser_required
@require_http_methods(["GET"])
def user_list(request):
    """Superuser: list all users with optional filter and search."""
    qs = User.objects.all().order_by("date_joined")

    active_filter = request.GET.get("active", "")
    if active_filter == "true":
        qs = qs.filter(is_active=True)
    elif active_filter == "false":
        qs = qs.filter(is_active=False)

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(email__icontains=q) | qs.filter(username__icontains=q)

    context = {
        "users": qs,
        "active_filter": active_filter,
        "q": q,
        "active_page": "user_management",
    }
    if request.headers.get("HX-Request"):
        return render(request, "accounts/partials/user_table.html", context)
    return render(request, "accounts/user_list.html", context)


@_superuser_required
@require_http_methods(["POST"])
def user_toggle_active(request, user_id):
    """Superuser: toggle is_active for a user. Returns HTMX row partial."""
    target_user = get_object_or_404(User, pk=user_id)

    # Superusers cannot deactivate themselves
    if target_user == request.user:
        return HttpResponse(status=403)

    target_user.is_active = not target_user.is_active
    target_user.save(update_fields=["is_active"])

    return render(
        request,
        "accounts/partials/user_row.html",
        {"u": target_user, "current_user": request.user},
    )


@_superuser_required
@require_http_methods(["POST"])
def user_send_reset(request, user_id):
    """Superuser: send password reset email for a specific user."""
    target_user = get_object_or_404(User, pk=user_id)

    form = PasswordResetForm({"email": target_user.email})
    if form.is_valid():
        form.save(
            request=request,
            use_https=request.is_secure(),
            token_generator=default_token_generator,
            email_template_name="accounts/email/password_reset.txt",
            subject_template_name="accounts/email/password_reset_subject.txt",
        )

    return render(
        request,
        "accounts/partials/user_row.html",
        {"u": target_user, "current_user": request.user, "reset_sent": True},
    )
