import { api } from "./api";
import type { StatusResponse } from "../components/organizations/OnboardFlow";


export type JoinSubmitPayload = {
  org_did?: string; // optional if already selected
  name: string;
  email: string;
  roles: string[];
  why_join?: string;
  location?: string;
  discord?: string;
  wormhole?: string;
  wallet_address?: string;
  wallet_chain?: "cardano" | "ethereum";
  renewal?: boolean;
  renewing_previous?: string;
  [key: string]: unknown;
};

export const organizationsApi = {
  async getKnownOrgs(): Promise<Record<string, any>> {
    const { data } = await api.get(`/organizations/known`);
    return data;
  },

  async getJoinedOrgs(): Promise<any[]> {
    const { data } = await api.get(`/organizations/joined`);
    return data;
  },

  async postSelectOrg(org_did: string) {
    const { data } = await api.post(`/organizations/select`, {
      org_did,
    });
    return data;
  },

  async postJoinSubmit(payload: JoinSubmitPayload) {
    const { data } = await api.post(
      `/organizations/join/submit`,
      payload
    );
    return data;
  },

  async startRenewal(org_did: string) {
    const { data } = await api.post(`/organizations/renew/start`, { org_did });
    return data;
  },

  async leaveOrg(org_did: string) {
    const { data } = await api.delete(
      `/organizations/join/${encodeURIComponent(org_did)}`
    );
    return data;
  },

  async getStatus(): Promise<StatusResponse> {
    const { data } = await api.get(`/organizations/status`);
    return data;
  },

  async refreshKnownOrgs(): Promise<{
    status: string;
    count: number;
    known: Record<string, any>;
  }> {
    const { data } = await api.post(`/organizations/known/update`);
    return data;
  },

  async postProcess() {
    const { data } = await api.post(
      `/organizations/join/process`,
      true
    );
    return data;
  },

  async poll() {
    const { data } = await api.get(`/organizations/join/poll`);
    return data;
  },

  async reset() {
    const { data } = await api.post(
      `/organizations/onboarding/reset`
    );
    return data;
  },
};
