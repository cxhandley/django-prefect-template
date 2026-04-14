"""
mojo-compute HTTP API server.

Exposes two endpoints:

  POST /execute
    Body: {"run_id": "...", "script": "compute/<name>.mojo",
           "s3_input": "s3://...", "s3_output": "s3://..."}
    Success: {"status": "ok", "row_count": N, "duration_ms": N}
    Error:   {"status": "error", "message": "..."}

  GET /health
    Returns: {"status": "ok"}

Environment variables consumed by Mojo scripts (injected by Docker / the
host environment — never passed as parameters):
  AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION

Usage:
  python server.py          # listens on 0.0.0.0:8080
"""

import http.server
import json
import logging
import os
import subprocess
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mojo-compute")

PORT = int(os.environ.get("PORT", "8080"))
SCRIPTS_DIR = Path(os.environ.get("SCRIPTS_DIR", "/mojo"))


class MojoHandler(http.server.BaseHTTPRequestHandler):
    """Minimal HTTP handler — no framework dependency."""

    def log_message(self, fmt, *args):  # noqa: N802
        log.info(fmt, *args)

    def _send_json(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        return json.loads(raw) if raw else {}

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
        else:
            self._send_json(404, {"status": "error", "message": "not found"})

    def do_POST(self):  # noqa: N802
        if self.path != "/execute":
            self._send_json(404, {"status": "error", "message": "not found"})
            return

        try:
            body = self._read_body()
            result = _execute(body)
            self._send_json(200, result)
        except Exception as exc:
            log.exception("Unhandled error in /execute")
            self._send_json(200, {"status": "error", "message": str(exc)[:2000]})


def _execute(body: dict) -> dict:
    """
    Dispatch a Mojo script and return a result dict.

    The script is expected to:
      - Read input Parquet from S3_INPUT (env var)
      - Write output Parquet + result.json to S3_OUTPUT (env var)
      - Exit 0 on success, non-zero on failure (stderr contains the error)
    """
    run_id: str = body.get("run_id", "")
    script: str = body.get("script", "")
    s3_input: str = body.get("s3_input", "")
    s3_output: str = body.get("s3_output", "")

    if not script:
        return {"status": "error", "message": "script is required"}

    script_path = SCRIPTS_DIR / script
    if not script_path.exists():
        return {"status": "error", "message": f"script not found: {script}"}

    env = {
        **os.environ,
        "RUN_ID": run_id,
        "S3_INPUT": s3_input,
        "S3_OUTPUT": s3_output,
    }

    log.info("Executing Mojo script %s for run_id=%s", script, run_id)
    t0 = time.monotonic()

    result = subprocess.run(
        ["mojo", str(script_path)],
        env=env,
        capture_output=True,
        text=True,
        timeout=540,
    )

    duration_ms = int((time.monotonic() - t0) * 1000)

    if result.returncode != 0:
        error_detail = (result.stderr or result.stdout or "")[-2000:]
        log.error("Script %s failed: %s", script, error_detail)
        return {"status": "error", "message": error_detail}

    log.info("Script %s completed in %d ms", script, duration_ms)
    return {"status": "ok", "row_count": 0, "duration_ms": duration_ms}


if __name__ == "__main__":
    server = http.server.HTTPServer(("0.0.0.0", PORT), MojoHandler)
    log.info("mojo-compute listening on port %d", PORT)
    server.serve_forever()
