# Product Backlog

Derived from [user-stories.md](user-stories.md). Items are ordered by priority within each tier. Each item references the parent user story and follows the [development workflow](../CLAUDE.md) before implementation begins.

**Effort sizing:** S = ~half day · M = 1–2 days · L = 3–5 days · XL = 1–2 weeks

> **Note:** US-7.1, US-7.2, and US-7.3 in user-stories.md are marked `[ ]` but their corresponding backlog items (BL-010, BL-011, BL-012) are complete. Those user story statuses need updating to `[x]`.

---

## Active — In Progress

---

### ~~BL-018~~ · ~~Production Environment — Docker Swarm + PostgreSQL Backups~~ `XL` ✓ Complete

**User story:** US-T6

**Completed:**
- [x] `backend/config/settings/production.py` — security headers, WhiteNoise, HSTS, structured logging
- [x] `docker-stack.yml` — Swarm-compatible with `deploy:` keys (replicas, restart policy, health checks)
- [x] `pg-backup` service — scheduled `pg_dump` → S3 via cron on manager node
- [x] `GET /health/` endpoint in `core/views.py`
- [x] GitHub Actions workflow — build → push GHCR → `docker service update`
- [x] Docker Swarm init and node join procedure documented in `docs/deployment/production.md`
- [x] Backup restore procedure documented in `docs/deployment/production.md`

---

### ~~BL-021~~ · ~~OpenTelemetry — Distributed Tracing & Metrics~~ `M` ✓ Complete

**User story:** US-T8
**Value:** With Celery tasks, S3 calls, DuckDB queries, and Django views all involved in a single pipeline run, there is currently no way to see where time is spent or which component caused a failure. OpenTelemetry adds end-to-end traces across all environments with no changes to business logic.

**Scope:**
- Add `opentelemetry-sdk`, `opentelemetry-instrumentation-django`, `opentelemetry-instrumentation-celery`, `opentelemetry-instrumentation-boto`, `opentelemetry-exporter-otlp-proto-grpc` to `backend/pyproject.toml`
- `apps/core/apps.py` — initialise SDK in `AppConfig.ready()` using env vars (`OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_TRACES_SAMPLER`)
- Propagate trace context from Django view into dispatched Celery tasks so traces span the full request lifecycle
- `otel/collector-dev.yml` — OTLP receiver → debug exporter + Jaeger exporter (stdout + local UI)
- `otel/collector-staging.yml` — OTLP receiver → stdout JSON exporter (CloudWatch-friendly)
- `otel/collector-production.yml` — OTLP receiver → configurable backend exporter (Tempo / Honeycomb / X-Ray via env var)
- `docker-compose.yml` — add `otel-collector` (dev) + `jaeger` (dev UI) services
- `docker-stack.yml` — add `otel-collector` service with production collector config
- `deploy/.env.tpl` — add `OTEL_*` variables sourced from 1Password
- Per-environment Django settings: dev uses `SimpleSpanProcessor`; staging/production use `BatchSpanProcessor`

**Depends on:** BL-018

**Docs required before starting:**
- Sequence diagram: `docs/sequences/otel_trace_lifecycle.mmd`

---

## Tier 1 — Structural Design (foundational)

These address complected data structures that compound in cost with every feature added on top. They are not urgent rewrites, but they gate a whole class of future capability (per-step progress, model versioning, analytics). They should be sequenced before the DataTable component (BL-024) since that component will query the new structures.

> See [design-review.md](design-review.md) for the full analysis.

---

### ~~BL-026~~ · ~~Split Execution Models — Typed Results, Remove Schemaless Blob~~ `L` ✓ Complete

**User story:** US-T11
**Value:** `FlowExecution.parameters` currently conflates prediction inputs (immutable, set at submission) with prediction results (written on completion). Every downstream consumer — comparison view, history list, analytics — has to know the internal key names and do JSON gymnastics. Typed columns make queries, filtering, and future analytics trivial.

