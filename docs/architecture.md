# Django Project Architecture

## App Organization

```
backend/apps/
├── core/                          # Shared layouts & components
│   ├── views.py                  # index, base_layout, navbar
│   ├── urls.py
│   ├── templates/
│   │   └── core/
│   │       ├── base.html             # Authenticated layout (sidebar + navbar)
│   │       ├── base_dashboard.html   # Dashboard variant of base
│   │       ├── base_public.html      # Unauthenticated / marketing layout
│   │       ├── index.html            # Home page
│   │       ├── components/
│   │       │   ├── navbar.html
│   │       │   ├── sidebar.html
│   │       │   └── footer.html
│   │       └── components/ui/
│   │           ├── badge.html
│   │           ├── breadcrumbs.html
│   │           ├── empty_state.html
│   │           ├── form_checkbox.html
│   │           ├── form_input.html
│   │           ├── modal.html
│   │           ├── pagination.html
│   │           ├── search_bar.html
│   │           └── stat_card.html
│   └── migrations/
│
├── accounts/                      # Authentication & user profile
│   ├── views.py                  # login, signup, logout, profile, settings, user_menu
│   ├── urls.py
│   ├── forms.py
│   ├── templates/
│   │   └── accounts/
│   │       ├── login.html
│   │       ├── signup.html
│   │       ├── profile.html
│   │       ├── settings.html
│   │       ├── password_reset.html          # Enter email to request reset link
│   │       ├── password_reset_done.html     # "Check your email" confirmation
│   │       ├── password_reset_confirm.html  # Set new password (or "Link Expired")
│   │       ├── password_reset_complete.html # Success — password updated
│   │       ├── email/
│   │       │   ├── password_reset.txt              # Email body
│   │       │   └── password_reset_subject.txt      # Email subject
│   │       ├── components/
│   │       │   └── user_menu.html    # HTMX dropdown
│   │       └── partials/
│   │           ├── login_form.html
│   │           └── signup_form.html
│   └── migrations/
│
├── flags/                         # Runtime feature toggles
│   ├── models.py                 # FeatureFlag (rollout %, per-user overrides)
│   ├── decorators.py             # @feature_flag_required
│   ├── utils.py                  # is_active_for_user()
│   ├── templatetags/
│   │   └── feature_flags.py
│   └── migrations/
│
├── training/                      # Model training runs & datasets
│   ├── models.py                 # TrainingDataset, TrainingRun
│   ├── views.py
│   ├── urls.py
│   ├── tasks.py                  # Celery: training jobs
│   ├── services/
│   └── migrations/
│
└── flows/                         # Pipeline & prediction execution
    ├── models.py                 # FlowExecution, ExecutionStep, PredictionResult
    ├── views.py                  # All pipeline & prediction views
    ├── urls.py
    ├── tasks.py                  # Celery: run_pipeline_task, run_prediction_task
    ├── runner.py                 # Step definitions + PipelineRunner entry point
    ├── backends/
    │   ├── base.py               # PipelineBackend ABC
    │   ├── doit.py               # DoitBackend — doit subprocess (default)
    │   └── prefect.py            # PrefectBackend — Prefect server (optional)
    ├── admin.py
    ├── services/
    │   └── datalake.py           # DuckDB analytics over S3 Parquet
    ├── templatetags/
    │   └── flow_extras.py
    ├── management/commands/
    │   └── setup_s3_buckets.py
    ├── templates/
    │   └── flows/
    │       ├── index.html            # Flows landing page
    │       ├── dashboard.html        # Prediction form + recent executions
    │       ├── history.html          # Paginated execution history
    │       ├── execution_detail.html # Single execution detail
    │       ├── comparison.html       # Side-by-side execution comparison
    │       ├── results.html          # DuckDB results preview + download
    │       ├── upload.html           # File upload form
    │       ├── components/
    │       │   └── flows_menu.html   # HTMX dropdown
    │       └── partials/
    │           ├── history_table_body.html
    │           ├── prediction_running.html
    │           ├── prediction_result.html
    │           └── prediction_error.html
    └── migrations/
```

## URL Routing

### Main Project (`config/urls.py`)
```python
urlpatterns = [
    path('admin/',    admin.site.urls),
    path('accounts/', include('apps.accounts.urls')),
    path('flows/',    include('apps.flows.urls')),
    path('',          include('apps.core.urls')),
]
```

### Core Routes (`apps/core/urls.py`)
| URL | View | Name |
|-----|------|------|
| `/` | `index` | `core:index` |
| `/base/` | `base_layout` | `core:base` |
| `/navbar/` | `navbar` | `core:navbar` |

