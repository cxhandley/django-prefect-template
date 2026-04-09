# Accessibility Manual Testing Guide

This document covers the two BL-025 acceptance criteria that cannot be verified by code: the automated contrast audit and the keyboard smoke test. Run both before marking any accessibility story as complete.

**Target standard:** WCAG 2.1 Level AA
**Relevant criteria:** 1.4.3 (Contrast Minimum), 2.1.1 (Keyboard), 2.4.7 (Focus Visible)

---

## 1. Colour Contrast Audit (WCAG 1.4.3)

**Thresholds:**

| Text size | Required contrast ratio |
|-----------|------------------------|
| Normal text (< 18 pt / < 14 pt bold) | 4.5 : 1 |
| Large text (≥ 18 pt / ≥ 14 pt bold) | 3.0 : 1 |
| UI components and focus indicators | 3.0 : 1 |

### Option A — Axe DevTools (browser extension, recommended)

1. Install the [axe DevTools browser extension](https://www.deque.com/axe/devtools/) (Chrome or Firefox).
2. Start the local dev stack:
   ```bash
   docker compose up
   ```
3. Open each page listed in the [Pages to audit](#pages-to-audit) table while logged in.
4. Open DevTools → **axe DevTools** tab → click **Scan ALL of my page**.
5. Filter results to **Impact: Critical** and **Impact: Serious**.
6. Any result with rule ID `color-contrast` is a failure — note the element, foreground colour, background colour, and actual ratio reported.
7. Fix by either increasing font size, darkening the foreground token, or lightening/darkening the background. Re-scan after each fix.

**Definition of done:** Zero critical or serious `color-contrast` violations on all pages in the table below.

### Option B — Lighthouse (built into Chrome DevTools)

1. Open the page in Chrome.
2. DevTools → **Lighthouse** tab → check **Accessibility** → **Analyze page load**.
3. Expand the **Accessibility** section in the report.
4. Look for failures under **Color contrast** — each entry shows the element and the ratio found vs. required.
5. Lighthouse scores 0–100; the project target is ≥ 90 on every audited page.

### Option C — CLI (CI-friendly)

```bash
# Install once
npm install -g @axe-core/cli

# Run against a running local instance (replace port if needed)
axe http://localhost:8000/accounts/login/ --exit
axe http://localhost:8000/ --exit                      # dashboard
axe http://localhost:8000/flows/history/ --exit
axe http://localhost:8000/flows/comparison/ --exit
axe http://localhost:8000/admin/executions/ --exit

# Exit code 0 = no violations. Non-zero = failures printed to stdout.
```

### Pages to audit

| Page | URL | Notes |
|------|-----|-------|
| Login | `/accounts/login/` | Public; no auth needed |
| Dashboard | `/` | Requires login; contains prediction form and stats |
| Execution history | `/flows/history/` | Table with pagination |
| Execution detail | `/flows/executions/<id>/` | Step timeline + status badge |
| Comparison | `/flows/comparison/` | Side-by-side table |
| Admin executions | `/admin/executions/` | Staff login required |
| User management | `/accounts/users/` | Superuser login required |
| Notifications | `/accounts/notifications/` | Requires login |

### Known areas of risk

The following CSS patterns exist in the codebase and warrant manual inspection even if Axe passes:

| Pattern | Where | Risk |
|---------|-------|------|
| `text-base-content/60` | Subtitle/help text throughout | 60% opacity on a light background may fall below 4.5 : 1 for small text |
| `text-base-content/50` | Empty state message, notification timestamps | Higher risk — 50% opacity |
| `text-base-content/70` | Table secondary text | Lower risk but verify |
| `badge-ghost` | Default badge variant | Ghost variant uses muted colours |

To check a specific token pair, use the [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/) with the exact hex values from the rendered page (use the browser colour picker on the element).

---

## 2. Keyboard Smoke Test (WCAG 2.1.1, 2.4.7)

The goal is to confirm every primary task flow is completable using the keyboard alone — no mouse required at any step.

### Setup

- Use Chrome or Firefox on desktop (Safari has known keyboard differences with `<dialog>`).
- Disable mouse use entirely for each flow — use only Tab, Shift+Tab, Enter, Space, Escape, and arrow keys.
- Ensure a visible focus ring is present on every focused element at all times. If focus is invisible at any point, that is a WCAG 2.4.7 failure.

### Flow 1 — Login

| Step | Keys | Expected |
|------|------|----------|
| Land on `/accounts/login/` | — | Focus starts at skip link or first input |
| Tab to skip link (if not auto-focused) | Tab | "Skip to main content" link becomes visible and focused |
| Tab to email field | Tab | Email input focused, visible ring |
| Enter email | Type | — |
| Tab to password field | Tab | Password input focused |
| Enter password | Type | — |
| Tab to submit button | Tab | "Sign In" button focused |
| Submit | Enter | Redirects to dashboard |

### Flow 2 — Run a prediction

| Step | Keys | Expected |
|------|------|----------|
| Arrive at dashboard | — | — |
| Tab through nav to prediction form | Tab (×n) | Each interactive element receives visible focus in DOM order |
| Fill in Income, Age, Credit Score, Employment Years | Tab between fields, Type values | — |
| Tab to "Run Prediction" button | Tab | Button focused |
| Submit | Enter | Form submits; spinner appears; result populates `#prediction-result` |
| After completion | — | Screen reader would announce update (aria-live region); visually result is visible |

### Flow 3 — View execution history and open a detail page

| Step | Keys | Expected |
|------|------|----------|
| Tab to History link in sidebar or navbar | Tab | Link focused |
| Navigate to history | Enter | History page loads |
| Tab to first row's Details link | Tab (×n) | "Details" link in first row focused |
| Open detail page | Enter | Execution detail page loads |
| Tab through step timeline | Tab | Each step row navigable |

### Flow 4 — Open, interact with, and close a modal

| Step | Keys | Expected |
|------|------|----------|
| Tab to "Save as Preset" button on dashboard | Tab | Button focused |
| Open modal | Enter | `<dialog>` opens; focus moves inside modal |
| Tab through modal fields | Tab | Preset name input focused; Tab cycles within modal |
| Close without saving | Tab to Cancel → Enter, or press Escape | Modal closes; focus returns to trigger button |

### Flow 5 — Mark a notification as read

| Step | Keys | Expected |
|------|------|----------|
| Tab to notification bell in navbar | Tab | Bell button focused, visible ring |
| Open dropdown | Enter or Space | Dropdown opens, notification list visible |
| Tab to first notification | Tab | Notification link focused |
| Open notification | Enter | Navigates to notification read URL; redirects to execution detail |

### Flow 6 — Sign out

| Step | Keys | Expected |
|------|------|----------|
| Tab to user avatar button in navbar | Tab | Avatar button focused |
| Open user menu | Enter or Space | Dropdown opens |
| Tab to Logout | Tab | Logout link focused |
| Trigger logout | Enter | Sign Out confirmation modal opens |
| Tab to "Sign Out" button | Tab | Confirm button focused |
| Confirm | Enter | Signs out; redirects to login page |

### Failure criteria

Log a bug for any of the following:

- Focus is not visible (no visible ring) on any interactive element.
- Tab order is illogical or skips interactive elements.
- A modal opens but focus does not move inside it.
- A modal closes but focus does not return to the element that opened it.
- Any flow cannot be completed without using a mouse.
- Focus becomes trapped outside of a modal (i.e. Tab exits the modal into the page behind it).

### Assistive technology spot-check (optional but recommended)

Run Flow 2 (prediction) and Flow 4 (modal) with a screen reader to verify that `aria-live` regions announce results and modal titles are read on open:

| OS | Screen reader | Browser |
|----|--------------|---------|
| macOS | VoiceOver (built-in, Cmd+F5) | Safari or Chrome |
| Windows | NVDA (free) | Chrome or Firefox |
| Linux | Orca (built-in) | Firefox |

For VoiceOver: use VO+Right/Left to read content; Tab to navigate interactive elements.

---

## Recording results

After completing both audits, update [docs/user-stories.md](../user-stories.md) and [docs/backlog.md](../backlog.md):

- Mark all acceptance criteria checkboxes under **US-T10** as `[x]`
- Change the BL-025 status row in the backlog summary table to `Complete`
- Note the Axe/Lighthouse score and the date tested in a comment or PR description
