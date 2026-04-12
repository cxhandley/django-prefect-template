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

### ~~BL-031~~ · ~~Live Execution Detail Auto-Refresh & Prediction Step Progress~~ `M` ✓ Complete

**User story:** US-2.5
**Value:** The execution detail page currently renders a static snapshot; users watching a long-running pipeline must refresh manually to see step progress or know when it finishes. The prediction "running" panel shows only a generic spinner with no step visibility. Both surfaces already have the `ExecutionStep` model and the `prediction_status` polling pattern available — this item wires them together with HTMX to give users live feedback without any page reload.

**Scope:**

1. **New partial endpoint** — `GET /flows/executions/<id>/live-status/`
   - Requires login; scoped to `triggered_by=request.user` (staff endpoint mirrors with any-user access)
   - Returns an HTML partial (`flows/partials/execution_live_status.html`) containing:
     - Status badge (re-rendered from current `execution.status`)
     - Duration (computed from `created_at` → now or `completed_at`)
     - `ExecutionStep` timeline: step name, status icon, `started_at`, `completed_at`, `error_message`
     - Structured log lines built from `ExecutionStep` records (one log line per step event)
   - When status is terminal (COMPLETED or FAILED): omit `hx-trigger` from the returned partial so the poll loop terminates naturally
   - When status is PENDING or RUNNING: include `hx-trigger="every 3s"` and `hx-swap="outerHTML"` so HTMX re-polls

2. **Update `execution_detail.html`** — wrap the status badge, duration stat, pipeline steps section, and execution logs section in a single `<div>` that carries the initial `hx-get`, `hx-trigger`, and `hx-swap` attributes; these are already omitted by the partial when the execution is terminal on first load (no unnecessary polls for completed executions)

3. **Update `prediction_running.html`** — replace the static spinner with a call to the same `live-status` partial; show per-step progress (step name + status icon for each `ExecutionStep`) alongside the spinner so the user can see which notebook step is executing; retain the "View execution details →" link

4. **Route** — add `path("executions/<uuid:run_id>/live-status/", views.execution_live_status, name="execution_live_status")` to `flows/urls.py`

5. **No model changes required** — `ExecutionStep` already carries all needed fields (`step_name`, `step_index`, `status`, `started_at`, `completed_at`, `error_message`)

**Out of scope:** raw notebook stdout streaming (not stored), WebSocket/SSE (HTMX polling is sufficient given 3-step pipelines complete in ~30 s)

**Depends on:** BL-027 (`ExecutionStep` model must exist — already complete)

**Docs required before starting:**
- Sequence diagram: `docs/sequences/execution_live_status.mmd` — shows HTMX poll loop, Django view, DB query, and terminal-state poll removal

---

## Tier 3 — Platform & Infrastructure

---

## Tier 3 — Scoring Model Training & Promotion (Admin Epic 13)

These five items collectively deliver the end-to-end model-training workflow: synthetic data → optimisation → backtest → visual review → promotion. They must be sequenced in dependency order; parallelism is possible between BL-034 (backtest engine) and BL-035 (charts scaffold) once BL-033 is complete.

---

### ~~BL-032 · Synthetic Training Dataset Generation~~ `M` ✓ Complete

**User story:** US-13.1
**Value:** There is currently no labelled dataset to train or backtest a scoring model against. Real applicant data cannot be used for experimentation. Faker-generated synthetic data with a deterministic ground-truth label function gives the training pipeline a reproducible, realistic input without privacy risk.

**Scope:**

*New model — `TrainingDataset`:*
- `id` PK, `slug` (auto-generated UUID prefix), `description`, `row_count`, `seed`, `s3_path`, `status` (`TextChoices`: PENDING / RUNNING / COMPLETED / FAILED), `created_at`, `created_by FK → USER`
- Admin registration

*Celery task — `generate_training_dataset_task`:*
- Accepts `dataset_id`; updates status to RUNNING
- Uses **Faker** (locale `en_US`) to generate: `income` (LogNormal ~ $45 k, σ=0.6), `age` (Normal ~ 38, σ=12, clipped 18–80), `credit_score` (Normal ~ 650, σ=80, clipped 300–850), `employment_years` (Gamma shape=2, scale=4, clipped 0–40)
- Applies the same normalisation logic as `predict_02_score.ipynb` plus injected Gaussian noise (σ=0.03) to derive a continuous `ground_truth_score`; converts to `ground_truth_label` using the current active `ScoringModel` thresholds
- All manipulation in **Polars** — no pandas
- Writes Parquet to `s3://{bucket}/training/datasets/{dataset_id}/data.parquet`
- Updates `TrainingDataset.row_count`, `s3_path`, `status = COMPLETED`

