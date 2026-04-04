# Production environment template — secrets resolved by 1Password at runtime.
#
# Usage (push to host):
#   just -f deploy/justfile push-env
#
# This file uses op inject template syntax: {{ op://Vault/Item/field }}
# NEVER store plaintext secrets here. This file is safe to commit.
#
# 1Password vault structure (create these items in the "Production" vault):
#   Item "App"
#     - django_secret_key
#     - db_password
#     - data_lake_bucket
#     - backup_bucket        (populated from `terraform output backup_bucket`)
#     - production_host      (populated from `terraform output host_ip`)
#     - ghcr_repo            (e.g. my-org/my-repo)
#     - email_host
#     - email_user
#     - email_password
#     - from_email
#   Item "AWS"
#     - access_key_id        (IAM user with S3 data-lake access)
#     - secret_access_key

# Django
DJANGO_SECRET_KEY={{ op://Production/App/django_secret_key }}
DJANGO_ALLOWED_HOSTS={{ op://Production/App/production_host }}
DEBUG=False

# Database
DB_NAME=app
DB_USER=app
DB_PASSWORD={{ op://Production/App/db_password }}
DATABASE_URL=postgresql://app:{{ op://Production/App/db_password }}@db:5432/app

# Redis / Celery
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# AWS — data lake (S3)
AWS_ACCESS_KEY_ID={{ op://Production/AWS/access_key_id }}
AWS_SECRET_ACCESS_KEY={{ op://Production/AWS/secret_access_key }}
AWS_DEFAULT_REGION=ap-southeast-2
AWS_STORAGE_BUCKET_NAME={{ op://Production/App/data_lake_bucket }}

# PostgreSQL backups
BACKUP_BUCKET={{ op://Production/App/backup_bucket }}

# Email (SES or SMTP relay)
EMAIL_HOST={{ op://Production/App/email_host }}
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER={{ op://Production/App/email_user }}
EMAIL_HOST_PASSWORD={{ op://Production/App/email_password }}
DEFAULT_FROM_EMAIL={{ op://Production/App/from_email }}

# Docker image registry
GHCR_REPO={{ op://Production/App/ghcr_repo }}

# OpenTelemetry
OTEL_SERVICE_NAME={{ op://Production/App/otel_service_name }}
OTEL_EXPORTER_OTLP_ENDPOINT={{ op://Production/App/otel_endpoint }}
OTEL_TRACES_SAMPLER=parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG=0.1
OTEL_SDK_DISABLED=false

# Trace backend credentials (used by otel/collector-production.yml)
# Set whichever backend you're using; leave others blank.
TEMPO_ENDPOINT={{ op://Production/App/tempo_endpoint }}
TEMPO_TOKEN={{ op://Production/App/tempo_token }}
HONEYCOMB_API_KEY={{ op://Production/App/honeycomb_api_key }}
