"""
PrefectBackend — runs pipelines as Prefect 3.x flow runs.

Architecture:
  - PrefectBackend.run() submits a Prefect flow run to the configured
    Prefect server and polls until it reaches a terminal state.
  - The actual work happens on the Prefect Worker container, which
    executes pipeline_flow (defined below) step by step via papermill.
  - Each Prefect task (one per pipeline step) uses state hooks to POST
    step status back to Django's /internal/step-status/ endpoint.
  - FlowExecution.external_run_id stores the Prefect flow-run UUID so
    that the UI can link to the Prefect dashboard and cancellation works.

Requirements:
  - PREFECT_API_URL: URL of the Prefect server API
    (e.g. http://prefect-server:4200/api)
  - PREFECT_INTERNAL_SECRET: shared secret for authenticating callbacks
    from the Prefect worker to Django's /internal/step-status/

Both are read from Django settings (sourced from environment variables).
"""

import logging
import time
from pathlib import Path
from typing import Any

from apps.flows.backends.base import PipelineBackend

logger = logging.getLogger(__name__)

# Map FlowExecution.flow_name → step list key used in runner
_FLOW_NAME_TO_DOIT_TASK: dict[str, str] = {
    "data-processing": "pipeline",
    "credit-prediction": "predict_pipeline",
}

_POLL_INTERVAL_SECONDS = 2
_POLL_TIMEOUT_SECONDS = 660  # slightly above the doit 600 s hard timeout

# Prefect 3.x terminal state types
_TERMINAL_STATES = {"COMPLETED", "FAILED", "CRASHED", "CANCELLED"}


# ─── Prefect flow / task definitions ────────────────────────────────────────
# These run on the Prefect Worker container, not in the Django/Celery process.


def _post_step_status(
    run_id: str,
    step_index: int,
    step_name: str,
    status: str,
    error_message: str = "",
) -> None:
    """
    Best-effort HTTP callback to Django's internal step-status endpoint.

    Runs inside the Prefect Worker process.  Failures are logged but never
    propagated — a broken callback must not abort the pipeline step.
    """
    try:
        import httpx
        from django.conf import settings

        url = f"{settings.DJANGO_INTERNAL_URL}/internal/step-status/"
        secret = settings.PREFECT_INTERNAL_SECRET
        httpx.post(
            url,
            json={
                "run_id": run_id,
                "step_index": step_index,
                "step_name": step_name,
                "status": status,
                "error_message": error_message,
            },
            headers={"Authorization": f"Bearer {secret}"},
            timeout=10,
        )
    except Exception:
        logger.exception(
            "step-status callback failed (run_id=%s step=%s status=%s) — continuing",
            run_id,
            step_index,
            status,
        )


def _build_step_params(
    run_id: str,
    input_s3_path: str,
    extra_params: dict,
) -> dict:
    """Build the parameter dict passed to each notebook (mirrors PipelineRunner)."""
    from django.conf import settings

    params: dict[str, Any] = {
        "run_id": run_id,
        "input_s3_path": input_s3_path,
        "bucket": settings.DATA_LAKE_BUCKET,
        "aws_s3_region": settings.AWS_S3_REGION_NAME,
        "s3_endpoint": settings.AWS_S3_ENDPOINT_URL or "",
        "notebook_output_dir": str(settings.NOTEBOOK_OUTPUT_DIR),
    }
    params.update(extra_params)
    return params


