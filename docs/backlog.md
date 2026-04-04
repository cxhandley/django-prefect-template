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

### ~~BL-003 · Presigned S3 Download URLs~~ `S` ✓ Complete
**User story:** US-2.3
**Value:** Download links currently expose internal S3 paths directly; presigned URLs scope access and set an expiry.

**Scope:**
- `FlowExecution.generate_download_url()` is already implemented — wire it into the download view (`download_results`) instead of streaming via Django
- Support CSV, Parquet, and JSON with appropriate `Content-Disposition` headers
- URL expiry: 1 hour (configurable via settings)

**No new wireframe or diagram needed.**

---

### ~~BL-004 · Export Execution History as CSV~~ `S` ✓ Complete
**User story:** US-4.1
**Value:** Users frequently want to take their history into a spreadsheet.

**Scope:**
- Add `GET /flows/history/export/` endpoint
- Query `FlowExecution` for the authenticated user, serialise to CSV (Python `csv` module)
- Return as `Content-Disposition: attachment; filename=history.csv`
- Add "Export CSV" button to `history.html`

**No new wireframe needed — add button to existing history wireframe.**

---

### ~~BL-005 · Prediction Comparison — Input & Score Detail~~ `M` ✓ Complete
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

### ~~BL-006 · Superuser User Management UI~~ `L` ✓ Complete
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

### ~~BL-007 · Registration Email Confirmation~~ `M` ✓ Complete
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

### ~~BL-008 · Admin Monitoring Dashboard~~ `L` ✓ Complete
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

### ~~BL-009 · Admin Execution Log Viewer~~ `M` ✓ Complete
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

### ~~BL-010 · Input Presets (Save & Reuse Prediction Inputs)~~ `L` ✓ Complete
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

### ~~BL-011 · Email Notifications for Failed Executions~~ `M` ✓ Complete
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

### ~~BL-012 · Retry Failed Execution~~ `S` ✓ Complete
**User story:** US-4.3 (original backlog)
**Value:** Users must re-enter all inputs to re-run a failed prediction; retrying with the same parameters requires a button, not a form.

**Scope:**
- Add `POST /flows/execution/<uuid>/retry/` endpoint
- Clone the `FlowExecution` record (new UUID, same `parameters` and `flow_name`), dispatch the appropriate Celery task
- "Retry" button on `execution_detail.html` (only visible when `status=FAILED`)

**No new model or wireframe needed.** Update `execution_detail_page_user.excalidraw` to show the retry button.

---

---

## Tier 4 (continued) — User Experience Enhancements

---

### ~~BL-014 · UI Polish — Button Padding, Spacing & Visual Consistency~~ `S` ✓ Complete

**Value:** Several UI elements have inconsistent padding and margins, making the interface feel unfinished. Fixing these increases perceived quality without touching any backend logic.

**Known issues to address:**
- Prediction form action buttons (`Run Prediction`, `Save as Preset`) have inconsistent padding vs adjacent controls
- Spacing between form field labels and inputs varies across pages
- Badge and tag sizing is inconsistent in history and comparison tables
- Mobile viewport: sidebar collapse leaves content partially obscured on small screens

**Scope:**
- Audit all pages with browser DevTools at 1280px and 375px (mobile)
- Apply consistent DaisyUI spacing utilities (`gap-*`, `p-*`, `space-y-*`)
- No new components — fix existing templates only
- No backend changes

**No new wireframe needed** — reference existing DaisyUI spacing guidelines.

---

### ~~BL-015 · Prediction Form UX — Disable During Run & Fix Cancel Behaviour~~ `S` ✓ Complete

**Value:** The prediction form stays active while a prediction is running, allowing duplicate submissions. Closing the "Compare with Another" modal also gives the visual impression the prediction is restarting.

**Known issues:**
1. **Form stays active during run** — After clicking "Run Prediction", the form inputs and button remain enabled. The user can click again and trigger a second parallel prediction. The form should be visually disabled (greyed out, button shows spinner) until a result or error is shown.
2. **Compare modal cancel flicker** — Closing the Compare Predictions modal briefly makes the result area appear to reset or re-render. Investigate whether the `<dialog>` close event is bubbling to anything that triggers a re-fetch or DOM update.

**Scope:**
- On form submit, disable all inputs and replace button text with a spinner via JS (no HTMX)
- Re-enable the form if an error is returned
- Debug the cancel-flicker: check for event listeners on the dialog `close` event or the `#prediction-result` container that trigger unintended re-renders

**No new model or diagram needed.**

---

## Tier 5 — Technical Debt & Infrastructure

