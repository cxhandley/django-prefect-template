"""
Tests for PipelineRunner: subprocess invocation and result reading.

Note: _extract_metadata was removed in BL-029.  Pipelines now write a
result.json manifest to S3; PipelineRunner._read_result_json reads it.
"""

import json
import uuid

import pytest
from apps.flows.runner import PipelineRunner

# ============================================================================
# run_pipeline
# ============================================================================


@pytest.mark.django_db
def test_run_pipeline_success(mocker, settings, tmp_path):
    settings.NOTEBOOK_OUTPUT_DIR = str(tmp_path / "outputs")
    settings.DATA_LAKE_BUCKET = "test-bucket"
    settings.AWS_ACCESS_KEY_ID = "testing"
    settings.AWS_SECRET_ACCESS_KEY = "testing"
    settings.AWS_S3_REGION_NAME = "us-east-1"
    settings.AWS_S3_ENDPOINT_URL = None
    settings.NOTEBOOKS_DIR = str(tmp_path / "notebooks")

    expected_metadata = {"row_count": 42, "s3_output_path": "processed/out.parquet"}

    mock_result = mocker.MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""
    mocker.patch("apps.flows.runner.subprocess.run", return_value=mock_result)
    # BL-029: runner reads result.json from S3 instead of parsing stdout
    mocker.patch.object(PipelineRunner, "_read_result_json", return_value=expected_metadata)
    mocker.patch.object(PipelineRunner, "_sync_step_records")
    mocker.patch.object(PipelineRunner, "_create_pending_steps")

    runner = PipelineRunner()
    metadata = runner.run_pipeline(
        run_id=uuid.uuid4(),
        input_s3_path="s3://test-bucket/raw/input.csv",
    )

    assert metadata["row_count"] == 42
    assert metadata["s3_output_path"] == "processed/out.parquet"


@pytest.mark.django_db
def test_run_pipeline_failure(mocker, settings, tmp_path):
    settings.NOTEBOOK_OUTPUT_DIR = str(tmp_path / "outputs")
    settings.DATA_LAKE_BUCKET = "test-bucket"
    settings.AWS_ACCESS_KEY_ID = "testing"
    settings.AWS_SECRET_ACCESS_KEY = "testing"
    settings.AWS_S3_REGION_NAME = "us-east-1"
    settings.AWS_S3_ENDPOINT_URL = None
    settings.NOTEBOOKS_DIR = str(tmp_path / "notebooks")

    mock_result = mocker.MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = "some output"
    mock_result.stderr = "error detail"
    mocker.patch("apps.flows.runner.subprocess.run", return_value=mock_result)

    import uuid

    runner = PipelineRunner()
    with pytest.raises(RuntimeError, match="doit pipeline failed"):
        runner.run_pipeline(
            run_id=uuid.uuid4(),
            input_s3_path="s3://test-bucket/raw/input.csv",
        )


@pytest.mark.django_db
def test_run_pipeline_extra_params(mocker, settings, tmp_path):
    settings.NOTEBOOK_OUTPUT_DIR = str(tmp_path / "outputs")
    settings.DATA_LAKE_BUCKET = "test-bucket"
    settings.AWS_ACCESS_KEY_ID = "testing"
    settings.AWS_SECRET_ACCESS_KEY = "testing"
    settings.AWS_S3_REGION_NAME = "us-east-1"
    settings.AWS_S3_ENDPOINT_URL = None
    settings.NOTEBOOKS_DIR = str(tmp_path / "notebooks")

    mock_result = mocker.MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = '{"row_count": 5}\n'
    mock_result.stderr = ""
    mock_run = mocker.patch("apps.flows.runner.subprocess.run", return_value=mock_result)

    import uuid

    runner = PipelineRunner()
    runner.run_pipeline(
        run_id=uuid.uuid4(),
        input_s3_path="s3://test-bucket/raw/input.csv",
        extra_params={"custom_param": "value"},
        doit_task="predict_pipeline",
    )

    call_env = mock_run.call_args.kwargs["env"]
    params = json.loads(call_env["PIPELINE_PARAMS"])
    assert params["custom_param"] == "value"
