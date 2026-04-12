# Django Pipeline & Prediction Platform — User Stories (MVP)

Status legend: `[x]` complete · `[~]` partial · `[ ]` not started

---

## Epic 1: User Management & Authentication

### US-1.1: User Registration and Login `[x]`
**As a** new user
**I want to** create an account and log in
**So that** I can access the pipeline and prediction system

**Acceptance Criteria:**
- [x] User can register with email and password
- [x] User can log in with credentials
- [x] User can view and edit their basic profile
- [x] User can reset a forgotten password
- [x] User receives a confirmation email on registration

### US-1.2: Superuser Management `[x]`
**As a** superuser
**I want to** manage user roles and permissions
**So that** I can control who can access the system and features

**Acceptance Criteria:**
- [x] Superuser can view all users in the system
- [x] Superuser can activate and deactivate users
- [x] Superuser can see user activity history
- [x] Superuser can reset user passwords

---

## Epic 2: Data Pipeline Execution

### US-2.1: Upload and Process a File `[x]`
**As a** user
**I want to** upload a CSV or Parquet file and trigger a processing pipeline
**So that** I can transform and aggregate my data without writing code

**Acceptance Criteria:**
- [x] User can upload a CSV or Parquet file from the dashboard
- [x] File is stored in S3 and a pipeline execution is created
- [x] Pipeline runs asynchronously (ingest → validate → transform → aggregate)
- [x] User sees a "running" indicator while the pipeline executes
- [x] User is shown the result or an error message once complete
- [x] Execution is recorded with status, row count, and file size

### US-2.2: Monitor Pipeline Status `[x]`
**As a** user
**I want to** see live status updates while my pipeline is running
**So that** I know when results are ready without refreshing the page

**Acceptance Criteria:**
- [x] Dashboard polls for status updates via HTMX
- [x] Status transitions shown: PENDING → RUNNING → COMPLETED / FAILED
- [x] Error message displayed if the pipeline fails
- [x] User can stop a running pipeline

### US-2.3: View Pipeline Results `[x]`
**As a** user
**I want to** view the output of my pipeline
**So that** I can inspect and act on the processed data

**Acceptance Criteria:**
- [x] User can view a preview of the output Parquet (up to 100 rows via DuckDB)
- [x] User can see summary statistics (total rows, revenue, transactions, customers)
- [x] User can download results in CSV, Parquet, or JSON format
- [x] Download link uses a presigned S3 URL with expiry

### US-2.4: Delete a Pipeline Execution `[x]`
**As a** user
**I want to** delete a past execution record
**So that** I can keep my history clean

**Acceptance Criteria:**
- [x] User can delete an execution from the detail page
- [x] Execution record is removed from the database
- [x] Associated S3 files are cleaned up on deletion

### US-2.5: Live Auto-Refresh on Execution Detail and Prediction Progress Panel `[x]`
**As a** user
**I want** the execution detail page and the inline prediction progress panel to update automatically while an execution is running
**So that** I can watch step-by-step progress and see the final result without manually refreshing the page

**Acceptance Criteria:**
- [x] `flows/executions/<id>/` polls a status partial endpoint (every 3 s) while execution status is PENDING or RUNNING; polling stops automatically once COMPLETED or FAILED
- [x] Status badge on the detail page updates in-place (PENDING → RUNNING → COMPLETED / FAILED)
- [x] Pipeline Steps timeline on the detail page updates in-place: each step shows its current status (✓ / ✗ / ⟳ / —), `started_at`, and `completed_at` as they are written to `ExecutionStep`
- [x] Execution Logs section on the detail page shows structured, step-level log lines derived from `ExecutionStep` records (step name, timestamps, error message if present) rather than placeholder text; logs update in-place each poll cycle
- [x] The "Running prediction…" panel on the dashboard / predictions page shows live per-step progress (which steps are done, which is currently running) instead of a generic spinner, using the same polling endpoint
- [x] Polling is removed from the DOM (not just paused) once a terminal status is returned, so no wasted requests after completion
- [x] Duration stat on the detail page updates live while running

---

## Epic 3: Credit Prediction

### US-3.1: Run a Credit Prediction `[x]`
**As a** user
**I want to** enter applicant data and get a credit prediction
**So that** I can assess creditworthiness quickly

**Acceptance Criteria:**
- [x] User sees a prediction form on the dashboard
- [x] Form accepts: income, age, credit score, employment years
- [x] System validates inputs before submission
- [x] Prediction runs asynchronously via Celery
- [x] User sees a "processing" state while the prediction runs
- [x] Result shows: score, classification (Approved / Review / Declined), confidence

### US-3.2: View Prediction Status `[x]`
**As a** user
**I want to** receive a live result without reloading the page
**So that** I get a seamless experience

**Acceptance Criteria:**
- [x] HTMX polls prediction status endpoint until complete
- [x] Result or error is swapped into the page automatically
- [x] Classification and confidence score displayed inline

---

## Epic 4: Execution History & Comparison

### US-4.1: View Execution History `[x]`
**As a** user
**I want to** see all my past pipeline and prediction executions
**So that** I can track what I have run and review past results

**Acceptance Criteria:**
- [x] User sees paginated list of all their executions
- [x] List shows: date, flow name, status, row count
- [x] User can filter by status and search by flow name
- [x] User can click any execution to view full details
- [x] User can download their full execution history as CSV
- [x] Failed executions show error messages

