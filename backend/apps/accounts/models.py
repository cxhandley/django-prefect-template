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
        help_text="Send an email when an execution reaches terminal FAILED status.",
    )

    def __str__(self):
        return f"Profile({self.user.email})"
