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

## Epic 10: Production Environment (BL-018) `[ ]`

### US-T6: Production Deployment `[~]`
**As a** developer
**I want** a production-ready Docker Swarm deployment with automated database backups and a CI/CD pipeline
**So that** the application can be safely deployed, scaled, and recovered from failure in production

**Acceptance Criteria:**
- [x] `backend/config/settings/production.py` has full security headers, WhiteNoise static serving, HSTS, and structured logging to stdout
- [x] `docker-stack.yml` is Swarm-compatible with `deploy:` keys (replicas, restart policy, health checks) for web, celery-worker, and flower services
- [x] A `pg-backup` service runs scheduled `pg_dump` exports to S3 (triggered via cron on the manager node)
- [x] `GET /health/` endpoint in `core/views.py` returns `{"status": "ok"}` and is used by load balancer health checks
- [x] GitHub Actions workflow builds the Docker image, pushes to GHCR, and rolls out to production via `docker service update`
- [ ] Swarm init and node join procedure documented in `docs/deployment/production.md`
- [ ] Backup restore procedure documented and tested against staging

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
