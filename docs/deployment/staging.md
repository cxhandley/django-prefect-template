# Staging Environment

Single EC2 instance running all services via Docker Compose, with Traefik handling SSL termination and automatic Let's Encrypt certificates.

## Architecture

```
Internet → Traefik (port 80/443) → Django (web)
                                 → Flower (Celery monitor)
                                 → RustFS / MinIO (S3-compatible, internal only)
                          Redis  ← Celery worker
                          PostgreSQL (container, volume-backed)
```

All services run in a single `docker-compose.yml` (or a `docker-compose.staging.yml` override). Traefik runs as a container on the same host and routes by hostname label.

## EC2 Setup

**Recommended instance:** `t3.medium` (2 vCPU, 4 GB RAM) for light staging load.

```bash
# 1. Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker ubuntu

# 2. Open ports in Security Group
# 80  (HTTP  — Traefik redirect to HTTPS)
# 443 (HTTPS — Traefik)
# 22  (SSH)
# All outbound

# 3. Create app directory
sudo mkdir -p /opt/app
sudo chown ubuntu:ubuntu /opt/app
```

## Directory layout on EC2

```
/opt/app/
├── docker-compose.yml
├── docker-compose.staging.yml   # staging overrides
├── .env.staging                 # secrets (not in git)
├── traefik/
│   ├── traefik.yml              # static config
│   └── acme.json                # Let's Encrypt certs (chmod 600)
└── data/
    ├── postgres/                # PG data volume
    └── rustfs/                  # S3 data volume
```

## Traefik Configuration

`traefik/traefik.yml`:
```yaml
entryPoints:
  web:
    address: ":80"
    http:
      redirections:
        entryPoint:
          to: websecure
          scheme: https
  websecure:
    address: ":443"

certificatesResolvers:
  letsencrypt:
    acme:
      email: ops@example.com
      storage: /acme.json
      httpChallenge:
        entryPoint: web

providers:
  docker:
    exposedByDefault: false

api:
  dashboard: false
```

`docker-compose.staging.yml` (Traefik service + label overrides):
```yaml
services:
  traefik:
    image: traefik:v3
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./traefik/traefik.yml:/traefik.yml:ro
      - ./traefik/acme.json:/acme.json

  web:
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.web.rule=Host(`staging.example.com`)"
      - "traefik.http.routers.web.entrypoints=websecure"
      - "traefik.http.routers.web.tls.certresolver=letsencrypt"
      - "traefik.http.services.web.loadbalancer.server.port=8000"
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.staging
    env_file:
      - .env.staging

  celery-worker:
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.staging
    env_file:
      - .env.staging
```

## Django Settings — Staging

Create `backend/config/settings/staging.py`:
```python
from .base import *

DEBUG = False
ALLOWED_HOSTS = [env("STAGING_HOST")]

# Use production-grade whitenoise static file serving
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Security headers
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 3600
```

## `.env.staging` (template — never commit)

```env
SECRET_KEY=<generate with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())">
STAGING_HOST=staging.example.com
DATABASE_URL=postgres://app:password@db:5432/app
REDIS_URL=redis://redis:6379/0
AWS_ACCESS_KEY_ID=rustfs
AWS_SECRET_ACCESS_KEY=<strong-secret>
DATA_LAKE_BUCKET=django-prefect-datalake-staging
EMAIL_URL=smtp://user:pass@smtp.example.com:587
SITE_URL=https://staging.example.com
```

## Deploy

```bash
# Initial deploy
git clone <repo> /opt/app
cd /opt/app
touch traefik/acme.json && chmod 600 traefik/acme.json
docker compose -f docker-compose.yml -f docker-compose.staging.yml pull
docker compose -f docker-compose.yml -f docker-compose.staging.yml run --rm web python manage.py migrate
docker compose -f docker-compose.yml -f docker-compose.staging.yml run --rm web python manage.py collectstatic --noinput
docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d

# Subsequent deploys
git pull
docker compose -f docker-compose.yml -f docker-compose.staging.yml pull
docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.staging.yml exec web python manage.py migrate
```
