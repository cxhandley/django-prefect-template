import ipaddress
import urllib.parse

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

# ── Private RFC-1918 / loopback ranges blocked for LLAMA_OPENAI base_url ─────
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def _is_private(host: str) -> bool:
    """Return True if *host* resolves to a private / loopback address."""
    try:
        addr = ipaddress.ip_address(host)
        return any(addr in net for net in _PRIVATE_NETWORKS)
    except ValueError:
        # hostname — only block known internal Docker service names
        return host in {"db", "redis", "rustfs", "otel-collector", "jaeger", "postgres"}


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

    mcp_token_budget = models.IntegerField(
        null=True,
        blank=True,
        help_text="Per-user token budget override for MCP sessions. Null = use MCP_SESSION_TOKEN_BUDGET setting.",
    )

    def __str__(self):
        return f"Profile({self.user.email})"


class UserApiKey(models.Model):
    """
    A user-supplied API key for an AI provider, used by the conversational
    dashboard builder.  The key value is encrypted at rest with Fernet;
    only the last four characters are stored in plaintext for display.

    No platform-level key ever exists — each dispatch uses the requesting
    user's own key, decrypted in memory only.
    """

    class Provider(models.TextChoices):
        ANTHROPIC = "ANTHROPIC", "Anthropic"
        LLAMA_OPENAI = "LLAMA_OPENAI", "Llama (local, OpenAI-compatible)"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="api_keys",
    )
    provider = models.CharField(max_length=20, choices=Provider.choices)
    # Fernet-encrypted key value — write-only after save
    encrypted_key = models.TextField(
        blank=True,
        help_text="Fernet-encrypted API key. Never returned to the frontend.",
    )
    # Last 4 chars of the plaintext key — safe to display
    masked_suffix = models.CharField(
        max_length=4,
        blank=True,
        help_text="Last 4 characters of the key, stored unencrypted for display only.",
    )
    # Only required (and only shown) for LLAMA_OPENAI
    base_url = models.URLField(
        blank=True,
        help_text="OpenAI-compatible base URL for local providers (e.g. http://localhost:11434/v1).",
    )
    label = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # One active key per provider per user
        unique_together = [("user", "provider")]
        indexes = [
            models.Index(fields=["user", "is_active"]),
        ]
        ordering = ["provider"]

    def __str__(self):
        return f"{self.get_provider_display()} key for {self.user.email} (****{self.masked_suffix})"

    # ── Encryption helpers ─────────────────────────────────────────────────

    @staticmethod
    def _fernet() -> Fernet:
        key = settings.FIELD_ENCRYPTION_KEY
        if not key:
            raise RuntimeError("FIELD_ENCRYPTION_KEY setting is not configured.")
        return Fernet(key.encode() if isinstance(key, str) else key)

    def set_key(self, plaintext: str) -> None:
        """Encrypt and store *plaintext*; derive masked_suffix."""
        if not plaintext:
            return
        self.encrypted_key = self._fernet().encrypt(plaintext.encode()).decode()
        self.masked_suffix = plaintext[-4:] if len(plaintext) >= 4 else plaintext

    def get_key(self) -> str:
        """Decrypt and return the key value. Call only during dispatch — never log the result."""
        if not self.encrypted_key:
            return ""
        return self._fernet().decrypt(self.encrypted_key.encode()).decode()

    # ── Validation ────────────────────────────────────────────────────────

    def clean(self):
        if self.provider == self.Provider.LLAMA_OPENAI:
            if not self.base_url:
                raise ValidationError(
                    {"base_url": "Base URL is required for Llama (local) provider."}
                )
            parsed = urllib.parse.urlparse(self.base_url)
            if parsed.scheme not in {"http", "https"}:
                raise ValidationError({"base_url": "Base URL must use http or https."})
            host = parsed.hostname or ""
            if _is_private(host):
                # Localhost is explicitly allowed for local AI (ollama, lm-studio, etc.)
                # We only block known Docker-internal service names.
                if host not in {"localhost", "127.0.0.1", "::1"}:
                    raise ValidationError(
                        {
                            "base_url": f"Base URL hostname '{host}' resolves to a private network address."
                        }
                    )
        if self.provider == self.Provider.ANTHROPIC and not self.encrypted_key:
            raise ValidationError({"api_key": "An API key is required for Anthropic."})


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
