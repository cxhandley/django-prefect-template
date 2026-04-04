# Design System

This document describes the visual language, component library, and conventions for the Django Pipeline & Prediction Platform. It is derived from what is actually implemented — not aspirational.

**Stack:** Tailwind CSS + DaisyUI · HTMX 2.x · Alpine.js 3.x · Inline SVG (Heroicons outline)

---

## Foundation

### Technology

| Layer | Tool | Version | Source |
|-------|------|---------|--------|
| Utility CSS | Tailwind CSS | 3.x | Compiled to `backend/static/dist/main.css` |
| Component layer | DaisyUI | 4.x | Bundled with Tailwind build |
| Interactivity (server) | HTMX | 2.x | Vendored at `backend/static/vendor/htmx.min.js` |
| Interactivity (client) | Alpine.js | 3.14.x | CDN (jsdelivr) |
| Icons | Heroicons outline | — | Inline SVG, `24×24` viewBox |

DaisyUI's `light` theme is active globally (`data-theme="light"` on `<html>`). No dark mode is currently implemented.

---

## Colour Tokens

All colours use DaisyUI semantic tokens. Never use raw Tailwind palette values (e.g. `blue-500`) directly — use the semantic tokens so they stay consistent with the active theme.

| Token | Usage |
|-------|-------|
| `primary` | Main actions, active states, key data values |
| `secondary` | Secondary actions, supporting data |
| `accent` | Highlights (reserved, not yet used) |
| `success` | Completed / healthy states |
| `error` | Failed states, destructive actions, validation errors |
| `warning` | Pending states, caution notices |
| `info` | Running / in-progress states |
| `base-100` | Page background, card backgrounds |
| `base-200` | Sidebar, stat card backgrounds, subtle fills |
| `base-content` | Body text |
| `base-content/60` | Muted text (labels, descriptions) |
| `base-content/50` | Very muted text (empty state messages) |
| `base-content/20` | Decorative elements (empty state icons) |
| `primary-content` | Text on primary-coloured backgrounds |

### Status → Colour mapping

| Status | DaisyUI token | Badge class |
|--------|--------------|-------------|
| COMPLETED / SUCCESS | `success` | `badge-success` |
| RUNNING | `info` | `badge-info` |
| FAILED | `error` | `badge-error` |
| PENDING | `warning` | `badge-warning` |

Status is always communicated with both colour **and** text (never colour alone).

---

## Typography

All type is set in the DaisyUI default font stack (system-ui). No custom typeface is loaded.

| Class | Usage |
|-------|-------|
| `text-2xl font-bold` | Page headings (`<h1>`) |
| `text-xl font-bold` | Section headings |
| `text-lg font-bold` | Card titles (`card-title`) |
| `text-sm font-medium` | Form labels, sub-headings |
| `text-sm` | Body copy, table cells |
| `text-sm text-base-content/60` | Muted descriptions beneath headings |
| `text-xs` | Badges, fine print |
| `font-bold` | Emphasis within body copy |
| `stat-value text-{color}` | Stat card primary value (large, coloured) |
| `stat-title` | Stat card label |
| `stat-desc` | Stat card sub-description |

---

## Spacing

Base unit: `4px` (Tailwind default). Common patterns:

| Pattern | Classes | Context |
|---------|---------|---------|
| Page padding | `p-4 sm:p-6` | Dashboard content wrapper |
| Card inner padding | `card-body` (DaisyUI default = `p-6`) | All cards |
| Section spacing | `space-y-6` | Vertical rhythm between page sections |
| Form field gap | `gap-4` | Grid of form inputs |
| Button group gap | `gap-3` | Horizontal button row |
| Heading + sub | `mt-1` | Sub-text below a heading |
| Button row top | `mt-6` | Actions below a form |
| Result/feedback | `mt-4` | Loading/result areas |

---

## Layout

### Base templates

```
base.html                  ← <html>, <head>, navbar, <main>, global JS
├── base_public.html       ← centred single-column, for login/signup/reset
└── base_dashboard.html    ← DaisyUI drawer layout (sidebar + content)
    └── (page templates)
```

### Dashboard drawer layout

```html
<div class="drawer lg:drawer-open min-h-screen">
  <input id="dashboard-drawer" type="checkbox" class="drawer-toggle" />
  <div class="drawer-content">          <!-- main content area -->
    {% block breadcrumbs %}{% endblock %}
    <div class="p-4 sm:p-6 pt-8">
      {% block dashboard_content %}{% endblock %}
    </div>
  </div>
  <div class="drawer-side z-30">
    <label for="dashboard-drawer" aria-label="close sidebar" class="drawer-overlay"></label>
    {% include "core/components/sidebar.html" %}
  </div>
</div>
```

- Sidebar is always visible on `lg+` (`lg:drawer-open`)
- On mobile, toggled by the hamburger button in the navbar
- Sidebar width: `w-64`, background: `bg-base-200`

