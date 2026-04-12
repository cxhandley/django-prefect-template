"""
PipelineRunner: entry point for pipeline execution.

Callers (Celery tasks, management commands) call run_pipeline() exactly as
before.  Internally, run_pipeline() loads the FlowExecution from the database
and delegates to the configured PipelineBackend:

  - settings.PIPELINE_BACKEND == "doit"    → DoitBackend (default, unchanged)
  - settings.PIPELINE_BACKEND == "prefect" → PrefectBackend

The backend is responsible for running the pipeline to completion and returning
a metadata dict.  FlowExecution.status updates remain the caller's responsibility.
"""

import io
import json
import os
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from django.conf import settings

# Step definitions: (step_name, step_index, s3_output_path_pattern)
# s3_output_path_pattern uses {run_id} as a placeholder.
_PIPELINE_STEPS = [
    ("01_ingest", 0, "processed/flows/data-processing/{run_id}/01_raw.parquet"),
    ("02_validate", 1, "processed/flows/data-processing/{run_id}/02_validated.parquet"),
    ("03_transform", 2, "processed/flows/data-processing/{run_id}/03_transformed.parquet"),
    ("04_aggregate", 3, "processed/flows/data-processing/{run_id}/output.parquet"),
]
_PREDICT_STEPS = [
    ("predict_01_ingest", 0, "processed/flows/credit-prediction/{run_id}/predict_01_raw.parquet"),
    ("predict_02_score", 1, "processed/flows/credit-prediction/{run_id}/output.parquet"),
]
_STEPS_BY_TASK = {
    "pipeline": _PIPELINE_STEPS,
    "predict_pipeline": _PREDICT_STEPS,
}

# result.json S3 path pattern per pipeline type
_RESULT_PATH_PATTERNS = {
    "pipeline": "processed/flows/data-processing/{run_id}/result.json",
    "predict_pipeline": "processed/flows/credit-prediction/{run_id}/result.json",
}

# Map FlowExecution.flow_name → doit task name
_FLOW_NAME_TO_DOIT_TASK = {
    "data-processing": "pipeline",
    "credit-prediction": "predict_pipeline",
}


