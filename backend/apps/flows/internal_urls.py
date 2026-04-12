"""
Internal URL patterns — not exposed externally.

These endpoints are called by the Prefect Worker container over the Docker
internal network.  They are authenticated by a shared bearer token
(PREFECT_INTERNAL_SECRET setting) and must never be accessible from the
public internet.
"""

from django.urls import path

from . import views

urlpatterns = [
    path("step-status/", views.internal_step_status, name="internal_step_status"),
]
