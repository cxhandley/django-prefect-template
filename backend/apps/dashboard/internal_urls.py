"""
Internal URL patterns for the MCP server ↔ Django API.

These endpoints are authenticated by a shared bearer token (MCP_INTERNAL_SECRET)
and must never be publicly accessible.
"""

from django.urls import path

from . import views

urlpatterns = [
    path(
        "dashboard/<int:dashboard_id>/widgets/<int:widget_id>/",
        views.internal_widget_data,
        name="internal_widget_data",
    ),
    path(
        "dashboard/<int:dashboard_id>/widgets/",
        views.internal_widget_upsert,
        name="internal_widget_upsert",
    ),
    path(
        "session/tokens/",
        views.internal_session_token_update,
        name="internal_session_token_update",
    ),
]
