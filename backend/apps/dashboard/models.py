from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

# ── Widget config allow-lists — enforced in clean() ───────────────────────────

_WIDGET_CONFIG_KEYS: dict[str, set[str]] = {
    "METRIC_CARD": {"field", "aggregation", "label", "unit"},
    "LINE_CHART": {"x_field", "y_field", "label", "color"},
    "BAR_CHART": {"x_field", "y_field", "label", "color"},
    "TABLE": {"fields", "limit", "order_by", "order_dir"},
    "SCORE_DISTRIBUTION": {"bins", "label"},
}


class UserDashboard(models.Model):
    """
    A user's personal dashboard layout.  One active dashboard per user;
    additional (inactive) rows are kept as history but not rendered.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dashboards",
    )
    title = models.CharField(max_length=200, default="My Dashboard")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.owner.email})"

    @classmethod
    def get_or_create_active(cls, user):
        """Return the user's active dashboard, creating one if none exists."""
        dashboard = cls.objects.filter(owner=user, is_active=True).first()
        if dashboard is None:
            dashboard = cls.objects.create(owner=user, title="My Dashboard", is_active=True)
        return dashboard


class DashboardWidget(models.Model):
    """
    A single widget on a UserDashboard.  The config JSONField is validated
    against a per-type allow-list in clean() — no untyped blobs.
    """

    class WidgetType(models.TextChoices):
        METRIC_CARD = "METRIC_CARD", "Metric Card"
        LINE_CHART = "LINE_CHART", "Line Chart"
        BAR_CHART = "BAR_CHART", "Bar Chart"
        TABLE = "TABLE", "Table"
        SCORE_DISTRIBUTION = "SCORE_DISTRIBUTION", "Score Distribution"

    dashboard = models.ForeignKey(
        UserDashboard,
        on_delete=models.CASCADE,
        related_name="widgets",
    )
    widget_type = models.CharField(max_length=30, choices=WidgetType.choices)
    title = models.CharField(max_length=200)
    config = models.JSONField(default=dict)
    position_x = models.SmallIntegerField(default=0)
    position_y = models.SmallIntegerField(default=0)
    width = models.SmallIntegerField(default=2)
    height = models.SmallIntegerField(default=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position_y", "position_x"]
        indexes = [
            models.Index(fields=["dashboard"]),
        ]

    def __str__(self):
        return f"{self.get_widget_type_display()}: {self.title}"

    def clean(self):
        allowed = _WIDGET_CONFIG_KEYS.get(self.widget_type, set())
        disallowed = set(self.config.keys()) - allowed
        if disallowed:
            raise ValidationError(
                {"config": f"Disallowed config keys for {self.widget_type}: {sorted(disallowed)}"}
            )


class McpSession(models.Model):
    """
    One conversational session between a user and the MCP server.
    Tracks token consumption against the user's budget.
    Linked to the UserApiKey that was active when the session started;
    deleting the key ends the session immediately.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mcp_sessions",
    )
    user_api_key = models.ForeignKey(
        "accounts.UserApiKey",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
    )
    tokens_used = models.IntegerField(default=0)
    tokens_budget = models.IntegerField()
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["user", "ended_at"]),
        ]

    def __str__(self):
        return f"McpSession({self.user.email}, {self.tokens_used}/{self.tokens_budget})"

    @property
    def is_exhausted(self) -> bool:
        return self.tokens_used >= self.tokens_budget

    @property
    def tokens_remaining(self) -> int:
        return max(0, self.tokens_budget - self.tokens_used)