---

### ~~BL-013 · Migrate HTMX from 1.9.10 to 2.x~~ `S` ✓ Complete

**Value:** HTMX 1.9.10 has a known bug with `outerHTML` polling (crashes with `Cannot read properties of null (reading 'htmx-internal-data')`). Version 2.x fixes this. The upgrade is low-effort for this project.

**Scope:**
- Update the CDN script tag in `core/base.html` from `htmx.org@1.9.10` to `htmx.org@2.0.4` (or latest 2.x)
- Verify `hx-delete` usage — in 2.x, DELETE requests send params in the URL instead of the request body
- Confirm no `hx-on` attribute syntax is in use (syntax changed in 2.x)
- Smoke-test all HTMX interactions: history filters/pagination, upload flow, preset load/delete, admin execution list
- `htmx.config.selfRequestsOnly` now defaults to `true` — all requests are same-origin so no change needed

**No new model, wireframe, or diagram needed.** See `CLAUDE.md` for full migration notes.

---

### ~~BL-016 · Frontend Asset Pipeline — Tailwind Build + django-compressor~~ `M` ✓ Complete

**Value:** CSS and JS are currently loaded from CDN at runtime. A local build step removes CDN dependencies, enables tree-shaking (smaller Tailwind output), and adds cache-busting via django-compressor.

**Scope:**
- Add `package.json` with Tailwind CSS CLI build script (`npm run build` / `npm run watch`)
- Replace CDN `<link>` for Tailwind/DaisyUI with compiled `static/dist/main.css`
- Vendor HTMX (download `htmx.min.js` to `static/vendor/`), reference via `{% static %}`
- Install and configure `django-compressor` (`COMPRESS_OFFLINE=True` for staging/prod)
- Add a `frontend-build` Docker service (Node image) that runs before `collectstatic`
- Update `Dockerfile` and CI to run `npm ci && npm run build` before `python manage.py collectstatic`

**Docs:** See `docs/deployment/frontend-pipeline.md` for full approach and config snippets.

**Depends on:** Nothing, but should be done before BL-017/BL-018 (staging/prod) so static files are handled correctly at deploy time.

---

### ~~BL-017 · Staging Environment — Docker on EC2 with Traefik SSL~~ `L` ✓ Complete

**Value:** There is currently no shared staging environment. Developers test against localhost only. A staging environment enables pre-production testing, stakeholder demos, and smoke-testing deployments before production.

