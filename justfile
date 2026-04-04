# justfile - Task runner for django-doit-template
# Primary dev workflow: open in VS Code → "Reopen in Container" → run commands here
# All commands assume they run inside the devcontainer where Python is system-installed.

set dotenv-load

default:
    @just --list


# ============================================================================
# Project Setup  (run once inside devcontainer after postCreateCommand)
# ============================================================================

# Complete first-time setup: start services, create S3 buckets, run migrations
setup:
    @echo "Setting up project..."
    just frontend-build
    just setup-rustfs
    just migrate
    @echo "Setup complete!"


# ============================================================================
# Frontend Build  (run inside devcontainer — Node.js 20 is pre-installed)
# ============================================================================

# Build Tailwind CSS + vendor HTMX (one-shot)
frontend-build:
    cd backend/frontend && npm install && npm run build

# Watch Tailwind CSS for live rebuild during development
frontend-watch:
    cd backend/frontend && npm run watch


# ============================================================================
# Django Management  (run inside devcontainer)
# ============================================================================

# Django shell
shell:
    python backend/manage.py shell_plus

# Django db shell
dbshell:
    python backend/manage.py dbshell

# Run migrations
migrate:
    python backend/manage.py migrate

# Collect static files
collectstatic:
    python backend/manage.py collectstatic --noinput

# Create a new Django app inside backend/apps/
startapp name:
    cd backend/apps && python manage.py startapp {{name}}

# Create migrations
makemigrations app="":
    @if [ -z "{{app}}" ]; then \
        python backend/manage.py makemigrations; \
    else \
        python backend/manage.py makemigrations {{app}}; \
    fi

# Create superuser
createsuperuser:
    python backend/manage.py createsuperuser


# ============================================================================
# doit / Notebooks  (run inside devcontainer)
# ============================================================================

# List available doit pipeline tasks
doit-list:
    doit -f dodo.py list

# Manually trigger the full pipeline (pass run_id and input_s3_path)
# AWS credentials are NOT passed in PIPELINE_PARAMS — notebooks read them from
# the process environment via the standard AWS credential chain.
run-pipeline run_id input_s3_path:
    PIPELINE_PARAMS='{"run_id":"{{run_id}}","input_s3_path":"{{input_s3_path}}","bucket":"${DATA_LAKE_BUCKET}","aws_s3_region":"${AWS_S3_REGION}","s3_endpoint":"${AWS_S3_ENDPOINT_URL}","notebook_output_dir":"data/notebook_outputs"}' \
    NOTEBOOKS_DIR=notebooks \
    NOTEBOOK_OUTPUT_DIR=data/notebook_outputs \
    doit -f dodo.py run pipeline


# ============================================================================
# Testing
# ============================================================================

test:
    @echo "Running tests..."
    pytest backend/apps/ -v
    @echo "All tests passed!"

# Run tests with coverage report and regenerate badges/tests.svg + badges/coverage.svg
test-cov:
    cd backend && pytest apps/ \
        --cov=apps \
        --cov-report=html:../htmlcov \
        --cov-report=term-missing \
        --cov-report=xml:../coverage.xml \
        --junitxml=../junit.xml \
        -v
    genbadge tests -i junit.xml -o badges/tests.svg -n Tests
    genbadge coverage -i coverage.xml -o badges/coverage.svg -n Coverage


# ============================================================================
# Docker Compose
# ============================================================================

# Start all services (db, redis, rustfs, web, devcontainer, celery-worker, flower)
docker-up:
    docker compose up -d

# Stop all services
docker-down:
    docker compose down

# View logs for all or a specific service
docker-logs service="":
    @if [ -z "{{service}}" ]; then \
        docker compose logs -f; \
    else \
        docker compose logs -f {{service}}; \
    fi

# Open a Django shell inside the running devcontainer
docker-shell:
    docker compose exec devcontainer python backend/manage.py shell_plus

# Setup RustFS S3 buckets
setup-rustfs:
    @echo "Setting up RustFS buckets..."
    python backend/manage.py setup_s3_buckets


# ============================================================================
# Code Quality
# ============================================================================

# Format code with ruff
format:
    ruff format .

# Lint code
lint:
    ruff check .
    mypy backend/

# Fix linting issues automatically
fix:
    ruff check --fix .
    ruff format .

# Run all pre-commit hooks
pre-commit:
    pre-commit run --all-files

# Clean cache / build artefacts
clean:
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete
    find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
    find . -name ".doit.db" -delete 2>/dev/null || true
    rm -rf htmlcov/ .coverage


# ============================================================================
# Status & Utilities
# ============================================================================

status:
    @echo "Project Status"
    @echo "=============="
    @uv --version
    @just --version
    @echo ""
    @docker compose ps

reset-db:
    @echo "This will delete all data. Are you sure? (y/N)"
    @read -p "" confirm && [ "$$confirm" = "y" ] || exit 1
    docker compose down -v
    docker compose up -d db
    sleep 3
    just migrate

tree:
    tree -I '__pycache__|*.pyc|staticfiles|__init__.py|.doit.db|.venv'


# ============================================================================
# Production  (delegates to deploy/justfile — requires op CLI, terraform, SSH)
# ============================================================================

# Initialise Terraform remote state (run once)
prod-tf-init:
    just -f deploy/justfile tf-init

# Preview infrastructure changes
prod-tf-plan:
    just -f deploy/justfile tf-plan

# Apply infrastructure changes
prod-tf-apply:
    just -f deploy/justfile tf-apply

# Show Terraform outputs (host IP, bucket, etc.)
prod-tf-outputs:
    just -f deploy/justfile tf-outputs

# First-time bootstrap: push config, init Swarm, deploy stack
prod-bootstrap:
    just -f deploy/justfile bootstrap

# Deploy a specific image tag to production
prod-deploy tag:
    just -f deploy/justfile deploy {{tag}}

# Roll back web + worker to previous image
prod-rollback:
    just -f deploy/justfile rollback

# Run Django migrations
prod-migrate tag="latest":
    just -f deploy/justfile migrate {{tag}}

# Open SSH session on production host
prod-ssh:
    just -f deploy/justfile ssh

# Show Swarm service status
prod-status:
    just -f deploy/justfile status

# Tail logs for a service (default: web)
prod-logs service="web":
    just -f deploy/justfile logs {{service}}

# Trigger a manual PostgreSQL backup
prod-backup:
    just -f deploy/justfile backup
