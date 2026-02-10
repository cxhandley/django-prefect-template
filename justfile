# justfile - Task runner for django-prefect-kit

set dotenv-load

default:
    @just --list

# Complete project setup
setup:
    @echo "🚀 Setting up django-prefect-kit..."
    just install
    just docker-up
    @echo "Waiting for services to be ready..."
    sleep 10
    just setup-rustyfs
    just migrate
    @echo "✅ Setup complete!"

# Install all dependencies
install:
    @echo "📦 Installing dependencies..."
    uv venv --python 3.13
    uv pip install -e "backend[dev,test]"
    uv pip install -e "gateway[dev,test]"
    uv pip install -e "worker[dev,test]"

# Start Django dev server
dev:
    cd backend && uv run python manage.py runserver

# Start FastAPI gateway
dev-gateway:
    cd gateway && uv run uvicorn main:app --reload --port 8001

# Django shell
shell:
    cd backend && uv run python manage.py shell_plus

# Run migrations
migrate:
    cd backend && uv run python manage.py migrate

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

# Run all tests
test:
    uv run pytest

# Run tests with coverage
test-cov:
    uv run pytest --cov --cov-report=html

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

# Setup RustyFS buckets
setup-rustyfs:
    @echo "🗄️  Setting up RustyFS buckets..."
    cd backend && uv run python manage.py setup_s3_buckets

# Format code
format:
    uv run ruff format .

# Lint code
lint:
    uv run ruff check .
    uv run mypy backend/ gateway/ worker/

# Fix linting issues
fix:
    uv run ruff check --fix .
    uv run ruff format .

# Clean cache files
clean:
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete
    find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
    rm -rf htmlcov/ .coverage

# Show status
status:
    @echo "📊 Project Status"
    @echo "================="
    @python --version
    @uv --version
    @just --version
    @echo ""
    @docker compose ps