### US-4.2: Compare Multiple Executions `[x]`
**As a** user
**I want to** compare two or three executions side-by-side
**So that** I can understand how different inputs affect the output

**Acceptance Criteria:**
- [x] User can select executions and navigate to a comparison view
- [x] Page displays execution metadata side-by-side
- [x] Prediction input values (income, age, credit score, employment years) displayed per execution
- [x] Score, classification, and confidence read from `FlowExecution.parameters` (no mocks)
- [x] Input fields that differ across executions are visually highlighted (distinct badge colour)
- [x] User can export comparison as CSV via a dedicated endpoint
- [x] History page shows input summary per row so user can pick meaningful predictions to compare
- [x] Comparison page shows "No predictions yet" empty state with CTA to dashboard when user has 0 predictions
- [x] Comparison page shows "Need at least 2 predictions" state with warning alert and dual CTAs when fewer than 2 IDs are resolved

---

## Epic 5: Admin Monitoring `[x]`

### US-5.1: Usage Dashboard `[x]`
**As an** admin
**I want to** see how the system is being used
**So that** I can understand demand and identify issues

**Acceptance Criteria:**
- [x] Admin dashboard shows: total executions, success rate, average run time
- [x] Breakdown by user and by pipeline type
- [x] Charts show execution trends over time

### US-5.2: View All Execution Logs `[x]`
**As an** admin
**I want to** see detailed logs from all executions
**So that** I can troubleshoot failures and optimise performance

**Acceptance Criteria:**
- [x] Admin can view logs for any user's execution
- [x] Logs filterable by user, date range, and status
- [x] Error messages and stack traces visible

---

## Epic 6: UI Component Library `[ ]`

### US-6.1: Reusable Advanced DataTable `[ ]`
**As a** developer
**I want** a reusable DataTable template component
**So that** every list view in the application gets consistent advanced filtering, column control, and bulk actions without duplicating logic

**Acceptance Criteria:**
- [ ] Column definitions passed from view context control which fields are shown, their labels, and whether they are sortable / filterable / hideable
- [ ] Column visibility toggled per-user via browser localStorage (persists across page loads, keyed by `table_id`)
- [ ] Filter builder supports operators: contains, not contains, equals, not equals, starts with, ends with, is empty, is not empty (text); eq, neq, gt, gte, lt, lte (number); eq, before, after (datetime); eq, neq (choice)
- [ ] Multiple filters combinable (AND logic); each shown as a dismissable chip in an active-filters bar
- [ ] Filter state encoded in URL query params so filtered views are shareable and browser back/forward works
- [ ] Bulk action bar appears when ≥ 1 row is checked; actions are enabled/disabled based on `min_select` / `max_select` per action
- [ ] Bulk actions configurable per table (GET navigation or POST form submission)
- [ ] Sorting via column header click; sort state encoded in URL params
- [ ] HTMX fetches filtered / sorted / paginated results without full page reload
- [ ] Alpine.js manages all client-side interactive state (filter builder rows, column toggles, selected IDs)
- [ ] Component requires no changes to base templates; added via `{% include %}` with a `table_config` context dict

---

## Technical User Stories

### US-T1: Asynchronous Pipeline Execution `[x]`
**As a** system
**I want** pipelines to run in background workers
**So that** the web process stays responsive under concurrent load

**Acceptance Criteria:**
- [x] Celery workers execute doit tasks via subprocess
- [x] Each execution uses an isolated S3 path keyed by `run_id`
- [x] Worker captures stdout/stderr and extracts row count from notebook output
- [x] Max 2 retries with 30-second back-off on failure

### US-T2: S3 Data Lake Storage `[x]`
**As a** system
**I want** all pipeline input and output stored in S3
**So that** data is durable and queryable without loading into the database

**Acceptance Criteria:**
- [x] Input files uploaded to `s3://bucket/raw/flows/...`
- [x] Pipeline outputs written to `s3://bucket/processed/flows/.../output.parquet`
- [x] DuckDB queries S3 Parquet directly for analytics

### US-T3: Responsive Web Interface `[x]`
**As a** user
**I want** the application to work on desktop and mobile
**So that** I can run predictions from anywhere

**Acceptance Criteria:**
- [x] UI built with Tailwind CSS + DaisyUI, responsive across breakpoints
- [x] HTMX used for dynamic updates without full page reloads
- [x] Navigation adapts to authenticated vs unauthenticated state

---

## Epic 7: User Experience Enhancements

### US-7.1: Save and Reuse Prediction Inputs `[ ]`
**As a** power user
**I want to** save my prediction inputs as a named preset and reload them later
**So that** I don't have to re-enter the same values for recurring predictions

**Acceptance Criteria:**
- [ ] User can click "Save as Preset" on the prediction form to name and save current inputs
- [ ] User can select a saved preset from a dropdown to pre-fill the prediction form
- [ ] User can view, rename, and delete their presets from the Settings page
- [ ] Presets are private to each user

### US-7.2: Email Notification for Failed Executions `[ ]`
**As a** user
**I want to** receive an email when my pipeline or prediction fails
**So that** I know a long-running job has failed without having to check the history page

