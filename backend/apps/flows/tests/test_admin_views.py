"""
Tests for staff-only admin monitoring views (BL-008, BL-009).
"""

import datetime
import uuid

import pytest
from apps.flows.models import FlowExecution
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

User = get_user_model()


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        username="staffmember",
        email="staff@example.com",
        password="staffPass123!",
        is_staff=True,
    )


@pytest.fixture
def regular_user(db):
    return User.objects.create_user(
        username="regular",
        email="regular@example.com",
        password="regularPass123!",
    )


@pytest.fixture
def completed_execution(db, regular_user):
    return FlowExecution.objects.create(
        flow_run_id=uuid.uuid4(),
        flow_name="credit-prediction",
        triggered_by=regular_user,
        status="COMPLETED",
        parameters={"income": 50000, "age": 30, "credit_score": 700, "employment_years": 5},
        created_at=timezone.now() - datetime.timedelta(hours=1),
        completed_at=timezone.now(),
    )


@pytest.fixture
def failed_execution(db, regular_user):
    return FlowExecution.objects.create(
        flow_run_id=uuid.uuid4(),
        flow_name="data-processing",
        triggered_by=regular_user,
        status="FAILED",
        error_message="Timeout after 60s",
        celery_task_id="celery-abc-123",
        created_at=timezone.now() - datetime.timedelta(hours=2),
    )


# ============================================================================
# Admin Dashboard (BL-008)
# ============================================================================


@pytest.mark.django_db
def test_admin_dashboard_requires_staff(regular_user):
    client = Client()
    client.force_login(regular_user)
    response = client.get("/flows/admin/dashboard/")
    assert response.status_code == 302


@pytest.mark.django_db
def test_admin_dashboard_anonymous_redirects():
    client = Client()
    response = client.get("/flows/admin/dashboard/")
    assert response.status_code == 302


