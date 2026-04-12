"""
PipelineBackend — abstract base class for pipeline execution backends.

All backends receive a FlowExecution instance and are responsible for:
  - Running the pipeline to completion
  - Updating ExecutionStep records as steps progress
  - Returning the result.json metadata dict on success
  - Raising RuntimeError on failure

They must NOT update FlowExecution.status — that remains the caller's
(Celery task's) responsibility, so that notification and retry logic
is identical regardless of backend.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.flows.models import FlowExecution


class PipelineBackend(ABC):
    """Protocol for pluggable pipeline execution engines."""

    @abstractmethod
    def run(self, execution: "FlowExecution") -> dict[str, Any]:
        """
        Execute the pipeline for the given FlowExecution.

        Args:
            execution: The FlowExecution instance to run. Must already exist in
                       the database with status PENDING or RUNNING.

        Returns:
            Metadata dict read from result.json in S3, e.g.:
            {"row_count": 42, "s3_output_path": "processed/…/output.parquet"}

        Raises:
            RuntimeError: if the pipeline fails.
        """

    @abstractmethod
    def cancel(self, execution: "FlowExecution") -> None:
        """
        Cancel an in-progress pipeline execution.

        Should be a best-effort operation — implementations must not raise if
        the execution has already reached a terminal state or the external
        run cannot be found.

        Args:
            execution: The FlowExecution to cancel.
        """
