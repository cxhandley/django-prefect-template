
# Django + Prefect Integration Template - API Layer with Data Lake

**Decoupled API Gateway with S3 Data Lake** - FastAPI middleware + DuckDB + Polars for efficient data processing and analytics

## Architecture Overview

This approach introduces a **FastAPI API Gateway** between Django and Prefect, with an **S3 Data Lake** for efficient data storage and analytics:

```
┌────────────────────────────────────────────────────┐
│  Browser (DaisyUI + HTMX)                          │
└──────────────────────┬─────────────────────────────┘
                       │ HTTP
┌──────────────────────▼─────────────────────────────┐
│  Django Application                                │
│  ┌──────────────────────────────────────────────┐  │
│  │ Views (HTMX endpoints)                       │  │
│  └──────────────────┬───────────────────────────┘  │
│  ┌──────────────────▼───────────────────────────┐  │
│  │ DuckDB Analytics Layer                       │  │
│  │ - Query S3 Parquet directly                  │  │
│  │ - No data loading needed                     │  │
│  │ - Fast analytical queries                    │  │
│  └──────────────────┬───────────────────────────┘  │
│  ┌──────────────────▼───────────────────────────┐  │
│  │ Django Models (Metadata Only)                │  │
│  │ - FlowExecution tracking                     │  │
│  │ - S3 paths, not data                         │  │
│  │ - User permissions                           │  │
│  └──────────────────────────────────────────────┘  │
└──────────────────────┬─────────────────────────────┘
                       │ HTTP REST API
┌──────────────────────▼─────────────────────────────┐
│  FastAPI Gateway                                   │
│  ┌──────────────────────────────────────────────┐  │
│  │ Endpoints:                                   │  │
│  │ - POST /flows/{flow_name}/execute            │  │
│  │ - GET /flows/runs/{run_id}                   │  │
│  │ - GET /flows/runs/{run_id}/result            │  │
│  │ - GET /flows/deployments                     │  │
│  └──────────────────┬───────────────────────────┘  │
│  ┌──────────────────▼───────────────────────────┐  │
│  │ Middleware:                                  │  │
│  │ - JWT token validation                       │  │
│  │ - Rate limiting                              │  │
│  │ - Request/response logging                   │  │
│  └──────────────────┬───────────────────────────┘  │
│  ┌──────────────────▼───────────────────────────┐  │
│  │ Prefect Client SDK                           │  │
│  └──────────────────┬───────────────────────────┘  │
└──────────────────────┬─────────────────────────────┘
                       │ HTTP API
                       ▼
┌────────────────────────────────────────────────────┐
│  Prefect Server/Cloud                              │
└──────────────────────┬─────────────────────────────┘
                       │ Work Queue Polling
                       ▼
┌────────────────────────────────────────────────────┐
│  Prefect Worker Pool                               │
│  ┌──────────────────────────────────────────────┐  │
│  │ Polars Processing Engine                     │  │
│  │ - Read from S3 (lazy loading)                │  │
│  │ - 15x faster than Pandas                     │  │
│  │ - In-memory transformations                  │  │
│  │ - Write Parquet to S3                        │  │
│  └──────────────────────────────────────────────┘  │
└──────────────────────┬─────────────────────────────┘
                       │ S3 API
                       ▼
┌────────────────────────────────────────────────────┐
│  S3 Data Lake                                      │
│  ├── raw/                  (User uploads)          │
│  ├── processed/            (Flow outputs)          │
│  └── results/              (Final deliverables)    │
│                                                    │
│  Format: Parquet (columnar, compressed)            │
│  Cost: 97% cheaper than PostgreSQL                 │
└────────────────────────────────────────────────────┘
```

### Key Decisions

1. **FastAPI as API Gateway** - Clean REST interface between Django and Prefect
2. **S3 Data Lake** - Store flow results in S3, not PostgreSQL
3. **DuckDB for Analytics** - Query S3 Parquet files directly from Django
4. **Polars in Workers** - 15x faster data processing than Pandas
5. **Parquet Format** - Columnar storage, excellent compression
6. **JWT Authentication** - Stateless tokens for service-to-service auth
7. **Django Models Store Metadata** - Paths and stats, not actual data

### Advantages

- ✅ **Better separation of concerns** - Django UI, FastAPI orchestration, S3 storage
- ✅ **Independent scaling** - Scale each component separately
- ✅ **Cost efficient** - S3 is 97% cheaper than PostgreSQL for large data
- ✅ **Fast analytics** - DuckDB queries S3 without loading data
- ✅ **Fast processing** - Polars is 15x faster than Pandas
- ✅ **Unlimited storage** - S3 scales to petabytes
- ✅ **Multiple frontends** - Mobile apps, CLIs can use same API
- ✅ **Security isolation** - Prefect credentials never touch Django

### Disadvantages

- ⚠️ Additional services to maintain (FastAPI + S3)
- ⚠️ More network hops (adds ~50ms latency)
- ⚠️ Learning curve for DuckDB and Polars
- ⚠️ S3 consistency model (though now strongly consistent)

# Project Structure

