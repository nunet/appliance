import axios from "axios";
import type { StatusResponse } from "../components/organizations/OnboardFlow";


export const api = {
  async getKnownOrgs(): Promise<Record<string, any>> {
    const { data } = await axios.get(`/organizations/known`);
    return data;
  },

  async getJoinedOrgs(): Promise<Record<string, any>> {
    const { data } = await axios.get(`/organizations/joined`);
    return data;
  },

  async postSelectOrg(org_did: string) {
    const { data } = await axios.post(`/organizations/select`, {
      org_did,
    });
    return data;
  },

  async postJoinSubmit(payload: {
    org_did?: string; // optional if already selected
    name: string;
    email: string;
    location?: string;
    discord?: string;
  }) {
    const { data } = await axios.post(
      `/organizations/join/submit`,
      payload
    );
    return data;
  },

  async getStatus(): Promise<StatusResponse> {
    const { data } = await axios.get(`/organizations/status`);
    return data;
  },

  async postProcess() {
    const { data } = await axios.post(
      `/organizations/join/process`,
      true
    );
    return data;
  },

  async poll() {
    const { data } = await axios.get(`/organizations/join/poll`);
    return data;
  },

  async reset() {
    const { data } = await axios.post(
      `/organizations/onboarding/reset`
    );
    return data;
  },
};
