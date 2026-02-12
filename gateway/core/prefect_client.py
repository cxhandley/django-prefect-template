"""
Prefect API client wrapper.
"""
from typing import Dict, Any, Optional, List
import httpx

from core.config import get_settings

settings = get_settings()


class PrefectClient:
    """Client for interacting with Prefect API."""
    
    def __init__(self, api_url: Optional[str] = None):
        """
        Initialize Prefect client.
        
        Args:
            api_url: Prefect API URL (defaults to settings)
        """
        self.api_url = api_url or settings.prefect_api_url
        self.client = httpx.AsyncClient(base_url=self.api_url, timeout=30.0)
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
    
    async def run_deployment(
        self,
        deployment_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Trigger a Prefect deployment run.
        
        Args:
            deployment_name: Name of deployment (format: "flow-name/deployment-name")
            parameters: Flow parameters
            tags: Optional tags for the flow run
        
        Returns:
            Flow run information
        
        Raises:
            httpx.HTTPError: If API request fails
        """
        # Parse deployment name
        if "/" in deployment_name:
            flow_name, deployment_suffix = deployment_name.split("/", 1)
        else:
            flow_name = deployment_name
            deployment_suffix = "default"
        
        payload = {
            "parameters": parameters or {},
            "tags": tags or [],
        }
        
        # Create flow run via Prefect API
        response = await self.client.post(
            f"/deployments/name/{flow_name}/{deployment_suffix}/create_flow_run",
            json=payload
        )
        response.raise_for_status()
        
        flow_run = response.json()
        
        return {
            "id": flow_run.get("id"),
            "flow_name": flow_name,
            "deployment_name": deployment_name,
            "state": flow_run.get("state", {}).get("name", "SCHEDULED"),
            "state_type": flow_run.get("state", {}).get("type", "SCHEDULED"),
            "parameters": parameters or {},
            "tags": tags or [],
            "created": flow_run.get("created"),
        }
    
    async def get_flow_run(self, flow_run_id: str) -> Dict[str, Any]:
        """
        Get flow run details by ID.
        
        Args:
            flow_run_id: UUID of the flow run
        
        Returns:
            Flow run information
        """
        response = await self.client.get(f"/flow_runs/{flow_run_id}")
        response.raise_for_status()
        
        flow_run = response.json()
        
        return {
            "id": flow_run.get("id"),
            "flow_name": flow_run.get("flow_name"),
            "state": flow_run.get("state", {}).get("name"),
            "state_type": flow_run.get("state", {}).get("type"),
            "start_time": flow_run.get("start_time"),
            "end_time": flow_run.get("end_time"),
            "total_run_time": flow_run.get("total_run_time"),
            "parameters": flow_run.get("parameters", {}),
        }
    
    async def get_flow_run_result(self, flow_run_id: str) -> Optional[Any]:
        """
        Get flow run result/output.
        
        Args:
            flow_run_id: UUID of the flow run
        
        Returns:
            Flow run result if available, None otherwise
        """
        flow_run = await self.get_flow_run(flow_run_id)
        
        # Check if flow is completed
        state_type = flow_run.get("state_type")
        if state_type != "COMPLETED":
            return None
        
        # Get state details which may contain result
        response = await self.client.get(f"/flow_runs/{flow_run_id}")
        response.raise_for_status()
        
        full_data = response.json()
        state_data = full_data.get("state", {}).get("data")
        
        return state_data
    
    async def list_deployments(
        self,
        limit: int = 10,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List available Prefect deployments.
        
        Args:
            limit: Maximum number of deployments to return
            offset: Number of deployments to skip
        
        Returns:
            List of deployment information
        """
        response = await self.client.post(
            "/deployments/filter",
            json={
                "limit": limit,
                "offset": offset,
            }
        )
        response.raise_for_status()
        
        deployments = response.json()
        
        return [
            {
                "id": d.get("id"),
                "name": d.get("name"),
                "flow_name": d.get("flow_name"),
                "description": d.get("description"),
                "tags": d.get("tags", []),
                "parameters": d.get("parameters", {}),
            }
            for d in deployments
        ]
    
    async def cancel_flow_run(self, flow_run_id: str) -> Dict[str, Any]:
        """
        Cancel a running flow.
        
        Args:
            flow_run_id: UUID of the flow run
        
        Returns:
            Updated flow run information
        """
        response = await self.client.post(
            f"/flow_runs/{flow_run_id}/set_state",
            json={
                "type": "CANCELLED",
                "name": "Cancelled",
                "message": "Flow run cancelled via API"
            }
        )
        response.raise_for_status()
        
        return await self.get_flow_run(flow_run_id)


# Singleton instance
_prefect_client: Optional[PrefectClient] = None


async def get_prefect_client() -> PrefectClient:
    """
    Get or create Prefect client instance.
    
    Returns:
        PrefectClient instance
    """
    global _prefect_client
    
    if _prefect_client is None:
        _prefect_client = PrefectClient()
    
    return _prefect_client