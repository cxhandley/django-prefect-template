# mojo-compute: lightweight Mojo execution container
#
# Installs Mojo via Pixi (Modular's recommended package manager).
# The server is a plain Python stdlib HTTP wrapper around the `mojo` CLI so
# that no additional Python dependencies are needed.
#
# Mojo scripts live in /mojo (mounted read-only from the host mojo/ directory).
# AWS credentials are injected via environment variables — never baked in.
#
# GPU future-proofing: swap the base image to nvidia/cuda:12.x-runtime-ubuntu24.04
# and add the max-gpu conda package when GPU compute is needed.

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# System deps: curl for pixi installer, python3 for the HTTP server
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl python3 ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Install Pixi (Modular-recommended package manager)
RUN curl -fsSL https://pixi.sh/install.sh | bash
ENV PATH="/root/.pixi/bin:${PATH}"

WORKDIR /app

# Create a pixi project and install mojo from the Modular channel
RUN pixi init . -c https://conda.modular.com/max/ -c conda-forge && \
    pixi add mojo

# Copy the HTTP API server (no pip install required — stdlib only)
COPY server.py /app/server.py

# Health-check endpoint
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# Mojo scripts are mounted at /mojo by docker-compose (read-only)
ENV SCRIPTS_DIR=/mojo
ENV PORT=8080

EXPOSE 8080

# Run server.py inside the pixi environment so `mojo` is on PATH
CMD ["pixi", "run", "python3", "/app/server.py"]
