from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("render/<int:dashboard_id>/", views.dashboard_render, name="render"),
    path("chat/", views.dashboard_chat, name="chat"),
    path("session/reset/", views.session_reset, name="session_reset"),
]
