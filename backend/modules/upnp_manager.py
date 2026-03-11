"""
UPnP (Universal Plug and Play) management module for NuNet Appliance

This module provides functionality to:
- Discover UPnP-enabled routers on the network
- Query router capabilities
- Automatically configure port forwarding for the appliance
"""

import logging
import time
from typing import Dict, List, Optional, Tuple
from .utils import get_local_ip

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("UPnPManager")


class UPnPManager:
    """Manager for UPnP router discovery and port forwarding operations."""
    
    def __init__(self):
        """Initialize the UPnP manager."""
        self._upnp = None
        self._last_discovery = 0
        self._discovery_cache_ttl = 30  # 30 seconds (short TTL to detect router changes quickly)
        self._cached_gateway_info = None
        
    def _ensure_upnp_available(self) -> Tuple[bool, Optional[str]]:
        """
        Check if miniupnpc library is available.
        
        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        try:
            import miniupnpc
            return True, None
        except ImportError:
            error_msg = (
                "miniupnpc library not installed. "
                "Install with: pip install miniupnpc"
            )
            logger.error(error_msg)
            return False, error_msg
    
    def _initialize_upnp(self) -> Tuple[bool, Optional[str], Optional[any]]:
        """
        Initialize and discover UPnP gateway.
        
        Returns:
            Tuple of (success: bool, error_message: Optional[str], upnp_object: Optional[miniupnpc.UPnP])
        """
        available, error = self._ensure_upnp_available()
        if not available:
            return False, error, None
        
        try:
            import miniupnpc
            
            upnp = miniupnpc.UPnP()
            upnp.discoverdelay = 2000  # 2 seconds
            
            logger.info("Discovering UPnP devices on network...")
            devices_found = upnp.discover()
            
            if devices_found == 0:
                return False, "No UPnP devices found on the network", None
            
            logger.info(f"Found {devices_found} UPnP device(s)")
            
            # Select the Internet Gateway Device (IGD)
            try:
                upnp.selectigd()
            except Exception as select_error:
                # miniupnpc throws misleading exceptions when no IGD found
                # Common messages: "Success", "No IGD found", etc.
                error_str = str(select_error)
                if error_str in ("Success", ""):
                    error_msg = "No UPnP-enabled router found. Please enable UPnP on your router."
                else:
                    error_msg = f"Cannot select UPnP gateway: {error_str}"
                logger.warning(error_msg)
                return False, error_msg, None
            
            return True, None, upnp
            
        except Exception as e:
            # miniupnpc throws misleading exceptions like "Success" when operations fail
            error_str = str(e)
            if error_str in ("Success", ""):
                error_msg = "UPnP is not enabled on your router. Please enable UPnP in your router settings."
            elif "timeout" in error_str.lower():
                error_msg = "UPnP discovery timed out. Check your network connection."
            else:
                error_msg = f"UPnP discovery failed: {error_str}"
            
            logger.error(error_msg)
            return False, error_msg, None
    
    def discover_gateway(self, force_refresh: bool = False) -> Dict[str, any]:
        """
        Discover and get information about the UPnP gateway.
        
        Steps:
        1. Detect router (gateway IP, MAC, brand)
        2. Attempt UPnP discovery on that router
        3. Return combined information
        
        Args:
            force_refresh: Force a new discovery even if cache is valid
            
        Returns:
            Dictionary with status, router info, and gateway information
        """
        now = time.time()
        
        # Use cache if available and not expired
        if (not force_refresh and 
            self._cached_gateway_info and 
            now - self._last_discovery < self._discovery_cache_ttl):
            return self._cached_gateway_info
        
        # Step 1: Detect the router first
        from .router_detect import detect_router
        router_info = detect_router()
        
        logger.info(f"Router detection: {router_info['message']}")
        
        # Step 2: Attempt UPnP discovery
        success, error, upnp = self._initialize_upnp()
        
        if not success:
            # Clear cache on failure so subsequent calls re-attempt discovery
            self._cached_gateway_info = None
            self._upnp = None
            
            result = {
                "status": "error",
                "message": error,
                "gateway_found": False,
                "router_info": router_info  # Include router info even on failure
            }
            return result
        
        # Get gateway information (with fallbacks for limited UPnP implementations)
        external_ip = None
        connection_type = None
        status_info = None
        
        # Try to get external IP (most important)
        try:
            external_ip = upnp.externalipaddress()
        except Exception as e:
            logger.warning(f"Could not get external IP: {e}")
            # Try alternative method
            try:
                import urllib.request
                with urllib.request.urlopen("https://api.ipify.org", timeout=5) as response:
                    external_ip = response.read().decode("utf-8")
                    logger.info(f"Got external IP via fallback method: {external_ip}")
            except Exception as e2:
                logger.warning(f"Fallback external IP lookup also failed: {e2}")
                external_ip = "Unknown"
        
        # Try to get connection type (optional)
        try:
            connection_type = upnp.connectiontype()
        except Exception as e:
            logger.debug(f"Could not get connection type: {e}")
            connection_type = "Unknown"
        
        # Try to get status info (optional)
        try:
            status_info_raw = upnp.statusinfo()
            # statusinfo() returns a tuple: (status, uptime, last_error)
            # Format it nicely for display
            if isinstance(status_info_raw, (list, tuple)) and len(status_info_raw) > 0:
                status_info = str(status_info_raw[0])  # Just the status string
            else:
                status_info = str(status_info_raw) if status_info_raw else "Connected"
        except Exception as e:
            logger.debug(f"Could not get status info: {e}")
            status_info = "Connected"  # Assume connected if IGD was selected
        
        # Get gateway IP - prefer router detection, fallback to UPnP's lanaddr
        gateway_ip = router_info.get('gateway_ip')
        if not gateway_ip:
            # Fallback: Get gateway IP from UPnP's discovered device
            try:
                gateway_ip = upnp.lanaddr
                if gateway_ip:
                    logger.info(f"Got gateway IP from UPnP: {gateway_ip}")
                    # Update router_info with the discovered IP
                    if not router_info.get('gateway_ip'):
                        router_info['gateway_ip'] = gateway_ip
                        router_info['message'] = f"Router detected via UPnP at {gateway_ip}"
            except Exception as e:
                logger.warning(f"Could not get gateway IP from UPnP: {e}")
                gateway_ip = "Unknown"
        
        result = {
            "status": "success",
            "gateway_found": True,
            "router_info": router_info,  # Router detection results
            "gateway_info": {
                "external_ip": external_ip,
                "connection_type": connection_type,
                "connection_status": status_info,
                "gateway_ip": gateway_ip,  # Router's IP (from detection or UPnP)
                "local_ip": get_local_ip(),  # Appliance's IP
            }
        }
        
        # Cache the result
        self._cached_gateway_info = result
        self._last_discovery = now
        self._upnp = upnp  # Store for later use
        
        logger.info(f"Gateway discovered: {external_ip} (Router: {router_info['brand']} at {router_info.get('gateway_ip')})")
        return result
    
    def _parse_port_mapping(self, mapping: tuple, index: int) -> Dict[str, any]:
        """
        Parse a port mapping tuple from UPnP into a standardized dictionary.
        
        Handles multiple router formats defensively:
        - Standard UPnP: (ext_port, protocol, int_ip, int_port, desc, enabled, remote, lease)
        - MikroTik: (ext_port, protocol, (int_ip, int_port), desc, enabled, remote, lease)
        - Minimal: (ext_port, protocol, int_ip, int_port)
        - Other variations with different field counts
        
        Args:
            mapping: Tuple returned by getgenericportmapping
            index: Mapping index (for logging)
            
        Returns:
            Dictionary with standardized port mapping fields, or None to skip
        """
        if not mapping or not isinstance(mapping, (tuple, list)):
            logger.warning(f"Invalid mapping type at index {index}: {type(mapping)}")
            return None
        
        if len(mapping) < 4:
            logger.warning(f"Mapping at index {index} has too few fields ({len(mapping)}): {mapping}")
            return None
        
        try:
            # Extract external port and protocol (should be consistent across all formats)
            external_port = int(mapping[0]) if mapping[0] else 0
            protocol = str(mapping[1]).upper() if mapping[1] else "TCP"
            
            # Determine format by checking if element [2] is a tuple (MikroTik style)
            if isinstance(mapping[2], (tuple, list)):
                # MikroTik format: (ext_port, protocol, (int_ip, int_port), ...)
                if len(mapping[2]) >= 2:
                    internal_ip = str(mapping[2][0]) if mapping[2][0] else "0.0.0.0"
                    internal_port = int(mapping[2][1]) if mapping[2][1] else 0
                else:
                    logger.warning(f"MikroTik-style mapping at index {index} has malformed IP tuple: {mapping[2]}")
                    return None
                
                # Remaining fields shift by -1 compared to standard
                description = str(mapping[3]) if len(mapping) > 3 and mapping[3] else ""
                enabled = mapping[4] if len(mapping) > 4 else True
                remote_host = str(mapping[5]) if len(mapping) > 5 and mapping[5] else ""
                lease_duration = int(mapping[6]) if len(mapping) > 6 and mapping[6] else 0
                
            else:
                # Standard format: (ext_port, protocol, int_ip, int_port, ...)
                internal_ip = str(mapping[2]) if mapping[2] else "0.0.0.0"
                internal_port = int(mapping[3]) if len(mapping) > 3 and mapping[3] else 0
                description = str(mapping[4]) if len(mapping) > 4 and mapping[4] else ""
                enabled = mapping[5] if len(mapping) > 5 else True
                remote_host = str(mapping[6]) if len(mapping) > 6 and mapping[6] else ""
                lease_duration = int(mapping[7]) if len(mapping) > 7 and mapping[7] else 0
            
            # Normalize enabled field (can be bool, int, or string)
            if isinstance(enabled, str):
                enabled_bool = enabled.lower() in ("1", "true", "yes", "enabled")
            elif isinstance(enabled, int):
                enabled_bool = enabled == 1
            else:
                enabled_bool = bool(enabled)
            
            # Validate IP address format (basic check)
            if not self._is_valid_ip(internal_ip):
                logger.warning(
                    f"Mapping at index {index} has invalid internal IP '{internal_ip}', "
                    f"keeping it anyway for visibility"
                )
            
            return {
                "external_port": external_port,
                "protocol": protocol,
                "internal_ip": internal_ip,
                "internal_port": internal_port,
                "description": description,
                "enabled": enabled_bool,
                "remote_host": remote_host,
                "lease_duration": lease_duration
            }
            
        except Exception as e:
            logger.error(
                f"Exception parsing mapping at index {index}: {e}. "
                f"Raw mapping: {mapping}"
            )
            return None
    
    def _is_valid_ip(self, ip: str) -> bool:
        """Basic IP address validation."""
        try:
            parts = str(ip).split('.')
            return len(parts) == 4 and all(0 <= int(p) <= 255 for p in parts)
        except (ValueError, AttributeError):
            return False
    
    def list_port_mappings(self, filter_internal_ip: str = None) -> Dict[str, any]:
        """
        List all existing port mappings on the UPnP gateway.
        
        Args:
            filter_internal_ip: Optional IP address to filter mappings (e.g., show only this appliance's mappings)
        
        Returns:
            Dictionary with status and list of port mappings
        """
        # Reuse cached upnp object or initialize new one
        upnp = self._upnp
        if upnp is None:
            success, error, upnp = self._initialize_upnp()
            if not success:
                return {
                    "status": "error",
                    "message": error,
                    "mappings": [],
                    "total_count": 0,
                    "filtered_count": 0
                }
            self._upnp = upnp
        
        try:
            all_mappings = []
            index = 0
            
            # Iterate through all port mappings
            while True:
                try:
                    mapping = upnp.getgenericportmapping(index)
                    if not mapping:
                        break
                    
                    # Parse mapping with defensive handling for different router formats
                    # Known formats:
                    # - Standard UPnP: (ext_port, protocol, int_ip, int_port, desc, enabled, remote, lease)
                    # - MikroTik: (ext_port, protocol, (int_ip, int_port), desc, enabled, remote, lease)
                    # - Some routers may return fewer fields or in different order
                    
                    try:
                        parsed_mapping = self._parse_port_mapping(mapping, index)
                        if parsed_mapping:
                            all_mappings.append(parsed_mapping)
                        index += 1
                    except Exception as parse_error:
                        logger.warning(
                            f"Failed to parse mapping at index {index}: {parse_error}. "
                            f"Raw data: {mapping}. Skipping this entry."
                        )
                        index += 1
                        # Continue to next mapping instead of breaking
                        continue
                        
                except Exception as e:
                    # End of mappings reached or connection error
                    error_str = str(e)
                    if "Array" in error_str or "not found" in error_str.lower():
                        logger.debug(f"Reached end of port mappings at index {index}")
                    else:
                        logger.warning(f"Error listing port mappings at index {index}: {e}")
                    break
            
            # Filter by internal IP if requested
            if filter_internal_ip:
                filtered_mappings = [
                    m for m in all_mappings 
                    if m["internal_ip"] == filter_internal_ip
                ]
                message = f"Found {len(filtered_mappings)} port mapping(s) for {filter_internal_ip} (total: {len(all_mappings)})"
            else:
                filtered_mappings = all_mappings
                message = f"Found {len(all_mappings)} port mapping(s)"
            
            return {
                "status": "success",
                "message": message,
                "mappings": filtered_mappings,
                "total_count": len(all_mappings),
                "filtered_count": len(filtered_mappings)
            }
            
        except Exception as e:
            error_msg = f"Failed to list port mappings: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "error",
                "message": error_msg,
                "mappings": [],
                "total_count": 0,
                "filtered_count": 0
            }
    
    def check_port_mapping(self, external_port: int, protocol: str = "TCP") -> Dict[str, any]:
        """
        Check if a specific port mapping exists.
        
        Args:
            external_port: External port number to check
            protocol: Protocol (TCP or UDP)
            
        Returns:
            Dictionary with status and mapping information
        """
        # Reuse cached upnp object or initialize new one
        upnp = self._upnp
        if upnp is None:
            success, error, upnp = self._initialize_upnp()
            if not success:
                return {
                    "status": "error",
                    "message": error,
                    "mapping_exists": False
                }
            self._upnp = upnp
        
        try:
            mapping = upnp.getspecificportmapping(external_port, protocol)
            
            if mapping:
                # Parse mapping details with robust handling
                try:
                    # getspecificportmapping returns different format than getgenericportmapping
                    # Usually: (int_ip, int_port, description, enabled, remote_host, lease_duration)
                    # or for MikroTik: ((int_ip, int_port), description, enabled, remote_host, lease_duration)
                    
                    if isinstance(mapping, (list, tuple)) and len(mapping) >= 2:
                        # Check for MikroTik tuple format in first element
                        if isinstance(mapping[0], tuple):
                            internal_ip = str(mapping[0][0])
                            internal_port = int(mapping[0][1])
                            description = str(mapping[1]) if len(mapping) > 1 else ""
                            enabled = mapping[2] if len(mapping) > 2 else True
                            remote_host = str(mapping[3]) if len(mapping) > 3 else ""
                            lease_duration = int(mapping[4]) if len(mapping) > 4 else 0
                        else:
                            # Standard format
                            internal_ip = str(mapping[0])
                            internal_port = int(mapping[1]) if len(mapping) > 1 else 0
                            description = str(mapping[2]) if len(mapping) > 2 else ""
                            enabled = mapping[3] if len(mapping) > 3 else True
                            remote_host = str(mapping[4]) if len(mapping) > 4 else ""
                            lease_duration = int(mapping[5]) if len(mapping) > 5 else 0
                        
                        # Normalize enabled field
                        if isinstance(enabled, str):
                            enabled_bool = enabled.lower() in ("1", "true", "yes", "enabled")
                        elif isinstance(enabled, int):
                            enabled_bool = enabled == 1
                        else:
                            enabled_bool = bool(enabled)
                        
                        return {
                            "status": "success",
                            "mapping_exists": True,
                            "mapping": {
                                "external_port": external_port,
                                "protocol": protocol,
                                "internal_ip": internal_ip,
                                "internal_port": internal_port,
                                "description": description,
                                "enabled": enabled_bool,
                                "remote_host": remote_host,
                                "lease_duration": lease_duration
                            }
                        }
                    else:
                        # Mapping exists but format is unexpected
                        logger.warning(
                            f"Unexpected mapping format for port {external_port}/{protocol}: "
                            f"{type(mapping)} - {mapping}"
                        )
                        return {
                            "status": "success",
                            "mapping_exists": True,
                            "message": f"Port mapping exists for {external_port}/{protocol} (format not recognized)"
                        }
                except (IndexError, TypeError, ValueError) as parse_error:
                    logger.warning(f"Could not parse mapping details for {external_port}/{protocol}: {parse_error}")
                    return {
                        "status": "success",
                        "mapping_exists": True,
                        "message": f"Port mapping exists for {external_port}/{protocol} (details unavailable)"
                    }
            else:
                return {
                    "status": "success",
                    "mapping_exists": False,
                    "message": f"No mapping found for port {external_port}/{protocol}"
                }
                
        except Exception as e:
            # Different routers use different exception types/messages for "not found"
            error_str = str(e)
            not_found_indicators = [
                "NoSuchEntryInArray", "NoSuchEntry", "not found", 
                "no such", "does not exist", "404"
            ]
            
            if any(indicator in error_str for indicator in not_found_indicators):
                return {
                    "status": "success",
                    "mapping_exists": False,
                    "message": f"No mapping found for port {external_port}/{protocol}"
                }
            
            # Actual error
            error_msg = f"Failed to check port mapping {external_port}/{protocol}: {error_str}"
            logger.error(error_msg)
            return {
                "status": "error",
                "message": error_msg,
                "mapping_exists": False
            }
    
    def add_port_mapping(
        self,
        external_port: int,
        internal_port: int,
        protocol: str = "TCP",
        description: str = "NuNet Appliance",
        internal_ip: Optional[str] = None,
        lease_duration: int = 0  # 0 = permanent
    ) -> Dict[str, any]:
        """
        Add a port mapping to the UPnP gateway.
        
        Args:
            external_port: External port to forward
            internal_port: Internal port to forward to
            protocol: Protocol (TCP or UDP)
            description: Description for the mapping
            internal_ip: Internal IP address (defaults to local IP)
            lease_duration: Lease duration in seconds (0 = permanent)
            
        Returns:
            Dictionary with status and result information
        """
        # Reuse cached upnp object or initialize new one
        upnp = self._upnp
        if upnp is None:
            success, error, upnp = self._initialize_upnp()
            if not success:
                return {
                    "status": "error",
                    "message": error
                }
            self._upnp = upnp
        
        if internal_ip is None:
            internal_ip = get_local_ip()
        
        try:
            # Check if mapping already exists
            existing = self.check_port_mapping(external_port, protocol)
            
            if existing.get("mapping_exists"):
                existing_mapping = existing.get("mapping", {})
                if (existing_mapping.get("internal_ip") == internal_ip and 
                    existing_mapping.get("internal_port") == internal_port):
                    return {
                        "status": "success",
                        "message": f"Port mapping already exists for {external_port}/{protocol}",
                        "mapping": existing_mapping,
                        "newly_created": False
                    }
                else:
                    # Delete existing mapping with different config
                    logger.info(f"Removing conflicting mapping for port {external_port}/{protocol}")
                    self.delete_port_mapping(external_port, protocol)
            
            # Add the port mapping
            result = upnp.addportmapping(
                external_port,
                protocol,
                internal_ip,
                internal_port,
                description,
                '',  # remote host (empty = any)
                lease_duration
            )
            
            if result:
                logger.info(
                    f"Successfully added port mapping: {external_port}/{protocol} -> "
                    f"{internal_ip}:{internal_port}"
                )
                return {
                    "status": "success",
                    "message": f"Port mapping added successfully",
                    "mapping": {
                        "external_port": external_port,
                        "internal_port": internal_port,
                        "internal_ip": internal_ip,
                        "protocol": protocol,
                        "description": description,
                        "lease_duration": lease_duration
                    },
                    "newly_created": True
                }
            else:
                return {
                    "status": "error",
                    "message": "Failed to add port mapping (returned false)"
                }
                
        except Exception as e:
            error_msg = f"Failed to add port mapping: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "error",
                "message": error_msg
            }
    
    def delete_port_mapping(
        self,
        external_port: int,
        protocol: str = "TCP"
    ) -> Dict[str, any]:
        """
        Delete a port mapping from the UPnP gateway.
        
        Args:
            external_port: External port of the mapping to delete
            protocol: Protocol (TCP or UDP)
            
        Returns:
            Dictionary with status and result information
        """
        # Reuse cached upnp object or initialize new one
        upnp = self._upnp
        if upnp is None:
            success, error, upnp = self._initialize_upnp()
            if not success:
                return {
                    "status": "error",
                    "message": error
                }
            self._upnp = upnp
        
        try:
            result = upnp.deleteportmapping(external_port, protocol)
            
            if result:
                logger.info(f"Successfully deleted port mapping: {external_port}/{protocol}")
                return {
                    "status": "success",
                    "message": f"Port mapping deleted successfully"
                }
            else:
                return {
                    "status": "error",
                    "message": "Failed to delete port mapping (returned false)"
                }
                
        except Exception as e:
            error_msg = f"Failed to delete port mapping: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "error",
                "message": error_msg
            }
    
    def configure_appliance_port_forwarding(
        self,
        enable_web_apps: bool = True,
        enable_remote_management: bool = False
    ) -> Dict[str, any]:
        """
        Configure port forwarding for the NuNet appliance.
        
        This configures:
        - Port 443 -> 443: For Caddy proxy to serve multiple web apps (optional)
        - Port 8443 -> 8443: For remote management access (optional)
        
        Args:
            enable_web_apps: Forward port 443 for web applications (default: True)
            enable_remote_management: Forward port 8443 for appliance management (default: False)
            
        Returns:
            Dictionary with status and configuration details
        """
        results = {
            "status": "success",
            "message": "",
            "web_apps": None,
            "remote_management": None,
            "gateway_info": None
        }
        
        # First, discover the gateway to ensure it's available
        gateway_info = self.discover_gateway()
        
        if gateway_info.get("status") != "success":
            return {
                "status": "error",
                "message": "Cannot configure port forwarding: " + gateway_info.get("message", "Unknown error"),
                "gateway_info": gateway_info
            }
        
        results["gateway_info"] = gateway_info.get("gateway_info", {})
        messages = []
        
        # Configure web apps port (443 -> 443)
        if enable_web_apps:
            logger.info("Configuring web apps port forwarding: 443 -> 443")
            web_result = self.add_port_mapping(
                external_port=443,
                internal_port=443,
                protocol="TCP",
                description="NuNet Appliance Web Apps (Caddy)"
            )
            results["web_apps"] = web_result
            
            if web_result.get("status") == "success":
                messages.append("✓ Port 443 configured for web applications")
            else:
                results["status"] = "partial"
                messages.append(f"✗ Port 443 failed: {web_result.get('message')}")
        
        # Configure remote management port (8443 -> 8443)
        if enable_remote_management:
            logger.info("Configuring remote management port forwarding: 8443 -> 8443")
            mgmt_result = self.add_port_mapping(
                external_port=8443,
                internal_port=8443,
                protocol="TCP",
                description="NuNet Appliance Remote Management"
            )
            results["remote_management"] = mgmt_result
            
            if mgmt_result.get("status") == "success":
                messages.append("✓ Port 8443 configured for remote management")
            else:
                results["status"] = "partial" if results["status"] == "success" else "error"
                messages.append(f"✗ Port 8443 failed: {mgmt_result.get('message')}")
        
        if not enable_web_apps and not enable_remote_management:
            results["status"] = "error"
            results["message"] = "No ports were configured (both options disabled)"
            return results
        
        # Build final message
        ext_ip = results["gateway_info"].get("external_ip", "unknown")
        results["message"] = " | ".join(messages)
        
        if results["status"] == "success":
            access_info = []
            if enable_web_apps:
                access_info.append(f"Web apps: https://{ext_ip}")
            if enable_remote_management:
                access_info.append(f"Management: https://{ext_ip}:8443")
            
            results["message"] += f" | External access: {', '.join(access_info)}"
        
        return results
    
    def disable_appliance_port_forwarding(
        self,
        disable_web_apps: bool = False,
        disable_remote_management: bool = False
    ) -> Dict[str, any]:
        """
        Remove port forwarding for the NuNet appliance.
        
        Args:
            disable_web_apps: Remove port 443 forwarding
            disable_remote_management: Remove port 8443 forwarding
            
        Returns:
            Dictionary with status and results
        """
        results = {
            "status": "success",
            "message": "",
            "web_apps": None,
            "remote_management": None
        }
        
        messages = []
        
        if disable_web_apps:
            logger.info("Removing web apps port forwarding (443)")
            web_result = self.delete_port_mapping(443, "TCP")
            results["web_apps"] = web_result
            
            if web_result.get("status") == "success":
                messages.append("✓ Port 443 removed")
            else:
                results["status"] = "partial"
                messages.append(f"✗ Port 443 removal failed: {web_result.get('message')}")
        
        if disable_remote_management:
            logger.info("Removing remote management port forwarding (8443)")
            mgmt_result = self.delete_port_mapping(8443, "TCP")
            results["remote_management"] = mgmt_result
            
            if mgmt_result.get("status") == "success":
                messages.append("✓ Port 8443 removed")
            else:
                results["status"] = "partial" if results["status"] == "success" else "error"
                messages.append(f"✗ Port 8443 removal failed: {mgmt_result.get('message')}")
        
        if not disable_web_apps and not disable_remote_management:
            results["status"] = "error"
            results["message"] = "No ports were specified for removal"
            return results
        
        results["message"] = " | ".join(messages)
        return results
    
    def configure_appliance_port_forwarding_legacy(
        self,
        external_port: int = 443,
        internal_port: int = 443
    ) -> Dict[str, any]:
        """
        Legacy method for backwards compatibility.
        Configure port forwarding with specific ports.
        
        Args:
            external_port: External port (default: 443)
            internal_port: Internal port (default: 443)
            
        Returns:
            Dictionary with status and configuration details
        """
        logger.info(
            f"Configuring appliance port forwarding: "
            f"{external_port} -> {internal_port}"
        )
        
        # First, discover the gateway to ensure it's available
        gateway_info = self.discover_gateway()
        
        if gateway_info.get("status") != "success":
            return {
                "status": "error",
                "message": "Cannot configure port forwarding: " + gateway_info.get("message", "Unknown error"),
                "gateway_info": gateway_info
            }
        
        # Add the port mapping
        result = self.add_port_mapping(
            external_port=external_port,
            internal_port=internal_port,
            protocol="TCP",
            description="NuNet Appliance HTTPS"
        )
        
        if result.get("status") == "success":
            result["gateway_info"] = gateway_info.get("gateway_info", {})
            result["message"] = (
                f"Appliance port forwarding configured successfully. "
                f"External access: https://{gateway_info['gateway_info']['external_ip']}:{external_port}"
            )
        
        return result
    
    def get_appliance_status(self) -> Dict[str, any]:
        """
        Get comprehensive UPnP status for the appliance.
        
        Returns:
            Dictionary with gateway status and appliance port forwarding status
        """
        # Discover gateway
        gateway = self.discover_gateway()
        
        if gateway.get("status") != "success":
            return {
                "status": "error",
                "message": "UPnP gateway not available",
                "gateway_info": gateway,
                "appliance_forwarding": None
            }
        
        # Check if appliance port forwarding is configured
        port_443_status = self.check_port_mapping(443, "TCP")
        port_8443_status = self.check_port_mapping(8443, "TCP")
        
        return {
            "status": "success",
            "gateway_info": gateway.get("gateway_info", {}),
            "appliance_forwarding": {
                "port_443": port_443_status,
                "port_8443": port_8443_status
            }
        }