**Acceptance Criteria:**
- [ ] User receives an email when an execution reaches terminal FAILED status
- [ ] Email contains: flow name, run ID, error message, and a link to the execution detail page
- [ ] User can opt out of failure notifications via a toggle in Settings
- [ ] Notification is only sent once per execution (terminal failure, not on each retry)

### US-7.3: Retry Failed Execution `[ ]`
**As a** user
**I want to** retry a failed execution with the same parameters
**So that** I don't have to re-enter inputs to re-run a transient failure

**Acceptance Criteria:**
- [ ] A "Retry" button appears on the execution detail page when status is FAILED
- [ ] Clicking Retry creates a new execution with the same flow name, inputs, and S3 path
- [ ] The new execution is dispatched immediately and user is redirected to its detail page

---

### US-T4: Local Frontend Asset Build `[x]`
**As a** developer
**I want** all CSS and JavaScript served from locally-built static files
**So that** the application has no CDN dependencies at runtime and benefits from tree-shaking and cache-busting

**Acceptance Criteria:**
- [x] Tailwind CSS + DaisyUI compiled to `backend/static/dist/main.css` via Tailwind CLI
- [x] HTMX vendored to `backend/static/vendor/htmx.min.js` via npm build step
- [x] CDN `<link>` and `<script>` tags replaced with `{% static %}` references in `base.html`
- [x] `django-compressor` installed with `COMPRESS_OFFLINE=True` for staging/prod
- [x] Multi-stage Dockerfile builds frontend assets before collecting static files
- [x] `frontend-build` Docker service available in `docker-compose.yml`
- [x] `just frontend-build` command documented for local dev

### US-T5: Staging Environment `[x]`
**As a** developer
**I want** a shared staging environment on EC2 with SSL
**So that** the team can test deployments and demo features before production

**Acceptance Criteria:**
- [x] `docker-compose.staging.yml` defines Traefik service with Let's Encrypt SSL
- [x] `backend/config/settings/staging.py` sets `DEBUG=False`, WhiteNoise, HSTS
- [x] `traefik/traefik.yml` configures HTTP→HTTPS redirect and ACME HTTP challenge
- [x] All services (web, celery-worker, Redis, PostgreSQL, RustFS) start correctly
- [x] EC2 provisioning and initial deploy steps documented in `docs/deployment/staging.md`

---

---

## Epic 8: Notification Management (BL-019) `[x]`

### US-8.1: In-App Notification Centre `[x]`
**As a** user
**I want to** see in-app notifications when my executions complete or fail
**So that** I know the outcome without checking email or the history page

**Acceptance Criteria:**
- [x] A bell icon in the navbar shows a badge with the count of unread notifications
- [x] Clicking the bell opens a dropdown showing up to 5 recent notifications
- [x] Each notification links to the related execution detail page
- [x] A "View all" link navigates to a full notification list page at `/accounts/notifications/`
- [x] The full list page shows all notifications, newest first, with a "Mark all as read" action
- [x] Individual notifications can be marked as read by clicking them
- [x] The unread badge disappears when all notifications are read

### US-8.2: Notification Preferences `[x]`
**As a** user
**I want to** control how I am notified about execution outcomes
**So that** I only receive the notifications I care about through the channels I prefer

**Acceptance Criteria:**
- [x] Settings page shows four toggles: "Notify on failure", "Notify on success", "In-app notifications", "Email notifications"
- [x] Each toggle persists independently; changes take effect on next execution
- [x] When "In-app notifications" is off, no Notification records are created
- [x] When "Email notifications" is off, no emails are sent
- [x] Notification on success is opt-in (default off); notification on failure is opt-in (default on)

---

## Epic 9: Feature Flags (BL-020) `[x]`

### US-9.1: Feature Flag Administration `[x]`
**As an** admin
**I want to** toggle features on or off per user or by percentage rollout
**So that** I can safely release new features incrementally without a code deploy

**Acceptance Criteria:**
- [x] Flags are managed entirely through Django Admin (`/admin/`)
- [x] Each flag has: name (slug), description, global enabled toggle, rollout percentage (0–100), and an optional explicit user list
- [x] Flag resolution order: explicit user list → rollout percentage → global toggle
- [x] Rollout percentage uses deterministic hashing so a given user always gets the same result
- [x] A `{% flag "name" %}...{% endflag %}` template tag conditionally renders content
- [x] A `@require_flag("name")` view decorator returns 404 when the flag is off for that user
- [x] Flag lookups are cached (Redis, 5-minute TTL) with cache invalidation on admin save

---

---

## Epic 10: Production Environment (BL-018) `[x]`

### US-T6: Production Deployment `[x]`
**As a** developer
**I want** a production-ready Docker Swarm deployment with automated database backups and a CI/CD pipeline
**So that** the application can be safely deployed, scaled, and recovered from failure in production

**Acceptance Criteria:**
- [x] `backend/config/settings/production.py` has full security headers, WhiteNoise static serving, HSTS, and structured logging to stdout
- [x] `docker-stack.yml` is Swarm-compatible with `deploy:` keys (replicas, restart policy, health checks) for web, celery-worker, and flower services
- [x] A `pg-backup` service runs scheduled `pg_dump` exports to S3 (triggered via cron on the manager node)
- [x] `GET /health/` endpoint in `core/views.py` returns `{"status": "ok"}` and is used by load balancer health checks
- [x] GitHub Actions workflow builds the Docker image, pushes to GHCR, and rolls out to production via `docker service update`
- [x] Swarm init and node join procedure documented in `docs/deployment/production.md`
- [x] Backup restore procedure documented in `docs/deployment/production.md`

