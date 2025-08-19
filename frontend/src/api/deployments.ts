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
    `${API_BASE}/ensemble/deployments/${id}/manifest`
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
  const [status, manifest, logs, allocations] = await Promise.all([
    getDeploymentStatus(id),
    getDeploymentManifest(id),
    getDeploymentLogs(id),
    getDeploymentAllocations(id),
  ]);
  return { status, manifest, logs, allocations };
}
