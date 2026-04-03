import hashlib

from django.conf import settings
from django.core.validators import MaxValueValidator
from django.db import models


class FeatureFlag(models.Model):
    """
    Runtime feature toggle.

    Resolution order for is_active_for_user(user) — first match wins:
      1. enabled_for_users — if the user is explicitly listed, flag is on.
      2. rollout_percentage — deterministic per-user hash; stable across requests.
      3. is_enabled — global on/off fallback.
    """

    name = models.SlugField(
        unique=True,
        help_text="Unique identifier used in code (e.g. 'notifications').",
    )
    description = models.TextField(blank=True)
    is_enabled = models.BooleanField(
        default=False,
        help_text="Global on/off fallback when no user-specific rule applies.",
    )
    rollout_percentage = models.PositiveSmallIntegerField(
        default=0,
        validators=[MaxValueValidator(100)],
        help_text="0 = disabled. 1–100 = percentage of users who see the feature (deterministic).",
    )
    enabled_for_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        help_text="Users who always see this feature regardless of other settings.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def is_active_for_user(self, user) -> bool:
        """Return True if this flag is active for the given user."""
        if not user or not user.is_authenticated:
            return self.is_enabled

        # 1. Explicit allow-list
        if self.enabled_for_users.filter(pk=user.pk).exists():
            return True

        # 2. Percentage rollout — deterministic hash so the result is stable per user
        if self.rollout_percentage > 0:
            key = f"{user.pk}:{self.name}"
            digest = int(hashlib.sha256(key.encode()).hexdigest(), 16)
            return (digest % 100) < self.rollout_percentage

        # 3. Global toggle
        return self.is_enabled