### US-T7: Infrastructure as Code & Secrets Management `[ ]`
**As a** developer
**I want** Terraform to provision production AWS infrastructure and 1Password to manage all secrets
**So that** infrastructure is reproducible, secrets are never stored in files or CI, and deploys are CI-agnostic

**Acceptance Criteria:**
- [ ] `terraform/` provisions VPC, EC2 (t3.medium, ap-southeast-2), security groups, Elastic IP, S3 backup bucket, and IAM instance profile
- [ ] SSH key pair sourced from 1Password via the 1Password Terraform provider — no key material in the repo
- [ ] S3 remote state backend with versioning and encryption; bootstrapped via `just -f deploy/justfile tf-init`
- [ ] `deploy/.env.tpl` uses `op inject` template syntax (`{{ op://Vault/Item/field }}`) — no plaintext secrets in the repo
- [ ] `deploy/justfile` covers: `tf-init`, `tf-plan`, `tf-apply`, `push-env`, `push-stack`, `bootstrap`, `deploy`, `rollback`, `migrate`, `ssh`, `status`, `logs`, `backup`
- [ ] Root `justfile` delegates to `deploy/justfile` via namespaced `prod-*` recipes
- [ ] `gunicorn` added to `backend/pyproject.toml` production dependencies

---

## Epic 11: Structural Design `[x]`

> See [design-review.md](design-review.md) for the full Hickey/Torvalds analysis these stories are derived from.

### US-T11: Separate Pipeline and Prediction Execution Models `[x]`
**As a** developer
**I want** data processing pipelines and credit predictions to be distinct domain concepts with their own data structures
**So that** queries, views, and analytics are unambiguous and the codebase doesn't branch on a string discriminator throughout

**Acceptance Criteria:**
- [x] Prediction inputs (`income`, `age`, `credit_score`, `employment_years`) are stored in typed columns on `FlowExecution` — not in the schemaless `parameters` blob
- [x] Prediction results (score, classification, confidence) are stored in a `PredictionResult` relation with typed columns — queryable without JSON field gymnastics
- [x] `classification` is indexable; "all Declined predictions" is a standard `filter(prediction_result__classification="Declined")` call
- [x] All existing views, tasks, and templates are updated to use the new structure; no behaviour changes

### US-T12: Explicit Pipeline Step Tracking `[x]`
**As a** user
**I want** to see which step of a pipeline is currently running and which step failed
**So that** I can diagnose failures accurately and understand progress without waiting for completion

**As a** developer
**I want** per-step timing and status persisted in the database
**So that** I can answer "which step is slowest" and "where do pipelines most often fail" with a simple query

**Acceptance Criteria:**
- [x] `ExecutionStep` model exists: `execution FK`, `step_name`, `step_index`, `status`, `started_at`, `completed_at`, `output_s3_path`, `error_message`
- [x] `dodo.py` writes step start/end markers to local filesystem; `PipelineRunner` syncs them to `ExecutionStep` records after each pipeline run
- [x] Execution detail shows per-step progress (✓/✗/⟳/— per step with timestamps)
- [x] Failure message is scoped to the failing step via `error_message` on `ExecutionStep`
- [x] Admin can query `ExecutionStep` directly to filter/aggregate by step name and status

### US-T13: Versioned Scoring Model `[x]`
**As a** developer
**I want** the credit scoring algorithm to be stored as data — not as literal numbers in a notebook
**So that** every prediction is permanently linked to the model version that produced it, and weights can be changed without editing code

**Acceptance Criteria:**
- [x] `ScoringModel` entity: `version`, `description`, `weights` (JSON), `thresholds` (JSON), `is_active`, `created_at`, `created_by`
- [x] `PredictionResult` carries a `scoring_model FK`
- [x] `PipelineRunner` injects active `ScoringModel` weights and thresholds into prediction notebook parameters
- [x] Prediction notebook reads weights/thresholds from injected params — no hardcoded values
- [x] Seed migration creates `ScoringModel v1.0` capturing the original hardcoded values
- [x] Admin can view which model version produced any given prediction via `PredictionResult.scoring_model`

### US-T14: Robust Notebook Result Protocol `[x]`
**As a** developer
**I want** notebook results communicated to Django via a structured file, not by parsing stdout
**So that** the contract is explicit, testable, and not fragile to incidental print output from libraries

**Acceptance Criteria:**
- [x] Each final notebook step (`04_aggregate`, `predict_02_score`) writes a `result.json` manifest to a known S3 path
- [x] `PipelineRunner` reads `result.json` from S3 after subprocess exit instead of scanning stdout
- [x] `_extract_metadata()` removed; replaced by `_read_result_json()` that reads from S3
- [x] Existing stdout logging from notebooks is unaffected — libraries can print freely

### US-T15: Status as an Enforced State Machine `[x]`
**As a** developer
**I want** execution status transitions to be enforced at the model layer
**So that** illegal states (e.g. COMPLETED with no `completed_at`, FAILED → RUNNING) are caught before they reach the database

