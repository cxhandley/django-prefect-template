import os

from .base import *  # noqa: F401, F403

# Disable OpenTelemetry in tests — avoids collector connection attempts and
# keeps the test suite fast.
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

DEBUG = False

# Use in-memory SQLite for tests
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Speed up password hashing
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]


# Disable migrations for tests (faster)
class DisableMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = DisableMigrations()

# Email — capture in memory so tests can inspect django.core.mail.outbox
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
