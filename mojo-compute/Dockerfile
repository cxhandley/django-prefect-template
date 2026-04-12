# mojo-compute: lightweight Mojo execution container
#
# Base image: modular/mojo (pinned to a stable release).
# The server is a plain Python stdlib HTTP wrapper around the `mojo` CLI so
# that no additional Python dependencies are needed.
#
# Mojo scripts live in /mojo (mounted read-only from the host mojo/ directory).
# AWS credentials are injected via environment variables — never baked in.

FROM modular/mojo:nightly

WORKDIR /app

# Copy the HTTP API server (no pip install required — stdlib only)
COPY server.py /app/server.py

# Health-check endpoint
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# Mojo scripts are mounted at /mojo by docker-compose (read-only)
ENV SCRIPTS_DIR=/mojo
ENV PORT=8080

EXPOSE 8080

CMD ["python3", "/app/server.py"]
