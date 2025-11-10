import { api } from "./api";

export type ContractState =
  | "UNKNOWN"
  | "DRAFT"
  | "ACCEPTED"
  | "APPROVED"
  | "SIGNED"
  | "COMPLETED"
  | "SETTLED"
  | "TERMINATED"
  | "EXPIRED"
  | "REJECTED"
  | "CANCELLED";

export type ContractPaymentType = "unknown" | "blockchain" | "fiat";

export type ContractBlockchain =
  | "UNKNOWN"
  | "ETHEREUM"
  | "POLYGON"
  | "BSC"
  | "CARDANO";

export interface ContractDIDRef {
  uri: string;
}

export interface ContractResourceCPU {
  cores?: number | null;
  clock_speed?: number | null;
}

export interface ContractResourceMemory {
  size?: number | null;
}

export interface ContractResourceDisk {
  size?: number | null;
}

export interface ContractResourceConfiguration {
  cpu?: ContractResourceCPU | null;
  ram?: ContractResourceMemory | null;
  disk?: ContractResourceDisk | null;
  [key: string]: unknown;
}

export interface ContractTerminationOption {
  allowed?: boolean | null;
  notice_period?: number | null;
  [key: string]: unknown;
}

export interface ContractPenalty {
  condition?: string | null;
  penalty?: number | null;
  [key: string]: unknown;
}

export interface ContractParticipants {
  provider?: ContractDIDRef | null;
  requestor?: ContractDIDRef | null;
  [key: string]: unknown;
}

export interface ContractPaymentAddress {
  requester_addr?: string | null;
  provider_addr?: string | null;
  currency?: string | null;
  blockchain?: ContractBlockchain | null;
  [key: string]: unknown;
}

export interface ContractPaymentDetails {
  payment_type: ContractPaymentType;
  requester_addr?: string | null;
  provider_addr?: string | null;
  currency?: string | null;
  fees_per_allocation?: string | null;
  timestamp?: string | null;
  blockchain?: ContractBlockchain | null;
  addresses?: ContractPaymentAddress[] | null;
  [key: string]: unknown;
}

export interface ContractDuration {
  start_date?: string | null;
  end_date?: string | null;
  [key: string]: unknown;
}

export interface ContractMetadata {
  contract_did: string;
  current_state: ContractState;
  solution_enabler_did?: ContractDIDRef | null;
  payment_validator_did?: ContractDIDRef | null;
  resource_configuration?: ContractResourceConfiguration | null;
  termination_option?: ContractTerminationOption | null;
  penalties: ContractPenalty[];
  duration?: ContractDuration | null;
  participants?: ContractParticipants | null;
  payment_details?: ContractPaymentDetails | null;
  paid?: boolean | null;
  settled?: boolean | null;
  signatures?: unknown;
  verification?: Record<string, unknown> | null;
  contract_proof?: unknown;
  contract_terms?: string | null;
  termination_started?: string | null;
  transitions: Record<string, unknown>[];
  [key: string]: unknown;
}

export interface ContractListResponse {
  status: "success" | "error";
  message?: string | null;
  contracts: ContractMetadata[];
  filter?: string | null;
  total_count?: number | null;
  filtered_count?: number | null;
  raw?: Record<string, unknown> | null;
  stdout?: string | null;
  stderr?: string | null;
  returncode?: number | null;
  command?: string | null;
}

export interface ContractStateResponse {
  status: "success" | "error";
  message?: string | null;
  contract?: ContractMetadata | null;
  raw?: Record<string, unknown> | null;
  stdout?: string | null;
  stderr?: string | null;
  returncode?: number | null;
  command?: string | null;
}

export interface ContractCreatePayload {
  contract: Record<string, unknown>;
  destination?: string | null;
  template_id?: string | null;
  organization_did?: string | null;
  extra_args?: string[];
}

export interface ContractApprovePayload {
  contract_did: string;
  extra_args?: string[];
}

export interface ContractTerminatePayload {
  contract_did: string;
  contract_host_did?: string | null;
  extra_args?: string[];
}

export interface ContractActionResponse {
  status: "success" | "error";
  message?: string | null;
  contract_did?: string | null;
  contract_file?: string | null;
  destination?: string | null;
  template_id?: string | null;
  source?: "local" | "remote" | null;
  organization_did?: string | null;
  contract_host_did?: string | null;
  stdout?: string | null;
  stderr?: string | null;
  returncode?: number | null;
  command?: string | null;
}

export interface ContractTemplateSummary {
  template_id: string;
  name: string;
  description?: string | null;
  source: "local" | "remote";
  origin?: string | null;
  organization_did?: string | null;
  organizations: string[];
  tags: string[];
  categories: string[];
  default_destination?: string | null;
}

export interface ContractTemplateDetail extends ContractTemplateSummary {
  contract: Record<string, unknown>;
  metadata?: Record<string, unknown> | null;
}

export interface ContractTemplateListResponse {
  status: "success" | "error";
  templates: ContractTemplateSummary[];
  message?: string | null;
}

export type ContractListView = "incoming" | "active" | "all";

export const contractsApi = {
  async getContracts(view: ContractListView = "all", signal?: AbortSignal): Promise<ContractListResponse> {
    const { data } = await api.get<ContractListResponse>("/api/contracts/", {
      params: { view },
      signal,
    });
    return data;
  },

  async getIncomingContracts(signal?: AbortSignal): Promise<ContractListResponse> {
    return contractsApi.getContracts("incoming", signal);
  },

  async getSignedContracts(signal?: AbortSignal): Promise<ContractListResponse> {
    return contractsApi.getContracts("active", signal);
  },

  async getContractState(
    contractDid: string,
    options: { hostDid?: string | null; signal?: AbortSignal } = {}
  ): Promise<ContractStateResponse> {
    const { hostDid, signal } = options;
    const params = hostDid ? { contract_host_did: hostDid } : undefined;
    const { data } = await api.get<ContractStateResponse>(`/api/contracts/state/${encodeURIComponent(contractDid)}`, {
      params,
      signal,
    });
    return data;
  },

  async createContract(payload: ContractCreatePayload): Promise<ContractActionResponse> {
    const { data } = await api.post<ContractActionResponse>("/api/contracts/create", payload);
    return data;
  },

  async approveContract(payload: ContractApprovePayload): Promise<ContractActionResponse> {
    const { data } = await api.post<ContractActionResponse>("/api/contracts/approve", payload);
    return data;
  },

  async terminateContract(payload: ContractTerminatePayload): Promise<ContractActionResponse> {
    const { data } = await api.post<ContractActionResponse>("/api/contracts/terminate", payload);
    return data;
  },

  async getContractTemplates(signal?: AbortSignal): Promise<ContractTemplateListResponse> {
    const { data } = await api.get<ContractTemplateListResponse>("/api/contracts/templates", {
      signal,
    });
    return data;
  },

  async getContractTemplateDetail(templateId: string, signal?: AbortSignal): Promise<ContractTemplateDetail> {
    const { data } = await api.get<ContractTemplateDetail>(
      `/api/contracts/templates/${encodeURIComponent(templateId)}`,
      { signal }
    );
    return data;
  },
};

export type ContractSummaryCounts = {
  incoming: number;
  signed: number;
};
