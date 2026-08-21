import { api } from "./api";


export interface FileLog {
  path: string;
  exists: boolean;
  readable: boolean;
  size_bytes?: number | null;
  mtime_iso?: string | null;
  tail_lines?: number | null;
  content?: string | null;
  error?: string | null;
}

export interface AllocationLogsResponse {
  dir?: string | null;
  stdout: FileLog;
  stderr: FileLog;
}

export interface DmsLogBundleResponse {
  source?: string | null;
  lines?: number | null;
  stdout?: string | null;
  stderr?: string | null;
  returncode?: number | null;
}

export interface DeploymentLogsResponse {
  status: string;
  message: string;
  stdout?: string | null;
  stderr?: string | null;
  dms?: string | null;
  allocation?: AllocationLogsResponse | null;
  dms_logs?: DmsLogBundleResponse | null;
}

export interface DeploymentInfoStatus {
  status: string;
  deployment_status: string;
  message: string;
}

export interface DeploymentInfoResponse {
  id: string;
  error?: string | null;
  raw_status?: string | null;
  status: DeploymentInfoStatus;
  manifest: any;
  allocations: string[];
  allocations_info: Record<string, any>;
}

// deployments
export interface GetDeploymentsParams {
  status?: string | string[];
  created_after?: string;
  limit?: number;
  offset?: number;
  sort?: string;
  filter?: string;
}

export interface GetDeploymentsResponse {
  status: string;
  deployments: any[];
  count: number;
  total?: number;
  has_more?: boolean;
  next_offset?: number;
}

export async function getDeployments(
  params: GetDeploymentsParams = {}
): Promise<GetDeploymentsResponse> {
  const query: Record<string, string | number> = {};
  if (params.status !== undefined) {
    query.status = Array.isArray(params.status)
      ? params.status.join(",")
      : params.status;
  }
  if (params.created_after) query.created_after = params.created_after;
  if (params.limit !== undefined) query.limit = params.limit;
  if (params.offset !== undefined) query.offset = params.offset;
  if (params.sort) query.sort = params.sort;
  if (params.filter) query.filter = params.filter;
  const res = await api.get(`/ensemble/deployments`, { params: query });
  return res.data;
}

export async function getDeploymentFile(id) {
  const res = await api.get(`/ensemble/deployments/${id}/file`);
  return res.data;
}

export interface AsyncDeploymentLogsResponse {
  status: string;
  message: string;
  logs_written_to?: string | null;
  fetch_status?: string | null;
  bytes_written?: number | null;
  follow?: boolean | null;
  follow_interval?: string | null;
  error?: string | null;
}

export interface GetDeploymentLogsOptions {
  allocation?: string | null;
  dmsQuery?: string | null;
  refreshAlloc?: boolean | null;
  dmsLines?: number | null;
  dmsView?: string | null;
  includeAlloc?: boolean | null;
  /** Comma-separated names from GET /ensemble/deployments/{id}/info?logs=true (required when include_alloc is true) */
  allocations?: string | null;
  stdoutPath?: string | null;
  stderrPath?: string | null;
}

export async function getDeploymentLogs(
  id: string,
  options: GetDeploymentLogsOptions = {}
): Promise<DeploymentLogsResponse> {
  const {
    allocation = null,
    dmsQuery = null,
    refreshAlloc = null,
    dmsLines = null,
    dmsView = null,
    includeAlloc = true,
    allocations = null,
    stdoutPath = null,
    stderrPath = null,
  } = options;

  const params: Record<string, string> = {};
  if (allocation) params.allocation = allocation;
  if (dmsQuery) params.dms_query = dmsQuery;
  if (refreshAlloc !== null) params.refresh_alloc = refreshAlloc ? "true" : "false";
  if (dmsLines !== null) params.dms_lines = `${dmsLines}`;
  if (dmsView) params.dms_view = dmsView;
  if (includeAlloc === false) params.include_alloc = "false";
  if (includeAlloc !== false) {
    if (allocations) params.allocations = allocations;
    if (stdoutPath) params.stdout_path = stdoutPath;
    if (stderrPath) params.stderr_path = stderrPath;
  }
  const res = await api.get(`/ensemble/deployments/${id}/logs`, {
    params,
  });
  return res.data;
}

export async function requestDeploymentLogs(
  id: string,
  options: {
    allocation?: string | null;
    /** Comma-separated names from GET /ensemble/deployments/{id}/info?logs=true */
    allocations: string;
    wait?: boolean;
  }
) {
  const { allocation = null, allocations, wait = false } = options;
  const params: Record<string, string> = { allocations };
  if (allocation) params.allocation = allocation;
  if (wait) params.wait = "true";
  const res = await api.post(`/ensemble/deployments/${id}/logs/request`, null, {
    params,
  });
  return res.data;
}

export interface AsyncDeploymentLogsRequestOptions {
  allocation?: string | null;
  /** Comma-separated names from GET /ensemble/deployments/{id}/info?logs=true */
  allocations: string;
}

function buildAsyncLogsParams(options: AsyncDeploymentLogsRequestOptions): Record<string, string> {
  const { allocation = null, allocations } = options;
  const params: Record<string, string> = { allocations };
  if (allocation) params.allocation = allocation;
  return params;
}

