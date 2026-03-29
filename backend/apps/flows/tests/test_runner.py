"""
Tests for PipelineRunner: subprocess invocation and metadata extraction.
"""

import json

import pytest
from apps.flows.runner import PipelineRunner

# ============================================================================
# _extract_metadata
# ============================================================================


def test_extract_metadata_valid():
    stdout = 'some log line\n{"row_count": 100, "s3_output_path": "processed/out.parquet"}\n'
    result = PipelineRunner._extract_metadata(stdout)
    assert result["row_count"] == 100
    assert result["s3_output_path"] == "processed/out.parquet"


def test_extract_metadata_last_json_wins():
    """When multiple JSON lines exist, the last one is returned."""
    stdout = '{"first": true}\nsome text\n{"second": true}\n'
    result = PipelineRunner._extract_metadata(stdout)
    assert result == {"second": True}


def test_extract_metadata_empty_stdout():
    assert PipelineRunner._extract_metadata("") == {}


def test_extract_metadata_no_json():
    assert PipelineRunner._extract_metadata("just plain log output\n") == {}


def test_extract_metadata_invalid_json_skipped():
    stdout = "{not valid json}\n{}\n"
    result = PipelineRunner._extract_metadata(stdout)
    assert result == {}


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
    mock_result.stdout = json.dumps(expected_metadata) + "\n"
    mock_result.stderr = ""
    mocker.patch("apps.flows.runner.subprocess.run", return_value=mock_result)

    import uuid

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
