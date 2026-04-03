"""
Tests for accounts app — UserProfile (BL-011) and settings view.
"""

import pytest
from apps.accounts.models import UserProfile
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

User = get_user_model()


# ============================================================================
# UserProfile model
# ============================================================================


@pytest.mark.django_db
def test_userprofile_created_on_user_save():
    """Signal auto-creates UserProfile when a new User is saved."""
    user = User.objects.create_user(
        username="testprofile",
        email="testprofile@example.com",
        password="pass",
    )
    assert UserProfile.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_userprofile_defaults_notify_on_failure_true():
    user = User.objects.create_user(
        username="testdefault",
        email="testdefault@example.com",
        password="pass",
    )
    assert user.profile.notify_on_failure is True


@pytest.mark.django_db
def test_userprofile_str():
    user = User.objects.create_user(
        username="strtest",
        email="strtest@example.com",
        password="pass",
    )
    assert "strtest@example.com" in str(user.profile)


# ============================================================================
# Settings view — notify_on_failure toggle (BL-011)
# ============================================================================


@pytest.mark.django_db
def test_settings_view_renders_profile_toggle():
    user = User.objects.create_user(
        username="settingsuser",
        email="settingsuser@example.com",
        password="pass",
        is_active=True,
    )
    client = Client()
    client.force_login(user)
    response = client.get(reverse("accounts:settings"))
    assert response.status_code == 200
    assert b"notify_on_failure" in response.content


@pytest.mark.django_db
def test_settings_view_post_enables_notification():
    user = User.objects.create_user(
        username="notifyon",
        email="notifyon@example.com",
        password="pass",
        is_active=True,
    )
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.notify_on_failure = False
    profile.save()

    client = Client()
    client.force_login(user)
    client.post(reverse("accounts:settings"), {"notify_on_failure": "on"})

    profile.refresh_from_db()
    assert profile.notify_on_failure is True


@pytest.mark.django_db
def test_settings_view_post_disables_notification():
    user = User.objects.create_user(
        username="notifyoff",
        email="notifyoff@example.com",
        password="pass",
        is_active=True,
    )
    UserProfile.objects.update_or_create(user=user, defaults={"notify_on_failure": True})

    client = Client()
    client.force_login(user)
    # Unchecked checkbox sends no value
    client.post(reverse("accounts:settings"), {})

    user.profile.refresh_from_db()
    assert user.profile.notify_on_failure is False
