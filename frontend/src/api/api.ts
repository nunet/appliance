// src/api.ts
import axios, { AxiosError } from "axios";
import { AuthResponse } from "./auth";


// ==== TYPES ====
export interface CommandResult {
  status: string;
  message?: string;
}

/** API returns HTTP 200 with `status: "error"` in the body for failed nunet/system commands. */
export function isCommandResultOk(res: CommandResult | undefined): boolean {
  return res?.status === "success" || res?.status === "warning";
}

export interface InstallStatus {
  status: string;
  version: string;
}

export interface DmsStatus {
  dms_status: string;
  dms_version: string;
  dms_running: boolean;
  dms_context: string;
  dms_did: string;
  dms_peer_id: string;
  dms_is_relayed?: boolean;
}

export interface PeerInfo {
  dms_status: string;
  dms_version: string;
  dms_running: boolean;
  dms_context: string;
  dms_did: string;
  dms_peer_id: string;
  dms_is_relayed: boolean;
}

export interface ResourcesInfo {
  onboarding_status: string;
  free_resources: string;
  allocated_resources: string;
  onboarded_resources: string;
}

export interface SshStatus {
  running: boolean;
  authorized_keys: number;
}

export type ApplianceEnvironment = "production" | "staging";

export interface EnvironmentUpdateChannelStatus {
  channel: string;
  resolved_channel: string;
  fell_back: boolean;
}

export interface EnvironmentStatus {
  environment: ApplianceEnvironment;
  updates: {
    appliance: EnvironmentUpdateChannelStatus;
    dms: EnvironmentUpdateChannelStatus;
  };
  ethereum: {
    chain_id: number;
    token_address: string;
    token_symbol: string;
    token_decimals: number;
    explorer_base_url?: string | null;
    network_name?: string | null;
  };
}

export interface UpdateInfo {
  available: boolean;
  current: string;
  latest: string;
}

export interface DmsLogBundleResponse {
  source?: string | null;
  lines?: number | null;
  stdout?: string | null;
  stderr?: string | null;
  returncode?: number | null;
}

export interface DmsLogsResponse {
  status: string;
  message?: string;
  dms?: string | null;
  dms_logs?: DmsLogBundleResponse | null;
}

export type ApplianceLogs = Record<string, string>;

export interface ApplianceUptime {
  uptime: string;
}

export interface TelemetryPluginConfig {
  enabled: boolean;
  remote_enabled: boolean;
  local_enabled: boolean;
  dcgm_exporter_enabled: boolean;
  grafana_enabled: boolean;
  nvidia_gpu_available: boolean;
  gateway_url: string;
  token_set: boolean;
  token_last8?: string | null;
  generated_config_path: string;
  local_grafana_running: boolean;
  cadvisor_running: boolean;
  grafana_url: string;
}

export interface TelemetryPluginConfigUpdate {
  enabled?: boolean;
  remote_enabled?: boolean;
  local_enabled?: boolean;
  dcgm_exporter_enabled?: boolean;
  grafana_enabled?: boolean;
  gateway_url?: string;
  telemetry_token?: string;
  generated_config_path?: string;
}

export interface TelemetryPluginStatus {
  plugin_id: string;
  installed_version?: string | null;
  updated_at?: string | null;
  alloy_installed?: boolean | null;
  alloy_running?: boolean | null;
  local_mimir_running?: boolean | null;
  dcgm_exporter_running?: boolean | null;
  local_grafana_running?: boolean | null;
  cadvisor_running?: boolean | null;
  grafana_enabled?: boolean | null;
  grafana_url?: string | null;
  nvidia_gpu_available?: boolean | null;
  enabled?: boolean | null;
  token_set?: boolean | null;
  raw_status?: Record<string, unknown> | null;
}

