# django-doit-template

![Tests](badges/tests.svg) ![Coverage](badges/coverage.svg)

Django + doit + papermill + DuckDB data pipeline template. Upload a file, trigger a multi-step notebook pipeline asynchronously via Celery, and query the results with DuckDB — all inside a VS Code DevContainer.

Pipeline execution is pluggable: use the default **doit** backend (subprocess-based, no extra infrastructure) or switch to the **Prefect** backend for a full workflow orchestration UI. Individual pipeline steps can also run as **Mojo** compute jobs dispatched to a sidecar container.

## Architecture

```
┌────────────────────────────────────────────────┐
│  Browser (DaisyUI + HTMX)                      │
└──────────────────┬─────────────────────────────┘
                   │ HTTP
┌──────────────────▼─────────────────────────────┐
│  Django Application  (:8000)                   │
│  ┌──────────────────────────────────────────┐  │
│  │ Views (upload, status polling, results)  │  │
│  └──────────────────┬───────────────────────┘  │
│  ┌──────────────────▼───────────────────────┐  │
│  │ Celery task  →  enqueues to Redis        │  │
│  └──────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────┐  │
│  │ DuckDB Analytics Layer                   │  │
│  │ Queries S3 Parquet directly (no load)    │  │
│  └──────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
                   │ Redis task queue
┌──────────────────▼─────────────────────────────┐
│  Celery Worker                                 │
│  ┌──────────────────────────────────────────┐  │
│  │ PipelineBackend (doit or prefect)        │  │
│  └──────┬──────────────────────┬────────────┘  │
└─────────┼──────────────────────┼───────────────┘
          │ doit task graph      │ HTTP POST /execute
┌─────────▼────────────┐  ┌─────▼──────────────────┐
│ papermill notebooks  │  │ mojo-compute  (:8080)   │
│                      │  │ Runs .mojo scripts via  │
│ 01_ingest            │  │ Mojo CLI (Pixi-managed) │
│ 02_validate          │  └─────────────────────────┘
│ 03_transform         │
│ 04_aggregate         │
└──────────┬───────────┘
           │ S3 API
┌──────────▼─────────────────────────────────────┐
│  RustFS  (S3-compatible, local dev)            │
│  raw/uploads/…      → input files             │
│  processed/flows/…  → intermediate Parquet    │
│  processed/flows/…/output.parquet → results   │
└────────────────────────────────────────────────┘
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Web framework | Django 5.2 + DaisyUI + HTMX |
| Task queue | Celery 5.5 + Redis |
| Pipeline orchestration | doit 0.36 (default) or Prefect |
| Notebook execution | papermill 2.6 |
| Data processing | Polars 1.38 (lazy, columnar) |
| Analytics queries | DuckDB 1.4 (queries S3 Parquet directly) |
| Mojo compute | Mojo via Pixi (sidecar HTTP service) |
| Object storage | RustFS (S3-compatible, local) / AWS S3 (prod) |
| Database | PostgreSQL 18 (metadata only) |
| Observability | OpenTelemetry + Jaeger |
| Dev environment | VS Code DevContainers |

## Project Structure

```
django-doit-template/
├── .devcontainer/
│   ├── Dockerfile              # Dev environment image
│   ├── devcontainer.json       # VS Code DevContainer config
│   └── post-create.sh          # postCreateCommand: uv sync, pre-commit install
├── backend/                    # Django application
│   ├── Dockerfile
│   ├── config/
│   │   ├── settings/
│   │   │   ├── base.py
│   │   │   ├── development.py
│   │   │   └── test.py
│   │   ├── celery.py           # Celery app init
│   │   └── urls.py
│   └── apps/
│       ├── core/               # Home page
│       ├── accounts/           # Auth & profiles
│       ├── flags/              # Runtime feature flags
│       ├── training/           # Model training runs & datasets
│       └── flows/
│           ├── models.py           # FlowExecution, ExecutionStep
│           ├── views.py            # Upload, status, results endpoints
│           ├── tasks.py            # Celery task (run_pipeline_task)
│           ├── runner.py           # PipelineRunner + step definitions
│           ├── backends/
│           │   ├── base.py         # PipelineBackend ABC
│           │   ├── doit.py         # DoitBackend (default)
│           │   └── prefect.py      # PrefectBackend (optional)
│           └── services/
│               └── datalake.py     # DuckDB analytics service
├── mojo-compute/
│   ├── Dockerfile              # Ubuntu + Pixi + Mojo install
│   └── server.py               # Stdlib HTTP server wrapping mojo CLI
├── mojo/
│   └── compute/
│       └── normalise.mojo      # Example Mojo compute script
├── notebooks/
│   └── steps/
│       ├── 01_ingest.ipynb     # Read raw file → S3 staging Parquet
│       ├── 02_validate.ipynb   # Clean + validate
│       ├── 03_transform.ipynb  # Business transformations (Polars)
│       └── 04_aggregate.ipynb  # Group-by aggregation → output.parquet
├── dodo.py                     # doit task definitions (pipeline DAG)
├── docker-compose.yml          # Default (doit backend)
├── docker-compose.prefect.yml  # Prefect backend overlay
├── justfile
└── .env.example
```

## Getting Started

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [VS Code](https://code.visualstudio.com/) + [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)

### 1. Clone and open in devcontainer

```bash
git clone https://github.com/cxhandley/django-doit-template.git
cd django-doit-template
cp .env.example .env
code .
```

VS Code will prompt **"Reopen in Container"** — click it. Docker Compose starts all services and `post-create.sh` runs automatically:

```bash
uv sync --group dev
pre-commit install
nbstripout --install --attributes .gitattributes
```

### 2. Run migrations and set up storage

```bash
just migrate
just setup-rustfs
```

The web server and Celery worker start automatically as Docker Compose services — no separate terminal processes needed.

### 3. Access the app

| Service | URL |
|---------|-----|
| Django | http://localhost:8000 |
| Flower | http://localhost:5555 |
| Mailhog | http://localhost:8025 |
| Jaeger (traces) | http://localhost:16686 |
| RustFS (S3) | http://localhost:9000 |

## Running the Pipeline

Upload a CSV file via the Django UI → a `FlowExecution` record is created with `status=RUNNING` → Celery dispatches `run_pipeline_task` → the configured `PipelineBackend` runs the steps → `FlowExecution` updated to `status=COMPLETED`.

### Pipeline steps

| Step | Notebook | What it does |
|------|----------|-------------|
| 1 | `01_ingest.ipynb` | Reads raw CSV/Parquet from S3, writes `01_raw.parquet` |
| 2 | `02_validate.ipynb` | Drops nulls, deduplicates, filters invalid dates/amounts |
| 3 | `03_transform.ipynb` | Parses dates, computes totals/tax, categorises by amount |
| 4 | `04_aggregate.ipynb` | Groups by year-month + category, writes `output.parquet` |

Each notebook receives parameters (S3 paths, run_id) via papermill. Intermediate Parquet files are written to `s3://<bucket>/processed/flows/data-processing/<run_id>/`.

