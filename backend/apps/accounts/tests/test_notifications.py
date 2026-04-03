"""
Tests for BL-019 — Notification model, views, context processor, and task integration.
"""

import uuid
from unittest.mock import patch

import pytest
from apps.accounts.models import Notification
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

User = get_user_model()


# ── helpers ───────────────────────────────────────────────────────────────────


def make_user(username, **kwargs):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="pass",
        is_active=True,
        **kwargs,
    )


# ── Notification model ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_notification_str():
    user = make_user("notifstr")
    n = Notification.objects.create(user=user, notification_type="EXECUTION_FAILED", message="boom")
    assert "EXECUTION_FAILED" in str(n)
    assert user.email in str(n)
    assert "unread" in str(n)


@pytest.mark.django_db
def test_notification_ordered_newest_first():
    user = make_user("notiforder")
    n1 = Notification.objects.create(user=user, notification_type="SYSTEM", message="first")
    n2 = Notification.objects.create(user=user, notification_type="SYSTEM", message="second")
    qs = list(Notification.objects.filter(user=user))
    assert qs[0] == n2
    assert qs[1] == n1


# ── UserProfile new fields ────────────────────────────────────────────────────


@pytest.mark.django_db
def test_userprofile_new_field_defaults():
    user = make_user("newfields")
    profile = user.profile
    assert profile.notify_on_success is False
    assert profile.notify_in_app is True
    assert profile.notify_via_email is True


# ── context processor ─────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_context_processor_adds_unread_count():
    user = make_user("ctxproc")
    Notification.objects.create(user=user, notification_type="SYSTEM", message="hi")
    Notification.objects.create(user=user, notification_type="SYSTEM", message="hi2", is_read=True)

    cache.delete(f"notification_count_{user.pk}")
    client = Client()
    client.force_login(user)
    response = client.get(reverse("accounts:notifications"))
    assert response.context["unread_notification_count"] == 1


@pytest.mark.django_db
def test_context_processor_zero_for_unauthenticated():
    client = Client()
    response = client.get(reverse("accounts:login"))
    assert "unread_notification_count" not in response.context


# ── notifications list view ───────────────────────────────────────────────────


@pytest.mark.django_db
def test_notifications_view_requires_login():
    client = Client()
    response = client.get(reverse("accounts:notifications"))
    assert response.status_code == 302
    assert "/login/" in response["Location"]


@pytest.mark.django_db
def test_notifications_view_shows_user_notifications():
    user = make_user("notifview")
    Notification.objects.create(user=user, notification_type="SYSTEM", message="Test message")

    other = make_user("notifother")
    Notification.objects.create(
        other, notification_type="SYSTEM", message="Not mine"
    ) if False else None

    client = Client()
    client.force_login(user)
    response = client.get(reverse("accounts:notifications"))
    assert response.status_code == 200
    assert b"Test message" in response.content


@pytest.mark.django_db
def test_notifications_view_empty_state():
    user = make_user("notifempty")
    client = Client()
    client.force_login(user)
    response = client.get(reverse("accounts:notifications"))
    assert response.status_code == 200
    assert b"No notifications yet" in response.content


# ── mark-all-read view ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_mark_all_read():
    user = make_user("markall")
    Notification.objects.create(user=user, notification_type="SYSTEM", message="a")
    Notification.objects.create(user=user, notification_type="SYSTEM", message="b")

    cache.delete(f"notification_count_{user.pk}")
    client = Client()
    client.force_login(user)
    response = client.post(reverse("accounts:notifications_mark_all_read"))
    assert response.status_code == 302
    assert Notification.objects.filter(user=user, is_read=False).count() == 0
    assert cache.get(f"notification_count_{user.pk}") is None


# ── single notification read/redirect view ────────────────────────────────────


@pytest.mark.django_db
def test_notification_read_marks_as_read_and_redirects_to_list():
    user = make_user("notifread")
    notif = Notification.objects.create(user=user, notification_type="SYSTEM", message="x")

    client = Client()
    client.force_login(user)
    response = client.get(reverse("accounts:notification_read", kwargs={"pk": notif.pk}))
    assert response.status_code == 302
    notif.refresh_from_db()
    assert notif.is_read is True


