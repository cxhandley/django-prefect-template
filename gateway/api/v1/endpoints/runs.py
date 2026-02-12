"""
Flow run status and result endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Path

from core.security import get_current_user
from core.prefect_client import get_prefect_client, PrefectClient
from schemas.execution import FlowRunResponse, FlowRunResultResponse

router = APIRouter()


@router.get(
    "/{run_id}",
    response_model=FlowRunResponse,
    summary="Get flow run status",
)
async def get_flow_run(
    run_id: str = Path(..., description="Flow run UUID"),
    current_user: str = Depends(get_current_user),
    prefect_client: PrefectClient = Depends(get_prefect_client),
):
    """Get flow run status."""
    try:
        result = await prefect_client.get_flow_run(run_id)
        return FlowRunResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Flow run not found: {str(e)}"
        )


@router.get(
    "/{run_id}/result",
    response_model=FlowRunResultResponse,
    summary="Get flow run result",
)
async def get_flow_run_result(
    run_id: str = Path(..., description="Flow run UUID"),
    current_user: str = Depends(get_current_user),
    prefect_client: PrefectClient = Depends(get_prefect_client),
):
    """Get flow run result."""
    try:
        run_info = await prefect_client.get_flow_run(run_id)
        
        result_data = None
        error_message = None
        
        if run_info.get("state_type") == "COMPLETED":
            result_data = await prefect_client.get_flow_run_result(run_id)
        elif run_info.get("state_type") == "FAILED":
            error_message = f"Flow run failed: {run_info.get('state')}"
        
        return FlowRunResultResponse(
            run_id=run_id,
            state=run_info.get("state", "UNKNOWN"),
            result=result_data,
            error=error_message,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Flow run not found: {str(e)}"
        )


@router.delete(
    "/{run_id}",
    summary="Cancel flow run",
)
async def cancel_flow_run(
    run_id: str = Path(..., description="Flow run UUID"),
    current_user: str = Depends(get_current_user),
    prefect_client: PrefectClient = Depends(get_prefect_client),
):
    """Cancel a flow run."""
    try:
        result = await prefect_client.cancel_flow_run(run_id)
        return {
            "message": "Flow run cancelled successfully",
            "run_id": run_id,
            "state": result.get("state"),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel flow run: {str(e)}"
        )