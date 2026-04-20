from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("widgets/", views.widget_grid, name="widget_grid"),
    path("chat/", views.dashboard_chat, name="chat"),
    path("session/reset/", views.session_reset, name="session_reset"),
]
