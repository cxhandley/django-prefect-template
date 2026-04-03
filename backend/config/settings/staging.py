"""
Staging settings.

Intended for a single EC2 instance running all services via Docker Compose
with Traefik handling SSL termination (see docs/deployment/staging.md).
"""

from .base import *  # noqa: F401, F403
from .base import MIDDLEWARE, STORAGES, env  # noqa: F401 — explicit re-import silences F405

DEBUG = False

ALLOWED_HOSTS = [env("STAGING_HOST")]

# WhiteNoise serves and compresses static files with long-lived cache headers.
# Must come immediately after SecurityMiddleware.
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

STORAGES = {
    **STORAGES,
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Security headers (Traefik terminates TLS so Django sees plain HTTP internally,
# but the SECURE_PROXY_SSL_HEADER setting tells it the request was originally HTTPS).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = False  # Traefik handles the HTTP→HTTPS redirect
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = True

# django-compressor: pre-compress all {% compress %} blocks at deploy time
COMPRESS_OFFLINE = True
COMPRESS_ENABLED = True
