# Product Backlog

Derived from [user-stories.md](user-stories.md). Items are ordered by priority within each tier. Each item references the parent user story and follows the [development workflow](../CLAUDE.md) before implementation begins.

**Effort sizing:** S = ~half day · M = 1–2 days · L = 3–5 days · XL = 1–2 weeks

---

## Tier 1 — Complete the MVP (immediate)

These close gaps in already-delivered epics. Low risk, small scope.

---

### ~~BL-001 · Password Reset Flow~~ `M` ✓ Complete


**User story:** US-1.1
**Value:** Users who forget their password currently have no self-service path — an admin must intervene.

**Scope:**
- Add Django's built-in password reset URLs (`django.contrib.auth.urls`) to `config/urls.py`
- Wire up email backend (SMTP or console for dev)
- Template: `accounts/password_reset.html`, `accounts/password_reset_done.html`, `accounts/password_reset_confirm.html`, `accounts/password_reset_complete.html` — all extending `core/base_public.html`
- Link "Forgot password?" on the login page

**Docs required before starting:**
- Wireframe: `password_reset_page.excalidraw`

---

### ~~BL-002 · S3 Cleanup on Execution Delete~~ `S` ✓ Complete
**User story:** US-2.4
**Value:** Deleting an execution currently orphans its S3 files; storage grows unbounded.

**Scope:**
- Override `FlowExecution.delete()` (or use a `post_delete` signal) to remove `s3_input_path` and `s3_output_path` objects from S3
- Handle the case where S3 objects are already absent (idempotent)
- Add test coverage in `test_models.py`
- Use daisy_ui modals for confirmation of delete.

**No new wireframe or diagram needed.**

---

### BL-003 · Presigned S3 Download URLs `S`
**User story:** US-2.3
**Value:** Download links currently expose internal S3 paths directly; presigned URLs scope access and set an expiry.

**Scope:**
- `FlowExecution.generate_download_url()` is already implemented — wire it into the download view (`download_results`) instead of streaming via Django
- Support CSV, Parquet, and JSON with appropriate `Content-Disposition` headers
- URL expiry: 1 hour (configurable via settings)

**No new wireframe or diagram needed.**

---

### BL-004 · Export Execution History as CSV `S`
**User story:** US-4.1
**Value:** Users frequently want to take their history into a spreadsheet.

**Scope:**
- Add `GET /flows/history/export/` endpoint
- Query `FlowExecution` for the authenticated user, serialise to CSV (Python `csv` module)
- Return as `Content-Disposition: attachment; filename=history.csv`
- Add "Export CSV" button to `history.html`

**No new wireframe needed — add button to existing history wireframe.**

---

### BL-005 · Prediction Comparison — Input & Score Detail `M`
**User story:** US-4.2
**Value:** The comparison page exists but only shows metadata; the key value is seeing how different inputs produced different scores.

**Scope:**
- For prediction executions, extract input values and score from `FlowExecution.parameters` and display them side-by-side in `comparison.html`
- Highlight differing input values visually (e.g. badge colour)
- Add "Export comparison as CSV" button (single endpoint, generates 2–3 column CSV)

**Update wireframe:** `comparison_page_user.excalidraw` — sketch the input/score rows.

---

## Tier 2 — Auth & Access Control

Prerequisite for any multi-user or admin work.

---

### BL-006 · Superuser User Management UI `L`
**User story:** US-1.2
**Value:** Currently superusers must use Django Admin (`/admin/`) to manage users — there is no first-class UI.

**Scope:**
- New app page: `accounts/user_list.html` (superuser only, `@user_passes_test`)
- List all users: email, date joined, active status, last login
- Actions per user: activate / deactivate, reset password (trigger password-reset email)
- Filter by active/inactive
- No new model needed — uses Django's built-in `User`

**Docs required before starting:**
- Wireframe: `superuser_user_management.excalidraw`
- Sequence diagram: `docs/sequences/superuser_user_management.mmd`

---

### BL-007 · Registration Email Confirmation `M`
**User story:** US-1.1
**Value:** Prevents fake accounts; confirms email ownership before granting access.

**Scope:**
- On signup, set `user.is_active = False` and send a confirmation email with a signed token (`django.core.signing`)
- Add confirmation view: `GET /accounts/confirm-email/<token>/` — activates the account
- Template: `accounts/confirm_email.html`, `accounts/email_confirmation_sent.html`
- Consider: what happens if user tries to log in before confirming?

**Depends on:** BL-001 (email backend must be configured)

**Docs required before starting:**
- Wireframe: `email_confirmation_page.excalidraw`
- Sequence diagram: `docs/sequences/registration_email_confirmation.mmd`