**Scope:**
- Introduce `PredictionResult` model: `execution` (OneToOne FK), `scoring_model` (FK, nullable initially), `score` (FloatField), `classification` (TextChoices: Approved/Review/Declined), `confidence` (FloatField), `scored_at` (DateTimeField)
- Introduce `PredictionInput` model (or add typed columns to `FlowExecution`): `income`, `age`, `credit_score`, `employment_years` as proper fields
- Migration: backfill from existing `parameters` JSON for all `predict_pipeline` executions
- Update `run_prediction_task` to write a `PredictionResult` row instead of merging into `parameters`
- Update comparison view, history view, and execution detail to read from typed fields — remove all `.parameters.get("score")` calls
- Update `data-model.mmd`

**Depends on:** nothing — this is foundational
**Docs required:** Update `docs/data-model.mmd`

---

### ~~BL-027~~ · ~~`ExecutionStep` — Per-Step Pipeline Tracking~~ `M` ✓ Complete

**User story:** US-T12
**Value:** A 4-step pipeline is currently a black box. Users see "FAILED" with a truncated error and no indication of whether step 1 succeeded. Step-level records unlock accurate failure diagnosis, per-step progress display, and performance analytics without any additional instrumentation.

**Scope:**
- New model: `ExecutionStep` (`execution FK`, `step_name VARCHAR`, `step_index SMALLINT`, `status TextChoices`, `started_at`, `completed_at`, `output_s3_path`, `error_message`)
- Update `dodo.py` / `PipelineRunner` to create/update step records as each notebook starts and finishes (via a lightweight callback or by having each notebook write a step-start/step-end marker to a known S3 path)
- Update execution detail UI to show step-level progress: e.g. `✓ Ingest · ✓ Validate · ⟳ Transform · — Aggregate`
- Update `data-model.mmd`

**Depends on:** BL-026 (clean execution model first)
**Docs required:** Update `docs/data-model.mmd`; sequence diagram `docs/sequences/pipeline_step_tracking.mmd`

---

### ~~BL-028~~ · ~~`ScoringModel` — Versioned Scoring Algorithm~~ `M` ✓ Complete

**User story:** US-T13
**Value:** The scoring weights (0.40/0.30/0.20/0.10) and thresholds (0.70/0.50) are hardcoded in `predict_02_score.ipynb`. There is no record of which algorithm version produced a given score. Changing weights is invisible in the data layer. A `ScoringModel` entity makes the algorithm data — versionable, auditable, and swappable without touching notebook code.

**Scope:**
- New model: `ScoringModel` (`version VARCHAR`, `description TEXT`, `weights JSON`, `thresholds JSON`, `is_active BOOLEAN`, `created_at`, `created_by FK`)
- Seed migration with `v1.0` capturing the current hardcoded values
- Update `PipelineRunner` to pass the active `ScoringModel`'s weights and thresholds as notebook parameters (or write them to a known S3 config path that the notebook reads)
- Remove hardcoded numbers from `predict_02_score.ipynb`; read from parameters
- Link `PredictionResult.scoring_model FK → ScoringModel`
- Admin registration so scoring models can be managed via `/admin/`
- Update `data-model.mmd`

**Depends on:** BL-026 (`PredictionResult` must exist first)
**Docs required:** Update `docs/data-model.mmd`

---

### ~~BL-029~~ · ~~Notebook Result Protocol — Write `result.json` to S3~~ `S` ✓ Complete

**User story:** US-T14
**Value:** `PipelineRunner._extract_metadata()` scans stdout backwards for the first `{`. Any library printing a dict-like string can silently corrupt the result. Writing a `result.json` manifest to S3 instead makes the contract explicit, independently readable, and not fragile to logging noise.

