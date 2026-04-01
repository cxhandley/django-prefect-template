"""
Tests for accounts views and forms.
"""

import pytest
from apps.accounts.forms import SignupForm
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.signing import TimestampSigner
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

User = get_user_model()


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def existing_user(db):
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="validpassword123",
        first_name="Test",
        last_name="User",
    )


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="adminPass123!",
    )


@pytest.fixture
def anon_client():
    from django.test import Client

    return Client()


# ============================================================================
# login_user
# ============================================================================


@pytest.mark.django_db
def test_login_get(anon_client):
    response = anon_client.get("/accounts/login/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_login_post_success(anon_client, existing_user):
    response = anon_client.post(
        "/accounts/login/",
        {"email": "test@example.com", "password": "validpassword123"},
    )
    assert response.status_code == 302


@pytest.mark.django_db
def test_login_post_wrong_password(anon_client, existing_user):
    response = anon_client.post(
        "/accounts/login/",
        {"email": "test@example.com", "password": "wrongpassword"},
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_login_post_unknown_email(anon_client):
    response = anon_client.post(
        "/accounts/login/",
        {"email": "nobody@example.com", "password": "whatever"},
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_login_htmx_success(anon_client, existing_user):
    response = anon_client.post(
        "/accounts/login/",
        {"email": "test@example.com", "password": "validpassword123"},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert response.headers.get("HX-Redirect") == "/flows/dashboard/"


@pytest.mark.django_db
def test_login_htmx_invalid_form(anon_client):
    response = anon_client.post(
        "/accounts/login/",
        {},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_login_redirects_authenticated(existing_user):
    from django.test import Client

    client = Client()
    client.force_login(existing_user)
    response = client.get("/accounts/login/")
    assert response.status_code == 302


@pytest.mark.django_db
def test_login_unconfirmed_user_sees_helpful_error(anon_client, db):
    """User with correct credentials but is_active=False sees a clear message."""
    unconfirmed = User.objects.create_user(
        username="unconfirmed",
        email="unconfirmed@example.com",
        password="validPass123!",
        is_active=False,
    )
    response = anon_client.post(
        "/accounts/login/",
        {"email": unconfirmed.email, "password": "validPass123!"},
    )
    assert response.status_code == 200
    assert b"confirm your email" in response.content


@pytest.mark.django_db
def test_login_confirmed_banner_shown(anon_client):
    """?confirmed=1 query param triggers the success banner on the login page."""
    response = anon_client.get("/accounts/login/?confirmed=1")
    assert response.status_code == 200
    assert b"Email confirmed" in response.content


# ============================================================================
# signup_user
# ============================================================================


@pytest.mark.django_db
def test_signup_get(anon_client):
    response = anon_client.get("/accounts/signup/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_signup_post_success_redirects_to_confirmation_sent(anon_client):
    """Successful signup redirects to email-confirmation-sent, not dashboard."""
    response = anon_client.post(
        "/accounts/signup/",
        {
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "username": "janedoe",
            "password": "securePass123!",
            "confirm_password": "securePass123!",
            "terms_accepted": "on",
        },
    )
    assert response.status_code == 302
    assert "/accounts/email-confirmation-sent/" in response["Location"]


@pytest.mark.django_db
def test_signup_creates_inactive_user(anon_client):
    """New user is created with is_active=False pending email confirmation."""
    anon_client.post(
        "/accounts/signup/",
        {
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "username": "janedoe",
            "password": "securePass123!",
            "confirm_password": "securePass123!",
            "terms_accepted": "on",
        },
    )
    user = User.objects.get(username="janedoe")
    assert user.is_active is False


@pytest.mark.django_db
def test_signup_sends_confirmation_email(anon_client):
    """Signing up sends one confirmation email containing the confirm link."""
    anon_client.post(
        "/accounts/signup/",
        {
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "username": "janedoe",
            "password": "securePass123!",
            "confirm_password": "securePass123!",
            "terms_accepted": "on",
        },
    )
    assert len(mail.outbox) == 1
    assert "jane@example.com" in mail.outbox[0].to
    assert "/accounts/confirm-email/" in mail.outbox[0].body


@pytest.mark.django_db
def test_signup_post_invalid_form(anon_client):
    """Missing fields keeps user on signup page."""
    response = anon_client.post("/accounts/signup/", {})
    assert response.status_code == 200


@pytest.mark.django_db
def test_signup_htmx_success(anon_client):
    """HTMX signup returns HX-Redirect to email-confirmation-sent."""
    response = anon_client.post(
        "/accounts/signup/",
        {
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "username": "janedoe",
            "password": "securePass123!",
            "confirm_password": "securePass123!",
            "terms_accepted": "on",
        },
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert response.headers.get("HX-Redirect") == "/accounts/email-confirmation-sent/"


@pytest.mark.django_db
def test_signup_redirects_authenticated(existing_user):
    from django.test import Client

    client = Client()
    client.force_login(existing_user)
    response = client.get("/accounts/signup/")
    assert response.status_code == 302


# ============================================================================
# Email confirmation flow (BL-007)
# ============================================================================


@pytest.mark.django_db
def test_email_confirmation_sent_page(anon_client):
    response = anon_client.get("/accounts/email-confirmation-sent/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_confirm_email_valid_token_activates_user(anon_client, db):
    user = User.objects.create_user(
        username="inactive",
        email="inactive@example.com",
        password="pass123!",
        is_active=False,
    )
    token = TimestampSigner().sign(user.pk)
    response = anon_client.get(f"/accounts/confirm-email/{token}/")
    assert response.status_code == 302
    assert "confirmed=1" in response["Location"]
    user.refresh_from_db()
    assert user.is_active is True


@pytest.mark.django_db
def test_confirm_email_invalid_token_shows_error(anon_client):
    response = anon_client.get("/accounts/confirm-email/totally-invalid-token/")
    assert response.status_code == 200
    assert b"invalid" in response.content.lower()


@pytest.mark.django_db
def test_confirm_email_expired_token_shows_error(anon_client, db):
    import time
    from unittest.mock import patch

    user = User.objects.create_user(
        username="inactive2",
        email="inactive2@example.com",
        password="pass123!",
        is_active=False,
    )
    # Sign with a far-past timestamp so it appears expired
    with patch("time.time", return_value=time.time() - 90000):
        token = TimestampSigner().sign(user.pk)

    response = anon_client.get(f"/accounts/confirm-email/{token}/")
    assert response.status_code == 200
    assert b"expired" in response.content.lower()
    user.refresh_from_db()
    assert user.is_active is False


# ============================================================================
# user_menu / logout / profile / settings
# ============================================================================


@pytest.mark.django_db
def test_user_menu(existing_user):
    from django.test import Client

    client = Client()
    client.force_login(existing_user)
    response = client.get("/accounts/api/user-menu/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_logout(existing_user):
    from django.test import Client

    client = Client()
    client.force_login(existing_user)
    response = client.post("/accounts/api/logout/")
    assert response.status_code == 200
    assert response.headers.get("HX-Redirect") == "/"


@pytest.mark.django_db
def test_profile(existing_user):
    from django.test import Client

    client = Client()
    client.force_login(existing_user)
    response = client.get("/accounts/profile/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_settings_page(existing_user):
    from django.test import Client

    client = Client()
    client.force_login(existing_user)
    response = client.get("/accounts/settings/")
    assert response.status_code == 200


# ============================================================================
# Superuser user management (BL-006)
# ============================================================================


@pytest.mark.django_db
def test_user_list_requires_superuser(anon_client, existing_user):
    """Regular users cannot access /accounts/users/."""
    from django.test import Client

    client = Client()
    client.force_login(existing_user)
    response = client.get("/accounts/users/")
    assert response.status_code == 302  # redirected to login


@pytest.mark.django_db
def test_user_list_forbidden_for_anonymous(anon_client):
    response = anon_client.get("/accounts/users/")
    assert response.status_code == 302


@pytest.mark.django_db
def test_user_list_visible_to_superuser(superuser, existing_user):
    from django.test import Client

    client = Client()
    client.force_login(superuser)
    response = client.get("/accounts/users/")
    assert response.status_code == 200
    assert b"test@example.com" in response.content


@pytest.mark.django_db
def test_user_list_filter_active(superuser, existing_user, db):
    from django.test import Client

    User.objects.create_user(
        username="inactive3", email="inactive3@example.com", password="x", is_active=False
    )
    client = Client()
    client.force_login(superuser)

    response = client.get("/accounts/users/?active=false", HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert b"inactive3@example.com" in response.content
    assert b"test@example.com" not in response.content


@pytest.mark.django_db
def test_user_list_search(superuser, existing_user):
    from django.test import Client

    client = Client()
    client.force_login(superuser)
    response = client.get("/accounts/users/?q=testuser", HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert b"test@example.com" in response.content


@pytest.mark.django_db
def test_toggle_active_deactivates_user(superuser, existing_user):
    from django.test import Client

    client = Client()
    client.force_login(superuser)
    response = client.post(f"/accounts/users/{existing_user.pk}/toggle-active/")
    assert response.status_code == 200
    existing_user.refresh_from_db()
    assert existing_user.is_active is False


@pytest.mark.django_db
def test_toggle_active_activates_inactive_user(superuser, db):
    from django.test import Client

    inactive = User.objects.create_user(
        username="toreactivate", email="reactivate@example.com", password="x", is_active=False
    )
    client = Client()
    client.force_login(superuser)
    client.post(f"/accounts/users/{inactive.pk}/toggle-active/")
    inactive.refresh_from_db()
    assert inactive.is_active is True


@pytest.mark.django_db
def test_superuser_cannot_deactivate_self(superuser):
    from django.test import Client

    client = Client()
    client.force_login(superuser)
    response = client.post(f"/accounts/users/{superuser.pk}/toggle-active/")
    assert response.status_code == 403
    superuser.refresh_from_db()
    assert superuser.is_active is True


@pytest.mark.django_db
def test_user_send_reset_sends_email(superuser, existing_user):
    from django.test import Client

    client = Client()
    client.force_login(superuser)
    response = client.post(f"/accounts/users/{existing_user.pk}/reset-password/")
    assert response.status_code == 200
    assert len(mail.outbox) == 1
    assert "test@example.com" in mail.outbox[0].to


@pytest.mark.django_db
def test_user_send_reset_requires_superuser(existing_user, db):
    from django.test import Client

    normal = User.objects.create_user(
        username="normal2", email="normal2@example.com", password="pass123!"
    )
    client = Client()
    client.force_login(normal)
    response = client.post(f"/accounts/users/{existing_user.pk}/reset-password/")
    assert response.status_code == 302  # redirected to login


# ============================================================================
# SignupForm validation
# ============================================================================


@pytest.mark.django_db
def test_signup_form_duplicate_email(existing_user):
    form = SignupForm(
        data={
            "full_name": "Another User",
            "email": "test@example.com",  # already exists
            "username": "anotheruser",
            "password": "securePass123!",
            "confirm_password": "securePass123!",
            "terms_accepted": True,
        }
    )
    assert not form.is_valid()
    assert "email" in form.errors


@pytest.mark.django_db
def test_signup_form_duplicate_username(existing_user):
    form = SignupForm(
        data={
            "full_name": "Another User",
            "email": "new@example.com",
            "username": "testuser",  # already exists
            "password": "securePass123!",
            "confirm_password": "securePass123!",
            "terms_accepted": True,
        }
    )
    assert not form.is_valid()
    assert "username" in form.errors


@pytest.mark.django_db
def test_signup_form_password_mismatch():
    form = SignupForm(
        data={
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "username": "janedoe",
            "password": "securePass123!",
            "confirm_password": "differentPass456!",
            "terms_accepted": True,
        }
    )
    assert not form.is_valid()
    assert "confirm_password" in form.errors


# ============================================================================
# Password reset flow
# ============================================================================


@pytest.mark.django_db
def test_password_reset_get(anon_client):
    response = anon_client.get("/accounts/password-reset/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_password_reset_post_known_email_sends_email(anon_client, existing_user):
    response = anon_client.post(
        "/accounts/password-reset/",
        {"email": "test@example.com"},
    )
    assert response.status_code == 302
    assert response["Location"] == "/accounts/password-reset/done/"
    assert len(mail.outbox) == 1
    assert "test@example.com" in mail.outbox[0].to


@pytest.mark.django_db
def test_password_reset_post_unknown_email_no_email_sent(anon_client):
    # Should redirect identically to avoid user enumeration
    response = anon_client.post(
        "/accounts/password-reset/",
        {"email": "nobody@example.com"},
    )
    assert response.status_code == 302
    assert response["Location"] == "/accounts/password-reset/done/"
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_password_reset_done_get(anon_client):
    response = anon_client.get("/accounts/password-reset/done/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_password_reset_confirm_invalid_token(anon_client):
    response = anon_client.get("/accounts/password-reset/confirm/bad-uid/bad-token/")
    assert response.status_code == 200
    assert b"Link Expired" in response.content


@pytest.mark.django_db
def test_password_reset_confirm_valid_token_and_set_password(anon_client, existing_user):
    uid = urlsafe_base64_encode(force_bytes(existing_user.pk))
    token = default_token_generator.make_token(existing_user)

    # GET — Django redirects to a session-based URL on valid tokens
    get_response = anon_client.get(
        f"/accounts/password-reset/confirm/{uid}/{token}/",
        follow=True,
    )
    assert get_response.status_code == 200

    # POST the new password to the redirected URL
    post_url = (
        get_response.redirect_chain[-1][0]
        if get_response.redirect_chain
        else f"/accounts/password-reset/confirm/{uid}/set-password/"
    )
    post_response = anon_client.post(
        post_url,
        {"new_password1": "NewSecurePass99!", "new_password2": "NewSecurePass99!"},
        follow=True,
    )
    assert post_response.status_code == 200

    existing_user.refresh_from_db()
    assert existing_user.check_password("NewSecurePass99!")


@pytest.mark.django_db
def test_password_reset_complete_get(anon_client):
    response = anon_client.get("/accounts/password-reset/complete/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_password_reset_email_contains_reset_link(anon_client, existing_user):
    anon_client.post("/accounts/password-reset/", {"email": "test@example.com"})
    body = mail.outbox[0].body
    assert "/accounts/password-reset/confirm/" in body


@pytest.mark.django_db
def test_password_reset_email_subject(anon_client, existing_user):
    anon_client.post("/accounts/password-reset/", {"email": "test@example.com"})
    assert mail.outbox[0].subject == "Reset your password"


@pytest.mark.django_db
def test_password_reset_confirm_password_mismatch(anon_client, existing_user):
    uid = urlsafe_base64_encode(force_bytes(existing_user.pk))
    token = default_token_generator.make_token(existing_user)

    get_response = anon_client.get(
        f"/accounts/password-reset/confirm/{uid}/{token}/",
        follow=True,
    )
    post_url = (
        get_response.redirect_chain[-1][0]
        if get_response.redirect_chain
        else f"/accounts/password-reset/confirm/{uid}/set-password/"
    )
    post_response = anon_client.post(
        post_url,
        {"new_password1": "NewSecurePass99!", "new_password2": "DifferentPass99!"},
    )
    assert post_response.status_code == 200
    existing_user.refresh_from_db()
    assert not existing_user.check_password("NewSecurePass99!")


@pytest.mark.django_db
def test_password_reset_confirm_weak_password_rejected(anon_client, existing_user):
    uid = urlsafe_base64_encode(force_bytes(existing_user.pk))
    token = default_token_generator.make_token(existing_user)

    get_response = anon_client.get(
        f"/accounts/password-reset/confirm/{uid}/{token}/",
        follow=True,
    )
    post_url = (
        get_response.redirect_chain[-1][0]
        if get_response.redirect_chain
        else f"/accounts/password-reset/confirm/{uid}/set-password/"
    )
    post_response = anon_client.post(
        post_url,
        {"new_password1": "password", "new_password2": "password"},
    )
    assert post_response.status_code == 200
    existing_user.refresh_from_db()
    assert not existing_user.check_password("password")


@pytest.mark.django_db
def test_password_reset_link_unusable_after_use(anon_client, existing_user):
    """Token can only be used once — second use shows Link Expired."""
    uid = urlsafe_base64_encode(force_bytes(existing_user.pk))
    token = default_token_generator.make_token(existing_user)
    confirm_url = f"/accounts/password-reset/confirm/{uid}/{token}/"

    # First use — follow redirect to session-based URL and set password
    get_response = anon_client.get(confirm_url, follow=True)
    post_url = (
        get_response.redirect_chain[-1][0]
        if get_response.redirect_chain
        else f"/accounts/password-reset/confirm/{uid}/set-password/"
    )
    anon_client.post(
        post_url,
        {"new_password1": "NewSecurePass99!", "new_password2": "NewSecurePass99!"},
    )

    # Second attempt with the original token URL — token is now consumed
    second_response = anon_client.get(confirm_url, follow=True)
    assert b"Link Expired" in second_response.content
