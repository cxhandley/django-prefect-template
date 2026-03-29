# CLAUDE.md

Guidelines and conventions for this project.

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

## Notebooks

Notebooks in `notebooks/steps/` are executed by papermill via doit. They must have `kernelspec` and `language_info` in their metadata — papermill requires this to determine the kernel language. The `nbstripout` hook strips cell outputs but preserves this metadata.

Do not add `--extra-keys metadata.kernelspec metadata.language_info` to the nbstripout hook args.

## Project structure

- `backend/` — Django application (web server + Celery tasks)
- `notebooks/steps/` — Papermill notebook pipeline steps
- `dodo.py` — doit task definitions (pipeline DAG)
- `docker-compose.yml` — Local services: PostgreSQL, Redis, RustFS (S3-compatible), web, celery-worker, flower
