FROM python:3.13-slim

# System dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    wget \
    postgresql-client \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

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

WORKDIR /workspace

# Pre-install Python dependencies at build time for faster container startup
COPY backend/pyproject.toml backend/
RUN uv pip install --system -e "backend[dev,test]"

USER $USERNAME
