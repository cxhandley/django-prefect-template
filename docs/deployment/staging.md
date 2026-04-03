# Staging Environment

Single EC2 instance running all services via Docker Compose, with Traefik handling SSL
termination and automatic Let's Encrypt certificates.

## Architecture

```
Internet → Traefik (port 80/443) → Django web  (port 8000, internal)
                                 → Flower       (port 5555, internal — SSH tunnel to access)
                          Redis  ← Celery worker
                          PostgreSQL (container, volume-backed)
                          RustFS     (S3-compatible, internal only)
```

All services run via `docker-compose.yml` + `docker-compose.staging.yml` override.
Traefik routes by hostname Docker label and terminates TLS.

---

## 1. EC2 Provisioning

**Recommended instance:** `t3.medium` (2 vCPU, 4 GB RAM).

### Security Group rules

| Type | Port | Source |
|------|------|--------|
| SSH | 22 | Your IP |
| HTTP | 80 | 0.0.0.0/0 (Traefik → redirect to HTTPS) |
| HTTPS | 443 | 0.0.0.0/0 |

All outbound traffic allowed.

### Bootstrap the instance

```bash
# 1. Install Docker + Compose plugin
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker ubuntu
newgrp docker          # or log out and back in

# 2. Create app directory
sudo mkdir -p /opt/app
sudo chown ubuntu:ubuntu /opt/app
cd /opt/app

# 3. Clone the repository
git clone <repo-url> .
```

---

## 2. Directory layout on the server

```
/opt/app/
├── docker-compose.yml
├── docker-compose.staging.yml
├── .env.staging                  # secrets — never commit
├── traefik/
│   ├── traefik.yml               # checked into git
│   └── acme.json                 # created below — chmod 600
└── data/                         # persistent volumes (created by Docker)
    ├── postgres/
    └── rustfs/
```

---

## 3. Traefik certificate store

Let's Encrypt stores issued certificates in `traefik/acme.json`.
It **must** exist and be `chmod 600` before first start or Traefik will refuse to start.

```bash
touch /opt/app/traefik/acme.json
chmod 600 /opt/app/traefik/acme.json
```

---

## 4. Environment file

Create `/opt/app/.env.staging` — this file is never committed.

```env
# Django
SECRET_KEY=<generate: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())">
DJANGO_ALLOWED_HOSTS=staging.example.com
STAGING_HOST=staging.example.com
SITE_URL=https://staging.example.com

# Database
DATABASE_URL=postgresql://app:StrongPassword@db:5432/app

# Redis
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# S3-compatible (RustFS running in Docker)
AWS_ACCESS_KEY_ID=rustfs
AWS_SECRET_ACCESS_KEY=<strong-random-secret>
AWS_S3_ENDPOINT_URL=http://rustfs:9000
DATA_LAKE_BUCKET=django-doit-staging

# Email (use real SMTP or keep mailhog out of staging)
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=noreply@example.com
EMAIL_HOST_PASSWORD=<smtp-password>
DEFAULT_FROM_EMAIL=noreply@example.com
```

---

## 5. Initial deploy

Run these commands **once** when setting up the environment for the first time.

```bash
cd /opt/app

# Pull images / build app image
docker compose -f docker-compose.yml -f docker-compose.staging.yml build
docker compose -f docker-compose.yml -f docker-compose.staging.yml pull

# Run database migrations
docker compose -f docker-compose.yml -f docker-compose.staging.yml \
    run --rm web python manage.py migrate

# Collect static files (WhiteNoise serves from staticfiles/)
docker compose -f docker-compose.yml -f docker-compose.staging.yml \
    run --rm -e DJANGO_SETTINGS_MODULE=config.settings.staging \
    web python manage.py collectstatic --noinput

# Pre-compress assets with django-compressor (generates CACHE/manifest.json)
docker compose -f docker-compose.yml -f docker-compose.staging.yml \
    run --rm -e DJANGO_SETTINGS_MODULE=config.settings.staging \
    web python manage.py compress --force

# Create a superuser
docker compose -f docker-compose.yml -f docker-compose.staging.yml \
    run --rm web python manage.py createsuperuser

# Create the S3 bucket in RustFS
docker compose -f docker-compose.yml -f docker-compose.staging.yml \
    run --rm web python manage.py setup_s3_buckets

# Start all services
docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d
```

Verify Traefik issued a certificate:

```bash
docker compose -f docker-compose.yml -f docker-compose.staging.yml logs traefik | grep -i "cert\|acme"
curl -I https://staging.example.com   # expect HTTP/2 200
```

---

## 6. Subsequent deploys

```bash
cd /opt/app

# Pull latest code
git pull

# Rebuild the app image (includes npm build + collectstatic via Dockerfile)
docker compose -f docker-compose.yml -f docker-compose.staging.yml build web celery-worker

# Apply any new migrations
docker compose -f docker-compose.yml -f docker-compose.staging.yml \
    run --rm web python manage.py migrate

# Re-collect and re-compress static files if templates/CSS changed
docker compose -f docker-compose.yml -f docker-compose.staging.yml \
    run --rm -e DJANGO_SETTINGS_MODULE=config.settings.staging \
    web python manage.py collectstatic --noinput
docker compose -f docker-compose.yml -f docker-compose.staging.yml \
    run --rm -e DJANGO_SETTINGS_MODULE=config.settings.staging \
    web python manage.py compress --force

# Rolling restart
docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d
```

---

## 7. Accessing Flower (Celery monitor)

Flower is not exposed via Traefik in staging. Use an SSH tunnel:

```bash
ssh -L 5555:localhost:5555 ubuntu@staging.example.com
# then open http://localhost:5555 in your browser
```

---

## 8. Useful maintenance commands

```bash
# Tail all logs
docker compose -f docker-compose.yml -f docker-compose.staging.yml logs -f

# Django shell
docker compose -f docker-compose.yml -f docker-compose.staging.yml \
    exec web python manage.py shell

# Check certificate expiry
echo | openssl s_client -connect staging.example.com:443 2>/dev/null \
    | openssl x509 -noout -dates
```
