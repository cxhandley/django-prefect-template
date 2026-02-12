"""
Deployment listing endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query

from core.security import get_current_user
from core.prefect_client import get_prefect_client, PrefectClient
from schemas.execution import DeploymentResponse, DeploymentListResponse

router = APIRouter()


@router.get(
    "/",
    response_model=DeploymentListResponse,
    summary="List deployments",
)
async def list_deployments(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: str = Depends(get_current_user),
    prefect_client: PrefectClient = Depends(get_prefect_client),
):
    """List available deployments."""
    try:
        deployments = await prefect_client.list_deployments(
            limit=limit,
            offset=offset
        )
        
        deployment_responses = [
            DeploymentResponse(**d) for d in deployments
        ]
        
        return DeploymentListResponse(
            deployments=deployment_responses,
            total=len(deployment_responses),
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list deployments: {str(e)}"
        )