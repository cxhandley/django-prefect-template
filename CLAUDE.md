# CLAUDE.md

Guidelines and conventions for this project.

## Development Workflow

When implementing any new feature, follow this sequence in order. Each step produces an artifact in the `docs/` folder that informs the next.

### 1. Write a User Story (`docs/user-stories.md`)

Before writing any code, define the feature as a user story:
- Format: *As a [role], I want to [action], so that [benefit]*
- Include acceptance criteria
- Mark status as `[ ]` (not started), `[~]` (in progress), or `[x]` (complete)

### 2. Design a Wireframe (`docs/wireframes/`)

Create an Excalidraw wireframe (`.excalidraw`) for any new UI surface:
- File naming: `<feature_name>.excalidraw`
- Captures page layout, forms, navigation, and interactive elements
- Must align with acceptance criteria from the user story

### 3. Update the Entity Relationship Diagram (`docs/data-model.mmd`)

Update the Mermaid ER diagram to include any new or changed models:
- Only include models that will be or are implemented (not aspirational)
- Keep in sync with actual Django model definitions in `backend/`
- Use Mermaid `erDiagram` syntax

### 4. Create Sequence and Flow Control Diagrams (`docs/sequences/`, `docs/flow-control/`)

For non-trivial features, add Mermaid diagrams before implementing:
- **Sequence diagrams** (`docs/sequences/`): show interactions between actors, Django views, Celery tasks, external services (S3, doit, notebooks)
- **Flow control diagrams** (`docs/flow-control/`): show decision logic and branching within a process
- Use Mermaid `sequenceDiagram` and `flowchart TD` syntax respectively

### 5. Implement Model Logic (`backend/apps/<app>/models.py`)

Add or update Django models based on the ER diagram:
- Run `python manage.py makemigrations` and `python manage.py migrate`
- Keep models focused — store only what cannot be derived from S3/DuckDB

### 6. Implement View Logic (`backend/apps/<app>/views.py`, `tasks.py`, `services/`)

Implement views, Celery tasks, and services:
- Views handle HTTP; delegate business logic to services and tasks
- HTMX partials live in `templates/<app>/partials/`
- Celery tasks in `tasks.py` for anything async

### 7. Write Tests (`backend/apps/<app>/tests/`)

Add tests before marking the user story complete:
- `test_models.py` — model field behaviour and properties
- `test_views.py` — HTTP responses, authenticated/unauthenticated access
- `test_tasks.py` — Celery task logic (mock S3/external calls)
- `test_services.py` — service layer unit tests
- Target ≥ 90% coverage on new code

## Pre-commit

Pre-commit hooks run automatically on `git commit`. Always ensure they pass before committing.

To run manually against staged files:
```bash
pre-commit run
```

To run against all files:
```bash
pre-commit run --all-files
```

To install hooks (first time setup):
```bash
pre-commit install
```

### Hooks configured

| Hook | What it checks |
|------|---------------|
| `trailing-whitespace` | No trailing whitespace |
| `end-of-file-fixer` | Files end with a newline |
| `check-yaml` | Valid YAML syntax |
| `check-json` | Valid JSON syntax |
| `check-toml` | Valid TOML syntax |
| `check-merge-conflict` | No unresolved merge conflict markers |
| `check-added-large-files` | No files > 1000 KB |
| `debug-statements` | No `pdb`/`breakpoint()` left in Python |
| `nbstripout` | Strip notebook outputs before commit (kernelspec metadata is preserved — required by papermill) |
| `ruff` | Python linting with auto-fix |
| `ruff-format` | Python formatting |
| `djlint-reformat-django` | Auto-reformat Django HTML templates |
| `djlint-django` | Lint Django HTML templates |

## Django HTML templates (djlint)

Profile: `django`. Key rules to follow:

- **T003**: `{% endblock %}` tags must include the block name.
  ```html
  {# Wrong #}
  {% endblock %}

  {# Correct #}
  {% endblock title %}
  {% endblock breadcrumbs %}
  {% endblock dashboard_content %}
  ```

## HTMX

The project uses **HTMX 1.9.10** (loaded from CDN in `core/base.html`).

### Known bug — 1.9.10 polling with `outerHTML` swap

HTMX 1.9.10 has a bug where polling via `hx-trigger="every Ns"` combined with `hx-swap="outerHTML"` crashes with:

> `Cannot read properties of null (reading 'htmx-internal-data')`

This happens because after the element is replaced, HTMX's settle phase tries to access the now-removed element. **Workaround**: replace HTMX polling with a plain `setInterval` + `fetch()` loop (see `prediction_running.html`).

### Scripts injected via `innerHTML` do not execute

When content is injected via plain JS `element.innerHTML = html`, any `<script>` tags in the HTML are **not executed** by the browser (security restriction). This means:
- HTMX `hx-*` attributes in innerHTML-injected content won't be bound (HTMX won't process them)
- Named functions defined in injected `<script>` blocks won't be available

**Workaround**: use delegated event listeners registered in `base.html` (which always runs), and communicate intent via `data-*` attributes on the injected elements. See the `[data-compare-modal]` click handler in `base.html` for an example.

### Upgrading to HTMX 2.x

HTMX 2.0 is the current stable release. The 1.9.10 polling bug is fixed in 2.x. Migration impact for this project is **low**:

- `hx-get`, `hx-post`, `hx-target`, `hx-swap`, `hx-trigger`, `hx-boost`, `hx-push-url` — **no changes needed**
- `htmx.config.selfRequestsOnly` now defaults to `true` — confirm all HTMX requests target the same origin (they do)
- DELETE requests send params in the URL instead of the request body — check any `hx-delete` usage
- `hx-on` attribute syntax changed (only if used)

To upgrade, update the CDN script tag in `core/base.html` from `htmx.org@1.9.10` to `htmx.org@2.0.4` (or latest 2.x).

## Notebooks

Notebooks in `notebooks/steps/` are executed by papermill via doit. They must have `kernelspec` and `language_info` in their metadata — papermill requires this to determine the kernel language. The `nbstripout` hook strips cell outputs but preserves this metadata.

Do not add `--extra-keys metadata.kernelspec metadata.language_info` to the nbstripout hook args.

## Project structure

- `backend/` — Django application (web server + Celery tasks)
- `notebooks/steps/` — Papermill notebook pipeline steps
- `dodo.py` — doit task definitions (pipeline DAG)
- `docker-compose.yml` — Local services: PostgreSQL, Redis, RustFS (S3-compatible), web, celery-worker, flower