### Trigger from CLI

```bash
just run-pipeline <run_id> s3://bucket/raw/uploads/1/myfile.csv
```

### Inspect available doit tasks

```bash
just doit-list
```

## Pipeline Backends

The pipeline execution engine is selected via `PIPELINE_BACKEND` in your `.env`:

| Backend | Value | Description |
|---------|-------|-------------|
| doit (default) | `doit` | Runs notebooks via doit subprocess. No extra infrastructure. |
| Prefect | `prefect` | Submits flows to a Prefect server. Provides a full workflow UI at `:4200`. |

To run with the Prefect backend:

```bash
# Start services including the Prefect server and worker
docker compose -f docker-compose.yml -f docker-compose.prefect.yml up -d
```

Set `PIPELINE_BACKEND=prefect` in `.env` and configure the Prefect-specific variables (see [Environment Variables](#environment-variables) below).

## Mojo Compute

Pipeline steps with `step_type=MOJO` are dispatched via HTTP to the `mojo-compute` sidecar container rather than run as notebooks. The container installs Mojo via Pixi and exposes a single endpoint:

```
POST http://mojo-compute:8080/execute
Body: {"run_id": "...", "script": "compute/<name>.mojo",
       "s3_input": "s3://...", "s3_output": "s3://..."}
```

Mojo scripts live in `mojo/compute/` (mounted read-only at `/mojo/compute` inside the container). AWS credentials flow through environment variables — they are never passed as parameters.

## Services

| Service | URL | Notes |
|---------|-----|-------|
| Django | http://localhost:8000 | Main web app |
| Flower | http://localhost:5555 | Celery task monitoring |
| Mailhog | http://localhost:8025 | Dev email inbox (SMTP sink) |
| Jaeger | http://localhost:16686 | Distributed trace UI |
| RustFS (S3) | http://localhost:9000 | Local S3-compatible storage |
| mojo-compute | http://localhost:8080 | Mojo script execution API |
| PostgreSQL | localhost:5432 | Metadata DB |
| Redis | localhost:6379 | Celery broker + cache |

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DJANGO_SECRET_KEY` | Django secret key | — |
| `DATABASE_URL` | PostgreSQL connection | `postgresql://django:…@localhost:5432/django_prefect` |
| `REDIS_URL` | Redis connection | `redis://localhost:6379/0` |
| `CELERY_BROKER_URL` | Celery broker | `redis://localhost:6379/0` |
| `CELERY_RESULT_BACKEND` | Celery result store | `redis://localhost:6379/0` |
| `AWS_ACCESS_KEY_ID` | S3 / RustFS key | `rustfs` |
| `AWS_SECRET_ACCESS_KEY` | S3 / RustFS secret | `rustfs_secret` |
| `AWS_S3_REGION` | S3 region | `us-east-1` |
| `DATA_LAKE_BUCKET` | S3 bucket name | `django-prefect-datalake-dev` |
| `AWS_S3_ENDPOINT_URL` | S3 endpoint (RustFS) | `http://localhost:9000` |
| `DUCKDB_THREADS` | DuckDB parallel threads | `4` |
| `DUCKDB_MEMORY_LIMIT` | DuckDB memory cap | `4GB` |
| `NOTEBOOKS_DIR` | Path to notebook steps | `notebooks` |
| `NOTEBOOK_OUTPUT_DIR` | Executed notebook outputs | `data/notebook_outputs` |
| `PIPELINE_BACKEND` | Execution backend (`doit` or `prefect`) | `doit` |
| `MOJO_COMPUTE_URL` | mojo-compute service URL | `http://mojo-compute:8080` |
| `PREFECT_API_URL` | Prefect server API (Prefect backend only) | `http://prefect-server:4200/api` |
| `PREFECT_UI_URL` | Prefect UI base URL (Prefect backend only) | `http://localhost:4200` |
| `PREFECT_INTERNAL_SECRET` | Shared secret for internal step-status callbacks | — |
| `DJANGO_INTERNAL_URL` | Django URL reachable from Prefect worker | `http://web:8000` |

## Development Workflow

```bash
just test          # Run all tests (pytest)
just test-cov      # Tests with coverage report + badge regeneration
just fix           # Auto-fix lint issues (ruff check --fix + ruff format)
just lint          # Ruff + mypy (check only, no auto-fix)
just pre-commit    # Run all pre-commit hooks against all files
just migrate       # Apply DB migrations
just makemigrations [app]  # Create new migrations
just shell         # Django shell_plus
just docker-up     # Start all services
just docker-down   # Stop all services
just docker-logs [service]  # Tail service logs
just status        # Show container statuses
```

## Pre-commit Hooks

| Hook | Purpose |
|------|---------|
| `nbstripout` | Strips notebook outputs before commit (keeps diffs small) |
| `ruff` | Python lint with auto-fix |
| `ruff-format` | Python formatting |
| `djlint-reformat-django` | Auto-reformat Django HTML templates |
| `djlint-django` | Lint Django HTML templates |
| Standard hooks | Trailing whitespace, YAML/JSON/TOML checks, large file guard, merge conflict markers |

Hooks are installed automatically by `post-create.sh`. To install manually:

```bash
pre-commit install
```
