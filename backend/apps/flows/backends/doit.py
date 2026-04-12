"""
DoitBackend — runs the pipeline via doit + papermill subprocesses.

This is the default backend and encapsulates the existing PipelineRunner
subprocess logic. Switching to this backend requires no infrastructure
changes beyond having doit and papermill installed.
"""

from typing import Any

from apps.flows.backends.base import PipelineBackend
from django.conf import settings

# Map FlowExecution.flow_name → doit task name
_FLOW_NAME_TO_DOIT_TASK: dict[str, str] = {
    "data-processing": "pipeline",
    "credit-prediction": "predict_pipeline",
}


class DoitBackend(PipelineBackend):
    """
    Executes pipelines via a doit subprocess (the original PipelineRunner path).

    Each call to run() is synchronous and blocks until the doit process exits.
    ExecutionStep records are updated by reading marker files written by dodo.py.
    """

    def run(self, execution) -> dict[str, Any]:
        """
        Delegate to PipelineRunner.run_pipeline() using params derived from
        the FlowExecution record.
        """
        from apps.flows.runner import PipelineRunner

        doit_task = _FLOW_NAME_TO_DOIT_TASK.get(execution.flow_name, "pipeline")
        # s3_input_path on the model is stored without the s3://bucket/ prefix
        input_s3_path = f"s3://{settings.DATA_LAKE_BUCKET}/{execution.s3_input_path}"

        runner = PipelineRunner()
        return runner._run_doit(
            run_id=execution.flow_run_id,
            input_s3_path=input_s3_path,
            doit_task=doit_task,
        )

    def cancel(self, execution) -> None:
        """
        doit runs as a subprocess owned by the Celery task.
        Cancellation is handled by revoking the Celery task (done in the view).
        This method is a no-op for the doit backend.
        """
