"""
Production settings.

Intended for Docker Swarm deployment with Traefik handling SSL termination.
See docs/deployment/production.md for full architecture and deploy procedure.
"""

from .base import *  # noqa: F401, F403
from .base import MIDDLEWARE, STORAGES, env  # noqa: F401 — explicit re-import silences F405

DEBUG = False

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

# WhiteNoise serves and compresses static files with long-lived cache headers.
# Must come immediately after SecurityMiddleware.
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

STORAGES = {
    **STORAGES,
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Security headers.
# Traefik terminates TLS so Django sees plain HTTP internally; the proxy header
# tells Django the original request was HTTPS.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = False  # Traefik handles the HTTP→HTTPS redirect
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Use real S3, not RustFS
AWS_S3_ENDPOINT_URL = None

# django-compressor: pre-compress all {% compress %} blocks at deploy time
COMPRESS_OFFLINE = True
COMPRESS_ENABLED = True

# Structured logging to stdout — captured by Docker and forwarded to
# CloudWatch / Datadog / any log aggregator via the logging driver.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {process:d} {thread:d} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