```
django-prefect-kit/
├── docker-compose.yml
├── docker-compose.prod.yml
├── terraform/
│   ├── staging.tf
│   ├── production.tf
│   └── modules/
│       ├── alb/
│       ├── ecs/
│       ├── rds/
│       └── s3/                 # S3 bucket configuration
├── backend/                    # Django application
│   ├── Dockerfile
│   ├── manage.py
│   ├── requirements.txt
│   ├── config/
│   │   ├── settings/
│   │   │   ├── base.py         # S3 and DuckDB config
│   │   │   ├── development.py
│   │   │   └── production.py
│   │   └── urls.py
│   ├── apps/
│   │   ├── flows/
│   │   │   ├── models.py       # FlowExecution with S3 paths
│   │   │   ├── views.py        # HTMX endpoints
│   │   │   ├── api_client.py   # FastAPI client wrapper
│   │   │   ├── services/
│   │   │   │   ├── datalake.py       # DuckDB analytics
│   │   │   │   └── s3_manager.py     # S3 operations
│   │   │   ├── templates/
│   │   │   └── static/
│   │   └── accounts/
│   └── flows_library/          # Prefect flow definitions (Polars)
│       ├── data_processing.py
│       ├── report_generation.py
│       └── analytics_pipeline.py
├── gateway/                    # FastAPI service
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   ├── api/
│   │   ├── v1/
│   │   │   ├── endpoints/
│   │   │   │   ├── flows.py
│   │   │   │   ├── deployments.py
│   │   │   │   └── runs.py
│   │   │   └── router.py
│   │   └── dependencies.py
│   ├── core/
│   │   ├── config.py
│   │   ├── security.py         # JWT validation
│   │   └── prefect_client.py
│   ├── middleware/
│   │   ├── rate_limit.py
│   │   └── logging.py
│   └── schemas/
│       ├── flow.py
│       └── execution.py
├── worker/
│   ├── Dockerfile
│   ├── requirements.txt        # Includes polars, pyarrow
│   └── start-worker.sh
└── docs/
    ├── api-spec.yaml
    ├── datalake-schema.md      # S3 folder structure
    └── architecture.md
```

## Technology Stack

- **Web Framework**: Django 5.2
- **API Gateway**: FastAPI 
- **UI**: DaisyUI (Tailwind CSS) + HTMX
- **Workflow Engine**: Prefect 3.x
- **Database**: PostgreSQL 18 (metadata only)
- **Data Lake**: AWS S3
- **Analytics Engine**: DuckDB 
- **Processing Engine**: Polars (in Prefect workers)
- **File Format**: Apache Parquet
- **Authentication**: JWT (PyJWT)
- **Cache**: Redis
- **Deployment**: Docker Compose (staging), Terraform + ECS (prod)

### Development Setup

1. **Clone repository**

```bash
git clone https://github.com/cxhandley/django-prefect-template.git
cd django-prefect-template
```

2. **Create environment file**

```bash
cp .env.example .env
```

Example `.env`:
```env
# Django
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_DEBUG=True
DATABASE_URL=postgresql://django:password@db:5432/django_prefect

# FastAPI Gateway
GATEWAY_JWT_SECRET=gateway-secret-key-here
GATEWAY_API_URL=http://gateway:8001
PREFECT_API_URL=http://prefect-server:4200/api

# Prefect
PREFECT_API_KEY=your-prefect-api-key

# Redis
REDIS_URL=redis://redis:6379/0

# AWS S3 Data Lake
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_S3_REGION=us-east-1
DATA_LAKE_BUCKET=django-prefect-datalake-dev
AWS_S3_ENDPOINT_URL=http://minio:9000  # Use MinIO for local dev

# DuckDB Configuration
DUCKDB_THREADS=4
DUCKDB_MEMORY_LIMIT=4GB
```

Services:
- Django web: http://localhost:8000
- FastAPI gateway: http://localhost:8001
- FastAPI docs: http://localhost:8001/docs
- Prefect UI: http://localhost:4200
- Rustfs (S3 compatible): http://localhost:9000
- PostgreSQL: localhost:5432
- Redis: localhost:6379


# S3 Data Lake Structure

The data lake is organized into three main zones:

```
s3://django-prefect-datalake/
├── raw/                              # Raw, unprocessed data
│   ├── uploads/
│   │   └── {user_id}/
│   │       └── {upload_id}/
│   │           └── data.{csv,json,parquet}
│   └── external/
│       └── {source_name}/
│           └── {date}/
│               └── data.parquet
│
├── processed/                        # Cleaned, transformed data
│   ├── flows/
│   │   └── {flow_name}/
│   │       └── {run_id}/
│   │           ├── output.parquet    # Main results
│   │           ├── metadata.json     # Schema, row count, etc.
│   │           └── _SUCCESS          # Completion marker
│   └── aggregates/
│       └── {date}/
│           └── summary.parquet
│
└── results/                          # User-facing outputs
    ├── reports/
    │   └── {report_id}/
    │       ├── report.parquet
    │       ├── report.pdf
    │       └── metadata.json
    └── exports/
        └── {export_id}/
            └── data.{csv,xlsx,json}
```

## Configuration

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `DJANGO_SECRET_KEY` | Django secret key | Yes | - |
| `DATABASE_URL` | PostgreSQL connection string | Yes | - |
| `GATEWAY_API_URL` | FastAPI gateway URL | Yes | - |
| `GATEWAY_SERVICE_TOKEN` | JWT token for Django→FastAPI | Yes | - |
| `PREFECT_API_URL` | Prefect server URL | Yes | - |
| `PREFECT_API_KEY` | Prefect API token | Yes | - |
| `REDIS_URL` | Redis connection string | Yes | - |
| `AWS_ACCESS_KEY_ID` | AWS credentials | Yes | - |
| `AWS_SECRET_ACCESS_KEY` | AWS credentials | Yes | - |
| `AWS_S3_REGION` | S3 region | Yes | us-east-1 |
| `DATA_LAKE_BUCKET` | S3 bucket name | Yes | - |
| `AWS_S3_ENDPOINT_URL` | S3 endpoint (MinIO for dev) | Dev only | - |
| `DUCKDB_THREADS` | DuckDB parallel threads | No | 4 |
| `DUCKDB_MEMORY_LIMIT` | DuckDB memory limit | No | 4GB |