export interface TelemetryLocalMetricPoint {
  ts: number;
  cpu_percent?: number | null;
  memory_percent?: number | null;
  disk_utilization_percent?: number | null;
  disk_read_bytes_per_sec?: number | null;
  disk_write_bytes_per_sec?: number | null;
  network_rx_bytes_per_sec?: number | null;
  network_tx_bytes_per_sec?: number | null;
  gpu_utilization_percent?: number | null;
  gpu_temp_celsius?: number | null;
  gpu_vram_used_mib?: number | null;
}

export interface TelemetryLocalMetricsResponse {
  available: boolean;
  reason?: string | null;
  range_minutes: number;
  step_seconds: number;
  points: TelemetryLocalMetricPoint[];
}

// ==== AXIOS INSTANCE ====
// In development, Vite runs on 5173 and backend on 8080
// In production, both frontend and backend serve from the same port
const getBaseURL = () => {
  if (import.meta.env.DEV) {
    // Allow override via env var in development
    const envUrl = (import.meta.env as ImportMetaEnv & { VITE_API_BASE_URL?: string }).VITE_API_BASE_URL;
    if (envUrl && envUrl.trim().length > 0) {
      return envUrl;
    }
    // Default to the current host with backend dev port 8080
    const protocol = window.location.protocol; // e.g., http:
    const host = window.location.hostname;     // e.g., 192.168.88.149 or localhost
    return `${protocol}//${host}:8080`;
  } else {
    // Production mode: frontend and backend serve from same origin
    return "";
  }
};

export const api = axios.create({
  baseURL: getBaseURL(),
  headers: {
    "Content-Type": "application/json",
  },
});

let authToken: string | null = null;
let unauthorizedHandler: (() => void) | null = null;
let onTokenRefreshedHandler: ((response: AuthResponse) => void) | null = null;
let refreshPromise: Promise<string | null> | null = null;

const TOKEN_KEY = "nunet-admin-token";
const TOKEN_EXPIRY_KEY = "nunet-admin-expiry";
const REFRESH_THRESHOLD_MS = 60 * 1000; // 1 minute

api.interceptors.request.use(async (config) => {
  // Do not intercept refresh requests
  if (config.url?.endsWith("/auth/refresh")) {
    if (authToken) {
      config.headers.Authorization = `Bearer ${authToken}`;
    }
    return config;
  }

  const expiryStr = localStorage.getItem(TOKEN_EXPIRY_KEY);
  const expiresAt = expiryStr ? Number.parseInt(expiryStr, 10) : 0;
  const shouldRefresh = authToken && expiresAt && expiresAt - Date.now() < REFRESH_THRESHOLD_MS;

  if (shouldRefresh) {
    if (!refreshPromise) {
      console.log("🚀 Kicking off token refresh...");
      refreshPromise = api
        .post<AuthResponse>("/auth/refresh")
        .then((res) => {
          const newAuthData = res.data;
          console.log("✅ Token refreshed successfully via interceptor.");
          onTokenRefreshedHandler?.(newAuthData);
          return newAuthData.access_token;
        })
        .catch((err) => {
          console.error("Token refresh failed in interceptor", err);
          unauthorizedHandler?.();
          return Promise.reject(err);
        })
        .finally(() => {
          refreshPromise = null;
        });
    }

    try {
      const newToken = await refreshPromise;
      if (newToken && config.headers) {
        config.headers.Authorization = `Bearer ${newToken}`;
      }
    } catch (error) {
      return Promise.reject(error);
    }
  } else if (authToken) {
    config.headers.Authorization = `Bearer ${authToken}`;
  }

  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      unauthorizedHandler?.();
    }
    return Promise.reject(error);
  }
);

export const setAuthToken = (token: string | null) => {
  console.log('🔑 Setting auth token in axios:', token ? 'Token present' : 'No token');
  authToken = token;
};

export const setUnauthorizedHandler = (handler: (() => void) | null) => {
  unauthorizedHandler = handler;
};

export const setOnTokenRefreshedHandler = (handler: (response: AuthResponse) => void) => {
  onTokenRefreshedHandler = handler;
};

