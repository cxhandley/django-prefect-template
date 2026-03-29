"""
Tests for accounts views and forms.
"""

import pytest
from apps.accounts.forms import SignupForm
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
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


# ============================================================================
# signup_user
# ============================================================================


@pytest.mark.django_db
def test_signup_get(anon_client):
    response = anon_client.get("/accounts/signup/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_signup_post_success(anon_client):
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
    assert User.objects.filter(username="janedoe").exists()


@pytest.mark.django_db
def test_signup_post_invalid_form(anon_client):
    """Missing fields keeps user on signup page."""
    response = anon_client.post("/accounts/signup/", {})
    assert response.status_code == 200


@pytest.mark.django_db
def test_signup_htmx_success(anon_client):
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
    assert response.headers.get("HX-Redirect") == "/flows/dashboard/"


@pytest.mark.django_db
def test_signup_redirects_authenticated(existing_user):
    from django.test import Client

    client = Client()
    client.force_login(existing_user)
    response = client.get("/accounts/signup/")
    assert response.status_code == 302


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