**Acceptance Criteria:**
- [x] `ExecutionStatus(TextChoices)` defines `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`
- [x] `FlowExecution.transition()` guards valid transitions; raises `ValueError` for invalid ones
- [x] `completed_at` is automatically set on transition to `COMPLETED` or `FAILED`
- [x] `tasks.py` uses `ExecutionStatus` constants instead of raw strings throughout

---

## Epic 12: Accessibility (A11y) `[ ]`


### US-T10: WCAG 2.1 AA Compliance `[ ]`
**As a** user with a disability
**I want** the application to be fully navigable and understandable using assistive technology
**So that** I can run predictions, manage executions, and use all features without relying on a mouse or colour perception

> **Reference:** WCAG 2.1 Level AA (W3C Recommendation); EN 301 549 v3.2.1 (EU accessibility standard); Section 508 (US). The following criteria are directly applicable: 1.1.1, 1.3.1, 1.3.3, 1.4.1, 1.4.3, 2.1.1, 2.4.1, 2.4.3, 2.4.7, 3.3.1, 3.3.2, 4.1.2, 4.1.3.

**Acceptance Criteria:**

- [ ] **Skip navigation** — a "Skip to main content" link is the first focusable element on every page; visible on focus (WCAG 2.4.1)
- [ ] **Icon-only buttons** — all icon-only interactive elements (`<button>`) carry an `aria-label`; `<div role="button">` usages in the navbar (notification bell, user avatar) are replaced with `<button>` elements (WCAG 4.1.2)
- [ ] **Decorative SVGs** — all inline SVG icons used alongside text labels carry `aria-hidden="true"` so screen readers skip them (WCAG 1.1.1)
- [ ] **Async regions** — `#prediction-result`, `#notification-dropdown-items`, and any other container that receives HTMX-injected content carry `aria-live="polite"` so screen readers announce updates (WCAG 4.1.3)
- [ ] **Form error association** — JS-injected validation errors (in `dashboard.html`) use `aria-describedby` to link each input to its error message, matching the pattern already used in `form_input.html` (WCAG 3.3.1)
- [ ] **Modal labelling** — all `<dialog>` modals carry `aria-labelledby` pointing at their `<h3>` title element (WCAG 4.1.2)
- [ ] **Table headers** — empty action-column `<th>` elements carry `scope="col"` and a visually-hidden label (e.g. "Actions"); all `<th>` elements carry `scope` (WCAG 1.3.1)
- [ ] **Pagination** — the active page button carries `aria-current="page"`; the pagination wrapper carries `aria-label="Pagination"` (WCAG 2.4.3)
- [ ] **Active nav items** — sidebar and navbar active links carry `aria-current="page"` (WCAG 2.4.3)
- [ ] **Colour and status** — confirmed by audit that no status or meaning is conveyed by colour alone; all status badges include a text label (already the case — verify and document) (WCAG 1.4.1)
- [ ] **Colour contrast** — automated scan (Axe or Lighthouse) reports zero contrast failures at WCAG AA thresholds (4.5:1 normal text, 3:1 large text) (WCAG 1.4.3)
- [ ] **Keyboard navigation** — full end-to-end task flows (login, run prediction, view history, manage notifications) are completable using keyboard only; no focus traps outside modals (WCAG 2.1.1)
- [ ] **Focus visibility** — all interactive elements have a visible focus ring in all states; no `outline: none` without a replacement (WCAG 2.4.7)
- [ ] **Document landmark** — navbar is wrapped in `<nav aria-label="Main navigation">`; the sidebar is wrapped in `<nav aria-label="Dashboard navigation">` (WCAG 1.3.1)
- [ ] **Automated baseline** — Axe (or equivalent) integrated into CI or run manually; zero critical/serious violations reported before the story is closed

---

## Epic 14: Security — Secrets Management `[ ]`

### US-T9: Audit and Remediate Plaintext Secret Exposure `[ ]`
**As a** developer
**I want to** ensure no secrets are stored or transmitted in plaintext anywhere in the application
**So that** credentials cannot be compromised via source code, logs, output files, or config leakage

> **Reference:** OWASP ASVS v4.0 §2.10 (Service Authentication), §6.1–6.2 (Stored Cryptography);
> OWASP Top 10:2021 A02 — Cryptographic Failures; OWASP Secrets Management Cheat Sheet.

**Acceptance Criteria:**

- [ ] **Source code** — no secrets (API keys, passwords, tokens, DSNs) hardcoded anywhere in the repo; confirmed by a `gitleaks` or `truffleHog` scan with zero high-severity findings (ASVS 2.10.4 / CWE-321)
- [ ] **Settings** — all secrets read exclusively from environment variables or a secrets vault; `settings/base.py` has no literal credential values; `DEBUG=True` cannot reach production
- [ ] **Notebook output** — papermill-executed notebooks write no credentials into injected-parameters cells; verified by inspecting a sample output `.ipynb` from S3 (CWE-312)
- [ ] **Docker Compose / stack files** — no plaintext passwords in `docker-compose.yml`, `docker-compose.staging.yml`, or `docker-stack.yml`; any shown values are placeholders that are overridden at runtime via env files or Docker secrets
- [ ] **CI/CD** — all secrets in GitHub Actions stored as repository secrets (not hardcoded in workflow YAML); secret values never echoed to logs
- [ ] **Logs and telemetry** — Django log handlers, Celery task output, and OpenTelemetry spans scrubbed so `AWS_SECRET_ACCESS_KEY`, `DATABASE_URL`, `SECRET_KEY`, and similar values are never emitted (ASVS 8.3.4)
- [ ] **Database fields** — confirm no sensitive user data (passwords, tokens) stored in plaintext model fields; Django auth uses PBKDF2/Argon2 (ASVS 2.10.3)
- [ ] **Rotation readiness** — document which secrets exist, where they are used, and the rotation procedure for each; confirm app can recover from a secret rotation without downtime

