# django-doit-template

Django + doit + papermill + DuckDB data pipeline template. Upload a file, trigger a multi-step notebook pipeline asynchronously via Celery, and query the results with DuckDB — all inside a VS Code DevContainer.

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
│  │ PipelineRunner → subprocess: doit        │  │
│  └──────────────────┬───────────────────────┘  │
└──────────────────────┼─────────────────────────┘
                       │ doit task graph
┌──────────────────────▼─────────────────────────┐
│  papermill  (parameterised notebooks)          │
│                                                │
│  01_ingest → 02_validate → 03_transform        │
│                                 ↓              │
│                          04_aggregate          │
└──────────────────────┬─────────────────────────┘
                       │ S3 API
┌──────────────────────▼─────────────────────────┐
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
| Pipeline orchestration | doit 0.36 |
| Notebook execution | papermill 2.6 |
| Data processing | Polars 1.38 (lazy, columnar) |
| Analytics queries | DuckDB 1.4 (queries S3 Parquet directly) |
| Object storage | RustFS (S3-compatible, local) / AWS S3 (prod) |
| Database | PostgreSQL 18 (metadata only) |
| Dev environment | VS Code DevContainers |

## Project Structure

```
django-doit-template/
├── .devcontainer/
│   ├── Dockerfile          # Dev environment image
│   └── devcontainer.json   # VS Code DevContainer config
├── backend/                # Django application
│   ├── Dockerfile
│   ├── config/
│   │   ├── settings/
│   │   │   ├── base.py
│   │   │   ├── development.py
│   │   │   └── test.py
│   │   ├── celery.py       # Celery app init
│   │   └── urls.py
│   └── apps/
│       ├── core/           # Home page
│       ├── accounts/       # Auth & profiles
│       └── flows/
│           ├── models.py       # FlowExecution (metadata + S3 paths)
│           ├── views.py        # Upload, status, results endpoints
│           ├── tasks.py        # Celery task (run_pipeline_task)
│           ├── runner.py       # PipelineRunner (invokes doit)
│           └── services/
│               └── datalake.py # DuckDB analytics service
├── notebooks/
│   └── steps/
│       ├── 01_ingest.ipynb     # Read raw file → S3 staging Parquet
│       ├── 02_validate.ipynb   # Clean + validate
│       ├── 03_transform.ipynb  # Business transformations (Polars)
│       └── 04_aggregate.ipynb  # Group-by aggregation → output.parquet
├── dodo.py                 # doit task definitions (pipeline DAG)
├── docker-compose.yml
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
code .
```

VS Code will prompt **"Reopen in Container"** — click it. Docker Compose starts all services and the `postCreateCommand` runs automatically:

```bash
just install && just migrate && just setup-rustfs
```

### 2. Start the development server

Open two terminals inside the devcontainer:

```bash
# Terminal 1 — Django
just dev
# → http://localhost:8000

# Terminal 2 — Celery worker
just celery
```

The Flower monitoring UI is also available at **http://localhost:5555** (started as a Docker service automatically).

### 3. Env file

```bash
cp .env.example .env
```

The `.env` file uses `localhost` values which work for running outside Docker. Inside Docker / the devcontainer, `docker-compose.yml` overrides the host-specific URLs (`DATABASE_URL`, `REDIS_URL`, etc.) with Docker service names automatically.

## Running the Pipeline

Upload a CSV file via the Django UI → a `FlowExecution` record is created with `status=RUNNING` → Celery dispatches `run_pipeline_task` → `PipelineRunner` calls `doit pipeline` → doit runs the four notebook steps in order → `FlowExecution` updated to `status=COMPLETED`.

### Pipeline steps

| Step | Notebook | What it does |
|------|----------|-------------|
| 1 | `01_ingest.ipynb` | Reads raw CSV/Parquet from S3, writes `01_raw.parquet` |
| 2 | `02_validate.ipynb` | Drops nulls, deduplicates, filters invalid dates/amounts |
| 3 | `03_transform.ipynb` | Parses dates, computes totals/tax, categorises by amount |
| 4 | `04_aggregate.ipynb` | Groups by year-month + category, writes `output.parquet` |

Each notebook receives parameters (S3 paths, credentials, run_id) via papermill. Intermediate Parquet files are written to `s3://<bucket>/processed/flows/data-processing/<run_id>/`.

### Trigger from CLI

```bash
just run-pipeline <run_id> s3://bucket/raw/uploads/1/myfile.csv
```

### Inspect available doit tasks

```bash
just doit-list
```

## Services

| Service | URL | Notes |
|---------|-----|-------|
| Django | http://localhost:8000 | Main web app |
| Flower | http://localhost:5555 | Celery task monitoring |
| RustFS (S3) | http://localhost:9000 | Local S3-compatible storage |
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

## Development Workflow

```bash
just test          # Run all tests (pytest)
just lint          # Ruff + mypy
just fix           # Auto-fix lint issues
just pre-commit    # Run all pre-commit hooks (includes nbstripout, djlint, rustywind)
just migrate       # Apply DB migrations
just makemigrations # Create new migrations
just shell         # Django shell_plus
just docker-shell  # Django shell inside running container (from host)
just docker-logs   # Tail all service logs
just status        # Show container statuses
```

## Pre-commit Hooks

| Hook | Purpose |
|------|---------|
| `nbstripout` | Strips notebook outputs before commit (keeps diffs small) |
| `ruff` | Python lint + format |
| `djlint` | Django HTML template lint + reformat |
| `rustywind` | Sorts Tailwind/DaisyUI class order |
| Standard hooks | Trailing whitespace, YAML/JSON checks, large file guard |

Install hooks:

```bash
uv run pre-commit install
```
