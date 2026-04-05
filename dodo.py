"""
dodo.py — doit task definitions for the data processing pipeline.

Each task runs a parameterised Jupyter notebook step via papermill.
doit manages task dependency ordering:
  ingest → validate → transform → aggregate

Usage:
    doit list                                      # show all tasks
    PIPELINE_PARAMS='...' doit run pipeline        # run full pipeline
    PIPELINE_PARAMS='...' doit run ingest          # run single step
    doit clean pipeline                            # remove output notebooks

PIPELINE_PARAMS environment variable (JSON):
    {
        "run_id": "uuid-string",
        "input_s3_path": "s3://bucket/raw/uploads/...",
        "bucket": "django-prefect-datalake-dev",
        "aws_s3_region": "us-east-1",
        "s3_endpoint": "localhost:9000",
        "notebook_output_dir": "data/notebook_outputs"
    }

AWS credentials are read from AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment
variables directly within each notebook, so they are never baked into output notebooks.
"""

import datetime
import json
import os
import sys
from pathlib import Path

import papermill as pm

# ============================================================================
# Configuration
# ============================================================================

NOTEBOOKS_DIR = Path(os.environ.get("NOTEBOOKS_DIR", "notebooks"))
OUTPUT_DIR = Path(os.environ.get("NOTEBOOK_OUTPUT_DIR", "data/notebook_outputs"))


def _get_params() -> dict:
    """Read pipeline parameters from PIPELINE_PARAMS env var."""
    return json.loads(os.environ.get("PIPELINE_PARAMS", "{}"))


def _step_marker_dir(run_id: str) -> Path:
    """Return the directory for step status marker files."""
    return OUTPUT_DIR / run_id / "steps"


def _write_step_started(run_id: str, step_index: int, step_name: str) -> None:
    marker_dir = _step_marker_dir(run_id)
    marker_dir.mkdir(parents=True, exist_ok=True)
    marker = marker_dir / f"{step_index:02d}_{step_name}_started.json"
    with open(marker, "w") as f:
        json.dump({"started_at": datetime.datetime.utcnow().isoformat()}, f)


def _write_step_completed(run_id: str, step_index: int, step_name: str) -> None:
    marker_dir = _step_marker_dir(run_id)
    marker = marker_dir / f"{step_index:02d}_{step_name}_completed.json"
    with open(marker, "w") as f:
        json.dump(
            {
                "completed_at": datetime.datetime.utcnow().isoformat(),
                "status": "COMPLETED",
            },
            f,
        )


def _write_step_failed(run_id: str, step_index: int, step_name: str, error: str) -> None:
    marker_dir = _step_marker_dir(run_id)
    marker = marker_dir / f"{step_index:02d}_{step_name}_failed.json"
    with open(marker, "w") as f:
        json.dump(
            {
                "completed_at": datetime.datetime.utcnow().isoformat(),
                "status": "FAILED",
                "error": error[:2000],
            },
            f,
        )


def _run_notebook(step_name: str, params: dict, run_id: str, step_index: int = 0) -> None:
    """Execute a single notebook step via papermill, writing step markers."""
    input_nb = NOTEBOOKS_DIR / "steps" / f"{step_name}.ipynb"
    output_nb = OUTPUT_DIR / f"{run_id}_{step_name}.ipynb"
    output_nb.parent.mkdir(parents=True, exist_ok=True)

    _write_step_started(run_id, step_index, step_name)
    try:
        pm.execute_notebook(
            str(input_nb),
            str(output_nb),
            parameters=params,
            kernel_name="python3",
            progress_bar=False,
            stdout_file=sys.stdout,
        )
        _write_step_completed(run_id, step_index, step_name)
    except Exception as exc:
        _write_step_failed(run_id, step_index, step_name, str(exc))
        raise


# ============================================================================
# Task definitions
# ============================================================================


def task_ingest():
    """Step 01 — Ingest raw file from S3 and write to staging Parquet."""
    params = _get_params()
    run_id = params.get("run_id", "dev")

    return {
        "actions": [lambda: _run_notebook("01_ingest", params, run_id, step_index=0)],
        "targets": [str(OUTPUT_DIR / f"{run_id}_01_ingest.ipynb")],
        "uptodate": [False],
        "verbosity": 2,
    }


def task_validate():
    """Step 02 — Validate and clean ingested data."""
    params = _get_params()
    run_id = params.get("run_id", "dev")

    return {
        "actions": [lambda: _run_notebook("02_validate", params, run_id, step_index=1)],
        "task_dep": ["ingest"],
        "targets": [str(OUTPUT_DIR / f"{run_id}_02_validate.ipynb")],
        "uptodate": [False],
        "verbosity": 2,
    }


def task_transform():
    """Step 03 — Apply business transformations."""
    params = _get_params()
    run_id = params.get("run_id", "dev")

    return {
        "actions": [lambda: _run_notebook("03_transform", params, run_id, step_index=2)],
        "task_dep": ["validate"],
        "targets": [str(OUTPUT_DIR / f"{run_id}_03_transform.ipynb")],
        "uptodate": [False],
        "verbosity": 2,
    }


def task_aggregate():
    """Step 04 — Aggregate results and write final output.parquet to S3."""
    params = _get_params()
    run_id = params.get("run_id", "dev")

    return {
        "actions": [lambda: _run_notebook("04_aggregate", params, run_id, step_index=3)],
        "task_dep": ["transform"],
        "targets": [str(OUTPUT_DIR / f"{run_id}_04_aggregate.ipynb")],
        "uptodate": [False],
        "verbosity": 2,
    }


def task_pipeline():
    """Full pipeline: ingest → validate → transform → aggregate."""
    return {
        "actions": None,
        "task_dep": ["ingest", "validate", "transform", "aggregate"],
        "verbosity": 2,
    }


def task_predict_ingest():
    """Predict Step 01 — Ingest 1-row prediction CSV from S3."""
    params = _get_params()
    run_id = params.get("run_id", "dev")

    return {
        "actions": [lambda: _run_notebook("predict_01_ingest", params, run_id, step_index=0)],
        "targets": [str(OUTPUT_DIR / f"{run_id}_predict_01_ingest.ipynb")],
        "uptodate": [False],
        "verbosity": 2,
    }


def task_predict_score():
    """Predict Step 02 — Score the ingested prediction data."""
    params = _get_params()
    run_id = params.get("run_id", "dev")

    return {
        "actions": [lambda: _run_notebook("predict_02_score", params, run_id, step_index=1)],
        "task_dep": ["predict_ingest"],
        "targets": [str(OUTPUT_DIR / f"{run_id}_predict_02_score.ipynb")],
        "uptodate": [False],
        "verbosity": 2,
    }


def task_predict_pipeline():
    """Full prediction pipeline: predict_ingest → predict_score."""
    return {
        "actions": None,
        "task_dep": ["predict_ingest", "predict_score"],
        "verbosity": 2,
    }
