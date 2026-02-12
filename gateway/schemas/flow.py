"""
Flow-related schemas.
"""
from pydantic import BaseModel, Field, validator
from typing import Dict, Any, Optional, List


class FlowExecuteRequest(BaseModel):
    """Request schema for flow execution."""
    
    parameters: Dict[str, Any] = Field(
        ...,
        description="Flow parameters"
    )
    tags: Optional[list[str]] = Field(
        default=None,
        description="Additional tags for the flow run"
    )
    
    @validator('parameters')
    def parameters_must_be_dict(cls, v):
        if not isinstance(v, dict):
            raise ValueError("parameters must be a dictionary")
        return v
    
    @validator('tags')
    def tags_must_be_strings(cls, v):
        if v is not None:
            if not isinstance(v, list):
                raise ValueError("tags must be a list")
            if not all(isinstance(tag, str) for tag in v):
                raise ValueError("all tags must be strings")
        return v


class FlowExecuteResponse(BaseModel):
    """Response schema for flow execution."""
    
    run_id: str = Field(..., description="Flow run UUID")
    flow_name: str = Field(..., description="Name of the flow")
    deployment_name: str = Field(..., description="Full deployment name")
    state: str = Field(..., description="Current state of the flow run")
    state_type: str = Field(..., description="State type (SCHEDULED, RUNNING, etc.)")
    parameters: Dict[str, Any] = Field(..., description="Flow parameters")
    tags: List[str] = Field(default_factory=list, description="Flow run tags")
    created: str = Field(..., description="Creation timestamp")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "run_id": "550e8400-e29b-41d4-a716-446655440000",
                "flow_name": "data-processing",
                "deployment_name": "data-processing/production",
                "state": "SCHEDULED",
                "state_type": "SCHEDULED",
                "parameters": {"input_s3_path": "s3://bucket/input.parquet"},
                "tags": ["user:admin"],
                "created": "2024-01-01T00:00:00Z"
            }
        }
    }