*Django views (admin-only, `@staff_member_required`):*
- `GET /admin-tools/training/datasets/` — list with status badges and row count; HTMX polling while status is RUNNING
- `POST /admin-tools/training/datasets/generate/` — form submission → dispatch task → redirect to list
- `GET /admin-tools/training/datasets/<id>/` — detail with statistical summary (feature means/stddev/quantiles via DuckDB, class balance pie via Altair)
- `DELETE /admin-tools/training/datasets/<id>/delete/` — with confirmation; S3 cleanup

*Data notes:*
- Class balance target: ~55 % Approved / ~25 % Review / ~20 % Declined (realistic portfolio distribution)
- Seed must be stored on the record so datasets are exactly reproducible

**Docs required before starting:**
- Update `docs/data-model.mmd` with `TrainingDataset`
- Sequence diagram: `docs/sequences/training_dataset_generation.mmd`

**Depends on:** BL-028 (`ScoringModel` must exist — complete)

---

### BL-033 · Model Training Run — Weight & Threshold Optimisation `L` `[~]`

**User story:** US-13.2
**Value:** Currently the only way to change scoring weights is to edit a notebook manually. This item gives admins a reproducible, logged optimisation pipeline that searches the weight and threshold space, records every round, and stores artefacts in S3 — so experimentation is data-driven and auditable rather than ad hoc.

**Scope:**

*New model — `ModelTrainingRun`:*
- `id` PK, `label` VARCHAR, `dataset FK → TrainingDataset`, `optimisation_target` (`TextChoices`: GINI / KS / F1_REVIEW), `status` (`TextChoices`: PENDING / RUNNING / COMPLETED / FAILED), `candidate_weights` JSON (null until complete), `candidate_thresholds` JSON (null until complete), `val_gini` FLOAT, `val_ks` FLOAT, `val_f1_review` FLOAT, `umap_enabled` BOOLEAN, `artefacts_s3_path`, `error_message`, `created_at`, `created_by FK → USER`
- Index on `(dataset, created_at DESC)` for list queries
- Admin registration

*Celery task — `run_model_training_task`:*
- Accepts `run_id`; updates status to RUNNING
- Reads dataset Parquet from S3 into a **Polars** DataFrame
- Reproducible 80/20 stratified split using the stored dataset `seed`
- Normalises the four features using the same ranges as the live scoring notebook (no `sklearn.preprocessing`)
- Uses **scipy.optimize.minimize** (L-BFGS-B) or **optuna** (TPE sampler) to search weights subject to: `sum(weights) == 1.0`, each weight ∈ `[0.05, 0.70]`; objective = negative of chosen target metric computed on the validation fold via **DuckDB** SQL over in-memory Parquet
- Threshold grid search: evaluates the Cartesian product of approval cutpoints `[0.55..0.85, step=0.05]` × review cutpoints `[0.30..0.60, step=0.05]` on the validation fold; picks the pair that maximises the optimisation target
- If `umap_enabled`: computes a 2-D **UMAP** embedding (n_neighbors=15, min_dist=0.1) of the 4-feature training fold; writes coordinates + ground_truth_label as `umap.parquet` to the artefact path
- Writes artefacts to `s3://{bucket}/training/runs/{run_id}/`:
  - `weights.json` — optimal weights dict
  - `thresholds.json` — optimal thresholds dict
  - `val_metrics.json` — validation metrics summary
  - `umap.parquet` — UMAP coordinates (if enabled)
  - `score_distributions.parquet` — score per sample + ground_truth_label (validation fold)
- Updates `ModelTrainingRun` with candidate weights, thresholds, val metrics, `status = COMPLETED`

*Django views (admin-only):*
- `GET /admin-tools/training/datasets/<dataset_id>/runs/` — list of runs for dataset, sortable by val_gini / val_ks
- `POST /admin-tools/training/datasets/<dataset_id>/runs/start/` — form → dispatch task → HTMX polling
- `GET /admin-tools/training/runs/<run_id>/` — training run detail page (links to BL-034 backtest, BL-035 charts, BL-036 promotion)

**Docs required before starting:**
- Update `docs/data-model.mmd` with `ModelTrainingRun`
- Sequence diagram: `docs/sequences/model_training_run.mmd`
- Flow control diagram: `docs/flow-control/weight_optimisation.mmd`

