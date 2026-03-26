# justfile - Task runner for django-doit-template

set dotenv-load

default:
    @just --list

# Complete project setup
setup:
    @echo "Setting up project..."
    just install
    just docker-up
    @echo "Waiting for services to be ready..."
    sleep 10
    just setup-rustfs
    just migrate
    @echo "Setup complete!"

# Install all dependencies
install:
    @echo "Installing dependencies..."
    uv venv --python 3.13
    uv pip install -e "backend[dev,test]"
    @echo "All dependencies installed"

# Quick check to verify dev dependencies
check-dev:
    @uv pip list | grep -E "(debug-toolbar|django-extensions|ipython)" || echo "Dev dependencies missing - run 'just install'"


# ============================================================================
# Django Management
# ============================================================================

# Start Django dev server
dev:
    cd backend && uv run --extra dev python manage.py runserver

# Django shell
shell:
    cd backend && uv run --extra dev python manage.py shell_plus

# Django db shell
dbshell:
    cd backend && uv run --extra dev python manage.py dbshell

# Run migrations
migrate:
    cd backend && uv run python manage.py migrate

# Collect static files
collectstatic:
    cd backend && uv run python manage.py collectstatic --noinput

# Create Django app
startapp name:
    cd backend/apps && uv run python ../manage.py startapp {{name}}

# Create migrations
makemigrations app="":
    @if [ -z "{{app}}" ]; then \
        cd backend && uv run python manage.py makemigrations; \
    else \
        cd backend && uv run python manage.py makemigrations {{app}}; \
    fi

# Create superuser
createsuperuser:
    cd backend && uv run python manage.py createsuperuser


# ============================================================================
# Celery
# ============================================================================

# Start Celery worker
celery:
    cd backend && uv run celery -A config.celery worker -l info -Q default

# Start Flower (Celery monitoring UI)
flower:
    cd backend && uv run celery -A config.celery flower --port=5555

# Open Flower UI
flower-ui:
    @echo "Opening Flower at http://localhost:5555"
    open http://localhost:5555 || xdg-open http://localhost:5555


# ============================================================================
# doit / Notebooks
# ============================================================================

# List available doit pipeline tasks
doit-list:
    uv run doit -f dodo.py list

# Run the full doit pipeline manually (pass RUN_ID and INPUT_S3_PATH)
run-pipeline run_id input_s3_path:
    PIPELINE_PARAMS='{"run_id":"{{run_id}}","input_s3_path":"{{input_s3_path}}","bucket":"${DATA_LAKE_BUCKET}","aws_access_key_id":"${AWS_ACCESS_KEY_ID}","aws_secret_access_key":"${AWS_SECRET_ACCESS_KEY}","aws_s3_region":"${AWS_S3_REGION}","s3_endpoint":"${AWS_S3_ENDPOINT_URL}","notebook_output_dir":"data/notebook_outputs"}' \
    NOTEBOOKS_DIR=notebooks \
    NOTEBOOK_OUTPUT_DIR=data/notebook_outputs \
    uv run doit -f dodo.py run pipeline


# ============================================================================
# Testing
# ============================================================================

test:
    @echo "Running tests..."
    just test-backend
    @echo "All tests passed!"

test-backend:
    cd backend && uv run --extra test pytest apps/ -v

# Run tests with coverage
test-cov:
    cd backend && uv run --extra test pytest apps/ --cov=apps --cov-report=html --cov-report=term-missing -v


# ============================================================================
# Docker
# ============================================================================

# Start Docker services
docker-up:
    docker compose up -d

# Stop Docker services
docker-down:
    docker compose down

# View Docker logs
docker-logs service="":
    @if [ -z "{{service}}" ]; then \
        docker compose logs -f; \
    else \
        docker compose logs -f {{service}}; \
    fi

# Setup RustFS buckets
setup-rustfs:
    @echo "Setting up RustFS buckets..."
    cd backend && uv run python manage.py setup_s3_buckets


# ============================================================================
# Code Quality
# ============================================================================

# Format code
format:
    uv run ruff format .

# Lint code
lint:
    uv run ruff check .
    uv run mypy backend/

# Fix linting issues
fix:
    uv run ruff check --fix .
    uv run ruff format .

# Run pre-commit on all files
pre-commit:
    uv run pre-commit run --all-files

# Clean cache files
clean:
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete
    find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name ".doit.db" -exec rm -rf {} + 2>/dev/null || true
    rm -rf htmlcov/ .coverage


# ============================================================================
# Status & Info
# ============================================================================

# Show project status
status:
    @echo "Project Status"
    @echo "=============="
    @python --version
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
    tree -I '__pycache__|*.pyc|staticfiles|__init__.py|.doit.db'