### Public layout (`base_public.html`)

Centred single-column card. Used for login, signup, password reset.

---

## Components

### Buttons

Use DaisyUI `btn` classes. Always choose the variant that matches the action's weight.

| Variant | Class | When to use |
|---------|-------|-------------|
| Primary | `btn btn-primary` | The single main action on a page/form |
| Ghost | `btn btn-ghost` | Secondary / cancel actions |
| Outline | `btn btn-outline` | Alternative actions (e.g. Save as Preset) |
| Error | `btn btn-error` | Destructive actions (e.g. Sign Out, Delete) |
| Link-style | `btn btn-ghost btn-sm` | Inline navigation actions (View More) |

**Sizes:** default (form submit), `btn-sm` (table row actions, nav links), `btn-xs` (dense table cells).

**Icon buttons** (`btn-circle`, `btn-square`): used in navbar for notifications and user avatar. Always include `aria-label`.

```html
<!-- Do -->
<button class="btn btn-ghost btn-circle" aria-label="Open notifications">…icon…</button>

<!-- Don't -->
<div role="button" class="btn btn-ghost btn-circle">…icon…</div>
```

---

### Badges

Template: `core/components/ui/badge.html`

Parameters: `status` (COMPLETED / SUCCESS / RUNNING / FAILED / PENDING), `text` (optional override), `size` (optional, e.g. `badge-sm`).

Status badges always include a text label alongside the colour and icon — never colour alone.

```django
{% include "core/components/ui/badge.html" with status=execution.status %}
{% include "core/components/ui/badge.html" with status="RUNNING" text="Processing" size="badge-sm" %}
```

---

### Cards

DaisyUI `card` with `bg-base-100 border border-base-200 shadow-sm`. Inner content uses `card-body`.

```html
<div class="card bg-base-100 border border-base-200 shadow-sm">
  <div class="card-body">
    <h2 class="card-title text-lg">…</h2>
    <!-- content -->
  </div>
</div>
```

Card headers with an action button use a flex row:

```html
<div class="flex items-center justify-between">
  <h2 class="card-title text-lg">Section Title</h2>
  <a href="…" class="btn btn-ghost btn-sm">Action</a>
</div>
```

---

### Stat Cards

Template: `core/components/ui/stat_card.html`

Parameters: `title`, `value`, `description`, `color` (primary / secondary / success / error / info).

```django
{% include "core/components/ui/stat_card.html" with title="Total Executions" value=total_executions description="All time" color="primary" %}
```

Displayed in a responsive grid: `grid grid-cols-1 md:grid-cols-3 gap-6`.

---

### Form Inputs

Template: `core/components/ui/form_input.html`

Parameters: `name`, `label`, `type`, `placeholder`, `required`, `value`, `error`, `help_text`, `min`, `max`, `step`.

- Input ID is always `id_{{ name }}` — links to the `<label for="…">`
- Validation errors appear as `label-text-alt text-error` beneath the input
- Error state adds `input-error` class to the `<input>`

```django
{% include "core/components/ui/form_input.html" with name="income" label="Annual Income" type="number" placeholder="e.g. 75000" required=True min=0 %}
```

**JS-injected validation errors** must also set `aria-describedby` on the input pointing to the error element (not yet implemented — see BL-025).

---

### Form Checkboxes

Template: `core/components/ui/form_checkbox.html`

Parameters: `name`, `label`, `checked`, `required`, `error`.

The `<label>` wraps the `<input>` and the label text; `for`/`id` are also present for explicit association.

---

### Tables

DaisyUI `table` class inside `overflow-x-auto`. Standard structure:

```html
<div class="overflow-x-auto">
  <table class="table">
    <thead>
      <tr>
        <th>Column</th>
        …
        <th><!-- actions column, needs aria-label --></th>
      </tr>
    </thead>
    <tbody>
      <tr class="hover">…</tr>
    </tbody>
  </table>
</div>
```

- Row hover: `class="hover"` on `<tr>`
- Empty state: span full `colspan`, include `empty_state.html` partial
- Action columns: the `<th>` is visually empty but should carry `scope="col"` and a screen-reader-only label (not yet done — see BL-025)

---

### Modals

Template: `core/components/ui/modal.html`

Uses the native HTML `<dialog>` element via DaisyUI. Opened with `.showModal()`, closed with `form[method="dialog"]`.

```django
{% include "core/components/ui/modal.html" with modal_id="confirm_delete" title="Delete Execution" %}
```

- The backdrop `<form method="dialog"><button>close</button></form>` closes the dialog on outside click
- Modal should have `aria-labelledby` pointing at the `<h3>` title (not yet implemented — see BL-025)
- Focus should be trapped inside the open modal; native `<dialog>` handles this in modern browsers

---

### Navigation

#### Navbar (`core/components/navbar.html`)

Sticky, `z-40`. Three zones: `navbar-start` (logo + mobile toggle), `navbar-center` (desktop links), `navbar-end` (notifications + user menu).