**Depends on:** BL-032 (`TrainingDataset` must exist)

---

### BL-034 · Backtest Engine — Held-Out Evaluation `M` `[~]`

**User story:** US-13.3
**Value:** Validation metrics from the training fold can be optimistic due to overfit. An independent backtest on the held-out 20 % split provides the real generalisation estimate that determines whether a model is fit for promotion.

**Scope:**

*New model — `ModelBacktestResult`:*
- `id` PK, `training_run FK → ModelTrainingRun` (OneToOne), `status` TextChoices, `accuracy` FLOAT, `precision_approved` / `precision_review` / `precision_declined` FLOAT, `recall_approved` / `recall_review` / `recall_declined` FLOAT, `f1_approved` / `f1_review` / `f1_declined` FLOAT, `gini` FLOAT, `ks_statistic` FLOAT, `confusion_matrix` JSON (3×3, row=actual, col=predicted), `artefacts_s3_path`, `completed_at`
- All metric fields are computed without scikit-learn — implemented in **Polars** expressions and **DuckDB** SQL

*Celery task — `run_model_backtest_task`:*
- Reads dataset Parquet; reconstructs identical 80/20 split (same seed → same rows)
- Applies candidate weights and thresholds from `ModelTrainingRun` to the **test fold only**
- Computes all metrics via Polars/DuckDB:
  - Confusion matrix: `GROUP BY (ground_truth_label, predicted_label)` in DuckDB
  - Precision/recall/F1: derived from confusion matrix in Polars (no sklearn)
  - Gini: `2 × AUC − 1` where AUC computed via trapezoid rule over sorted score ranks in Polars
  - KS statistic: max separation between CDF of positive and negative score distributions — computed in Polars with `cum_sum` over sorted score
- Writes `test_scores.parquet` (score + ground_truth + predicted per test row) to `s3://{bucket}/training/runs/{run_id}/backtest/`
- Creates / updates `ModelBacktestResult` record

*Django views (admin-only):*
- `POST /admin-tools/training/runs/<run_id>/backtest/` — trigger backtest task; HTMX polling
- Backtest metrics section on training run detail page (updated in-place once complete)
- `GET /admin-tools/training/runs/<run_id>/backtest/export/` — download `test_scores.parquet` as CSV

**Docs required before starting:**
- Update `docs/data-model.mmd` with `ModelBacktestResult`

**Depends on:** BL-033 (`ModelTrainingRun` must be COMPLETED)

---

### BL-035 · Admin Visual Diagnostics — Altair Charts `M` `[~]`

**User story:** US-13.4
**Value:** Numerical metrics alone are insufficient for model review — a chart can reveal score clustering, threshold placement issues, or unexpected class separation that a table of numbers hides. Altair charts rendered via Vega-Embed give admins interactive, shareable diagnostics without server-side image generation.

**Scope:**

*Chart endpoints — all return Altair JSON spec (`Content-Type: application/json`), no HTML; rendered client-side via Vega-Embed:*

- `GET /admin-tools/training/runs/<run_id>/charts/umap/` — UMAP scatter
  - Source: `umap.parquet` from S3 via DuckDB
  - Encoding: x=`umap_x`, y=`umap_y`, colour=`ground_truth_label` (3-class categorical palette), tooltip=`[income, age, credit_score, employment_years, ground_truth_label]`
  - Falls back to `{"error": "UMAP not computed for this run"}` JSON when `umap_enabled=False`

- `GET /admin-tools/training/runs/<run_id>/charts/score-distribution/` — score histogram by outcome
  - Source: `test_scores.parquet` (backtest fold) via DuckDB
  - Layered Altair chart: one density/histogram layer per `ground_truth_label`; vertical rules at approval and review threshold values
  - Requires backtest to be COMPLETED

- `GET /admin-tools/training/runs/<run_id>/charts/confusion-matrix/` — 3×3 heatmap
  - Source: `ModelBacktestResult.confusion_matrix` JSON field
  - Altair rect mark with colour=count, text overlay with cell count and row-normalised percentage

- `GET /admin-tools/training/runs/<run_id>/charts/class-metrics/` — precision/recall/F1 per class
  - Source: `ModelBacktestResult` typed columns
  - Grouped bar chart: x=class, colour=metric type (precision / recall / F1), y=value [0–1]

