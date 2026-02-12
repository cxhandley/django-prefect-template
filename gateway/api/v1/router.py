"""
API v1 router combining all endpoints.
"""
from fastapi import APIRouter

from api.v1.endpoints import flows, runs, deployments

# Create main v1 router
router = APIRouter()

# Include endpoint routers
router.include_router(
    flows.router,
    prefix="/flows",
    tags=["flows"],
)

router.include_router(
    runs.router,
    prefix="/runs",
    tags=["runs"],
)

router.include_router(
    deployments.router,
    prefix="/deployments",
    tags=["deployments"],
)