FROM python:3.13-slim

# System dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    wget \
    postgresql-client \
    build-essential \
    locales \
    openssh-client \
    && sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen \
    && locale-gen \
    && rm -rf /var/lib/apt/lists/*


ENV LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8

RUN git config --system --add safe.directory /workspace

RUN git config --system credential.helper "" && \
    git config --system url."git@github.com:".pushInsteadOf "https://github.com/"

# ── Node.js 20 (required for Claude Code) ─────────────────────────────
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# ── Claude Code ───────────────────────────────────────────────────────
RUN npm install -g @anthropic-ai/claude-code \
    && chmod -R o+rx "$(npm root -g)/@anthropic-ai"

# Install uv (fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install just (task runner)
RUN curl -sSf https://just.systems/install.sh | bash -s -- --to /usr/local/bin

# Install DuckDB CLI (useful for interactive debugging)
RUN wget -q -O /tmp/duckdb.gz \
    https://github.com/duckdb/duckdb/releases/latest/download/duckdb_cli-linux-amd64.gz \
    && gunzip /tmp/duckdb.gz \
    && mv /tmp/duckdb /usr/local/bin/duckdb \
    && chmod +x /usr/local/bin/duckdb

# Create non-root user matching typical dev UIDs
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID
RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME

# ── Python venv (outside /workspace so the bind mount doesn't overlay it) ──
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /workspace

# Pre-install Python dependencies at build time for faster container startup
COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/
RUN uv sync --no-install-workspace --group dev

# Ensure vscode user can write to the venv (for post-create uv sync)
RUN chown -R $USERNAME:$USERNAME /opt/venv

USER $USERNAME
