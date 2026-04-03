# Frontend Asset Pipeline

## Current State

Static assets are served directly by Django (via `whitenoise` in production). CSS comes from Tailwind CSS CDN and DaisyUI CDN. HTMX is loaded from CDN. There is no build step or asset bundling.

This is acceptable for development but has drawbacks in production:
- CDN dependency at runtime (no offline or airgapped support)
- No cache-busting for app-specific CSS/JS changes
- No minification or tree-shaking
- Multiple CDN round-trips on first load

## Recommended Approach — django-compressor + Node build step

[cookiecutter-django](https://github.com/cookiecutter/cookiecutter-django) uses `django-compressor` with a Gulp/Webpack/Vite build step as its reference frontend pipeline. This project should follow the same pattern.

### Tailwind CSS

Replace the CDN `<script>` with a local build:

```bash
npm install -D tailwindcss @tailwindcss/cli daisyui
npx tailwindcss -i ./static/src/main.css -o ./static/dist/main.css --minify
```

`static/src/main.css`:
```css
@import "tailwindcss";
@plugin "daisyui";
```

`tailwind.config.js`:
```js
export default {
  content: ["./backend/**/*.html", "./backend/**/*.py"],
  plugins: [require("daisyui")],
}
```

### django-compressor

`django-compressor` handles cache-busting and optional further minification of the compiled CSS/JS:

```python
# settings/base.py
INSTALLED_APPS += ["compressor"]
STATICFILES_FINDERS += ["compressor.finders.CompressorFinder"]
COMPRESS_ENABLED = True          # False in development
COMPRESS_OFFLINE = True          # Pre-compile at deploy time
```

```html
{% load compress %}
{% compress css %}
<link rel="stylesheet" href="{% static 'dist/main.css' %}">
{% endcompress %}
```

### HTMX and Alpine.js (if adopted)

Download and vendor these instead of using CDN:

```
static/vendor/htmx@2.0.4.min.js
static/vendor/alpinejs@3.x.x.min.js   # if added later
```

Reference via `{% static %}` tag, not CDN URL.

### Build integration

Add to `docker-compose.yml` as a one-shot build service (runs before `web`):

```yaml
services:
  frontend-build:
    image: node:22-alpine
    working_dir: /app
    volumes:
      - .:/app
    command: sh -c "npm ci && npm run build"
    profiles: ["build"]
```

Add to `justfile`:
```
build-frontend:
    docker compose --profile build run --rm frontend-build
```

In CI and Dockerfile, run `npm run build` before `collectstatic`.

### package.json scripts

```json
{
  "scripts": {
    "build": "tailwindcss -i static/src/main.css -o static/dist/main.css --minify",
    "watch": "tailwindcss -i static/src/main.css -o static/dist/main.css --watch"
  }
}
```
