import axios from "axios";

const API_BASE = import.meta.env.VITE_API_URL;

// deployments
export async function getDeployments() {
  const res = await axios.get(`${API_BASE}/ensemble/deployments`);
  return res.data;
}

export async function getDeploymentStatus(id) {
  const res = await axios.get(`${API_BASE}/ensemble/deployments/${id}/status`);
  return res.data;
}

export async function getDeploymentManifest(id) {
  const res = await axios.get(
    `${API_BASE}/ensemble/deployments/${id}/manifest/raw`
  );
  return res.data;
}

export async function getDeploymentLogs(id, allocation = null) {
  const res = await axios.get(`${API_BASE}/ensemble/deployments/${id}/logs`, {
    params: allocation ? { allocation } : {},
  });
  return res.data;
}

export async function getDeploymentAllocations(id) {
  const res = await axios.get(
    `${API_BASE}/ensemble/deployments/${id}/allocations`
  );
  return res.data;
}

// shutdown
export async function shutdownDeployment(id) {
  const res = await axios.post(
    `${API_BASE}/ensemble/deployments/${id}/shutdown`
  );
  return res.data;
}

// deploy (POST)
export async function deployEnsemble(payload) {
  const res = await axios.post(`${API_BASE}/deployments`, payload);
  return res.data;
}

// templates
export async function getTemplates() {
  const res = await axios.get(`${API_BASE}/ensemble/templates`);
  return res.data;
}

export async function copyTemplate(payload) {
  const res = await axios.post(`${API_BASE}/templates/copy`, payload);
  return res.data;
}

// examples
export async function downloadExamples(payload) {
  const res = await axios.post(`${API_BASE}/examples/download`, payload);
  return res.data;
}

// 🔹 Fetch everything in parallel
export async function getDeploymentDetails(id: string) {
  const [status, manifest, allocations] = await Promise.all([
    getDeploymentStatus(id),
    getDeploymentManifest(id),
    getDeploymentAllocations(id),
  ]);
  return { status, manifest, allocations };
}

export interface TemplatesResponse {
  root: string;
  page: number;
  page_size: number;
  total: number;
  category_totals: Record<string, number>;
  groups: Record<string, Template[]>;
  items: Template[];
}

export interface Template {
  category: string;
  name: string;
  stem: string;
  path: string;
  yaml_path: string;
  title: string;
  description: string;
  size: number;
  modified_at: string;
  schema: any; // could type this more strictly
}

export async function fetchTemplates(page: number): Promise<TemplatesResponse> {
  const res = await axios.get<TemplatesResponse>(
    `${API_BASE}/ensemble/templates/forms?page=${page}&page_size=10&include_schema=true&require_yaml_match=true`
  );
  return res.data;
}

export async function deployFromTemplate(payload: any) {
  const res = await axios.post(
    `${API_BASE}/ensemble/deploy/from-template`,
    payload,
    {
      headers: { "Content-Type": "application/json" },
    }
  );
  return res.data;
}