@pytest.mark.django_db
def test_admin_dashboard_accessible_to_staff(staff_user):
    client = Client()
    client.force_login(staff_user)
    response = client.get("/flows/admin/dashboard/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_admin_dashboard_shows_stat_cards(staff_user, completed_execution, failed_execution):
    client = Client()
    client.force_login(staff_user)
    response = client.get("/flows/admin/dashboard/")
    assert response.status_code == 200
    # Both executions present — total should be at least 2
    assert b"Total Executions" in response.content
    assert b"Success Rate" in response.content
    assert b"Avg Run Time" in response.content
    assert b"Executions (30d)" in response.content


@pytest.mark.django_db
def test_admin_dashboard_shows_breakdown_tables(staff_user, completed_execution, failed_execution):
    client = Client()
    client.force_login(staff_user)
    response = client.get("/flows/admin/dashboard/")
    assert response.status_code == 200
    assert b"By User" in response.content
    assert b"By Flow Type" in response.content
    assert b"credit-prediction" in response.content
    assert b"data-processing" in response.content


@pytest.mark.django_db
def test_admin_dashboard_shows_daily_chart(staff_user, completed_execution):
    client = Client()
    client.force_login(staff_user)
    response = client.get("/flows/admin/dashboard/")
    assert response.status_code == 200
    assert b"Daily Executions" in response.content


@pytest.mark.django_db
def test_admin_dashboard_link_to_execution_logs(staff_user):
    client = Client()
    client.force_login(staff_user)
    response = client.get("/flows/admin/dashboard/")
    assert b"Execution Logs" in response.content


# ============================================================================
# Admin Execution Log Viewer (BL-009)
# ============================================================================


@pytest.mark.django_db
def test_admin_executions_requires_staff(regular_user):
    client = Client()
    client.force_login(regular_user)
    response = client.get("/flows/admin/executions/")
    assert response.status_code == 302


@pytest.mark.django_db
def test_admin_executions_accessible_to_staff(staff_user, completed_execution, failed_execution):
    client = Client()
    client.force_login(staff_user)
    response = client.get("/flows/admin/executions/")
    assert response.status_code == 200
    assert b"regular@example.com" in response.content


@pytest.mark.django_db
def test_admin_executions_filter_by_status(staff_user, completed_execution, failed_execution):
    """Filtering by FAILED shows the failed execution's error and hides the completed one."""
    client = Client()
    client.force_login(staff_user)
    response = client.get("/flows/admin/executions/?f_field[]=status&f_op[]=eq&f_val[]=FAILED")
    assert response.status_code == 200
    # The failed execution has an error message; completed has none
    assert b"Timeout after 60s" in response.content
    assert b"credit-prediction" not in response.content


@pytest.mark.django_db
def test_admin_executions_filter_by_user(staff_user, completed_execution, db):
    other_user = User.objects.create_user(username="other", email="other@example.com", password="x")
    FlowExecution.objects.create(
        flow_run_id=uuid.uuid4(),
        flow_name="data-processing",
        triggered_by=other_user,
        status="COMPLETED",
    )
    client = Client()
    client.force_login(staff_user)
    response = client.get(
        "/flows/admin/executions/?f_field[]=user&f_op[]=contains&f_val[]=other%40example.com"
    )
    assert response.status_code == 200
    assert b"other@example.com" in response.content
    assert b"regular@example.com" not in response.content


@pytest.mark.django_db
def test_admin_executions_htmx_returns_partial(staff_user, completed_execution):
    client = Client()
    client.force_login(staff_user)
    response = client.get("/flows/admin/executions/", HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    # Partial template should not contain the full page chrome
    assert b"<!DOCTYPE" not in response.content


@pytest.mark.django_db
def test_admin_executions_shows_all_users(staff_user, completed_execution, db):
    """Staff can see executions from all users, not just their own."""
    other_user = User.objects.create_user(
        username="other2", email="other2@example.com", password="x"
    )
    FlowExecution.objects.create(
        flow_run_id=uuid.uuid4(),
        flow_name="credit-prediction",
        triggered_by=other_user,
        status="PENDING",
    )
    client = Client()
    client.force_login(staff_user)
    response = client.get("/flows/admin/executions/")
    assert b"regular@example.com" in response.content
    assert b"other2@example.com" in response.content


# ============================================================================
# Admin Execution Detail (BL-009)
# ============================================================================


@pytest.mark.django_db
def test_admin_execution_detail_requires_staff(regular_user, completed_execution):
    client = Client()
    client.force_login(regular_user)
    response = client.get(f"/flows/admin/executions/{completed_execution.flow_run_id}/")
    assert response.status_code == 302


@pytest.mark.django_db
def test_admin_execution_detail_accessible_to_staff(staff_user, completed_execution):
    client = Client()
    client.force_login(staff_user)
    response = client.get(f"/flows/admin/executions/{completed_execution.flow_run_id}/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_admin_execution_detail_shows_metadata(staff_user, completed_execution):
    client = Client()
    client.force_login(staff_user)
    response = client.get(f"/flows/admin/executions/{completed_execution.flow_run_id}/")
    assert response.status_code == 200
    assert b"regular@example.com" in response.content
    assert b"credit-prediction" in response.content
    assert b"COMPLETED" in response.content


@pytest.mark.django_db
def test_admin_execution_detail_shows_parameters(staff_user, completed_execution):
    client = Client()
    client.force_login(staff_user)
    response = client.get(f"/flows/admin/executions/{completed_execution.flow_run_id}/")
    # Parameters JSON should be rendered
    assert b"income" in response.content


@pytest.mark.django_db
def test_admin_execution_detail_shows_error_for_failed(staff_user, failed_execution):
    client = Client()
    client.force_login(staff_user)
    response = client.get(f"/flows/admin/executions/{failed_execution.flow_run_id}/")
    assert response.status_code == 200
    assert b"Timeout after 60s" in response.content


@pytest.mark.django_db
def test_admin_execution_detail_shows_celery_task_link(staff_user, failed_execution):
    client = Client()
    client.force_login(staff_user)
    response = client.get(f"/flows/admin/executions/{failed_execution.flow_run_id}/")
    assert b"celery-abc-123" in response.content
    assert b"Flower" in response.content


@pytest.mark.django_db
def test_admin_execution_detail_404_for_unknown_run_id(staff_user):
    client = Client()
    client.force_login(staff_user)
    response = client.get(f"/flows/admin/executions/{uuid.uuid4()}/")
    assert response.status_code == 404