export const refreshAuthToken = async (): Promise<AuthResponse> => {
  const res = await api.post<AuthResponse>("/auth/refresh");
  const data = res.data;
  authToken = data.access_token;
  localStorage.setItem(TOKEN_KEY, data.access_token);
  localStorage.setItem(TOKEN_EXPIRY_KEY, String(Date.now() + data.expires_in * 1000));
  onTokenRefreshedHandler?.(data);
  return data;
};

// ==== DMS ENDPOINTS ====
export const getDmsVersion = () =>
  api.get<string>("/dms/version").then((res) => res.data);

export const getInstallStatus = () =>
  api.get<InstallStatus>("/dms/install").then((res) => res.data);

export const getDmsStatus = (refresh = false) =>
  api
    .get<DmsStatus>("/dms/status", { params: refresh ? { refresh: true } : undefined })
    .then((res) => res.data);

export const getDmsFullStatus = (refresh = false) =>
  api
    .get<ResourcesInfo>("/dms/status/resources", { params: refresh ? { refresh: true } : undefined })
    .then((res) => res.data);

export const getPeerId = () =>
  api.get<string>("/dms/peer-id").then((res) => res.data);

export const getSelfPeers = () =>
  api.get<PeerInfo>("/dms/peers/self").then((res) => res.data);

export const restartDms = () =>
  api.post<CommandResult>("/dms/restart").then((res) => res.data);

export const stopDms = () =>
  api.post<CommandResult>("/dms/stop").then((res) => res.data);

export const enableDms = () =>
  api.post<CommandResult>("/dms/enable").then((res) => res.data);

export const disableDms = () =>
  api.post<CommandResult>("/dms/disable").then((res) => res.data);

export const onboardCompute = () =>
  api.post<CommandResult>("/dms/onboard").then((res) => res.data);

export const offboardCompute = () =>
  api.post<CommandResult>("/dms/offboard").then((res) => res.data);

// export const getResourcesAllocated = () =>
//   api.get<Record<string, any>>("/dms/resources/allocated").then(res => res.data);

export const initDms = () =>
  api.post<CommandResult>("/dms/init").then((res) => res.data);

export const updateDms = () =>
  api.post<CommandResult>("/dms/update").then((res) => res.data);

export const checkDmsUpdates = () =>
  api.get<string>("/dms/check-updates").then((res) => {
    // The backend returns a JSON string that is itself JSON-encoded.
    const result: UpdateInfo = JSON.parse(res.data);
    return result;
  });

export const getFilteredDmsLogs = (
  dmsQuery: string | null = null,
  dmsLines: number | null = null,
  dmsView: string | null = null
) => {
  const params: Record<string, string> = {};
  if (dmsQuery) params.dms_query = dmsQuery;
  if (dmsLines) params.dms_lines = `${dmsLines}`;
  if (dmsView) params.dms_view = dmsView;
  return api.get<DmsLogsResponse>("/dms/logs/filtered", { params }).then((res) => res.data);
};

// ==== SYSINFO ENDPOINTS ====
export const getLocalIp = () =>
  api.get<string>("/sys/local-ip").then((res) => res.data);

export const getPublicIp = () =>
  api.get<string>("/sys/public-ip").then((res) => res.data);

export const getApplianceVersion = () =>
  api.get<string>("/sys/appliance-version").then((res) => res.data);

export const getSshStatus = () =>
  api.get<SshStatus>("/sys/ssh-status").then((res) => res.data);

export const getEnvironmentStatus = () =>
  api.get<EnvironmentStatus>("/sys/environment").then((res) => res.data);

export const checkUpdates = () =>
  api.get<string>("/sys/check-updates").then((res) => {
    // The backend returns a JSON string that is itself JSON-encoded.
    const result: UpdateInfo = JSON.parse(res.data);
    return result;
  });

export const triggerUpdate = () =>
  api.post<CommandResult>("/sys/trigger-update").then((res) => res.data);

export const triggerPluginSync = () =>
  api.post<CommandResult>("/sys/trigger-plugin-sync").then((res) => res.data);

export const uninstallTelemetryPlugin = () =>
  api.post<CommandResult>("/sys/plugins/telemetry-exporter/uninstall").then((res) => res.data);