---

## Tier 3 — Admin Monitoring

Requires Tier 2 access control to be meaningful in a multi-user environment.

---

### BL-008 · Admin Monitoring Dashboard `L`
**User story:** US-5.1
**Value:** Admins have no visibility into system health or usage trends without querying the database directly.

**Scope:**
- New page: `flows/admin_dashboard.html` (staff-only, `@staff_member_required`)
- Stats cards: total executions, success rate, average run time (query `FlowExecution`)
- Breakdown table: executions by user (last 30 days)
- Breakdown table: executions by flow type (pipeline vs predict_pipeline)
- Time-series chart: daily execution count for last 30 days (use Chart.js or a simple HTML table — no new JS dependency needed)
- No new model needed — all data available in `FlowExecution`

**Docs required before starting:**
- Wireframe: `admin_dashboard.excalidraw`
- Update `docs/data-model.mmd` if any new fields are added

---

### BL-009 · Admin Execution Log Viewer `M`
**User story:** US-5.2
**Value:** When a user reports a failed execution, admins currently have no UI to inspect it — they must check Celery/Flower or the database.

**Scope:**
- Extend the admin dashboard (BL-008) or add a dedicated `flows/admin_executions.html` page
- List all executions across all users with filters: user, date range, status
- Execution detail shows: user, inputs (`parameters`), error message, celery task ID, timestamps
- Link through to Flower (`/flower/`) for Celery-level detail

**Depends on:** BL-008

**No new model needed.** Update admin dashboard wireframe to include this view.

---

## Tier 4 — User Experience Enhancements

Valuable but not blocking any core workflow.

---

### BL-010 · Input Presets (Save & Reuse Prediction Inputs) `L`
**User story:** US-5.2 (original backlog)
**Value:** Power users who run many predictions with similar inputs must re-enter values each time.

**Scope:**
- New model: `InputPreset` (user FK, name, `input_values` JSONField, created_at)
- Migration required
- Dashboard form: "Save as preset" button → modal with preset name input
- Dashboard form: "Load preset" dropdown → populates form fields via HTMX
- Manage presets: list, rename, delete (settings page or dedicated partial)

**Docs required before starting:**
- Update `docs/data-model.mmd` to add `InputPreset`
- Wireframe: update `dashboard_user_loggedin.excalidraw` to show preset controls
- Sequence diagram: `docs/sequences/input_presets.mmd`

---

### BL-011 · Email Notifications for Failed Executions `M`
**User story:** US-7.2 (original backlog)
**Value:** Users don't know a long-running pipeline has failed unless they check the history page.

**Scope:**
- In `run_pipeline_task` and `run_prediction_task`, send an email on terminal `FAILED` status
- Use Django's `send_mail` with a simple text template
- Email includes: flow name, run ID, error message, link to execution detail page
- Configurable opt-out: add `notify_on_failure` boolean to `accounts/settings.html`

**Depends on:** BL-001 (email backend)

**Docs required before starting:**
- Sequence diagram: update `docs/sequences/pipeline_execution.mmd` to show notification branch

---

### BL-012 · Retry Failed Execution `S`
**User story:** US-4.3 (original backlog)
**Value:** Users must re-enter all inputs to re-run a failed prediction; retrying with the same parameters requires a button, not a form.

**Scope:**
- Add `POST /flows/execution/<uuid>/retry/` endpoint
- Clone the `FlowExecution` record (new UUID, same `parameters` and `flow_name`), dispatch the appropriate Celery task
- "Retry" button on `execution_detail.html` (only visible when `status=FAILED`)

**No new model or wireframe needed.** Update `execution_detail_page_user.excalidraw` to show the retry button.

---

## Backlog Summary

| ID | Title | Tier | Effort | Depends on |
|----|-------|------|--------|------------|
| ~~BL-001~~ | ~~Password reset flow~~ | 1 | M | — |
| ~~BL-002~~ | ~~S3 cleanup on delete~~ | 1 | S | — |
| BL-003 | Presigned download URLs | 1 | S | — |
| BL-004 | Export history as CSV | 1 | S | — |
| BL-005 | Prediction comparison detail | 1 | M | — |
| BL-006 | Superuser user management UI | 2 | L | — |
| BL-007 | Registration email confirmation | 2 | M | BL-001 |
| BL-008 | Admin monitoring dashboard | 3 | L | BL-006 |
| BL-009 | Admin execution log viewer | 3 | M | BL-008 |
| BL-010 | Input presets | 4 | L | — |
| BL-011 | Email notifications for failures | 4 | M | BL-001 |
| BL-012 | Retry failed execution | 4 | S | — |
