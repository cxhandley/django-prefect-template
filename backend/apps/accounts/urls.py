from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_user, name="login"),
    path("signup/", views.signup_user, name="signup"),
    path("profile/", views.profile, name="profile"),
    path("settings/", views.settings, name="settings"),
    path("api/user-menu/", views.user_menu, name="user_menu"),
    path("api/logout/", views.logout_user, name="logout"),
    path(
        "api/notifications/dropdown/", views.notifications_dropdown, name="notifications_dropdown"
    ),
    # Notifications
    path("notifications/", views.notifications, name="notifications"),
    path("notifications/<int:pk>/read/", views.notification_read, name="notification_read"),
    path(
        "notifications/mark-all-read/",
        views.notifications_mark_all_read,
        name="notifications_mark_all_read",
    ),
    # Email confirmation
    path(
        "email-confirmation-sent/",
        views.email_confirmation_sent,
        name="email_confirmation_sent",
    ),
    path("confirm-email/<str:token>/", views.confirm_email, name="confirm_email"),
    # Superuser user management
    path("users/", views.user_list, name="user_list"),
    path("users/<int:user_id>/toggle-active/", views.user_toggle_active, name="user_toggle_active"),
    path("users/<int:user_id>/reset-password/", views.user_send_reset, name="user_send_reset"),
    # Password change flow for logged-in users (form-based, no email)
    path(
        "password-change/",
        auth_views.PasswordChangeView.as_view(
            template_name="accounts/password_change.html",
            success_url="/accounts/password-change/done/",
        ),
        name="password_change",
    ),
    path(
        "password-change/done/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="accounts/password_change_done.html",
        ),
        name="password_change_done",
    ),
    # Password reset flow (Django built-in views, custom templates)
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="accounts/password_reset.html",
            email_template_name="accounts/email/password_reset.txt",
            subject_template_name="accounts/email/password_reset_subject.txt",
            success_url="/accounts/password-reset/done/",
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="accounts/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "password-reset/confirm/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url="/accounts/password-reset/complete/",
        ),
        name="password_reset_confirm",
    ),
    path(
        "password-reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),
]