---

## Epic 15: Observability — OpenTelemetry `[x]`

### US-T8: Distributed Tracing & Metrics with OpenTelemetry `[x]`
**As a** developer
**I want** OpenTelemetry instrumentation across Django, Celery, and the OTLP pipeline
**So that** I can trace requests end-to-end, identify slow operations, and diagnose failures in all environments without changing application code

**Acceptance Criteria:**
- [x] `opentelemetry-sdk` and auto-instrumentation packages added to `backend/pyproject.toml`
- [x] Django requests automatically produce traces (HTTP method, URL, status code, DB query spans)
- [x] Celery tasks automatically produce traces (task name, queue, duration, exception details)
- [x] Outbound HTTP calls (boto3/S3, email) produce child spans
- [x] Trace context propagated from Django view → Celery task (distributed trace continuity)
- [x] **Dev:** OTLP exporter sends to a local `otel-collector` sidecar in `docker-compose.yml`; Jaeger UI available at `http://localhost:16686` for visual trace exploration
- [x] **Staging:** same collector pipeline; traces forwarded to stdout (JSON) for CloudWatch ingestion
- [x] **Production:** collector configured to export to a chosen backend (Grafana Tempo / Honeycomb / AWS X-Ray) via environment variable — backend is swappable without code changes
- [x] `OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`, and `OTEL_TRACES_SAMPLER` controlled by environment variables; no hardcoded values in Django settings
- [x] Instrumentation initialised via a Django `AppConfig.ready()` hook — no manual calls in views or tasks
- [x] `otel-collector` service added to `docker-compose.yml` (dev) and `docker-stack.yml` (production)
- [x] Collector config defines per-environment pipelines in `otel/collector-dev.yml`, `otel/collector-staging.yml`, `otel/collector-production.yml`

---

---

## Epic 13: Scoring Model Training & Promotion (Admin) `[ ]`

> Enables admin users to generate synthetic training data, run optimisation rounds, review quality through graphical diagnostics, and promote a winning model to production — all without editing notebook code or touching weights by hand.

### US-13.1: Generate a Synthetic Training Dataset `[~]`
**As an** admin
**I want to** generate a labelled synthetic dataset of credit applicants
**So that** I have realistic, reproducible ground-truth data to train and backtest scoring models against

**Acceptance Criteria:**
- [ ] Admin can navigate to a "Training Datasets" page under the admin area
- [ ] A "Generate Dataset" form accepts: row count (100–100 000), random seed, and an optional description
- [ ] Generation runs as a Celery task; admin sees a "generating…" progress indicator
- [ ] Dataset is produced using **Faker** for demographic fields and a configurable ground-truth scoring function (same normalisation logic as the live model) to derive synthetic outcome labels (`Approved` / `Review` / `Declined`)
- [ ] All data manipulation (generation, validation, storage) uses **Polars** — no pandas
- [ ] Output is written as a Parquet file to `s3://{bucket}/training/datasets/{dataset_id}/data.parquet`
- [ ] A `TrainingDataset` record is created with: version slug, description, row count, S3 path, generation seed, `created_at`, `created_by`
- [ ] Admin can view a statistical summary of the generated dataset (feature distributions, class balance)
- [ ] Admin can delete a dataset (with confirmation); associated S3 file is cleaned up

### US-13.2: Run a Model Training Round `[~]`
**As an** admin
**I want to** run a weight-and-threshold optimisation against a training dataset
**So that** I can discover better-performing scoring configurations without guessing by hand

**Acceptance Criteria:**
- [ ] Admin can start a training run from the dataset detail page
- [ ] Training run form accepts: a label (e.g. "round_1"), optimisation target (`gini` / `ks_statistic` / `f1_review`), and a UMAP visualisation toggle
- [ ] Training runs as a Celery task using **Polars** for all data manipulation and **DuckDB** for intermediate analytics queries — no pandas, no scikit-learn
- [ ] Optimisation uses **scipy.optimize** (or **optuna**) to search weight space; constraints: weights sum to 1.0, each weight ∈ [0.05, 0.70]
- [ ] Threshold optimisation searches the approval/review cutpoints to maximise the chosen target metric on a held-out 20 % validation split
- [ ] If the UMAP toggle is on, a 2-D **UMAP** embedding of the 4-feature space (coloured by ground-truth outcome) is computed and its coordinates stored for chart rendering
- [ ] Training artefacts (optimal weights, thresholds, UMAP coordinates, metric curves) written to `s3://{bucket}/training/runs/{run_id}/` as Parquet / JSON
- [ ] A `ModelTrainingRun` record is created with: label, dataset FK, status, optimisation target, candidate weights JSON, candidate thresholds JSON, S3 artefact path, `created_at`, `created_by`
- [ ] Admin can view all training runs for a dataset in a list, sortable by key quality metric

### US-13.3: Backtest a Training Run `[~]`
**As an** admin
**I want to** evaluate a training run's candidate model against a held-out test set
**So that** I can measure real generalisation performance before deciding whether to promote it

