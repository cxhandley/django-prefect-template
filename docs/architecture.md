# Django Project Structure

## App Organization

```
backend/apps/
├── core/                          # Shared components & layouts
│   ├── __init__.py
│   ├── apps.py
│   ├── views.py                  # Navbar rendering
│   ├── urls.py                   # Core routes
│   ├── templates/
│   │   └── core/
│   │       ├── base.html         # Main layout template
│   │       └── components/
│   │           └── navbar.html   # Navbar component
│   ├── static/
│   │   └── core/
│   │       ├── css/
│   │       └── js/
│   └── migrations/
│
├── accounts/                      # User & authentication
│   ├── __init__.py
│   ├── apps.py
│   ├── models.py                 # User profile extensions
│   ├── views.py                  # User menu, settings, profile
│   ├── urls.py                   # Account routes
│   ├── forms.py                  # User forms
│   ├── templates/
│   │   └── accounts/
│   │       ├── profile.html
│   │       ├── settings.html
│   │       └── components/
│   │           └── user_menu.html
│   ├── static/
│   └── migrations/
│
├── flows/                         # Flow management
│   ├── __init__.py
│   ├── apps.py
│   ├── models.py                 # FlowExecution, etc.
│   ├── views.py                  # Flow-specific views
│   ├── urls.py                   # Flow routes
│   ├── api_client.py             # FastAPI integration
│   ├── services/
│   │   ├── datalake.py           # DuckDB queries
│   │   └── s3_manager.py         # S3 operations
│   ├── templates/
│   │   └── flows/
│   │       ├── index.html        # Dashboard
│   │       └── components/
│   │           └── flows_menu.html
│   ├── static/
│   └── migrations/
```

## URL Routing

### Main Project (`config/urls.py`)
```python
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('apps.accounts.urls')),
    path('flows/', include('apps.flows.urls')),
    path('', include('apps.core.urls')),
]
```

### Core App Routes (`apps/core/urls.py`)
- `/` → base layout
- `/navbar/` → navbar component

### Accounts Routes (`apps/accounts/urls.py`)
- `/profile/` → user profile page
- `/settings/` → user settings page
- `/api/user-menu/` → HTMX user menu dropdown
- `/api/logout/` → logout endpoint

### Flows Routes (`apps/flows/urls.py`)
- `/` → flows dashboard
- `/api/flows-menu/` → HTMX flows dropdown

## INSTALLED_APPS Configuration

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third-party
    'rest_framework',
    'storages',
    
    # Local apps
    'apps.core',
    'apps.accounts',
    'apps.flows',
]
```

## Templates Inheritance Chain

```
base.html (core/base.html)
├── {% include "core/components/navbar.html" %}
├── {% block content %}
│   └── flows/index.html (extends base.html)
│   └── accounts/profile.html (extends base.html)
│   └── accounts/settings.html (extends base.html)
└── {% include scripts %}
```

## Key Separation of Concerns

| App | Responsibility |
|-----|-----------------|
| **core** | Layout templates, navbar, shared components, CSS/JS utilities |
| **accounts** | User profile, settings, authentication endpoints, user menu |
| **flows** | Flow management, dashboards, flow-specific operations |

## Benefits

✅ **Modularity**: Each app has a single responsibility  
✅ **Reusability**: Core components can be included anywhere  
✅ **Maintainability**: Easy to find and update related code  
✅ **Scalability**: Simple to add new apps that extend base layout  
✅ **Testability**: Can test each app independently  

## Template File Locations

**Always place templates in: `apps/<app_name>/templates/<app_name>/`**

This follows Django's template namespace convention and prevents naming conflicts.

```
apps/core/templates/core/              # Core namespace
apps/accounts/templates/accounts/      # Accounts namespace
apps/flows/templates/flows/            # Flows namespace
```

## Creating New Pages

1. Create view in `<app>/views.py`
2. Create template in `<app>/templates/<app>/yourpage.html`
3. Extend `core/base.html`
4. Add URL to `<app>/urls.py`

Example:

```python
# flows/views.py
@login_required
def run_detail(request, run_id):
    return render(request, 'flows/run_detail.html', {'run_id': run_id})

# flows/urls.py
path('runs/<int:run_id>/', views.run_detail, name='run_detail'),
```

```django
{# flows/templates/flows/run_detail.html #}
{% extends "core/base.html" %}

{% block title %}Run #{{ run_id }} - Prefect{% endblock %}

{% block content %}
    <!-- Your run detail content -->
{% endblock %}
```