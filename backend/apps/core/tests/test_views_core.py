"""
Tests for core views: index, base_layout, navbar.
"""

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def auth_user(db):
    return User.objects.create_user(
        username="coreuser", password="pass123", email="core@example.com"
    )


@pytest.mark.django_db
def test_index_anonymous(client):
    response = client.get("/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_index_authenticated(auth_user):
    from django.test import Client

    client = Client()
    client.force_login(auth_user)
    response = client.get("/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_base_layout(auth_user):
    from django.test import Client

    client = Client()
    client.force_login(auth_user)
    response = client.get("/base/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_navbar(auth_user):
    from django.test import Client

    client = Client()
    client.force_login(auth_user)
    response = client.get("/navbar/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_base_layout_requires_auth(client):
    response = client.get("/base/")
    assert response.status_code == 302


@pytest.mark.django_db
def test_navbar_requires_auth(client):
    response = client.get("/navbar/")
    assert response.status_code == 302


def test_health_anonymous(client):
    """Health endpoint must be publicly accessible (no auth, no DB)."""
    response = client.get("/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_post_not_allowed(client):
    response = client.post("/health/")
    assert response.status_code == 405
