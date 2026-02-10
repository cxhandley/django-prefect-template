# justfile - Task runner for django-prefect-template

set dotenv-load

default:
    @just --list

# Complete project setup
setup:
    @echo "🚀 Setting up django-prefect-template..."
    just install
    just docker-up
    @echo "Waiting for services to be ready..."
    sleep 10
    just setup-rustfs
    just migrate
    @echo "✅ Setup complete!"

# Install all dependencies with dev extras
install:
    @echo "📦 Installing dependencies..."
    uv venv --python 3.13
    @echo "Installing backend (with dev and test)..."
    uv pip install -e "backend[dev,test]"
    @echo "Installing gateway (with dev and test)..."
    uv pip install -e "gateway[dev,test]"
    @echo "Installing worker (with test)..."
    uv pip install -e "worker[test]"
    @echo "✅ All dependencies installed"

# Quick check to verify dev dependencies
check-dev:
    @echo "Checking dev dependencies..."
    @uv pip list | grep -E "(debug-toolbar|django-extensions|ipython)" || echo "❌ Dev dependencies missing - run 'just install'"


# Start Django dev server
dev:
    cd backend && uv run --extra dev python manage.py runserver

# Start FastAPI gateway
dev-gateway:
    cd gateway && uv run uvicorn main:app --reload --port 8001

# Django shell
shell:
    cd backend && uv run --extra dev python manage.py shell_plus

    # Run migrations
dbshell:
    cd backend && uv run --extra dev python manage.py dbshell

# Run migrations
migrate:
    cd backend && uv run --extra dev python manage.py migrate

# Create migrations
makemigrations app="":
    @if [ -z "{{app}}" ]; then \
        cd backend && uv run --extra dev python manage.py makemigrations; \
    else \
        cd backend && uv run --extra dev python manage.py makemigrations {{app}}; \
    fi

# Create superuser
createsuperuser:
    cd backend && uv run --extra dev python manage.py createsuperuser

test:
    @echo "🧪 Running all tests..."
    @just test-backend
    @just test-gateway
    @just test-worker
    @echo "✅ All tests passed!"

# Each package runs from its own directory
test-backend:
    cd backend && uv run --extra test pytest apps/ -v

test-gateway:
    cd gateway && uv run --extra test pytest tests/ -v

test-worker:
    cd worker && uv run --extra test pytest tests/ -v

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

# Setup RustS buckets
setup-rustfs:
    @echo "🗄️  Setting up RustFS buckets..."
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


reset-db:
    @echo "⚠️  This will delete all data. Are you sure? (y/N)"
    @read -p "" confirm && [ "$$confirm" = "y" ] || exit 1
    docker-compose down -v
    docker-compose up -d db
    sleep 3
    just migrate

# ============================================================================
# Prefect
# ============================================================================

# Deploy Prefect flows
deploy-flows:
    cd gateway && uv run python -m scripts.deploy_flows

# Start Prefect worker
worker:
    cd worker && uv run prefect worker start --pool default-pool

# Open Prefect UI
prefect-ui:
    @echo "Opening Prefect UI at http://localhost:4200"
    open http://localhost:4200 || xdg-open http://localhost:4200

# ============================================================================
# Django Management
# ============================================================================

# Collect static files
collectstatic:
    cd backend && uv run --extra dev python manage.py collectstatic --noinput

# Create Django app
startapp name:
    cd backend/apps && uv run --extra dev python ../manage.py startapp {{name}}

# ============================================================================
# Deployment
# ============================================================================

# Deploy to staging
deploy-staging:
    @echo "🚀 Deploying to staging..."
    cd terraform && terraform workspace select staging
    terraform apply -var-file=staging.tfvars -auto-approve

# Deploy to production
deploy-prod:
    @echo "🚀 Deploying to production..."
    @echo "⚠️  Are you sure? This will deploy to PRODUCTION. (yes/N)"
    @read -p "" confirm && [ "$$confirm" = "yes" ] || exit 1
    cd terraform && terraform workspace select production
    terraform apply -var-file=production.tfvars

# Build Docker images for production
build-prod:
    docker build -t django-prefect-template/web:latest ./backend
    docker build -t django-prefect-template/gateway:latest ./gateway
    docker build -t django-prefect-template/worker:latest ./worker

# Generate OpenAPI spec
openapi:
    cd gateway && uv run python -c "from main import app; import json; print(json.dumps(app.openapi(), indent=2))" > docs/api-spec.json