**Scope:**
- Each notebook's final cell writes `result.json` to `s3://{bucket}/processed/flows/{flow_type}/{run_id}/result.json` in addition to (or instead of) the stdout print
- `PipelineRunner` reads `result.json` from S3 after subprocess exit; `_extract_metadata()` is removed
- The manifest schema is a documented dict (or Pydantic model): `{step, row_count, s3_output_path, ...}` for pipeline; `{score, classification, confidence, ...}` for prediction
- Existing stdout logging is unchanged — notebooks can print freely

**Depends on:** nothing (independent improvement, but easier to do alongside BL-026/028)

---

### ~~BL-030~~ · ~~Status as Enforced `TextChoices` State Machine~~ `S` ✓ Complete

**User story:** US-T15
**Value:** `status = CharField(max_length=50)` with no `choices`. Invalid states (typos, missing `completed_at`, backward transitions) are silently written. The state machine is real — it drives the entire UI polling loop — but it is enforced only by convention.

**Scope:**
- Add `ExecutionStatus(models.TextChoices)`: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`
- Apply to `FlowExecution.status` and `ExecutionStep.status`
- Add a `transition()` method (or use `django-fsm`) that guards valid transitions and auto-sets `completed_at`
- Replace all raw `.update(status="COMPLETED")` calls in `tasks.py` with the transition interface
- Migration: `RunPython` to normalise any existing rows with non-standard status strings

**Depends on:** BL-026 (clean model first)

---

## Tier 1 — Accessibility & Security (immediate)

Both are cross-cutting concerns that affect every page. Accessibility is included here because it has legal and ethical weight equivalent to security; neither should be deferred behind feature work.

---

### BL-025 · WCAG 2.1 AA Accessibility Audit & Remediation `M` `[ ]`

**User story:** US-T10
**Value:** The application is not currently navigable by keyboard-only users or screen reader users. Several specific gaps are known from reading the templates. This item audits and remediates all WCAG 2.1 AA failures.

**Reference:** WCAG 2.1 Level AA; EN 301 549 v3.2.1; Section 508.

**Scope — known gaps to fix:**

1. **Skip link** — add `<a href="#main-content" class="sr-only focus:not-sr-only …">Skip to main content</a>` as first child of `<body>` in `base.html`; add `id="main-content"` to `<main>` (WCAG 2.4.1)
2. **Navbar interactive elements** — replace `<div role="button">` notification bell and user avatar with `<button>` elements; add `aria-label="Open notifications"` and `aria-label="Open user menu"` respectively (`navbar.html`) (WCAG 4.1.2)
3. **Decorative SVGs** — add `aria-hidden="true"` to all inline SVG icons used alongside visible text labels across all templates (`navbar.html`, `sidebar.html`, `dashboard.html`, `empty_state.html`, `badge.html`) (WCAG 1.1.1)
4. **Async live regions** — add `aria-live="polite" aria-atomic="true"` to `#prediction-result` in `dashboard.html` and `#notification-dropdown-items` in `navbar.html` (WCAG 4.1.3)
5. **Form error `aria-describedby`** — in `dashboard.html`'s JS `setFieldError`, set `aria-describedby` on the input pointing at the error element's ID; mirror the pattern from `form_input.html` (WCAG 3.3.1)
6. **Modal `aria-labelledby`** — add `aria-labelledby="<id>"` to every `<dialog>` element and a matching `id` on the `<h3>` title; update `modal.html` component and all inline modals in `dashboard.html`, `base.html` (WCAG 4.1.2)
7. **Table headers** — add `scope="col"` to all `<th>` elements; replace empty `<th></th>` action columns with `<th scope="col" class="sr-only">Actions</th>` in `dashboard.html`, `history.html`, `user_list.html`, `admin_executions.html` (WCAG 1.3.1)
8. **Pagination** — add `aria-current="page"` to active page button; wrap pagination `div` in `<nav aria-label="Pagination">` in `pagination.html` (WCAG 2.4.3)
9. **Active nav** — add `aria-current="page"` to active sidebar and navbar links in `sidebar.html` and `navbar.html` (WCAG 2.4.3)
10. **Landmark regions** — wrap navbar content in `<nav aria-label="Main navigation">`; wrap sidebar `<ul>` in `<nav aria-label="Dashboard navigation">` (WCAG 1.3.1)
11. **Contrast audit** — run Axe / Lighthouse on all page types; resolve any AA failures (WCAG 1.4.3)
12. **Keyboard smoke test** — manually verify login, run prediction, view history, open/close modal, and mark notification as read are all completable by keyboard alone (WCAG 2.1.1)

