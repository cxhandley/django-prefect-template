# justfile - Task runner for django-doit-template
# Primary dev workflow: open in VS Code → "Reopen in Container" → run commands here

set dotenv-load

default:
    @just --list

# Complete project setup (run once inside devcontainer after postCreateCommand)
setup:
    @echo "Setting up project..."
    just install
    just docker-up
    @echo "Waiting for services to be ready..."
    sleep 10
    just setup-rustfs
    just migrate
    @echo "Setup complete!"

# Install all dependencies into the backend venv
install:
    @echo "Installing dependencies..."
    uv venv --python 3.13 backend/.venv
    uv pip install --python backend/.venv -e "backend[dev,test]"
    @echo "All dependencies installed"


# ============================================================================
# Django Management  (run inside devcontainer)
# ============================================================================

# Start Django dev server on 0.0.0.0:8000
dev:
    cd backend && uv run python manage.py runserver 0.0.0.0:8000

# Django shell
shell:
    cd backend && uv run python manage.py shell_plus

# Django db shell
dbshell:
    cd backend && uv run python manage.py dbshell

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
# Celery  (run inside devcontainer)
# ============================================================================

# Start Celery worker (connects to redis://redis:6379/0 inside devcontainer)
celery:
    cd backend && uv run celery -A config.celery worker -l info -Q default

# Start Flower monitoring UI at :5555
flower:
    cd backend && uv run celery -A config.celery flower --port=5555

# Open Flower UI in browser (host)
flower-ui:
    @echo "Opening Flower at http://localhost:5555"
    open http://localhost:5555 || xdg-open http://localhost:5555


# ============================================================================
# doit / Notebooks  (run inside devcontainer)
# ============================================================================

# List available doit pipeline tasks
doit-list:
    uv run --python backend/.venv doit -f dodo.py list

# Manually trigger the full pipeline (pass run_id and input_s3_path)
run-pipeline run_id input_s3_path:
    PIPELINE_PARAMS='{"run_id":"{{run_id}}","input_s3_path":"{{input_s3_path}}","bucket":"${DATA_LAKE_BUCKET}","aws_access_key_id":"${AWS_ACCESS_KEY_ID}","aws_secret_access_key":"${AWS_SECRET_ACCESS_KEY}","aws_s3_region":"${AWS_S3_REGION}","s3_endpoint":"${AWS_S3_ENDPOINT_URL}","notebook_output_dir":"data/notebook_outputs"}' \
    NOTEBOOKS_DIR=notebooks \
    NOTEBOOK_OUTPUT_DIR=data/notebook_outputs \
    uv run --python backend/.venv doit -f dodo.py run pipeline


# ============================================================================
# Testing
# ============================================================================

test:
    @echo "Running tests..."
    just test-backend
    @echo "All tests passed!"

test-backend:
    cd backend && uv run pytest apps/ -v

# Run tests with coverage report
test-cov:
    cd backend && uv run pytest apps/ --cov=apps --cov-report=html --cov-report=term-missing -v


# ============================================================================
# Docker Compose
# ============================================================================

# Start all services (db, redis, rustfs, devcontainer, celery-worker, flower)
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

# Open a Django shell inside the running devcontainer (from host)
docker-shell:
    docker compose exec devcontainer bash -c "cd /workspace/backend && uv run python manage.py shell_plus"

# Setup RustFS S3 buckets
setup-rustfs:
    @echo "Setting up RustFS buckets..."
    cd backend && uv run python manage.py setup_s3_buckets


# ============================================================================
# Code Quality
# ============================================================================

# Format code with ruff
format:
    uv run --python backend/.venv ruff format .

# Lint code
lint:
    uv run --python backend/.venv ruff check .
    uv run --python backend/.venv mypy backend/

# Fix linting issues automatically
fix:
    uv run --python backend/.venv ruff check --fix .
    uv run --python backend/.venv ruff format .

# Run all pre-commit hooks
pre-commit:
    uv run --python backend/.venv pre-commit run --all-files

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
