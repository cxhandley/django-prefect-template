# Production Environment

Production runs Docker Compose on a dedicated host by default, with an optional upgrade path to Docker Swarm for multi-node horizontal scaling. PostgreSQL backups are automated to S3.

## Architecture

```
Internet → Load Balancer / Traefik → Django web (1–N replicas)
                                   → Celery worker (1–N replicas)
                                   → Flower (internal / admin access only)
           PostgreSQL (managed RDS or container with WAL-G backup)
           Redis (managed ElastiCache or container)
           S3 / RustFS (data lake storage)
```

## Option A — Docker Compose (single host, simpler)

Same structure as staging (see [staging.md](staging.md)) with production settings and a stronger instance (`t3.large` or `m6i.xlarge`). Scale by increasing replica counts:

```yaml
services:
  web:
    deploy:
      replicas: 2
  celery-worker:
    deploy:
      replicas: 2
```

> **Note:** `deploy.replicas` is ignored by plain `docker compose up`. Use `docker compose up --scale web=2` or migrate to Swarm.

## Option B — Docker Swarm (multi-node, optional)

Docker Swarm provides built-in service scheduling, rolling updates, and health-check restarts across multiple EC2 nodes without the complexity of Kubernetes.

### Swarm initialisation

```bash
# On the manager node
docker swarm init --advertise-addr <manager-private-ip>

# On each worker node (token shown by init command)
docker swarm join --token <token> <manager-private-ip>:2377
```

### Stack deployment

Convert `docker-compose.yml` to a Swarm stack file (`docker-stack.yml`) — the main difference is using `deploy:` keys and Swarm secrets instead of `env_file`:

```bash
docker stack deploy -c docker-stack.yml app
docker stack services app        # view running services
docker service scale app_web=3   # scale web tier
docker stack rm app              # teardown
```

### Secrets management (Swarm)

```bash
echo "supersecretvalue" | docker secret create django_secret_key -
```

Reference in `docker-stack.yml`:
```yaml
secrets:
  django_secret_key:
    external: true

services:
  web:
    secrets:
      - django_secret_key
    environment:
      SECRET_KEY_FILE: /run/secrets/django_secret_key
```

## Django Settings — Production

Create `backend/config/settings/production.py`:
```python
from .base import *

DEBUG = False
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Security
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Logging — structured JSON to stdout for CloudWatch / Datadog
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "pythonjsonlogger.jsonlogger.JsonFormatter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
```

## PostgreSQL Backups

### Option 1 — Scheduled `pg_dump` to S3 (simple)

Add a `pg-backup` service to the Compose/Swarm stack:

```yaml
services:
  pg-backup:
    image: postgres:16-alpine
    environment:
      PGPASSWORD: ${DB_PASSWORD}
    entrypoint: >
      sh -c "
        pg_dump -h db -U app app | gzip |
        aws s3 cp - s3://${BACKUP_BUCKET}/postgres/$(date +%Y-%m-%dT%H:%M:%S).sql.gz
      "
    deploy:
      restart_policy:
        condition: none
      # Run via external scheduler (e.g. cron on the manager node, or AWS EventBridge)
```

Trigger daily via cron on the manager node:
```cron
0 2 * * * docker service update --force app_pg-backup
```

Retention: set an S3 lifecycle rule to expire backups older than 30 days.

### Option 2 — WAL-G continuous archiving (robust)

WAL-G streams WAL segments to S3 continuously, enabling point-in-time recovery (PITR). Recommended if data loss tolerance is < 1 hour.

```bash
# Configure in postgresql.conf (via custom postgres image)
archive_mode = on
archive_command = 'wal-g wal-push %p'
restore_command = 'wal-g wal-fetch %f %p'
```

See [WAL-G docs](https://github.com/wal-g/wal-g) for full setup.

### Backup restore test

Always test restores on staging before relying on production backups:

```bash
# Restore latest pg_dump backup
aws s3 cp s3://${BACKUP_BUCKET}/postgres/latest.sql.gz - | gunzip | psql -h localhost -U app app
```

## CI/CD Pipeline (GitHub Actions sketch)

```yaml
jobs:
  deploy:
    steps:
      - uses: actions/checkout@v4
      - name: Build and push image
        run: |
          docker build -t ghcr.io/org/app:${{ github.sha }} .
          docker push ghcr.io/org/app:${{ github.sha }}
      - name: Deploy to production
        run: |
          ssh deploy@prod "docker service update --image ghcr.io/org/app:${{ github.sha }} app_web"
          ssh deploy@prod "docker service update --image ghcr.io/org/app:${{ github.sha }} app_celery-worker"
```

## Health checks

Add to `docker-compose.yml` / `docker-stack.yml`:

```yaml
services:
  web:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

Add a `GET /health/` view in `core/views.py` returning `{"status": "ok"}`.