- `GET /admin-tools/training/datasets/<dataset_id>/charts/gini-trend/` — Gini & KS across rounds
  - Source: DuckDB query joining `ModelTrainingRun` + `ModelBacktestResult` for the dataset
  - Dual-line chart: x=`created_at` (run timestamp), y=metric value, colour=metric (Gini vs KS), interactive tooltip showing run label

- `GET /admin-tools/training/runs/compare/charts/metrics/` — multi-run metric comparison
  - Accepts `?run_ids=<id1>,<id2>,...` (2–4 runs)
  - Grouped bar chart comparing Gini, KS, F1_review across selected runs

*Frontend integration:*
- Training run detail template includes `<div id="chart-{name}">` containers loaded via HTMX `hx-get` on page load
- Each container uses `vegaEmbed('#chart-{name}', spec)` (Vega-Embed CDN or vendored JS)
- Chart containers show a skeleton loader while fetching; error state if endpoint returns `{"error": ...}`

*Implementation notes:*
- All data read from S3 Parquet via `duckdb.connect().execute("SELECT ... FROM read_parquet('s3://...')")` — no file loaded into Django memory
- Altair specs built using the Python `altair` library installed in the virtualenv; serialised with `chart.to_dict()`
- No Matplotlib, no Seaborn, no Plotly

**Docs required before starting:**
- Wireframe: `docs/wireframes/training_run_detail.excalidraw`

**Depends on:** BL-033 (training run artefacts), BL-034 (backtest metrics) — charts degrade gracefully when backtest is absent

---

### BL-036 · Model Promotion Workflow `S` `[ ]`

**User story:** US-13.5, US-13.6
**Value:** Without a formal promotion gate, the only way to update the live model is to edit `ScoringModel` in `/admin/` manually — bypassing the training audit trail entirely. This item wires the training pipeline to the live scoring model so that promotion is a deliberate, logged action with side-by-side evidence.

**Scope:**

*New model — `ModelPromotion`:*
- `id` PK, `training_run FK → ModelTrainingRun` (OneToOne), `resulting_scoring_model FK → ScoringModel`, `promoted_by FK → USER`, `promoted_at` DateTimeField, `notes` TextField (optional admin rationale)

*Django view — `POST /admin-tools/training/runs/<run_id>/promote/`:*
- Guard: `training_run.backtest.status == COMPLETED` — returns 409 otherwise
- Wraps in `transaction.atomic()`:
  1. Deactivate current active `ScoringModel` (`is_active = False`)
  2. Create new `ScoringModel` with: `version` = auto-incremented (e.g. `"1.1"` from `"1.0"`), `weights = training_run.candidate_weights`, `thresholds = training_run.candidate_thresholds`, `is_active = True`, `created_by = request.user`
  3. Create `ModelPromotion` record
- HTMX response swaps training run detail page status section to show "Promoted → ScoringModel v1.1"

*Training history page — `GET /admin-tools/training/runs/`:*
- Lists all `ModelTrainingRun` records across all datasets
- Columns: dataset, label, target, Gini, KS, F1_review, status, promotion badge, created_at
- Sortable via URL params; DuckDB-backed aggregate query
- "Compare" checkbox action (2–4 runs) → navigates to `GET /admin-tools/training/runs/compare/?run_ids=...` which renders side-by-side metrics table + Altair comparison chart (BL-035)

*Navigation:*
- Add "Model Training" link to the admin sidebar section; visible only to `is_staff` users

**Docs required before starting:**
- Update `docs/data-model.mmd` with `ModelPromotion`

**Depends on:** BL-033, BL-034, BL-035

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
| ~~BL-025~~ | ~~WCAG 2.1 AA accessibility audit & remediation~~ | Complete | M | — |
| ~~BL-022~~ | ~~Secrets management audit~~ | Complete | M | — |
| ~~BL-023~~ | ~~Infrastructure as Code & 1Password secrets~~ | Complete | L | — |
| BL-024 | Reusable advanced DataTable component | Not started | L | BL-026 |
| ~~BL-032~~ | ~~Synthetic training dataset generation~~ | ~~Not started~~ | M | BL-028 |
| BL-033 | Model training run — weight & threshold optimisation | In progress | L | BL-032 |
| BL-034 | Backtest engine — held-out evaluation | In progress | M | BL-033 |
| BL-035 | Admin visual diagnostics — Altair charts | In progress | M | BL-033, BL-034 |
| BL-036 | Model promotion workflow | Not started | S | BL-033, BL-034, BL-035 |
