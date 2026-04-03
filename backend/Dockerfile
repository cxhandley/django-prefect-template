# ── Stage 1: Build frontend assets ───────────────────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /frontend

# Create output directories (sibling to /frontend, so /static/dist, /static/vendor)
RUN mkdir -p /static/dist /static/vendor

COPY frontend/package.json ./
RUN npm install

COPY frontend/ .

# Outputs: /static/dist/main.css and /static/vendor/htmx.min.js
RUN npm run build

# ── Stage 2: Django application ───────────────────────────────────────────────
FROM python:3.13-slim

RUN apt-get update && apt-get install -y \
    postgresql-client \
    curl \
    locales \
    && sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen \
    && locale-gen \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml ./
ARG INSTALL_EXTRAS=""
RUN if [ -n "$INSTALL_EXTRAS" ]; then \
        uv pip install --system -e ".[$INSTALL_EXTRAS]"; \
    else \
        uv pip install --system -e "."; \
    fi

COPY . .

# Copy compiled frontend assets from stage 1
COPY --from=frontend-build /static/dist/ /app/static/dist/
COPY --from=frontend-build /static/vendor/ /app/static/vendor/

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