### Accounts Routes (`apps/accounts/urls.py`)
| URL | View | Name |
|-----|------|------|
| `/accounts/login/` | `login_user` | `accounts:login` |
| `/accounts/signup/` | `signup_user` | `accounts:signup` |
| `/accounts/profile/` | `profile` | `accounts:profile` |
| `/accounts/settings/` | `settings` | `accounts:settings` |
| `/accounts/api/user-menu/` | `user_menu` | `accounts:user_menu` |
| `/accounts/api/logout/` | `logout_user` | `accounts:logout` |
| `/accounts/password-reset/` | `PasswordResetView` | `accounts:password_reset` |
| `/accounts/password-reset/done/` | `PasswordResetDoneView` | `accounts:password_reset_done` |
| `/accounts/password-reset/confirm/<uidb64>/<token>/` | `PasswordResetConfirmView` | `accounts:password_reset_confirm` |
| `/accounts/password-reset/complete/` | `PasswordResetCompleteView` | `accounts:password_reset_complete` |

### Flows Routes (`apps/flows/urls.py`)
| URL | View | Name |
|-----|------|------|
| `/flows/` | `index` | `flows:index` |
| `/flows/dashboard/` | `dashboard` | `flows:dashboard` |
| `/flows/history/` | `history` | `flows:history` |
| `/flows/execution/<uuid>/` | `execution_detail` | `flows:execution_detail` |
| `/flows/execution/<uuid>/stop/` | `stop_execution` | `flows:stop_execution` |
| `/flows/execution/<uuid>/delete/` | `delete_execution` | `flows:delete_execution` |
| `/flows/comparison/` | `comparison` | `flows:comparison` |
| `/flows/upload-and-process/` | `upload_and_process` | `flows:upload_and_process` |
| `/flows/run-prediction/` | `run_prediction` | `flows:run_prediction` |
| `/flows/prediction-status/<uuid>/` | `prediction_status` | `flows:prediction_status` |
| `/flows/status/<uuid>/` | `flow_status` | `flows:flow_status` |
| `/flows/results/<uuid>/` | `view_flow_results` | `flows:view_flow_results` |
| `/flows/results/<uuid>/download/<fmt>/` | `download_results` | `flows:download_results` |
| `/flows/api/flows-menu/` | `flows_menu` | `flows:flows_menu` |

## INSTALLED_APPS

```python
INSTALLED_APPS = [
    # Django
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    # Third-party
    'storages',
    'compressor',
    # Local
    'apps.core',
    'apps.accounts',
    'apps.flows',
    'apps.flags',
    'apps.training',
]
```

## Template Inheritance Chain

Three base layouts cover all pages:

```
core/base.html                    ← authenticated pages (sidebar + navbar)
├── flows/dashboard.html
├── flows/history.html
├── flows/execution_detail.html
├── flows/comparison.html
├── flows/results.html
├── flows/upload.html
├── accounts/profile.html
└── accounts/settings.html

core/base_dashboard.html          ← dashboard variant (extends base.html)
└── flows/index.html

core/base_public.html             ← unauthenticated / marketing
├── core/index.html
├── accounts/login.html
├── accounts/signup.html
├── accounts/password_reset.html
├── accounts/password_reset_done.html
├── accounts/password_reset_confirm.html
└── accounts/password_reset_complete.html
```

HTMX partials and component snippets (`partials/`, `components/`) are rendered
standalone and swapped into the page — they do **not** extend any base template.

## Key Separation of Concerns

| App | Responsibility |
|-----|----------------|
| **core** | Base layouts, navbar, sidebar, footer, shared UI components |
| **accounts** | Login, signup, profile, settings, user-menu dropdown |
| **flows** | Pipeline upload/execution, prediction form, history, results, Celery tasks, DuckDB analytics, pluggable execution backends |
| **flags** | Runtime feature toggles with per-user and percentage-rollout resolution |
| **training** | Model training dataset management and training run orchestration |

## Adding a New Page

1. Add a view in `<app>/views.py`
2. Add a template in `<app>/templates/<app>/yourpage.html` that extends the appropriate base
3. Add a URL to `<app>/urls.py`
4. Follow the [development workflow](../CLAUDE.md) — user story → wireframe → ER diagram first

```python
# flows/views.py
@login_required
def my_new_page(request):
    return render(request, 'flows/my_new_page.html', {})

# flows/urls.py
path('my-new-page/', views.my_new_page, name='my_new_page'),
```

```django
{# flows/templates/flows/my_new_page.html #}
{% extends "core/base.html" %}

{% block title %}My New Page{% endblock title %}

{% block content %}
  <!-- page content -->
{% endblock content %}
```
