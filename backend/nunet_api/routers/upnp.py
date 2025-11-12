# nunet_api/routers/upnp.py
"""
UPnP API endpoints for network router discovery and port forwarding.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional
from modules.upnp_manager import UPnPManager

router = APIRouter()
upnp_manager = UPnPManager()


class PortMappingRequest(BaseModel):
    """Request model for creating a port mapping."""
    external_port: int = Field(..., ge=1, le=65535, description="External port number")
    internal_port: int = Field(..., ge=1, le=65535, description="Internal port number")
    protocol: str = Field("TCP", pattern="^(TCP|UDP)$", description="Protocol (TCP or UDP)")
    description: str = Field("NuNet Appliance", max_length=100, description="Mapping description")
    internal_ip: Optional[str] = Field(None, description="Internal IP address (defaults to local IP)")
    lease_duration: int = Field(0, ge=0, description="Lease duration in seconds (0 = permanent)")


class PortMappingDeleteRequest(BaseModel):
    """Request model for deleting a port mapping."""
    external_port: int = Field(..., ge=1, le=65535, description="External port number")
    protocol: str = Field("TCP", pattern="^(TCP|UDP)$", description="Protocol (TCP or UDP)")


class ApplianceForwardingRequest(BaseModel):
    """Request model for configuring appliance port forwarding."""
    enable_web_apps: bool = Field(True, description="Forward port 443 for web applications (Caddy proxy)")
    enable_remote_management: bool = Field(False, description="Forward port 8443 for remote appliance management")

class ApplianceDisableRequest(BaseModel):
    """Request model for disabling appliance port forwarding."""
    disable_web_apps: bool = Field(False, description="Remove port 443 forwarding")
    disable_remote_management: bool = Field(False, description="Remove port 8443 forwarding")


@router.get("/gateway/discover")
def discover_gateway(force_refresh: bool = Query(False, description="Force new discovery")):
    """
    Discover UPnP gateway on the network.
    
    Returns information about the gateway including:
    - External IP address
    - Connection type
    - Connection status
    - Local IP address
    - Router information (IP, brand, MAC) - even when UPnP is disabled
    
    Results are cached for 5 minutes unless force_refresh is True.
    
    Note: Even when UPnP discovery fails (status="error"), router_info is still
    returned so the frontend can display router brand/IP information.
    """
    result = upnp_manager.discover_gateway(force_refresh=force_refresh)
    
    # Return the result even on error - it includes router_info which is useful
    # The frontend can check status and gateway_found to determine if UPnP is available
    return result


@router.get("/mappings")
def list_port_mappings(
    filter_ip: str = Query(None, description="Filter mappings by internal IP address (e.g., show only this appliance's rules)")
):
    """
    List all existing port mappings on the UPnP gateway.
    
    Returns a list of all configured port forwarding rules with:
    - External and internal ports
    - Protocol (TCP/UDP)
    - Target IP address
    - Description
    - Lease duration
    
    Args:
        filter_ip: Optional IP address to filter results (shows only mappings pointing to that IP)
    """
    result = upnp_manager.list_port_mappings(filter_internal_ip=filter_ip)
    
    if result["status"] == "error":
        raise HTTPException(status_code=503, detail=result["message"])
    
    return result


@router.get("/mappings/{external_port}")
def check_port_mapping(
    external_port: int,
    protocol: str = Query("TCP", pattern="^(TCP|UDP)$")
):
    """
    Check if a specific port mapping exists.
    
    Args:
        external_port: The external port number to check
        protocol: Protocol (TCP or UDP, default: TCP)
    
    Returns information about the mapping if it exists.
    """
    result = upnp_manager.check_port_mapping(external_port, protocol)
    
    if result["status"] == "error":
        raise HTTPException(status_code=503, detail=result["message"])
    
    return result


@router.post("/mappings")
def add_port_mapping(request: PortMappingRequest):
    """
    Add a new port mapping to the UPnP gateway.
    
    Creates a port forwarding rule that forwards traffic from the external
    port to the specified internal port and IP address.
    
    If a conflicting mapping exists, it will be replaced.
    """
    result = upnp_manager.add_port_mapping(
        external_port=request.external_port,
        internal_port=request.internal_port,
        protocol=request.protocol,
        description=request.description,
        internal_ip=request.internal_ip,
        lease_duration=request.lease_duration
    )
    
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    
    return result


@router.delete("/mappings/{external_port}")
def delete_port_mapping(
    external_port: int,
    protocol: str = Query("TCP", pattern="^(TCP|UDP)$")
):
    """
    Delete a port mapping from the UPnP gateway.
    
    Args:
        external_port: The external port number to delete
        protocol: Protocol (TCP or UDP, default: TCP)
    """
    result = upnp_manager.delete_port_mapping(external_port, protocol)
    
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    
    return result


@router.post("/appliance/configure")
def configure_appliance_forwarding(request: ApplianceForwardingRequest):
    """
    Configure port forwarding for the NuNet appliance.
    
    This endpoint configures two types of port forwarding:
    1. Port 443 -> 443: For web applications served via Caddy proxy (enable_web_apps)
    2. Port 8443 -> 8443: For remote management of the appliance (enable_remote_management)
    
    External access:
    - Web apps: https://<external_ip>
    - Management: https://<external_ip>:8443
    """
    result = upnp_manager.configure_appliance_port_forwarding(
        enable_web_apps=request.enable_web_apps,
        enable_remote_management=request.enable_remote_management
    )
    
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    
    return result


@router.post("/appliance/disable")
def disable_appliance_forwarding(request: ApplianceDisableRequest):
    """
    Remove port forwarding for the NuNet appliance.
    
    This endpoint removes configured port forwarding:
    1. Port 443: Web applications (disable_web_apps)
    2. Port 8443: Remote management (disable_remote_management)
    """
    result = upnp_manager.disable_appliance_port_forwarding(
        disable_web_apps=request.disable_web_apps,
        disable_remote_management=request.disable_remote_management
    )
    
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    
    return result


@router.get("/appliance/status")
def get_appliance_status():
    """
    Get comprehensive UPnP status for the appliance.
    
    Returns:
    - Gateway information (external IP, connection status, etc.)
    - Status of appliance port forwarding (443, 8443)
    - Recommendations for configuration
    """
    result = upnp_manager.get_appliance_status()
    
    if result["status"] == "error":
        raise HTTPException(status_code=503, detail=result["message"])
    
    return result