**Acceptance Criteria:**
- [ ] Admin can trigger a backtest from the training run detail page
- [ ] Backtest uses the 20 % held-out split (seeded identically to training) — not the training fold
- [ ] Backtest computes (using Polars / DuckDB, no scikit-learn):
  - Accuracy, precision, recall, F1 per class (`Approved` / `Review` / `Declined`)
  - Gini coefficient and KS statistic (rank-ordering power)
  - Confusion matrix (3 × 3)
  - Score distribution histogram per outcome class
- [ ] All backtest metrics persisted to a `ModelBacktestResult` record linked to the training run
- [ ] Admin can compare backtest metrics across multiple training runs in a summary table (DuckDB-backed)

### US-13.4: Review Model Quality with Visual Diagnostics `[~]`
**As an** admin
**I want to** see graphical quality and risk summaries for a training run
**So that** I can make an informed, evidence-based decision about whether to promote it

**Acceptance Criteria:**
- [ ] Training run detail page renders **Altair** charts served as JSON specs (Vega-Embed on the frontend — no server-side image rendering):
  - **UMAP scatter** — 2-D applicant embedding coloured by ground-truth outcome (shown only when UMAP toggle was enabled at training time)
  - **Score distribution** — overlapping density/histogram of scores by outcome class, with threshold markers
  - **Confusion matrix heatmap** — 3 × 3 grid with colour intensity proportional to cell count
  - **Metric bar chart** — precision / recall / F1 per class, side-by-side bars
  - **Gini / KS trend** — line chart of Gini and KS across all completed training rounds for the same dataset (model comparison view)
- [ ] All charts are derived from Parquet artefacts in S3 via DuckDB — no raw data loaded into Django memory
- [ ] Charts degrade gracefully: if UMAP coordinates are absent, the UMAP panel shows a "not computed" message
- [ ] Admin can download the backtest result as CSV from the detail page

### US-13.5: Promote a Training Run to Active Scoring Model `[ ]`
**As an** admin
**I want to** promote a successful training run to become the live scoring model
**So that** all subsequent predictions use the newly optimised weights and thresholds

**Acceptance Criteria:**
- [ ] A "Promote" button appears on training run detail page only when backtest status is `COMPLETED`
- [ ] Clicking Promote shows a confirmation modal displaying the candidate weights, thresholds, and key backtest metrics side-by-side with the currently active `ScoringModel`
- [ ] On confirmation, the system:
  1. Creates a new `ScoringModel` record using the candidate weights and thresholds, with a version slug auto-incremented from the current active model (e.g. `v1.0` → `v1.1`)
  2. Sets the new model's `is_active = True` and deactivates the previous active model
  3. Creates a `ModelPromotion` audit record linking training run → new scoring model, with `promoted_by` and `promoted_at`
- [ ] All subsequent prediction executions pick up the new active `ScoringModel` automatically (no restart required)
- [ ] The training run detail page shows "Promoted → ScoringModel v1.1" with a link to the admin scoring model view

### US-13.6: View Training History and Compare Rounds `[ ]`
**As an** admin
**I want to** see all training rounds across all datasets with their key metrics at a glance
**So that** I can track experimentation history and understand how model quality has evolved

**Acceptance Criteria:**
- [ ] A "Training History" page lists all `ModelTrainingRun` records: dataset, round label, optimisation target, Gini, KS, F1 (review class), status, promotion status, `created_at`
- [ ] Table is sortable by any metric column; backed by a DuckDB query over `ModelBacktestResult`
- [ ] Promoted runs are visually distinguished (badge showing the resulting `ScoringModel` version)
- [ ] Admin can delete a training run (with confirmation) provided it has not been promoted; associated S3 artefacts are cleaned up
- [ ] "Compare" action allows selecting 2–4 runs and rendering a side-by-side Altair bar chart of key metrics

---

## Epic 16: Pluggable Pipeline Orchestration `[ ]`

### US-16.1: Use Prefect as an Alternative Pipeline Backend `[ ]`
**As a** developer
**I want to** configure Prefect as a drop-in alternative to doit for pipeline execution
**So that** I can use Prefect's native UI, scheduling, and retry semantics without changing any Django model or tracking logic

**Acceptance Criteria:**
- [ ] A `PIPELINE_BACKEND` Django setting switches between `"doit"` (default, unchanged behaviour) and `"prefect"` — no other code change required for the swap
- [ ] `PipelineRunner` dispatches to a `PipelineBackend` protocol; `DoitBackend` encapsulates the existing subprocess logic; `PrefectBackend` implements the same interface using the Prefect Python API
- [ ] Each `FlowExecution` maps to a Prefect flow run; the Prefect flow run UUID is stored on `FlowExecution.external_run_id` (nullable — null when using doit)
- [ ] Each Prefect task maps to an `ExecutionStep`; step status (`RUNNING` / `COMPLETED` / `FAILED`) is written back to `ExecutionStep` via a Prefect state hook — identical fields to the doit path
- [ ] A Prefect flow run can be cancelled via the existing `cancel` view; `PrefectBackend.cancel()` calls the Prefect API with the stored `external_run_id`
- [ ] `docker-compose.yml` includes an optional `prefect-server` and `prefect-worker` service pair; both are no-ops unless `PIPELINE_BACKEND=prefect` is set
- [ ] All `FlowExecution` / `ExecutionStep` fields remain identical regardless of backend — the abstraction is in the service layer only

