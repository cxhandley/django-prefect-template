"""
PipelineRunner: invokes doit pipelines (which use papermill internally).
Used by Celery tasks to execute notebook-based pipelines asynchronously.
"""
import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

from django.conf import settings


class PipelineRunner:
    """
    Runs notebook pipelines via doit + papermill.

    doit manages task dependencies (ingest → validate → transform → aggregate).
    Each doit task executes a parameterised notebook via papermill.
    """

    def run_pipeline(
        self,
        run_id: uuid.UUID,
        input_s3_path: str,
        extra_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute the full data processing pipeline via doit.

        Args:
            run_id: UUID for this execution (used to name output notebooks).
            input_s3_path: S3 path to the input file (e.g. s3://bucket/raw/uploads/…).
            extra_params: Additional parameters merged into PIPELINE_PARAMS.

        Returns:
            Metadata dict extracted from the last notebook step's stdout JSON.

        Raises:
            RuntimeError: if doit exits with a non-zero return code.
        """
        output_dir = Path(settings.NOTEBOOK_OUTPUT_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)

        params: dict[str, Any] = {
            "run_id": str(run_id),
            "input_s3_path": input_s3_path,
            "bucket": settings.DATA_LAKE_BUCKET,
            "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
            "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
            "aws_s3_region": settings.AWS_S3_REGION_NAME,
            "s3_endpoint": settings.AWS_S3_ENDPOINT_URL or "",
            "notebook_output_dir": str(output_dir),
        }
        if extra_params:
            params.update(extra_params)

        project_root = str(Path(settings.BASE_DIR).parent)
        env = {
            **os.environ,
            "PIPELINE_PARAMS": json.dumps(params),
            "NOTEBOOKS_DIR": str(settings.NOTEBOOKS_DIR),
            "NOTEBOOK_OUTPUT_DIR": str(output_dir),
            "DJANGO_SETTINGS_MODULE": os.environ.get(
                "DJANGO_SETTINGS_MODULE", "config.settings.development"
            ),
        }

        result = subprocess.run(
            ["python", "-m", "doit", "-f", "dodo.py", "run", "pipeline"],
            cwd=project_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute hard timeout
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"doit pipeline failed (exit {result.returncode}):\n"
                f"stdout: {result.stdout[-2000:]}\n"
                f"stderr: {result.stderr[-2000:]}"
            )

        return self._extract_metadata(result.stdout)

    @staticmethod
    def _extract_metadata(stdout: str) -> dict[str, Any]:
        """
        Parse the last JSON object from doit/papermill stdout.

        The final notebook step (04_aggregate) prints a JSON dict:
          {"row_count": 1234, "s3_output_path": "processed/flows/..."}
        This helper scans stdout from the end to find that object.
        """
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return {}