def _dispatch_mojo_step_remote(
    run_id: str,
    step_index: int,
    step_name: str,
    s3_input: str,
    s3_output: str,
) -> None:
    """
    Dispatch a MOJO step to the mojo-compute container from inside a Prefect task.

    Posts step-status callbacks to Django identically to notebook steps so that
    ExecutionStep tracking is consistent regardless of step_type.
    """
    import json
    import urllib.error
    import urllib.request

    from django.conf import settings

    _post_step_status(run_id, step_index, step_name, "RUNNING")

    script_name = f"compute/{step_name}.mojo"
    payload = json.dumps(
        {
            "run_id": run_id,
            "script": script_name,
            "s3_input": s3_input,
            "s3_output": s3_output,
        }
    ).encode()

    mojo_url = settings.MOJO_COMPUTE_URL.rstrip("/")
    req = urllib.request.Request(
        f"{mojo_url}/execute",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            body = json.loads(resp.read())
    except Exception as exc:
        error_msg = f"mojo-compute unreachable: {exc}"[:2000]
        _post_step_status(run_id, step_index, step_name, "FAILED", error_msg)
        raise RuntimeError(error_msg) from exc

    if body.get("status") == "ok":
        _post_step_status(run_id, step_index, step_name, "COMPLETED")
    else:
        error_msg = body.get("message", "Unknown mojo-compute error")[:2000]
        _post_step_status(run_id, step_index, step_name, "FAILED", error_msg)
        raise RuntimeError(f"mojo-compute step '{step_name}' failed: {error_msg}")


def _make_step_task(step_name: str, step_index: int, step_type: str = "NOTEBOOK"):
    """
    Factory that returns a Prefect @task for a single pipeline step.

    Defined as a factory so each step gets a distinct task name in Prefect UI.
    Dispatches to papermill (NOTEBOOK) or mojo-compute (MOJO) based on step_type.
    """
    # Import inside function to avoid loading prefect at module import time
    from prefect import task

    @task(name=step_name, retries=0)
    def execute_step(
        run_id: str,
        input_s3_path: str,
        extra_params: dict,
        s3_output: str = "",
    ) -> None:
        if step_type == "MOJO":
            _dispatch_mojo_step_remote(
                run_id=run_id,
                step_index=step_index,
                step_name=step_name,
                s3_input=input_s3_path,
                s3_output=s3_output,
            )
            return

        import sys

        _post_step_status(run_id, step_index, step_name, "RUNNING")
        params = _build_step_params(run_id, input_s3_path, extra_params)

        try:
            import papermill as pm
            from django.conf import settings

            notebooks_dir = Path(settings.NOTEBOOKS_DIR)
            output_dir = Path(settings.NOTEBOOK_OUTPUT_DIR)
            output_dir.mkdir(parents=True, exist_ok=True)

            input_nb = notebooks_dir / "steps" / f"{step_name}.ipynb"
            output_nb = output_dir / f"{run_id}_{step_name}.ipynb"

            pm.execute_notebook(
                str(input_nb),
                str(output_nb),
                parameters=params,
                kernel_name="python3",
                progress_bar=False,
                stdout_file=sys.stdout,
            )
        except Exception as exc:
            _post_step_status(run_id, step_index, step_name, "FAILED", str(exc)[:2000])
            raise

        _post_step_status(run_id, step_index, step_name, "COMPLETED")

    return execute_step


def _get_pipeline_flow():
    """
    Build and return the Prefect @flow for a full pipeline run.

    Imported lazily so that prefect is only required when using this backend.
    """
    from apps.flows.runner import _STEPS_BY_TASK
    from prefect import flow

    @flow(name="django-pipeline", log_prints=True)
    def pipeline_flow(
        run_id: str,
        input_s3_path: str,
        doit_task: str,
        extra_params: dict,
    ) -> None:
        from django.conf import settings

        steps = _STEPS_BY_TASK.get(doit_task, [])
        for step in steps:
            s3_output = (
                f"s3://{settings.DATA_LAKE_BUCKET}/{step.s3_output_pattern.format(run_id=run_id)}"
            )
            task_fn = _make_step_task(step.step_name, step.step_index, step.step_type)
            task_fn(
                run_id=run_id,
                input_s3_path=input_s3_path,
                extra_params=extra_params,
                s3_output=s3_output,
            )

    return pipeline_flow


# ─── PrefectBackend ──────────────────────────────────────────────────────────


class PrefectBackend(PipelineBackend):
    """
    PipelineBackend implementation that submits work to a Prefect 3.x server.

    The Celery worker thread blocks in run() while polling Prefect for the
    flow-run outcome; the Prefect Worker container does the actual notebook
    execution in parallel and posts step status back to Django.
    """

    DEPLOYMENT_NAME = "django-pipeline/data-processing"
    WORK_POOL_NAME = "django-process-pool"

    # ── public interface ──────────────────────────────────────────────────────

    def run(self, execution) -> dict[str, Any]:
        from django.conf import settings

        doit_task = _FLOW_NAME_TO_DOIT_TASK.get(execution.flow_name, "pipeline")
        input_s3_path = f"s3://{settings.DATA_LAKE_BUCKET}/{execution.s3_input_path}"
        run_id = str(execution.flow_run_id)

        # Build extra params (scoring model for predictions)
        extra_params: dict[str, Any] = {}
        if doit_task == "predict_pipeline":
            from apps.flows.models import ScoringModel

            active = ScoringModel.get_active()
            if active:
                extra_params["scoring_weights"] = active.weights
                extra_params["scoring_thresholds"] = active.thresholds

        # Create PENDING ExecutionStep rows before submitting (mirrors DoitBackend)
        self._create_pending_steps(execution, doit_task)

        # Submit the flow run and store external_run_id
        prefect_run_id = self._create_flow_run(
            run_id=run_id,
            input_s3_path=input_s3_path,
            doit_task=doit_task,
            extra_params=extra_params,
        )
        self._store_external_run_id(execution, prefect_run_id)

        # Block until the flow run reaches a terminal state
        final_state = self._poll_until_done(prefect_run_id)

        if final_state not in ("COMPLETED",):
            raise RuntimeError(
                f"Prefect flow run {prefect_run_id} ended with state {final_state!r}"
            )

        # Read the result.json written by the final notebook step
        from apps.flows.runner import PipelineRunner

        return PipelineRunner()._read_result_json(execution.flow_run_id, doit_task)

    def cancel(self, execution) -> None:
        """Cancel the Prefect flow run identified by external_run_id."""
        if not execution.external_run_id:
            return
        try:
            self._cancel_flow_run(execution.external_run_id)
        except Exception:
            logger.exception(
                "Failed to cancel Prefect flow run %s — continuing",
                execution.external_run_id,
            )

    # ── internal helpers ──────────────────────────────────────────────────────

    def _create_pending_steps(self, execution, doit_task: str) -> None:
        """Create ExecutionStep rows (PENDING) before the flow run starts."""
        from apps.flows.models import ExecutionStep
        from apps.flows.runner import _STEPS_BY_TASK

        steps = _STEPS_BY_TASK.get(doit_task, [])
        for step in steps:
            ExecutionStep.objects.get_or_create(
                execution=execution,
                step_index=step.step_index,
                defaults={
                    "step_name": step.step_name,
                    "step_type": step.step_type,
                    "status": "PENDING",
                    "output_s3_path": step.s3_output_pattern.format(
                        run_id=str(execution.flow_run_id)
                    ),
                },
            )

    def _prefect_api_url(self) -> str:
        from django.conf import settings

        return settings.PREFECT_API_URL.rstrip("/")

    def _create_flow_run(
        self,
        run_id: str,
        input_s3_path: str,
        doit_task: str,
        extra_params: dict,
    ) -> str:
        """
        Ensure a deployment exists and create a Prefect flow run for it.
        Returns the Prefect flow run UUID string.
        """
        import httpx

        api = self._prefect_api_url()

        # Ensure the deployment exists
        deployment_id = self._ensure_deployment(api)

        payload = {
            "parameters": {
                "run_id": run_id,
                "input_s3_path": input_s3_path,
                "doit_task": doit_task,
                "extra_params": extra_params,
            },
            "name": f"django-{run_id[:8]}",
        }

        response = httpx.post(
            f"{api}/deployments/{deployment_id}/create_flow_run",
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        flow_run_id = response.json()["id"]
        logger.info("Created Prefect flow run %s for Django run_id %s", flow_run_id, run_id)
        return flow_run_id

    def _ensure_deployment(self, api: str) -> str:
        """
        Return the deployment ID for 'django-pipeline/data-processing', creating
        it if it does not already exist.
        """
        import httpx

        # Check for existing deployment
        resp = httpx.post(
            f"{api}/deployments/filter",
            json={"deployments": {"name": {"any_": [self.DEPLOYMENT_NAME]}}},
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data:
                return data[0]["id"]

        # Create deployment
        flow = _get_pipeline_flow()
        deployment_id = flow.deploy(
            name=self.DEPLOYMENT_NAME,
            work_pool_name=self.WORK_POOL_NAME,
            build=False,
            push=False,
        )
        logger.info("Created Prefect deployment %s", deployment_id)
        return deployment_id

    def _store_external_run_id(self, execution, prefect_run_id: str) -> None:
        from apps.flows.models import FlowExecution

        FlowExecution.objects.filter(flow_run_id=execution.flow_run_id).update(
            external_run_id=str(prefect_run_id)
        )

    def _poll_until_done(self, prefect_run_id: str) -> str:
        """
        Poll the Prefect API until the flow run reaches a terminal state.

        Returns the state type string, e.g. "COMPLETED", "FAILED".
        Raises RuntimeError on timeout.
        """
        import httpx

        api = self._prefect_api_url()
        deadline = time.monotonic() + _POLL_TIMEOUT_SECONDS

        while time.monotonic() < deadline:
            resp = httpx.get(f"{api}/flow_runs/{prefect_run_id}", timeout=10)
            resp.raise_for_status()
            state_type = resp.json().get("state", {}).get("type", "")
            if state_type in _TERMINAL_STATES:
                logger.info("Prefect flow run %s reached state %s", prefect_run_id, state_type)
                return state_type
            time.sleep(_POLL_INTERVAL_SECONDS)

        raise RuntimeError(
            f"Prefect flow run {prefect_run_id} did not complete within "
            f"{_POLL_TIMEOUT_SECONDS} seconds"
        )

    def _cancel_flow_run(self, prefect_run_id: str) -> None:
        import httpx

        api = self._prefect_api_url()
        resp = httpx.delete(f"{api}/flow_runs/{prefect_run_id}/cancel", timeout=10)
        # 404 means the run is already done — treat as success
        if resp.status_code not in (200, 201, 204, 404):
            resp.raise_for_status()
        logger.info("Cancelled Prefect flow run %s", prefect_run_id)
