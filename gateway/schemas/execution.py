"""
Flow execution and result schemas.
"""
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List


class FlowRunResponse(BaseModel):
    """Response schema for flow run details."""
    
    id: str = Field(..., description="Flow run UUID")
    flow_name: str = Field(..., description="Name of the flow")
    state: str = Field(..., description="Current state")
    state_type: str = Field(..., description="State type")
    start_time: Optional[str] = Field(None, description="Start timestamp")
    end_time: Optional[str] = Field(None, description="End timestamp")
    total_run_time: Optional[float] = Field(None, description="Total runtime in seconds")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Flow parameters")


class FlowRunResultResponse(BaseModel):
    """Response schema for flow run results."""
    
    run_id: str = Field(..., description="Flow run UUID")
    state: str = Field(..., description="Final state")
    result: Optional[Any] = Field(None, description="Flow run result data")
    error: Optional[str] = Field(None, description="Error message if failed")


class DeploymentResponse(BaseModel):
    """Response schema for deployment information."""
    
    id: str = Field(..., description="Deployment UUID")
    name: str = Field(..., description="Deployment name")
    flow_name: str = Field(..., description="Flow name")
    description: Optional[str] = Field(None, description="Deployment description")
    tags: List[str] = Field(default_factory=list, description="Deployment tags")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Default parameters")


class DeploymentListResponse(BaseModel):
    """Response schema for list of deployments."""
    
    deployments: List[DeploymentResponse]
    total: int = Field(..., description="Total number of deployments")
    limit: int = Field(..., description="Limit used in query")
    offset: int = Field(..., description="Offset used in query")