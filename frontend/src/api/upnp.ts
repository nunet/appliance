// src/api/upnp.ts
import { api } from "./api";

// ==== TYPES ====
export interface RouterInfo {
  detected: boolean;
  gateway_ip: string | null;
  mac_address: string | null;
  brand: string;
  message: string;
}

export interface GatewayInfo {
  external_ip: string;
  connection_type: string;
  connection_status: string;
  gateway_ip: string;  // Router's IP address
  local_ip: string;    // Appliance's IP address
}

export interface GatewayResponse {
  status: string;
  message?: string;
  gateway_found: boolean;
  router_info?: RouterInfo;
  gateway_info?: GatewayInfo;
}

export interface PortMapping {
  external_port: number;
  protocol: string;
  internal_ip: string;
  internal_port: number;
  description: string;
  enabled: boolean;
  remote_host: string;
  lease_duration: number;
}

export interface PortMappingsResponse {
  status: string;
  message: string;
  mappings: PortMapping[];
  total_count: number;
  filtered_count: number;
}

export interface PortMappingCheckResponse {
  status: string;
  mapping_exists: boolean;
  message?: string;
  mapping?: PortMapping;
}

export interface CreatePortMappingRequest {
  external_port: number;
  internal_port: number;
  protocol: string;
  description: string;
  internal_ip?: string;
  lease_duration?: number;
}

export interface CreatePortMappingResponse {
  status: string;
  message: string;
  mapping?: PortMapping;
  newly_created?: boolean;
}

export interface ApplianceConfigureRequest {
  enable_web_apps?: boolean; // Default: true - Port 443 for web apps
  enable_remote_management?: boolean; // Default: false - Port 8443 for management
}

export interface ApplianceDisableRequest {
  disable_web_apps?: boolean; // Default: false
  disable_remote_management?: boolean; // Default: false
}

export interface ApplianceConfigureResponse {
  status: string;
  message: string;
  gateway_info?: GatewayInfo;
  web_apps?: {
    status: string;
    message?: string;
    mapping?: PortMapping;
  };
  remote_management?: {
    status: string;
    message?: string;
    mapping?: PortMapping;
  };
}

export interface ApplianceStatusResponse {
  status: string;
  message?: string;
  gateway_info?: GatewayInfo;
  appliance_forwarding?: {
    port_443: PortMappingCheckResponse;
    port_8443: PortMappingCheckResponse;
  };
}

// ==== UPNP ENDPOINTS ====

/**
 * Discover UPnP gateway on the network
 */
export const discoverGateway = (forceRefresh: boolean = false) =>
  api
    .get<GatewayResponse>(`/upnp/gateway/discover`, {
      params: { force_refresh: forceRefresh },
    })
    .then((res) => res.data);

/**
 * List all port mappings on the gateway
 * @param filterIp - Optional IP address to filter mappings (e.g., show only this appliance's mappings)
 */
export const listPortMappings = (filterIp?: string) =>
  api
    .get<PortMappingsResponse>("/upnp/mappings", {
      params: filterIp ? { filter_ip: filterIp } : {},
    })
    .then((res) => res.data);

/**
 * Check if a specific port mapping exists
 */
export const checkPortMapping = (externalPort: number, protocol: string = "TCP") =>
  api
    .get<PortMappingCheckResponse>(`/upnp/mappings/${externalPort}`, {
      params: { protocol },
    })
    .then((res) => res.data);

/**
 * Create a new port mapping
 */
export const createPortMapping = (request: CreatePortMappingRequest) =>
  api
    .post<CreatePortMappingResponse>("/upnp/mappings", request)
    .then((res) => res.data);

/**
 * Delete a port mapping
 */
export const deletePortMapping = (externalPort: number, protocol: string = "TCP") =>
  api
    .delete<{ status: string; message: string }>(`/upnp/mappings/${externalPort}`, {
      params: { protocol },
    })
    .then((res) => res.data);

/**
 * Configure appliance port forwarding
 * - enable_web_apps: Forward port 443 for web applications (Caddy proxy)
 * - enable_remote_management: Forward port 8443 for appliance management
 */
export const configureApplianceForwarding = (request?: ApplianceConfigureRequest) =>
  api
    .post<ApplianceConfigureResponse>("/upnp/appliance/configure", request || {})
    .then((res) => res.data);

/**
 * Disable appliance port forwarding
 * - disable_web_apps: Remove port 443 forwarding
 * - disable_remote_management: Remove port 8443 forwarding
 */
export const disableApplianceForwarding = (request?: ApplianceDisableRequest) =>
  api
    .post<ApplianceConfigureResponse>("/upnp/appliance/disable", request || {})
    .then((res) => res.data);

/**
 * Get comprehensive appliance UPnP status
 */
export const getApplianceStatus = () =>
  api.get<ApplianceStatusResponse>("/upnp/appliance/status").then((res) => res.data);