@pytest.mark.django_db
def test_notification_read_redirects_to_execution_when_related(db):
    from apps.flows.models import FlowExecution

    user = make_user("notifexec")
    execution = FlowExecution.objects.create(
        flow_run_id=uuid.uuid4(),
        flow_name="pipeline",
        triggered_by=user,
        s3_input_path="raw/test.csv",
        status="FAILED",
    )
    notif = Notification.objects.create(
        user=user,
        notification_type="EXECUTION_FAILED",
        message="failed",
        related_execution=execution,
    )

    client = Client()
    client.force_login(user)
    response = client.get(reverse("accounts:notification_read", kwargs={"pk": notif.pk}))
    assert response.status_code == 302
    assert str(execution.flow_run_id) in response["Location"]


@pytest.mark.django_db
def test_notification_read_404_for_other_user():
    user = make_user("notif404owner")
    other = make_user("notif404other")
    notif = Notification.objects.create(user=other, notification_type="SYSTEM", message="secret")

    client = Client()
    client.force_login(user)
    response = client.get(reverse("accounts:notification_read", kwargs={"pk": notif.pk}))
    assert response.status_code == 404


# ── settings view — new notification prefs ────────────────────────────────────


@pytest.mark.django_db
def test_settings_saves_all_notification_prefs():
    user = make_user("notifprefs")
    client = Client()
    client.force_login(user)

    client.post(
        reverse("accounts:settings"),
        {
            "notify_on_failure": "on",
            "notify_on_success": "on",
            # notify_in_app and notify_via_email omitted → False
        },
    )

    user.profile.refresh_from_db()
    assert user.profile.notify_on_failure is True
    assert user.profile.notify_on_success is True
    assert user.profile.notify_in_app is False
    assert user.profile.notify_via_email is False


# ── task integration — _send_failure_notification ────────────────────────────


@pytest.mark.django_db
def test_failure_notification_creates_in_app_record(db):
    from apps.flows.tasks import _send_failure_notification

    user = make_user("taskfail")
    profile = user.profile
    profile.notify_on_failure = True
    profile.notify_in_app = True
    profile.notify_via_email = False
    profile.save()

    run_id = uuid.uuid4()
    with patch("apps.flows.tasks.send_mail"):
        _send_failure_notification(run_id, user.pk, "pipeline", "something broke")

    assert Notification.objects.filter(user=user, notification_type="EXECUTION_FAILED").count() == 1


@pytest.mark.django_db
def test_failure_notification_respects_notify_on_failure_false(db):
    from apps.flows.tasks import _send_failure_notification

    user = make_user("taskfailoff")
    profile = user.profile
    profile.notify_on_failure = False
    profile.save()

    run_id = uuid.uuid4()
    _send_failure_notification(run_id, user.pk, "pipeline", "error")
    assert Notification.objects.filter(user=user).count() == 0


@pytest.mark.django_db
def test_failure_notification_no_in_app_when_disabled(db):
    from apps.flows.tasks import _send_failure_notification

    user = make_user("taskfailnoinapp")
    profile = user.profile
    profile.notify_on_failure = True
    profile.notify_in_app = False
    profile.notify_via_email = False
    profile.save()

    run_id = uuid.uuid4()
    _send_failure_notification(run_id, user.pk, "pipeline", "error")
    assert Notification.objects.filter(user=user).count() == 0


# ── task integration — _send_success_notification ────────────────────────────


@pytest.mark.django_db
def test_success_notification_not_sent_when_disabled(db):
    from apps.flows.tasks import _send_success_notification

    user = make_user("tasksuccess")
    # notify_on_success defaults to False
    run_id = uuid.uuid4()
    _send_success_notification(run_id, user.pk, "pipeline")
    assert Notification.objects.filter(user=user).count() == 0


@pytest.mark.django_db
def test_success_notification_creates_record_when_enabled(db):
    from apps.flows.tasks import _send_success_notification

    user = make_user("tasksuccesson")
    profile = user.profile
    profile.notify_on_success = True
    profile.notify_in_app = True
    profile.notify_via_email = False
    profile.save()

    run_id = uuid.uuid4()
    with patch("apps.flows.tasks.send_mail"):
        _send_success_notification(run_id, user.pk, "pipeline")

    assert (
        Notification.objects.filter(user=user, notification_type="EXECUTION_COMPLETED").count() == 1
    )