class PipelineRunner:
    """
    Runs notebook pipelines via the configured PipelineBackend.

    The public interface (run_pipeline) is unchanged for existing callers.
    Internally, the backend is selected from settings.PIPELINE_BACKEND.

    Result contract: the final notebook step writes a result.json manifest to
    a known S3 path. The backend reads this file after completion.

    Step tracking: backends are responsible for creating and updating
    ExecutionStep records.  DoitBackend reads marker files written by dodo.py;
    PrefectBackend receives callbacks via /internal/step-status/.
    """

    def run_pipeline(
        self,
        run_id: uuid.UUID,
        input_s3_path: str,
        extra_params: dict[str, Any] | None = None,
        doit_task: str = "pipeline",
    ) -> dict[str, Any]:
        """
        Execute the full data processing pipeline via the configured backend.

        Args:
            run_id: UUID for this execution (must match a FlowExecution row).
            input_s3_path: Full S3 URL to the input file (s3://bucket/key).
            extra_params: Additional parameters merged into PIPELINE_PARAMS.
            doit_task: Pipeline variant ("pipeline" or "predict_pipeline").
                       Ignored by PrefectBackend, which derives the task from
                       FlowExecution.flow_name.

        Returns:
            Metadata dict read from result.json in S3.

        Raises:
            RuntimeError: if the pipeline fails.
        """
        from apps.flows.backends import get_backend
        from apps.flows.models import FlowExecution

        backend = get_backend()

        # If using the doit backend and extra_params are supplied, handle the
        # ScoringModel injection here (mirrors the original PipelineRunner path)
        # so that DoitBackend._run_doit() receives a fully-populated param set.
        if extra_params is None and doit_task == "predict_pipeline":
            from apps.flows.models import ScoringModel

            active = ScoringModel.get_active()
            if active:
                extra_params = {
                    "scoring_weights": active.weights,
                    "scoring_thresholds": active.thresholds,
                }

        # DoitBackend calls _run_doit() directly; PrefectBackend needs the
        # FlowExecution.  Both paths resolve through get_backend().run().
        # For the doit backend we skip the DB lookup and call _run_doit()
        # directly to preserve the original behaviour exactly.
        from apps.flows.backends.doit import DoitBackend

        if isinstance(backend, DoitBackend):
            return self._run_doit(
                run_id=run_id,
                input_s3_path=input_s3_path,
                extra_params=extra_params,
                doit_task=doit_task,
            )

        # Non-doit backend: load the FlowExecution and delegate
        try:
            execution = FlowExecution.objects.get(flow_run_id=run_id)
        except FlowExecution.DoesNotExist as exc:
            raise RuntimeError(f"FlowExecution with flow_run_id={run_id} not found") from exc

        return backend.run(execution)

    # ── doit subprocess path (used by DoitBackend) ───────────────────────────

    def _run_doit(
        self,
        run_id: uuid.UUID,
        input_s3_path: str,
        extra_params: dict[str, Any] | None = None,
        doit_task: str = "pipeline",
    ) -> dict[str, Any]:
        """
        Execute the doit subprocess pipeline.  Called by DoitBackend.run()
        and directly by run_pipeline() when the backend is doit.
        """
        output_dir = Path(settings.NOTEBOOK_OUTPUT_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)

        params: dict[str, Any] = {
            "run_id": str(run_id),
            "input_s3_path": input_s3_path,
            "bucket": settings.DATA_LAKE_BUCKET,
            "aws_s3_region": settings.AWS_S3_REGION_NAME,
            "s3_endpoint": settings.AWS_S3_ENDPOINT_URL or "",
            "notebook_output_dir": str(output_dir),
        }

        if extra_params:
            params.update(extra_params)

        project_root = os.environ.get("PROJECT_ROOT", str(Path(settings.BASE_DIR).parent))
        env = {
            **os.environ,
            "PIPELINE_PARAMS": json.dumps(params),
            "NOTEBOOKS_DIR": str(settings.NOTEBOOKS_DIR),
            "NOTEBOOK_OUTPUT_DIR": str(output_dir),
            "DJANGO_SETTINGS_MODULE": os.environ.get(
                "DJANGO_SETTINGS_MODULE", "config.settings.development"
            ),
        }

        # Create ExecutionStep records (PENDING) before the subprocess starts
        self._create_pending_steps(run_id, doit_task)

        result = subprocess.run(
            ["python", "-m", "doit", "-f", "dodo.py", "run", doit_task],
            cwd=project_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute hard timeout
        )

        # Read step markers and update ExecutionStep records regardless of outcome
        self._sync_step_records(run_id, doit_task, output_dir)

        if result.returncode != 0:
            raise RuntimeError(
                f"doit pipeline failed (exit {result.returncode}):\n"
                f"stdout: {result.stdout[-2000:]}\n"
                f"stderr: {result.stderr[-2000:]}"
            )

        return self._read_result_json(run_id, doit_task)

    # ── Step tracking ─────────────────────────────────────────────────────────

    def _create_pending_steps(self, run_id: uuid.UUID, doit_task: str) -> None:
        """Create ExecutionStep rows (PENDING) for all steps in this pipeline."""
        from apps.flows.models import ExecutionStep, FlowExecution

        steps = _STEPS_BY_TASK.get(doit_task, [])
        if not steps:
            return

        try:
            execution = FlowExecution.objects.get(flow_run_id=run_id)
        except FlowExecution.DoesNotExist:
            return

        for step_name, step_index, s3_pattern in steps:
            ExecutionStep.objects.get_or_create(
                execution=execution,
                step_index=step_index,
                defaults={
                    "step_name": step_name,
                    "status": "PENDING",
                    "output_s3_path": s3_pattern.format(run_id=str(run_id)),
                },
            )

    def _sync_step_records(self, run_id: uuid.UUID, doit_task: str, output_dir: Path) -> None:
        """
        Read step marker files written by dodo.py and update ExecutionStep rows.
        Marker files live at: output_dir/{run_id}/steps/{index:02d}_{name}_{event}.json
        """
        from apps.flows.models import ExecutionStep, FlowExecution

        steps = _STEPS_BY_TASK.get(doit_task, [])
        if not steps:
            return

        try:
            execution = FlowExecution.objects.get(flow_run_id=run_id)
        except FlowExecution.DoesNotExist:
            return

        marker_dir = output_dir / str(run_id) / "steps"
        if not marker_dir.exists():
            return

        for step_name, step_index, _ in steps:
            prefix = f"{step_index:02d}_{step_name}"

            started_at = self._read_marker_ts(marker_dir / f"{prefix}_started.json", "started_at")
            completed_file = marker_dir / f"{prefix}_completed.json"
            failed_file = marker_dir / f"{prefix}_failed.json"

            if completed_file.exists():
                completed_at = self._read_marker_ts(completed_file, "completed_at")
                ExecutionStep.objects.filter(execution=execution, step_index=step_index).update(
                    status="COMPLETED",
                    started_at=started_at,
                    completed_at=completed_at,
                )
            elif failed_file.exists():
                data = self._read_marker(failed_file)
                completed_at = self._parse_ts(data.get("completed_at"))
                ExecutionStep.objects.filter(execution=execution, step_index=step_index).update(
                    status="FAILED",
                    started_at=started_at,
                    completed_at=completed_at,
                    error_message=data.get("error", "")[:2000],
                )
            elif started_at is not None:
                # Started but no completion marker — interrupted mid-step
                ExecutionStep.objects.filter(execution=execution, step_index=step_index).update(
                    status="FAILED",
                    started_at=started_at,
                    error_message="Step was interrupted (no completion marker).",
                )

    @staticmethod
    def _read_marker(path: Path) -> dict:
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            return {}

    @staticmethod
    def _parse_ts(value: str | None):
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                from django.utils.timezone import make_aware

                dt = make_aware(dt)
            return dt
        except (ValueError, TypeError):
            return None

    def _read_marker_ts(self, path: Path, key: str):
        return self._parse_ts(self._read_marker(path).get(key))

    # ── Result reading ────────────────────────────────────────────────────────

    def _read_result_json(self, run_id: uuid.UUID, doit_task: str) -> dict[str, Any]:
        """
        Read the result.json manifest written by the final notebook step.
        Returns an empty dict if the file is not found (e.g. pipeline failed before writing).
        """
        pattern = _RESULT_PATH_PATTERNS.get(doit_task)
        if not pattern:
            return {}

        s3_key = pattern.format(run_id=str(run_id))

        try:
            s3_client = boto3.client(
                "s3",
                endpoint_url=settings.AWS_S3_ENDPOINT_URL,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_S3_REGION_NAME,
                config=Config(signature_version="s3v4"),
            )
            buf = io.BytesIO()
            s3_client.download_fileobj(settings.DATA_LAKE_BUCKET, s3_key, buf)
            buf.seek(0)
            return json.loads(buf.read())
        except Exception:
            return {}
