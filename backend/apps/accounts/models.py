from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    """Per-user preferences and settings, auto-created alongside each User."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    notify_on_failure = models.BooleanField(
        default=True,
        help_text="Notify when an execution reaches terminal FAILED status.",
    )
    notify_on_success = models.BooleanField(
        default=False,
        help_text="Notify when an execution completes successfully.",
    )
    notify_in_app = models.BooleanField(
        default=True,
        help_text="Create in-app notifications (bell icon).",
    )
    notify_via_email = models.BooleanField(
        default=True,
        help_text="Send email notifications.",
    )

    def __str__(self):
        return f"Profile({self.user.email})"


class Notification(models.Model):
    """In-app notification record for a user."""

    class Type(models.TextChoices):
        EXECUTION_FAILED = "EXECUTION_FAILED", "Execution Failed"
        EXECUTION_COMPLETED = "EXECUTION_COMPLETED", "Execution Completed"
        SYSTEM = "SYSTEM", "System"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    notification_type = models.CharField(max_length=30, choices=Type.choices)
    message = models.TextField()
    related_execution = models.ForeignKey(
        "flows.FlowExecution",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notifications",
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.notification_type} → {self.user.email} ({'read' if self.is_read else 'unread'})"
        )