export async function startDeploymentLogsAsync(
  id: string,
  options: AsyncDeploymentLogsRequestOptions
): Promise<AsyncDeploymentLogsResponse> {
  const res = await api.post(
    `/ensemble/deployments/${id}/logs/async/start`,
    null,
    { params: buildAsyncLogsParams(options) }
  );
  return res.data;
}

export async function getDeploymentLogsAsyncStatus(
  id: string,
  options: AsyncDeploymentLogsRequestOptions
): Promise<AsyncDeploymentLogsResponse> {
  const res = await api.get(`/ensemble/deployments/${id}/logs/async/status`, {
    params: buildAsyncLogsParams(options),
  });
  return res.data;
}

export async function stopDeploymentLogsAsync(
  id: string,
  options: AsyncDeploymentLogsRequestOptions
): Promise<AsyncDeploymentLogsResponse> {
  const res = await api.post(
    `/ensemble/deployments/${id}/logs/async/stop`,
    null,
    { params: buildAsyncLogsParams(options) }
  );
  return res.data;
}

export async function autoStartDeploymentLogsAfterDeploy(deploymentId: string): Promise<void> {
  try {
    const info = await getDeploymentInfo(deploymentId, { logs: true });
    const allocations = (info.allocations ?? [])
      .map((name) => String(name ?? "").trim())
      .filter((name) => name.length > 0);
    if (allocations.length === 0) {
      console.warn(`Auto-start deployment logs skipped: no allocations for ${deploymentId}`);
      return;
    }

    const csv = allocations.join(",");
    const allHaveLogPaths = allocations.every((alloc) => {
      const logs = (info.allocations_info as Record<string, any>)?.[alloc]?.logs;
      const stdoutPath = typeof logs?.stdout_path === "string" ? logs.stdout_path.trim() : "";
      const stderrPath = typeof logs?.stderr_path === "string" ? logs.stderr_path.trim() : "";
      return stdoutPath.length > 0 && stderrPath.length > 0;
    });
    if (!allHaveLogPaths) {
      console.warn(`Auto-start deployment logs skipped: log paths not ready for ${deploymentId}`);
      return;
    }

    for (const allocation of allocations) {
      try {
        await startDeploymentLogsAsync(deploymentId, { allocation, allocations: csv });
      } catch (err) {
        console.warn(`Failed to start async logs for allocation ${allocation}:`, err);
      }
    }
  } catch (err) {
    console.warn(`Auto-start deployment logs failed for ${deploymentId}:`, err);
  }
}

export async function getDeploymentInfo(
  id: string,
  opts: {
    usage?: boolean;
    logs?: boolean;
    allocations?: string[];
  } = {}
): Promise<DeploymentInfoResponse> {
  const params = new URLSearchParams();
  if (opts.usage) params.set("usage", "true");
  if (opts.logs) params.set("logs", "true");
  (opts.allocations ?? []).forEach((name) => {
    const trimmed = String(name ?? "").trim();
    if (trimmed.length > 0) {
      params.append("allocations", trimmed);
    }
  });

  const qs = params.toString();
  const url = qs
    ? `/ensemble/deployments/${id}/info?${qs}`
    : `/ensemble/deployments/${id}/info`;
  const res = await api.get(url);
  const data = res.data as any;
  if (!data || typeof data !== "object" || typeof data.id !== "string" || !data.status) {
    throw new Error("Invalid deployment info response from backend");
  }
  return data;
}

// shutdown
export async function shutdownDeployment(id) {
  const res = await api.post(
    `/ensemble/deployments/${id}/shutdown`
  );
  return res.data;
}

export async function deleteDeployment(id: string) {
  const res = await api.delete(`/ensemble/deployments/${id}`);
  return res.data;
}

export async function pruneDeployments(params: { before?: string; all?: boolean } = {}) {
  const res = await api.post(`/ensemble/deployments/prune`, null, { params });
  return res.data;
}

// deploy (POST)
export async function deployEnsemble(payload) {
  const res = await api.post(`/ensemble/deployments`, payload);
  return res.data;
}

// templates
export async function getTemplates() {
  const res = await api.get(`/ensemble/templates`);
  return res.data;
}

export async function copyTemplate(payload) {
  const res = await api.post(`/ensemble/templates/copy`, payload);
  return res.data;
}

export interface TemplateNodesCountResponse {
  status: string;
  template_path: string;
  nodes_count: number;
  nodes?: string[];
}

export async function getTemplateNodesCount(template_path: string): Promise<TemplateNodesCountResponse> {
  const res = await api.get(`/ensemble/templates/nodes-count`, {
    params: { template_path },
  });
  return res.data;
}

// examples
export async function downloadExamples(payload) {
  const res = await api.post(`/ensemble/examples/download`, payload);
  return res.data;
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
  const res = await api.get<TemplatesResponse>(
    `/ensemble/templates/forms?page=${page}&page_size=10&include_schema=true&require_yaml_match=true`
  );
  return res.data;
}

export async function deployFromTemplate(payload: any) {
  const res = await api.post(
    `/ensemble/deploy/from-template`,
    payload,
    {
      headers: { "Content-Type": "application/json" },
    }
  );
  return res.data;
}