**No new model or wireframe needed.** Reference [design-system.md](design-system.md) Do/Don't section.

**Definition of done:** Axe CLI or browser extension reports zero critical/serious violations on dashboard, history, and login pages.

---

## Tier 1 — Security (immediate)

Security items are prioritised above features. Both should be resolved before new feature work.

---

### ~~BL-022 · Secrets Management Audit~~ `M` ✓ Complete

**User story:** US-T9

**Completed:**
- Notebook credentials — `runner.py` and all 6 notebooks fixed; credentials never passed as papermill parameters
- `justfile run-pipeline` — `aws_access_key_id`/`aws_secret_access_key` removed from `PIPELINE_PARAMS`
- Password hashing — `PASSWORD_HASHERS` explicitly set to Argon2id with PBKDF2 fallback in `settings/base.py`; `argon2-cffi` added to `pyproject.toml`
- DuckDB f-string — known-limitation comment added to `services/datalake.py`
- Docker Compose — `django_password`/`rustfs_secret` are local dev placeholders; acceptable and documented
- GitHub Actions — all secrets use `${{ secrets.* }}`; no values echoed
- Django log config — clean; no credential fields in log formatters
- Secrets inventory — `docs/security/secrets-inventory.md` created; covers all secrets, injection paths, rotation procedures
- Remaining: `gitleaks`/`truffleHog` scan against repo history (recommend adding to CI)

---

### ~~BL-023 · Infrastructure as Code & 1Password Secrets Management~~ `L` ✓ Complete

**User story:** US-T7

**Completed:** All scope items were already implemented:
- `terraform/` — VPC, EC2, security groups, Elastic IP, S3 backup bucket, IAM instance profile
- SSH key sourced from 1Password (`op://Production/Infrastructure/public_key`)
- S3 remote state backend with versioning and encryption (`terraform/backend.tf`, `backend.hcl.example`)
- `deploy/.env.tpl` — full `op inject` template; no plaintext secrets
- `deploy/justfile` — all recipes: `tf-init`, `tf-plan`, `tf-apply`, `push-env`, `push-stack`, `bootstrap`, `deploy`, `rollback`, `migrate`, `ssh`, `status`, `logs`, `backup`
- Root `justfile` — `prod-*` namespace delegating to `deploy/justfile`
- `gunicorn` in `pyproject.toml`

---

## Tier 2 — Production Readiness

---

## Tier 3 — Platform & Infrastructure

---

## Tier 4 — Developer Experience

---

### BL-024 · Reusable Advanced DataTable Component `L` `[ ]`

**User story:** US-6.1
**Value:** Every list view (execution history, admin dashboard, notification list, user management) duplicates filter, sort, and pagination logic. A single reusable DataTable component eliminates that duplication and delivers consistent UX across all tables.

**Scope:**
- Reusable Django template partial: `core/templates/core/components/datatable.html`
- Column definitions passed via `table_config` context dict — fields, labels, sortable/filterable/hideable flags
- Column visibility toggled per-user via `localStorage` (keyed by `table_id`; no model change required)
- Filter builder supports: contains, not contains, equals, not equals, starts/ends with, is empty/not empty (text); eq/neq/gt/gte/lt/lte (number); before/after/eq (datetime); eq/neq (choice)
- Multiple filters combinable (AND); each shown as a dismissable chip in an active-filters bar
- Filter and sort state encoded in URL query params (shareable, browser back/forward compatible)
- Bulk action bar appears when ≥ 1 row checked; actions configured per table with `min_select`/`max_select`
- HTMX fetches filtered/sorted/paginated results without full page reload
- Alpine.js manages client-side state (filter builder rows, column toggles, selected IDs)
- No changes to base templates — added via `{% include %}` only
- Migrate history, admin execution list, notification list, and user management list to use the component

