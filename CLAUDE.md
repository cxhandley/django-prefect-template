# CLAUDE.md

Guidelines and conventions for this project.

## Design Principles

Two lenses to apply before designing any new feature. Full analysis in [`docs/design-review.md`](docs/design-review.md).

### Rich Hickey — Don't complect
Complecting means tangling together things that are inherently separate. Before adding to a model or function, ask: are these two different things at different points in time, or with different lifecycles? If yes, they belong in separate structures.

Current complections to be aware of (tracked in BL-026–030):
- `FlowExecution` serves two domain concepts — data pipelines and credit predictions — discriminated by a `flow_name` string. New features should not deepen this; they should work toward the split.
- `FlowExecution.parameters` holds both prediction inputs (immutable at submission) and results (written on completion) in one schemaless blob. Do not add more keys to this field; work toward `PredictionResult` and `PredictionInput` as typed relations.
- The scoring algorithm (weights/thresholds) is embedded in notebook code. Do not add more hardcoded values; work toward `ScoringModel`.

### Linus Torvalds — Data structures first
Get the data structures right and the code becomes obvious. Before writing any view or task logic, define the model fields. Ask: can this be queried with a standard ORM filter? If the answer requires `.parameters.get("key")`, the structure is wrong.

When designing new models:
- Prefer typed fields over JSONField blobs for anything that will be filtered, aggregated, or displayed
- State machines belong in `TextChoices` with transition guards — not bare `CharField`
- Every relation that will be queried should have a corresponding `Index`
- A string discriminator (`flow_name = "pipeline"`) is a code smell for a missing model

---

## Reference Documents

| Document | Purpose |
|----------|---------|
| [`docs/user-stories.md`](docs/user-stories.md) | All features as user stories with acceptance criteria and status |
| [`docs/backlog.md`](docs/backlog.md) | Prioritised backlog with effort, dependencies, and scope |
| [`docs/data-model.mmd`](docs/data-model.mmd) | Mermaid ER diagram — keep in sync with models |
| [`docs/design-system.md`](docs/design-system.md) | Component library, colour tokens, spacing, HTMX conventions, Do/Don't |
| [`docs/design-review.md`](docs/design-review.md) | Structural analysis — known complections and missing entities |

---

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

## just commands

This project uses [`just`](https://github.com/casey/just) as a task runner. Always prefer `just` commands over invoking `python manage.py`, `pytest`, or `docker compose` directly.

| Task | Command |
|------|---------|
| Run all migrations | `just migrate` |
| Create migrations for an app | `just makemigrations flows` |
| Run tests | `just test` |
| Lint + format | `just fix` |
| Start all services | `just docker-up` |
| Django shell | `just shell` |

See the full list with `just --list`.

---

## Container restarts

The `web` and `celery-worker` containers mount the workspace via a volume, so Python file edits are reflected immediately via Django's auto-reloader. However, some changes require an explicit restart because the auto-reloader does not catch them or stale bytecode (`__pycache__`) can mask the new code:

**Restart `web` and `celery-worker` after:**
- Changes to `models.py` (new fields, new models, `TextChoices` additions)
- Changes to `apps.py` (AppConfig, OTel init)
- Changes to `settings/*.py`
- Adding or removing entries in `INSTALLED_APPS`
- Any change that causes `TypeError` or `ImportError` on startup (stale `.pyc` is often the cause)

```bash
docker compose restart web celery-worker
```

If restarting does not resolve a stale-bytecode error, clear the cache first:

```bash
find /workspace/backend -name "*.pyc" -delete && find /workspace/backend -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null; echo "Cleared"
docker compose restart web celery-worker
```

## Python dependencies

Python packages are managed with `uv`. After pulling changes that add or update entries in
`backend/pyproject.toml`, sync the dev virtualenv so the new packages are available:

```bash
uv sync --group dev
```

Run this from the workspace root inside the devcontainer. If you skip this step and a new package
appears in `INSTALLED_APPS` (e.g. `compressor`), pytest will fail with
`ModuleNotFoundError: No module named '<package>'`.

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

The project uses **HTMX 2.x** (vendored at `backend/static/vendor/htmx.min.js`).

### Scripts injected via `innerHTML` do not execute

When content is injected via plain JS `element.innerHTML = html`, any `<script>` tags in the HTML are **not executed** by the browser (security restriction). This means:
- HTMX `hx-*` attributes in innerHTML-injected content won't be bound (HTMX won't process them)
- Named functions defined in injected `<script>` blocks won't be available

**Workaround**: use delegated event listeners registered in `base.html` (which always runs), and communicate intent via `data-*` attributes on the injected elements. See the `[data-compare-modal]` click handler in `base.html` for an example.

## Notebooks

Notebooks in `notebooks/steps/` are executed by papermill via doit. They must have `kernelspec` and `language_info` in their metadata — papermill requires this to determine the kernel language. The `nbstripout` hook strips cell outputs but preserves this metadata.

Do not add `--extra-keys metadata.kernelspec metadata.language_info` to the nbstripout hook args.

## Secrets & Credentials

**Never pass credentials as papermill parameters.** Parameters are injected into the output notebook as plaintext and stored in S3.

- AWS credentials (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) are read from the process environment by s3fs and polars automatically via the standard AWS credential chain — no explicit passing in notebooks required
- All secrets are read from environment variables in `backend/config/settings/base.py` via `env()`
- `PipelineRunner` passes non-secret parameters via `PIPELINE_PARAMS`; credentials flow through `**os.environ` automatically
- DuckDB `CREATE SECRET` in `services/datalake.py` currently interpolates credentials via f-string — this is a known limitation, not a pattern to follow elsewhere (tracked in BL-022)

---

## Accessibility

Target: **WCAG 2.1 Level AA** (tracked in BL-025, US-T10).

Rules to apply when writing or modifying templates:

- Use `<button>` for all interactive elements — never `<div role="button">`
- All icon-only `<button>` elements must have `aria-label`
- Decorative inline SVGs (alongside visible text) must have `aria-hidden="true"`
- Containers that receive HTMX-injected content must have `aria-live="polite"`
- All `<input>` elements must be associated with a `<label>` via `for`/`id`; JS-injected errors must use `aria-describedby`
- All `<dialog>` modals must have `aria-labelledby` pointing at their title element
- Table `<th>` elements must have `scope="col"` or `scope="row"`; empty action columns use `<th scope="col" class="sr-only">Actions</th>`
- Active nav and pagination items must carry `aria-current="page"`
- Never convey status or meaning by colour alone — always pair with text

See [`docs/design-system.md`](docs/design-system.md) for the full Do/Don't reference.

---

## Project structure

- `backend/` — Django application (web server + Celery tasks)
- `notebooks/steps/` — Papermill notebook pipeline steps
- `dodo.py` — doit task definitions (pipeline DAG)
- `docker-compose.yml` — Local services: PostgreSQL, Redis, RustFS (S3-compatible), web, celery-worker, flower