**Scope:**
- Create `docker-compose.staging.yml` (Traefik service + label overrides for Django/Flower)
- Create `backend/config/settings/staging.py` (DEBUG=False, WhiteNoise, HSTS)
- Create `traefik/traefik.yml` (Let's Encrypt ACME via HTTP challenge)
- Document EC2 provisioning steps and initial deploy procedure
- Add `DJANGO_SETTINGS_MODULE=config.settings.staging` to staging env
- Verify all services (web, celery-worker, Redis, PostgreSQL, RustFS) start correctly
- Verify SSL certificate issuance and HTTPS redirect

**Docs:** See `docs/deployment/staging.md` for full architecture and config.

**Depends on:** BL-016 (frontend pipeline should be in place so `collectstatic` works correctly).

---

### ~~BL-019 · Notification Management — In-App Notification Centre & Preferences~~ `M` ✓ Complete

**User story:** US-7.2 (extends BL-011)
**Value:** Email-only notifications (BL-011) miss users who don't monitor their inbox. An in-app notification centre surfaces run completions, failures, and system messages without requiring email, and a preferences page lets users control which channels they want.

**Scope:**
- New model: `Notification` (user FK, `notification_type` choices, `message`, `related_execution` FK nullable, `is_read` bool, `created_at`)
- Migration required
- In-app notification bell icon in `core/base.html` navbar — badge shows unread count (HTMX polling or SSE)
- Notification list page: `accounts/notifications.html` — mark individual or all as read
- Notification preferences page (extend `accounts/settings.html`): per-channel toggles (`notify_on_failure`, `notify_on_success`, `notify_in_app`, `notify_via_email`)
- Celery tasks that currently send email (BL-011) also create a `Notification` record when `notify_in_app` is enabled

**Depends on:** BL-011

**Docs required before starting:**
- Update `docs/data-model.mmd` to add `Notification` and update `UserProfile`
- Wireframe: `notification_centre.excalidraw`
- Sequence diagram: `docs/sequences/notifications.mmd`

---

### ~~BL-020 · Feature Flags — Per-User & Environment Toggle System~~ `M` ✓ Complete

**Value:** Before production, there is no mechanism to gradually roll out new features, run A/B tests, or disable functionality per environment without a code deploy. A lightweight feature-flag system removes this risk and enables confident incremental releases.

**Scope:**
- New model: `FeatureFlag` (name slug, description, `is_enabled` bool, `rollout_percentage` 0–100 integer, `enabled_for_users` M2M nullable)
- Flag resolution order (first match wins):
  1. `enabled_for_users` — if user is explicitly listed, flag is on regardless of other settings
  2. `rollout_percentage` — if > 0, deterministically hash `user.id + flag.name` to decide inclusion (stable per-user, no random drift on re-check)
  3. `is_enabled` — global on/off fallback
- Migration required
- Register model in Django Admin — managed entirely via `/admin/`; no custom UI needed
- Template tag `{% flag "flag-name" %}...{% endflag %}` for conditional rendering in templates
- View decorator `@require_flag("flag-name")` returning 404 when flag is off
- Seed migration with a small set of initial flags (e.g. `notifications`, `input-presets`) so existing features can be wrapped without breaking them
- No third-party dependency — implement with the new model and a simple cache layer (`django.core.cache`)

**Docs required before starting:**
- Update `docs/data-model.mmd` to add `FeatureFlag`

---

### BL-018 · Production Environment — Docker Compose/Swarm + PostgreSQL Backups `XL`

**Value:** No production deployment exists. This item covers the full production infrastructure: multi-replica web/worker services, automated PostgreSQL backups to S3, health checks, and a CI/CD deploy pipeline.

**Scope:**
- Create `backend/config/settings/production.py` (full security headers, structured JSON logging)
- Create `docker-stack.yml` (Swarm-compatible, with `deploy:` keys for replicas and restart policy)
- Add `pg-backup` service (scheduled `pg_dump` → S3 via cron on manager node)
- Add `GET /health/` endpoint in `core/views.py` (used by load balancer health checks)
- Document Docker Swarm init and node join procedure
- Set up GitHub Actions deploy workflow (build image → push to GHCR → `docker service update`)
- Test backup restore on staging before go-live

**Docs:** See `docs/deployment/production.md` for full architecture, Swarm config, backup options, and CI/CD sketch.

**Depends on:** BL-017 (staging must be proven stable first), BL-019 (notification system should be in place before prod traffic), BL-020 (feature flags needed to gate rollout).

---

## Backlog Summary

| ID | Title | Tier | Effort | Depends on |
|----|-------|------|--------|------------|
| ~~BL-001~~ | ~~Password reset flow~~ | 1 | M | — |
| ~~BL-002~~ | ~~S3 cleanup on delete~~ | 1 | S | — |
| ~~BL-003~~ | ~~Presigned download URLs~~ | 1 | S | — |
| ~~BL-004~~ | ~~Export history as CSV~~ | 1 | S | — |
| ~~BL-005~~ | ~~Prediction comparison detail~~ | 1 | M | — |
| ~~BL-006~~ | ~~Superuser user management UI~~ | 2 | L | — |
| ~~BL-007~~ | ~~Registration email confirmation~~ | 2 | M | BL-001 |
| ~~BL-008~~ | ~~Admin monitoring dashboard~~ | 3 | L | BL-006 |
| ~~BL-009~~ | ~~Admin execution log viewer~~ | 3 | M | BL-008 |
| ~~BL-010~~ | ~~Input presets~~ | 4 | L | — |
| ~~BL-011~~ | ~~Email notifications for failures~~ | 4 | M | BL-001 |
| ~~BL-012~~ | ~~Retry failed execution~~ | 4 | S | — |
| ~~BL-013~~ | ~~Migrate HTMX 1.9.10 → 2.x~~ | 5 | S | — |
| ~~BL-014~~ | ~~UI polish — buttons, spacing, consistency~~ | 4 | S | — |
| ~~BL-015~~ | ~~Prediction form UX — disable during run, fix cancel flicker~~ | 4 | S | — |
| ~~BL-016~~ | ~~Frontend asset pipeline (Tailwind build + compressor)~~ | 5 | M | — |
| ~~BL-017~~ | ~~Staging environment (EC2 + Traefik SSL)~~ | 5 | L | BL-016 |
| ~~BL-019~~ | ~~Notification management (in-app centre + preferences)~~ | 4 | M | BL-011 |
| ~~BL-020~~ | ~~Feature flags (per-user & environment toggles)~~ | 5 | M | — |
| BL-018 | Production environment (Swarm + PG backups) | 5 | XL | BL-017, BL-019, BL-020 |
