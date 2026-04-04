# OpenTelemetry — Design & Implementation Guide

## What we're instrumenting

| Component | Auto-instrumented by | Spans produced |
|-----------|---------------------|----------------|
| Django views | `opentelemetry-instrumentation-django` | HTTP method, route, status code, DB queries |
| Celery tasks | `opentelemetry-instrumentation-celery` | Task name, queue, duration, exceptions |
| boto3 / S3 | `opentelemetry-instrumentation-botocore` | S3 PutObject, GetObject, presign |
| PostgreSQL (psycopg) | `opentelemetry-instrumentation-psycopg` | Every SQL query, duration |

Trace context is propagated from the Django view into Celery task headers using the W3C `traceparent` standard, so a single pipeline run appears as one continuous trace from HTTP request through to task completion.

---

## Environment strategy

| | Dev | Staging | Production |
|---|---|---|---|
| Span processor | `SimpleSpanProcessor` (sync — immediate export, easy debugging) | `BatchSpanProcessor` (async) | `BatchSpanProcessor` (async) |
| Collector config | `otel/collector-dev.yml` | `otel/collector-staging.yml` | `otel/collector-production.yml` |
| Exporter in collector | Jaeger + debug (stdout) | Logging (JSON to stdout → CloudWatch) | Configurable backend (see below) |
| Visual UI | Jaeger at `http://localhost:16686` | CloudWatch Logs Insights | Grafana / Honeycomb / AWS X-Ray console |
| Sampling | Always-on (100%) | Always-on | Configurable via `OTEL_TRACES_SAMPLER` |

---

## Python dependencies

```toml
# backend/pyproject.toml — add to [project.dependencies]
"opentelemetry-sdk==1.28.0",
"opentelemetry-api==1.28.0",
"opentelemetry-instrumentation-django==0.49b0",
"opentelemetry-instrumentation-celery==0.49b0",
"opentelemetry-instrumentation-botocore==0.49b0",
"opentelemetry-instrumentation-psycopg==0.49b0",
"opentelemetry-exporter-otlp-proto-grpc==1.28.0",
```

> **Versioning note:** `opentelemetry-instrumentation-*` packages use a `0.Xb0` scheme that tracks the SDK major version. Always pin all packages to the same release wave.

---

## SDK initialisation

Instrumentation is wired up in `apps/core/apps.py` via `AppConfig.ready()`. This fires once when Django starts (web and Celery worker), before any request or task is processed.

```python
# apps/core/apps.py
from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"

    def ready(self):
        import os

        if os.environ.get("OTEL_SDK_DISABLED", "false").lower() == "true":
            return

        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.django import DjangoInstrumentor
        from opentelemetry.instrumentation.celery import CeleryInstrumentor
        from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
        from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor

        # Provider
        provider = TracerProvider()

        # Exporter — OTLP to collector (endpoint from env)
        exporter = OTLPSpanExporter()  # reads OTEL_EXPORTER_OTLP_ENDPOINT

        # Processor — sync in dev, async in staging/prod
        if os.environ.get("DJANGO_SETTINGS_MODULE", "").endswith("development"):
            provider.add_span_processor(SimpleSpanProcessor(exporter))
        else:
            provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(provider)

        # Auto-instrumentation
        DjangoInstrumentor().instrument()
        CeleryInstrumentor().instrument()
        BotocoreInstrumentor().instrument()
        PsycopgInstrumentor().instrument()
```

### Key environment variables

| Variable | Dev | Staging | Production |
|----------|-----|---------|------------|
| `OTEL_SERVICE_NAME` | `app-dev` | `app-staging` | `app` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4317` | `http://otel-collector:4317` | `http://otel-collector:4317` |
| `OTEL_TRACES_SAMPLER` | `always_on` | `always_on` | `parentbased_traceidratio` |
| `OTEL_TRACES_SAMPLER_ARG` | — | — | `0.1` (10% in prod, adjust to taste) |
| `OTEL_SDK_DISABLED` | `false` | `false` | `false` |

All are set in `docker-compose.yml` (dev), `.env.staging` (staging), and `deploy/.env.tpl` (production via 1Password).

---

## Collector configuration

The OTel Collector is the central pipeline component. It receives spans from the SDK over OTLP/gRPC, processes them, and forwards to the appropriate backend. Each environment has its own config file.

### Dev (`otel/collector-dev.yml`)

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

processors:
  batch: {}

