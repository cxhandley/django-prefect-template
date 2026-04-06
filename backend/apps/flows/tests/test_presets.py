"""
Tests for BL-010 (InputPreset) and BL-012 (retry_execution).
"""

import pytest
from apps.flows.models import FlowExecution, InputPreset
from django.urls import reverse

# ============================================================================
# BL-010 — InputPreset model
# ============================================================================


@pytest.mark.django_db
def test_input_preset_str(user):
    preset = InputPreset.objects.create(
        user=user,
        name="Test preset",
        input_values={"income": "80000"},
    )
    assert user.email in str(preset)
    assert "Test preset" in str(preset)


@pytest.mark.django_db
def test_input_preset_unique_per_user(user):
    from django.db import IntegrityError

    InputPreset.objects.create(user=user, name="My preset", input_values={})
    with pytest.raises(IntegrityError):
        InputPreset.objects.create(user=user, name="My preset", input_values={})


@pytest.mark.django_db
def test_input_preset_unique_name_different_users(user, user_factory):
    other = user_factory()
    InputPreset.objects.create(user=user, name="shared name", input_values={})
    # Same name for a different user is allowed
    preset = InputPreset.objects.create(user=other, name="shared name", input_values={})
    assert preset.pk is not None


# ============================================================================
# BL-010 — save_preset view
# ============================================================================


@pytest.mark.django_db
def test_save_preset_creates_preset(authenticated_client, user):
    url = reverse("flows:save_preset")
    data = {
        "preset_name": "My preset",
        "income": "75000",
        "age": "35",
        "credit_score": "720",
        "employment_years": "8",
    }
    response = authenticated_client.post(url, data)
    assert response.status_code == 200
    assert InputPreset.objects.filter(user=user, name="My preset").exists()
    preset = InputPreset.objects.get(user=user, name="My preset")
    assert preset.input_values["income"] == "75000"


@pytest.mark.django_db
def test_save_preset_updates_existing(authenticated_client, user):
    InputPreset.objects.create(user=user, name="My preset", input_values={"income": "50000"})
    url = reverse("flows:save_preset")
    data = {
        "preset_name": "My preset",
        "income": "90000",
        "age": "40",
        "credit_score": "750",
        "employment_years": "12",
    }
    authenticated_client.post(url, data)
    preset = InputPreset.objects.get(user=user, name="My preset")
    assert preset.input_values["income"] == "90000"
    assert InputPreset.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_save_preset_requires_name(authenticated_client, user):
    url = reverse("flows:save_preset")
    response = authenticated_client.post(url, {"income": "75000"})
    assert response.status_code == 200
    assert not InputPreset.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_save_preset_requires_login(api_client):
    url = reverse("flows:save_preset")
    response = api_client.post(url, {"preset_name": "x", "income": "100"})
    assert response.status_code == 302
    assert "/login/" in response["Location"]


# ============================================================================
# BL-010 — load_preset view
# ============================================================================


@pytest.mark.django_db
def test_load_preset_returns_form_partial(authenticated_client, user):
    preset = InputPreset.objects.create(
        user=user,
        name="Quick test",
        input_values={
            "income": "60000",
            "age": "30",
            "credit_score": "700",
            "employment_years": "5",
        },
    )
    url = reverse("flows:load_preset")
    response = authenticated_client.get(url, {"preset_id": preset.pk})
    assert response.status_code == 200
    content = response.content.decode()
    assert "60000" in content


@pytest.mark.django_db
def test_load_preset_empty_id_returns_blank_form(authenticated_client):
    url = reverse("flows:load_preset")
    response = authenticated_client.get(url, {"preset_id": ""})
    assert response.status_code == 200


@pytest.mark.django_db
def test_load_preset_cannot_access_other_user_preset(authenticated_client, user_factory):
    other = user_factory()
    preset = InputPreset.objects.create(user=other, name="Other", input_values={"income": "999"})
    url = reverse("flows:load_preset")
    response = authenticated_client.get(url, {"preset_id": preset.pk})
    assert response.status_code == 404


