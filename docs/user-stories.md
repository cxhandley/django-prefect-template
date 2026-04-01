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

### US-4.2: Compare Multiple Executions `[~]`
**As a** user
**I want to** compare two or three executions side-by-side
**So that** I can understand how different inputs affect the output

**Acceptance Criteria:**
- [x] User can select executions and navigate to a comparison view
- [x] Page displays execution metadata side-by-side
- [ ] Prediction input values (income, age, credit score, employment years) displayed per execution
- [ ] Score, classification, and confidence read from `FlowExecution.parameters` (no mocks)
- [ ] Input fields that differ across executions are visually highlighted (distinct badge colour)
- [ ] User can export comparison as CSV via a dedicated endpoint
- [ ] History page shows input summary per row so user can pick meaningful predictions to compare
- [ ] Comparison page shows "No predictions yet" empty state with CTA to dashboard when user has 0 predictions
- [ ] Comparison page shows "Need at least 2 predictions" state with warning alert and dual CTAs when fewer than 2 IDs are resolved

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

## MVP Scope Summary

| Area | Status |
|------|--------|
| User registration & login | Complete (email confirmation implemented) |
| File upload & pipeline execution | Complete |
| Pipeline status polling | Complete |
| View & download results | Complete |
| Credit prediction form & scoring | Complete |
| Execution history & detail | Complete |
| Execution comparison | Partial |
| Admin monitoring dashboard | Complete |
| Input presets | Not started |
| Email notifications | Not started |
| Superuser management | Complete |