export const getTelemetryPluginConfig = () =>
  api.get<TelemetryPluginConfig>("/sys/plugins/telemetry-exporter/config").then((res) => res.data);

export const updateTelemetryPluginConfig = (payload: TelemetryPluginConfigUpdate) =>
  api.put<TelemetryPluginConfig>("/sys/plugins/telemetry-exporter/config", payload).then((res) => res.data);

export const getTelemetryPluginStatus = () =>
  api.get<TelemetryPluginStatus>("/sys/plugins/telemetry-exporter/status").then((res) => res.data);

export const getTelemetryLocalMetrics = (rangeMinutes = 60, stepSeconds = 30) =>
  api
    .get<TelemetryLocalMetricsResponse>("/sys/plugins/telemetry-exporter/local-metrics", {
      params: { range_minutes: rangeMinutes, step_seconds: stepSeconds },
    })
    .then((res) => res.data);

export const getDockerContainer = () =>
  api
    .get<{
      count: number;
      containers: {
        id: string;
        name: string;
        image: string;
        running_for: string;
      }[];
    }>("/sys/docker/containers")
    .then((res) => res.data);

// ==== APPLIANCE ENDPOINTS ====
export const getApplianceLogs = (lines: number) =>
  api.get<ApplianceLogs>("/appliance/logs", { params: { lines } }).then((res) => res.data);

export const getApplianceUptime = () =>
  api.get<ApplianceUptime>("/appliance/uptime").then((res) => res.data);

// ==== HEALTH ====
export const getHealth = () =>
  api.get<{ ok: boolean }>("/health").then((res) => res.data);

export const allInfo = (refresh = false) => {
  return Promise.all([getDmsStatus(refresh), getDmsFullStatus(refresh), getSelfPeers()]).then(
    ([status, fullStats, peerData]) => ({
      ...status,
      ...fullStats,
      ...peerData,
    })
  );
};

export const allSysInfo = () => {
  return Promise.all([
    getLocalIp(),
    getPublicIp(),
    getApplianceVersion(),
    getSshStatus(),
    checkUpdates(),
    checkDmsUpdates(),
  ]).then(([localIp, publicIp, applianceVersion, sshStatus, updateInfo, dmsUpdateInfo]) => ({
    localIp,
    publicIp,
    applianceVersion,
    sshStatus,
    updateInfo,
    dmsUpdateInfo,
  }));
};