# ============================================================================
# BL-010 — delete_preset view
# ============================================================================


@pytest.mark.django_db
def test_delete_preset(authenticated_client, user):
    preset = InputPreset.objects.create(user=user, name="To delete", input_values={})
    url = reverse("flows:delete_preset", kwargs={"preset_id": preset.pk})
    response = authenticated_client.post(url)
    assert response.status_code == 200
    assert not InputPreset.objects.filter(pk=preset.pk).exists()


@pytest.mark.django_db
def test_delete_preset_other_user_returns_404(authenticated_client, user_factory):
    other = user_factory()
    preset = InputPreset.objects.create(user=other, name="Other", input_values={})
    url = reverse("flows:delete_preset", kwargs={"preset_id": preset.pk})
    response = authenticated_client.post(url)
    assert response.status_code == 404


# ============================================================================
# BL-012 — retry_execution view
# ============================================================================


@pytest.mark.django_db
def test_retry_creates_new_execution(authenticated_client, user, flow_execution_factory, mocker):
    original = flow_execution_factory(
        triggered_by=user,
        flow_name="predict_pipeline",
        status="FAILED",
        s3_input_path="raw/flows/abc/input.csv",
        income=70000,
        error_message="Pipeline error",
    )
    mock_task = mocker.patch("apps.flows.views.run_prediction_task")
    mock_task.delay.return_value.id = "new-task-id"

    url = reverse("flows:retry_execution", kwargs={"run_id": original.flow_run_id})
    response = authenticated_client.post(url)

    assert response.status_code == 302
    assert FlowExecution.objects.count() == 2

    new_exec = FlowExecution.objects.exclude(pk=original.pk).get()
    assert new_exec.status == "PENDING"
    assert new_exec.flow_name == "predict_pipeline"
    assert new_exec.s3_input_path == original.s3_input_path
    # BL-026: inputs are typed fields on FlowExecution, not parameters blob
    assert new_exec.income == original.income


@pytest.mark.django_db
def test_retry_pipeline_task_dispatched_for_pipeline_flow(
    authenticated_client, user, flow_execution_factory, mocker
):
    original = flow_execution_factory(
        triggered_by=user,
        flow_name="data-processing",
        status="FAILED",
        s3_input_path="raw/flows/abc/input.csv",
        parameters={},
    )
    mock_task = mocker.patch("apps.flows.views.run_pipeline_task")
    mock_task.delay.return_value.id = "pipeline-task-id"

    url = reverse("flows:retry_execution", kwargs={"run_id": original.flow_run_id})
    authenticated_client.post(url)

    mock_task.delay.assert_called_once()


@pytest.mark.django_db
def test_retry_non_failed_execution_redirects_without_clone(
    authenticated_client, user, flow_execution_factory
):
    original = flow_execution_factory(
        triggered_by=user,
        flow_name="predict_pipeline",
        status="COMPLETED",
        parameters={},
    )
    url = reverse("flows:retry_execution", kwargs={"run_id": original.flow_run_id})
    response = authenticated_client.post(url)

    assert response.status_code == 302
    assert FlowExecution.objects.count() == 1


@pytest.mark.django_db
def test_retry_requires_login(api_client, user, flow_execution_factory):
    original = flow_execution_factory(
        triggered_by=user, flow_name="predict_pipeline", status="FAILED", parameters={}
    )
    url = reverse("flows:retry_execution", kwargs={"run_id": original.flow_run_id})
    response = api_client.post(url)
    assert response.status_code == 302
    assert "/login/" in response["Location"]


@pytest.mark.django_db
def test_retry_cannot_access_other_user_execution(
    authenticated_client, user_factory, flow_execution_factory
):
    other = user_factory()
    original = flow_execution_factory(
        triggered_by=other, flow_name="predict_pipeline", status="FAILED", parameters={}
    )
    url = reverse("flows:retry_execution", kwargs={"run_id": original.flow_run_id})
    response = authenticated_client.post(url)
    assert response.status_code == 404