**Docs required before starting:**
- Wireframe: `docs/wireframes/datatable_component.excalidraw`
- Sequence diagram: `docs/sequences/datatable_filtering.mmd`

---

## Completed

All items below are done and closed.

| ID | Title | Tier | Effort |
|----|-------|------|--------|
| ~~BL-001~~ | ~~Password reset flow~~ | 1 | M |
| ~~BL-002~~ | ~~S3 cleanup on execution delete~~ | 1 | S |
| ~~BL-003~~ | ~~Presigned S3 download URLs~~ | 1 | S |
| ~~BL-004~~ | ~~Export execution history as CSV~~ | 1 | S |
| ~~BL-005~~ | ~~Prediction comparison — input & score detail~~ | 1 | M |
| ~~BL-006~~ | ~~Superuser user management UI~~ | 2 | L |
| ~~BL-007~~ | ~~Registration email confirmation~~ | 2 | M |
| ~~BL-008~~ | ~~Admin monitoring dashboard~~ | 3 | L |
| ~~BL-009~~ | ~~Admin execution log viewer~~ | 3 | M |
| ~~BL-010~~ | ~~Input presets (save & reuse prediction inputs)~~ | 4 | L |
| ~~BL-011~~ | ~~Email notifications for failed executions~~ | 4 | M |
| ~~BL-012~~ | ~~Retry failed execution~~ | 4 | S |
| ~~BL-013~~ | ~~Migrate HTMX 1.9.10 → 2.x~~ | 5 | S |
| ~~BL-014~~ | ~~UI polish — buttons, spacing, visual consistency~~ | 4 | S |
| ~~BL-015~~ | ~~Prediction form UX — disable during run & fix cancel flicker~~ | 4 | S |
| ~~BL-016~~ | ~~Frontend asset pipeline (Tailwind build + django-compressor)~~ | 5 | M |
| ~~BL-017~~ | ~~Staging environment (EC2 + Traefik SSL)~~ | 5 | L |
| ~~BL-019~~ | ~~Notification management (in-app centre + preferences)~~ | 4 | M |
| ~~BL-020~~ | ~~Feature flags (per-user & environment toggles)~~ | 5 | M |

---

## Backlog Summary

| ID | Title | Status | Effort | Depends on |
|----|-------|--------|--------|------------|
| ~~BL-018~~ | ~~Production environment (docs remaining)~~ | Complete | S | — |
| ~~BL-021~~ | ~~OpenTelemetry — distributed tracing & metrics~~ | Complete | M | BL-018 |
| ~~BL-026~~ | ~~Split execution models — typed results, remove blob~~ | Complete | L | — |
| ~~BL-027~~ | ~~`ExecutionStep` — per-step pipeline tracking~~ | Complete | M | BL-026 |
| ~~BL-028~~ | ~~`ScoringModel` — versioned scoring algorithm~~ | Complete | M | BL-026 |
| ~~BL-029~~ | ~~Notebook result protocol — write `result.json` to S3~~ | Complete | S | — |
| ~~BL-030~~ | ~~Status as enforced `TextChoices` state machine~~ | Complete | S | BL-026 |
| BL-025 | WCAG 2.1 AA accessibility audit & remediation | Not started | M | — |
| ~~BL-022~~ | ~~Secrets management audit~~ | Complete | M | — |
| ~~BL-023~~ | ~~Infrastructure as Code & 1Password secrets~~ | Complete | L | — |
| BL-024 | Reusable advanced DataTable component | Not started | L | BL-026 |