export async function getConnectedPeers(refresh = false): Promise<string[]> {
  try {
    const res = await api.get("/dms/peers/connected", {
      params: refresh ? { refresh: true } : undefined,
    });
    const peers = Array.isArray(res.data?.peers) ? res.data.peers : [];
    if (peers.length > 0) {
      return peers
        .map((entry: { peer_id?: unknown } | string) =>
          typeof entry === "string"
            ? entry
            : typeof entry?.peer_id === "string"
              ? entry.peer_id
              : ""
        )
        .filter((value: string) => value.trim().length > 0);
    }

    const raw = res.data?.raw || "";
    return raw
      .split("\n")
      .map((line: string) => line.trim())
      .filter(
        (line: string) =>
          line.length > 0 &&
          !line.startsWith("{") &&
          !line.startsWith("}") &&
          !line.startsWith('"Peers"') &&
          !line.includes("[") &&
          !line.includes("]") &&
          !line.includes(":")
      )
      .map((line: string) => line.replace(/["',]/g, ""));
  } catch (err) {
    console.error("Failed to fetch connected peers:", err);
    return [];
  }
}
// ==== PAYMENTS TYPES ====
// Config for the token/network
export interface TokenConfig {
  chain_id: number;
  token_address: string;
  token_symbol: string;
  token_decimals: number;
  explorer_base_url?: string | null;
  network_name?: string | null;
}

export interface CardanoTokenConfig extends TokenConfig {
  policy_id: string;
  asset_name_hex: string;
  asset_name: string;
  asset_name_encoded?: string;
  asset_id: string;
}

export interface PaymentsConfig {
  ethereum: TokenConfig;
  cardano: CardanoTokenConfig;
}

export type DmsPaymentMetadata = Record<string, unknown>;

// Single transaction item from DMS
export interface DmsPaymentItem {
  unique_id: string;
  payment_validator_did: string;
  contract_did: string;
  to_address: string;
  from_address?: string;
  amount: string;
  original_amount?: string;
  pricing_currency?: string;
  requires_conversion?: boolean;
  status: "paid" | "unpaid";
  tx_hash: string; // can be empty string when unpaid
  blockchain?: string;
  metadata?: DmsPaymentMetadata | null;
}

export interface DmsIgnoredPayment {
  unique_id: string;
  reason: string;
}

// List response with counts and sorted items (unpaid first, then paid)
export interface DmsPaymentsListResponse {
  total_count: number;
  paid_count: number;
  unpaid_count: number;
  items: DmsPaymentItem[];
  ignored_count: number;
  ignored?: DmsIgnoredPayment[];
}

// Report payload we POST to DMS via backend after MetaMask sends
export interface PaymentReport {
  tx_hash: string;
  to_address: string;
  amount: string;
  payment_provider: string; // maps to unique_id
  blockchain?: string;
  quote_id?: string;
}

export interface CardanoBuildPayload {
  from_address: string;
  to_address: string;
  amount: string;
  payment_provider: string;
  change_address?: string;
}

export interface CardanoBuildResponse {
  tx_cbor: string;
  tx_body_cbor: string;
  tx_hash: string;
  fee_lovelace: string;
  network: string;
}

export interface CardanoSubmitPayload {
  tx_body_cbor: string;
  witness_set_cbor: string;
  payment_provider: string;
  to_address: string;
  amount: string;
  quote_id?: string;
}

export interface PaymentQuoteGetPayload {
  unique_id: string;
  dest: string;
}

export interface PaymentQuote {
  quote_id: string;
  original_amount: string;
  converted_amount: string;
  pricing_currency: string;
  payment_currency: string;
  exchange_rate: string;
  expires_at: string;
}

export interface PaymentQuoteValidatePayload {
  quote_id: string;
  dest: string;
}

export interface PaymentQuoteValidation {
  valid: boolean;
  quote_id?: string;
  original_amount?: string;
  converted_amount?: string;
  pricing_currency?: string;
  payment_currency?: string;
  exchange_rate?: string;
  expires_at?: string;
  error?: string;
}

export interface PaymentQuoteCancelPayload {
  quote_id: string;
  dest: string;
}

// ==== PAYMENTS ENDPOINTS ====
// Config
export const getPaymentsConfig = () =>
  api.get<PaymentsConfig>("/payments/config").then((res) => res.data);

// New list endpoint (replaces old /payments/pending)
export const getPaymentsList = () =>
  api.get<DmsPaymentsListResponse>("/payments/list_payments").then((res) => res.data);

// Report endpoint (replaces old /payments/report)
export const reportToDms = (payload: PaymentReport) =>
  api.post<PaymentReport>("/payments/report_to_dms", payload).then((res) => res.data);

export const getPaymentQuote = (payload: PaymentQuoteGetPayload) =>
  api.post<PaymentQuote>("/payments/quote/get", payload).then((res) => res.data);

export const validatePaymentQuote = (payload: PaymentQuoteValidatePayload) =>
  api.post<PaymentQuoteValidation>("/payments/quote/validate", payload).then((res) => res.data);

export const cancelPaymentQuote = (payload: PaymentQuoteCancelPayload) =>
  api.post<{ status: string }>("/payments/quote/cancel", payload).then((res) => res.data);

export const buildCardanoTx = (payload: CardanoBuildPayload) =>
  api.post<CardanoBuildResponse>("/payments/cardano/build", payload).then((res) => res.data);

export const submitCardanoTx = (payload: CardanoSubmitPayload) =>
  api.post<PaymentReport>("/payments/cardano/submit", payload).then((res) => res.data);