The mobile hamburger label targets the `dashboard-drawer` checkbox. The notification bell and user avatar are `div[role="button"]` elements — these need converting to `<button>` elements with `aria-label` (see BL-025).

#### Sidebar (`core/components/sidebar.html`)

DaisyUI `menu` in `bg-base-200`. Active page highlighted with DaisyUI `active` class. Decorative SVG icons precede each link text.

All sidebar SVGs should carry `aria-hidden="true"` (not yet consistently applied — see BL-025).

---

### Pagination

Template: `core/components/ui/pagination.html`

Parameters: `page_obj` (Django `Page`), `target_id` (HTMX swap target), `hx_url` (base URL).

HTMX-driven — fetches new page without full reload, updates browser URL via `hx-push-url="true"`.

Current page uses `btn-active`; disabled pages use `btn-disabled`. The active page button should also carry `aria-current="page"` (not yet applied — see BL-025).

---

### Empty States

Template: `core/components/ui/empty_state.html`

Parameters: `title`, `message`, `action_url` (optional), `action_text` (optional).

Decorative SVG icon + heading + message + optional CTA button. The SVG should carry `aria-hidden="true"`.

---

### Loading States

Two patterns in use:

**HTMX indicator** (inline spinner shown while request is in flight):
```html
<span id="my-indicator" class="loading loading-spinner loading-md htmx-indicator mt-4"></span>
```
The `hx-indicator="#my-indicator"` attribute on the triggering element shows/hides this automatically.

**JS-driven spinner** (prediction form submit):
```js
submitBtn.innerHTML = '<span class="loading loading-spinner loading-sm"></span> Running…';
```

**Async result containers** (e.g. `#prediction-result`) should carry `aria-live="polite"` so screen readers announce when content appears (not yet applied — see BL-025).

---

### Breadcrumbs

Template: `core/components/ui/breadcrumbs.html`

Rendered in the `{% block breadcrumbs %}` slot of `base_dashboard.html`. Uses DaisyUI `breadcrumbs` class.

---

### Dropdowns

DaisyUI `dropdown dropdown-end`. Used for notifications and user menu in navbar. Toggled via `tabindex="0"` / focus. The trigger element should be a `<button>` with an `aria-label` and `aria-expanded` state (not yet applied — see BL-025).

---

### Alerts / Toast

Not yet implemented as a reusable component. Django messages are not currently surfaced. This is a gap.

---

## Icons

All icons are **inline SVG**, Heroicons outline style, `24×24` viewBox, `stroke="currentColor"`.

Standard attributes:
```html
<svg xmlns="http://www.w3.org/2000/svg"
     class="h-5 w-5"
     fill="none"
     viewBox="0 0 24 24"
     stroke="currentColor"
     aria-hidden="true">
  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="…" />
</svg>
```

- **Decorative icons** (alongside text labels): `aria-hidden="true"` — screen readers skip them
- **Standalone icon buttons**: no SVG aria-hidden; instead, the parent `<button>` carries `aria-label`
- Icon sizes: `h-5 w-5` (standard), `h-4 w-4` / `h-3 w-3` (dense contexts like badges)

Currently `aria-hidden="true"` is inconsistently applied — this is tracked in BL-025.

---

## HTMX Conventions

| Pattern | Usage |
|---------|-------|
| `hx-post` / `hx-get` | Form submission / data fetch |
| `hx-target="#id"` | Always explicit; never rely on defaults |
| `hx-swap="innerHTML"` | Replace content inside target |
| `hx-swap="outerHTML"` | Replace the target element itself |
| `hx-trigger="focus once"` | Lazy-load on first focus (notifications dropdown) |
| `hx-indicator="#id"` | Spinner element shown during request |
| `hx-disabled-elt="find button[type=submit]"` | Disable submit during request |
| `hx-push-url="true"` | Update browser URL (pagination) |

CSRF token is sent automatically via the `htmx:configRequest` handler in `base.html`.

Scripts injected via `innerHTML` do not execute — use delegated event listeners with `data-*` attributes instead (see `[data-compare-modal]` handler in `base.html`).

---

## Do / Don't

| Do | Don't |
|----|-------|
| Use DaisyUI semantic colour tokens | Use raw Tailwind palette values (`blue-500`) |
| Use `<button>` for actions | Use `<div role="button">` |
| Add `aria-hidden="true"` to decorative SVGs | Leave inline SVGs without aria attributes |
| Add `aria-label` to icon-only buttons | Leave icon buttons without a text alternative |
| Add `aria-live="polite"` to async result regions | Inject content into regions with no live announcement |
| Use the `form_input.html` component for all text inputs | Inline bespoke `<input>` markup |
| Always pair colour with text for status | Rely on colour alone to convey status |
| Use `<dialog>` for modals | Implement custom modal overlays with `div` |
| Use `aria-current="page"` on active pagination/nav items | Leave active state as visual-only |
