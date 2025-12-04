// src/api.ts
import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";


// ==== TYPES ====
export interface CommandResult {
  status: string;
  message?: string;
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

export interface UpdateInfo {
  available: boolean;
  current: string;
  latest: string;
}

// ==== AXIOS INSTANCE ====
// In development, Vite runs on 5173 and backend on 8080
// In production, both frontend and backend serve from the same port
const getBaseURL = () => {
  if (import.meta.env.DEV) {
    // Allow override via env var in development
    const envUrl = (import.meta as any).env?.VITE_API_BASE_URL as string | undefined;
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

const attachToken = (config: InternalAxiosRequestConfig) => {
  if (authToken) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${authToken}`;
    console.log('🚀 Adding Authorization header to request:', config.url);
  } else {
    console.log('⚠️ No auth token available for request:', config.url);
  }
  return config;
};

api.interceptors.request.use(attachToken);

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

// ==== DMS ENDPOINTS ====
export const getDmsVersion = () =>
  api.get<string>("/dms/version").then((res) => res.data);

export const getInstallStatus = () =>
  api.get<InstallStatus>("/dms/install").then((res) => res.data);

export const getDmsStatus = () =>
  api.get<DmsStatus>("/dms/status").then((res) => res.data);

export const getDmsFullStatus = () =>
  api.get<ResourcesInfo>("/dms/status/full").then((res) => res.data);

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

// ==== SYSINFO ENDPOINTS ====
export const getLocalIp = () =>
  api.get<string>("/sys/local-ip").then((res) => res.data);

export const getPublicIp = () =>
  api.get<string>("/sys/public-ip").then((res) => res.data);

export const getApplianceVersion = () =>
  api.get<string>("/sys/appliance-version").then((res) => res.data);

export const getSshStatus = () =>
  api.get<SshStatus>("/sys/ssh-status").then((res) => res.data);

export const checkUpdates = () =>
  api.get<string>("/sys/check-updates").then((res) => {
    // The backend returns a JSON string that is itself JSON-encoded.
    const result: UpdateInfo = JSON.parse(res.data);
    return result;
  });

export const triggerUpdate = () =>
  api.post<CommandResult>("/sys/trigger-update").then((res) => res.data);

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

// ==== HEALTH ====
export const getHealth = () =>
  api.get<{ ok: boolean }>("/health").then((res) => res.data);

export const allInfo = () => {
  return Promise.all([getDmsStatus(), getDmsFullStatus(), getSelfPeers()]).then(
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

export async function getConnectedPeers(): Promise<string[]> {
  try {
    const res = await api.get("/dms/peers/connected");

    // The backend gives a "raw" string with line breaks and indentation
    const raw = res.data?.raw || "";

    // Extract peer IDs safely
    const peers = raw
      .split("\n") // break into lines
      .map((line) => line.trim()) // trim spaces
      .filter(
        (line) =>
          line.length > 0 && // remove empty
          !line.startsWith("{") && // remove { or JSON braces
          !line.startsWith("}") &&
          !line.startsWith('"Peers"') &&
          !line.includes("[") &&
          !line.includes("]") &&
          !line.includes(":")
      )
      .map(
        (line) => line.replace(/["',]/g, "") // remove quotes and commas
      );

    return peers;
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

// Single transaction item from DMS
export interface DmsPaymentItem {
  unique_id: string;
  payment_validator_did: string;
  contract_did: string;
  to_address: string;
  amount: string;
  status: "paid" | "unpaid";
  tx_hash: string; // can be empty string when unpaid
}

export interface DmsIgnoredPayment {
  unique_id: string;
  reason: string;
}

// List response with counts and sorted items (paid first, then unpaid)
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
}

// ==== PAYMENTS ENDPOINTS ====
// Config
export const getPaymentsConfig = () =>
  api.get<TokenConfig>("/payments/config").then((res) => res.data);

// New list endpoint (replaces old /payments/pending)
export const getPaymentsList = () =>
  api.get<DmsPaymentsListResponse>("/payments/list_payments").then((res) => res.data);

// Report endpoint (replaces old /payments/report)
export const reportToDms = (payload: PaymentReport) =>
  api.post<PaymentReport>("/payments/report_to_dms", payload).then((res) => res.data);