exporters:
  debug:
    verbosity: normal
  jaeger:
    endpoint: jaeger:14250
    tls:
      insecure: true

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug, jaeger]
```

### Staging (`otel/collector-staging.yml`)

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

processors:
  batch: {}
  resource:
    attributes:
      - key: deployment.environment
        value: staging
        action: insert

exporters:
  logging:
    loglevel: info   # structured JSON to stdout → Docker log driver → CloudWatch

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch, resource]
      exporters: [logging]
```

### Production (`otel/collector-production.yml`)

The production config supports three backend options, selectable by which exporter is active in the `service.pipelines` block. Set one based on your chosen backend.

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

processors:
  batch: {}
  resource:
    attributes:
      - key: deployment.environment
        value: production
        action: insert

exporters:
  # Option A — Grafana Tempo (self-hosted or Grafana Cloud)
  otlp/tempo:
    endpoint: ${TEMPO_ENDPOINT}          # e.g. tempo:4317 or otlp-gateway.grafana.net:443
    headers:
      authorization: Bearer ${TEMPO_TOKEN}

  # Option B — Honeycomb
  otlp/honeycomb:
    endpoint: api.honeycomb.io:443
    headers:
      x-honeycomb-team: ${HONEYCOMB_API_KEY}

  # Option C — AWS X-Ray (via OTLP → X-Ray exporter)
  awsxray:
    region: ap-southeast-2
    # Uses EC2 instance role — no credentials needed

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch, resource]
      exporters: [otlp/tempo]   # ← swap to otlp/honeycomb or awsxray
```

---

## Docker Compose changes (dev)

```yaml
# docker-compose.yml additions
services:
  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.111.0
    command: ["--config=/etc/otelcol/config.yml"]
    volumes:
      - ./otel/collector-dev.yml:/etc/otelcol/config.yml:ro
    ports:
      - "4317:4317"   # OTLP gRPC (internal — web + celery connect here)
    networks:
      - app-network

  jaeger:
    image: jaegertracing/all-in-one:1.61
    ports:
      - "16686:16686"  # Jaeger UI — http://localhost:16686
    environment:
      COLLECTOR_OTLP_ENABLED: "true"
    networks:
      - app-network
```

Add to `web` and `celery-worker` environment:
```yaml
environment:
  OTEL_SERVICE_NAME: app-dev
  OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-collector:4317
  OTEL_TRACES_SAMPLER: always_on
  OTEL_SDK_DISABLED: "false"
```

---

## Docker Swarm changes (production)

```yaml
# docker-stack.yml additions
services:
  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.111.0
    command: ["--config=/etc/otelcol/config.yml"]
    volumes:
      - ./otel/collector-production.yml:/etc/otelcol/config.yml:ro
    networks:
      - app-network
    deploy:
      replicas: 1
      restart_policy:
        condition: on-failure
```

---

## 1Password — production secrets

Add to the **Production → App** item:
| Field | Value |
|-------|-------|
| `otel_service_name` | `app` |
| `otel_endpoint` | `http://otel-collector:4317` |
| `tempo_endpoint` | your Grafana Tempo endpoint |
| `tempo_token` | Grafana Cloud API token |

Add to `deploy/.env.tpl`:
```
OTEL_SERVICE_NAME={{ op://Production/App/otel_service_name }}
OTEL_EXPORTER_OTLP_ENDPOINT={{ op://Production/App/otel_endpoint }}
OTEL_TRACES_SAMPLER=parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG=0.1
TEMPO_ENDPOINT={{ op://Production/App/tempo_endpoint }}
TEMPO_TOKEN={{ op://Production/App/tempo_token }}
```

---

## Choosing a production backend

| Backend | Best for | Cost model |
|---------|----------|------------|
| **Grafana Tempo** (self-hosted) | Full control, no per-span cost | EC2 storage only |
| **Grafana Cloud** (managed Tempo) | Easiest managed option | Free tier: 50 GB/month |
| **Honeycomb** | Rich querying, great DX | Free tier: 20M events/month |
| **AWS X-Ray** | Already in AWS, IAM auth, integrates with CloudWatch | $5 per 1M traces recorded |

Recommendation for this project: **Grafana Cloud** (free tier covers early production volume) or **Honeycomb** (best querying for debugging Celery task chains). Both accept OTLP natively — no vendor SDK required.

---

## Testing instrumentation locally

1. `just docker-up` — starts all services including `otel-collector` and `jaeger`
2. Trigger a pipeline run in the browser
3. Open `http://localhost:16686` → search for service `app-dev`
4. You should see a root span for the HTTP POST with child spans for the Celery task, S3 calls, and DB queries

To verify context propagation (Django → Celery link), look for a single trace ID spanning both the `http.server` span and the `celery.task` span.