---

## Epic 17: Conversational Dashboard Builder `[ ]`

> Users own a personal dashboard they build conversationally. A fastMCP server exposes prefab UI tools to an AI; the result is rendered in a sandboxed iframe. Token limits protect shared API capacity. This epic will be decomposed into implementation-ready BL items once wireframes and threat model are approved.

### US-17.1: Build a Personal Dashboard by Describing It `[ ]`
**As a** user
**I want to** describe the charts and metrics I care about in natural language
**So that** I can build and own a custom dashboard view of my data without writing code or configuring anything technical

**Acceptance Criteria:**
- [ ] A "My Dashboard" page presents a chat panel alongside a live preview iframe
- [ ] User messages are forwarded to an AI (via a fastMCP session); the AI calls prefab MCP tools (`add_widget`, `update_widget`, `remove_widget`) to build the dashboard
- [ ] All available widgets are prefab (`METRIC_CARD`, `LINE_CHART`, `BAR_CHART`, `TABLE`, `SCORE_DISTRIBUTION`) — the AI cannot inject arbitrary HTML, CSS, or script content
- [ ] Each widget's data source is drawn from the user's own `FlowExecution` and `PredictionResult` records — the AI cannot request data from other users
- [ ] Dashboard state persists across sessions via a `UserDashboard` + `DashboardWidget` model; one active dashboard per user
- [ ] User can reset their dashboard to empty from the settings page

### US-17.2: Dashboard Rendered in a Sandboxed Iframe `[ ]`
**As a** platform operator
**I want** user-defined dashboards rendered in a sandboxed iframe with strict Content Security Policy
**So that** no user-defined content can execute arbitrary scripts or affect the host page

**Acceptance Criteria:**
- [ ] Dashboard grid is served from a dedicated URL (`/dashboard/render/<id>/`) with no navigation, no forms, and no HTMX outside the iframe
- [ ] The `<iframe>` carries `sandbox="allow-scripts allow-same-origin"` and the parent page sets `Content-Security-Policy: frame-src 'self'`
- [ ] The render endpoint sets its own strict CSP: `script-src 'self'`; no `unsafe-inline`; no external origins
- [ ] Widget data is consumed as JSON from scoped API endpoints — no raw DuckDB query strings are exposed to the client

### US-17.3: Per-User Token Budget for MCP Sessions `[ ]`
**As a** platform operator
**I want** each user's conversational dashboard sessions to consume from a configurable token budget
**So that** no single user can exhaust shared AI API capacity

**Acceptance Criteria:**
- [ ] A `McpSession` record tracks `tokens_used` and `tokens_budget` per user per session
- [ ] Default budget is set via `MCP_SESSION_TOKEN_BUDGET` Django setting; admin can override per user
- [ ] Before each AI dispatch, remaining budget is checked; a structured error is returned (not an exception) when budget is exhausted
- [ ] Budget consumption is visible to the user as a usage indicator in the chat panel
- [ ] Exhausted sessions can be reset by the user (starting a new session) or by an admin

---

## Epic 18: High-Performance Compute (Mojo) `[ ]`

### US-18.1: Define Pipeline Steps That Execute Mojo Scripts `[ ]`
**As a** developer
**I want to** mark a pipeline step as a Mojo execution target
**So that** I can use Mojo's SIMD and parallelism for compute-heavy transforms without changing how step status, results, or errors are tracked in Django

**Acceptance Criteria:**
- [ ] `ExecutionStep.step_type` TextChoices: `NOTEBOOK` (default, backwards-compatible) / `MOJO`
- [ ] A `mojo-compute` Docker service runs a lightweight HTTP API accepting `{"run_id", "script", "s3_input", "s3_output"}`; Mojo scripts live in `mojo/` at workspace root
- [ ] `PipelineRunner` dispatches to the Mojo container via HTTP when `step_type == MOJO`; all other steps use the existing papermill path — no change to callers
- [ ] Mojo scripts follow the `result.json` protocol (BL-029): write `result.json` to the step's S3 output path on completion
- [ ] `ExecutionStep` fields (`started_at`, `completed_at`, `output_s3_path`, `error_message`, `status`) are populated identically to notebook steps — no UI or admin changes required
- [ ] The Mojo container has no database access; it reads from S3 and writes to S3 only
- [ ] Migration adding `step_type` is non-breaking: existing rows default to `"notebook"`

---

## MVP Scope Summary

| Area | Status |
|------|--------|
| User registration & login | Complete (email confirmation implemented) |
| File upload & pipeline execution | Complete |
| Pipeline status polling | Complete |
| View & download results | Complete |
| Credit prediction form & scoring | Complete |
| Execution history & detail | Complete |
| Execution comparison | Complete |
| Admin monitoring dashboard | Complete |
| Input presets | Complete |
| Email notifications for failures | Complete |
| Retry failed execution | Complete |
| Superuser management | Complete |
| In-app notification centre & preferences | Complete |
| Feature flags (per-user & environment toggles) | Complete |
| Structural design — model split, step tracking, scoring model | Not started |
| Accessibility (WCAG 2.1 AA) | Not started |
| Secrets management audit | Not started |
| Scoring model training & promotion (admin) | Not started |
