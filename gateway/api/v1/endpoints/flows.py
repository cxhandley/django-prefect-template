"""
Flow execution endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from core.security import get_current_user
from core.prefect_client import get_prefect_client, PrefectClient
from schemas.flow import FlowExecuteRequest, FlowExecuteResponse

router = APIRouter()


@router.post(
    "/{flow_name}/execute",
    response_model=FlowExecuteResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Execute a flow",
    description="Trigger a Prefect flow deployment with the given parameters.",
)
async def execute_flow(
    flow_name: str,
    request: FlowExecuteRequest,
    current_user: str = Depends(get_current_user),
    prefect_client: PrefectClient = Depends(get_prefect_client),
):
    """Execute a Prefect flow."""
    try:
        # Add user tag
        tags = request.tags or []
        tags.append(f"user:{current_user}")
        
        # Execute flow via Prefect
        result = await prefect_client.run_deployment(
            deployment_name=f"{flow_name}/production",
            parameters=request.parameters,
            tags=tags,
        )
        
        return FlowExecuteResponse(**result)
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute flow: {str(e)}"
        )


@router.post(
    "/{flow_name}/execute/{deployment_name}",
    response_model=FlowExecuteResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Execute a specific deployment",
)
async def execute_deployment(
    flow_name: str,
    deployment_name: str,
    request: FlowExecuteRequest,
    current_user: str = Depends(get_current_user),
    prefect_client: PrefectClient = Depends(get_prefect_client),
):
    """Execute a specific Prefect deployment."""
    try:
        tags = request.tags or []
        tags.append(f"user:{current_user}")
        
        result = await prefect_client.run_deployment(
            deployment_name=f"{flow_name}/{deployment_name}",
            parameters=request.parameters,
            tags=tags,
        )
        
        return FlowExecuteResponse(**result)
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute deployment: {str(e)}"
        )