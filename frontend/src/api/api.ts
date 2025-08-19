// src/api.ts
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_URL;

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

// ==== AXIOS INSTANCE ====
const api = axios.create({
  baseURL: API_BASE,
  headers: {
    "Content-Type": "application/json",
  },
});

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

// ==== SYSINFO ENDPOINTS ====
export const getLocalIp = () =>
  api.get<string>("/sys/local-ip").then((res) => res.data);

export const getPublicIp = () =>
  api.get<string>("/sys/public-ip").then((res) => res.data);

export const getApplianceVersion = () =>
  api.get<string>("/sys/appliance-version").then((res) => res.data);

export const getSshStatus = () =>
  api.get<SshStatus>("/sys/ssh-status").then((res) => res.data);

// ==== HEALTH ====
export const getHealth = () =>
  api.get<{ ok: boolean }>("/health").then((res) => res.data);

export const allInfo = () => {
  return Promise.all([
    getDmsStatus(),
    getDmsFullStatus(),
    getSelfPeers(),
  ]).then(([status, fullStats, peerData]) => ({
    ...status,
    ...fullStats,
    ...peerData,
  }));
};

export const allSysInfo = () => {
  return Promise.all([
    getLocalIp(),
    getPublicIp(),
    getApplianceVersion(),
    getSshStatus(),
  ]).then(([localIp, publicIp, applianceVersion, sshStatus]) => ({
    localIp,
    publicIp,
    applianceVersion,
    sshStatus,
  }));
}