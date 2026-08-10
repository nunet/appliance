"use client";

import { useNavigate, useParams } from "react-router-dom";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import {
  getDeploymentInfo,
  type DeploymentInfoResponse,
  getDeploymentLogs,
  type DeploymentLogsResponse,
  getDeploymentLogsAsyncStatus,
  startDeploymentLogsAsync,
  stopDeploymentLogsAsync,
  shutdownDeployment,
  getDeploymentFile,
} from "@/api/deployments";
import {
  ArrowLeft,
  CheckCircle,
  Repeat2Icon,
  XCircleIcon,
  Download,
  Loader2,
  Maximize2,
  FileText,
  Play,
  Square,
} from "lucide-react";
import {
  Card,
  CardHeader,
  CardContent,
  CardDescription,
  CardTitle,
  CardFooter,
  CardAction,
} from "../components/ui/card";
import { Separator } from "../components/ui/separator";
import { Button } from "../components/ui/button";
import { toast } from "sonner";
import { CopyButton } from "../components/ui/CopyButton";
import { LeftTruncatedText } from "../components/ui/LeftTruncatedText";
import { useEffect, useMemo, useRef, useState } from "react";
import { ManifestPanel } from "../components/deployments/ManifestPanel";
import { Tooltip, TooltipTrigger, TooltipContent } from "../components/ui/tooltip";
import { RefreshButton } from "../components/ui/RefreshButton";
import { Skeleton } from "../components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { YamlViewer } from "../components/ui/YamlViewer";
import { ToggleGroup, ToggleGroupItem } from "../components/ui/toggle-group";
import { Switch } from "../components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { DmsLogSection } from "../components/logging/DmsLogSection";
import { DmsLogView, parseDmsLogEntries } from "../lib/dmsLogs";

export default function DeploymentDetailsPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [_alloc, _setAlloc] = useState<string | null>(null);

  // Toggle for the consolidated /info call (lifted so all cards share a single fetch).
  const [includeUsage, setIncludeUsage] = useState(false);

  // ?? Shutdown handler
  const handleShutdown = async (deploymentId: string) => {
    try {
      const res = await shutdownDeployment(deploymentId);
      toast.success(res.status, { description: res.message });
      return true;
    } catch (error: any) {
      toast.error("Shutdown Failed", {
        description:
          error?.response?.data?.message || "An unexpected error occurred",
      });
      return false;
    }
  };

  // Single consolidated query that powers every card on the page. Log path
  // metadata is always requested (logs=true) so DeploymentLogsCard can reuse
  // paths without a second GET .../info.
  const detailsQuery = useQuery<DeploymentInfoResponse>({
    queryKey: ["deployment-info", id, includeUsage ? 1 : 0],
    queryFn: () =>
      getDeploymentInfo(id!, {
        usage: includeUsage,
        logs: true,
      }),
    enabled: Boolean(id),
    refetchOnMount: "always",
    refetchOnWindowFocus: false,
    staleTime: Infinity,
    gcTime: Infinity,
    placeholderData: keepPreviousData,
  });

  const details = detailsQuery.data;
  const refetchDetails = detailsQuery.refetch;
  const isFetchingDetails = detailsQuery.isFetching;
  const isLoadingDetails = detailsQuery.isLoading;

  const deploymentSummary = useMemo(() => {
    if (!id) return null;
    if (!details) {
      return {
        id,
        status: "unknown",
        type: "",
        timestamp: "",
        ensemble_file: "",
        ensemble_file_name: undefined as string | undefined,
        ensemble_file_path: undefined as string | undefined,
        ensemble_file_relative: undefined as string | undefined,
      };
    }
    return {
      id: details.id ?? id,
      status: details.status?.deployment_status ?? "unknown",
      type: "",
      timestamp: "",
      ensemble_file: "",
      ensemble_file_name: undefined as string | undefined,
      ensemble_file_path: undefined as string | undefined,
      ensemble_file_relative: undefined as string | undefined,
    };
  }, [id, details]);

  if (!id) {
    return null;
  }

  if (detailsQuery.isError) {
    const err = detailsQuery.error as { message?: string; response?: { data?: { message?: string; detail?: unknown } } };
    const detail = err?.response?.data?.detail;
    const detailStr =
      typeof detail === "string"
        ? detail
        : detail && typeof detail === "object" && "message" in detail
          ? String((detail as { message?: string }).message)
          : undefined;
    const message =
      err?.response?.data?.message ||
      detailStr ||
      err?.message ||
      "Unable to load deployment details.";
    return (
      <div
        className="flex flex-col items-center justify-center mt-20 text-center px-4"
        data-testid="deployment-detail-error"
      >
        <p className="text-lg font-medium mb-2">Could not load deployment</p>
        <p className="text-sm text-muted-foreground mb-4 max-w-lg break-words">{message}</p>
        <Button variant="outline" onClick={() => navigate("/deploy")} className="flex items-center gap-2">
          <ArrowLeft className="h-4 w-4" /> Back to Deployments
        </Button>
      </div>
    );
  }

  if (!deploymentSummary) {
    return null;
  }

  return (
    <>
      {/* Deployment Info Card */}
      <DeploymentInfoCard
          deployment={deploymentSummary}
          handleShutdown={handleShutdown}
          details={details}
          refetch={refetchDetails}
          isFetching={isFetchingDetails}
        />

      {/* Deployment Progress + Allocations */}
      <div className="grid grid-cols-1 gap-4 px-4 lg:grid-cols-3 xl:grid-cols-3 lg:px-6 my-4">
        <DeploymentProgressCard details={details} />
        <DeploymentAllocationsCard
          selectedAllocation={_alloc}
          details={details}
          isFetching={isFetchingDetails}
          isLoading={isLoadingDetails}
          includeUsage={includeUsage}
          setIncludeUsage={setIncludeUsage}
        />
      </div>

      {/* Manifest */}
      <DeploymentManifestCard
        _setAlloc={_setAlloc}
        manifest={details?.manifest}
        isLoading={isLoadingDetails}
      />

      {/* Logs */}
      <DeploymentLogsCard
        deploymentId={id!}
        alloc={_alloc}
        details={details}
        isLoadingDetails={isLoadingDetails}
      />
    </>
  );
}


// ?? Deployment Info
function DeploymentInfoCard({
  deployment,
  handleShutdown,
  details,
  refetch,
  isFetching,
}: any) {
  const [isShuttingDown, setIsShuttingDown] = useState(false);
  const [isFileModalOpen, setIsFileModalOpen] = useState(false);
  const [fileLoading, setFileLoading] = useState(false);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [fileMeta, setFileMeta] = useState<{ name?: string; path?: string; relative?: string } | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [fileCandidates, setFileCandidates] = useState<string[]>([]);
  const shutdownRefreshTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const pickString = (...candidates: Array<unknown>) => {
    for (const candidate of candidates) {
      if (typeof candidate === "string") {
        const trimmed = candidate.trim();
        if (trimmed.length > 0) {
          return trimmed;
        }
      }
    }
    return undefined;
  };

  const manifestData: Record<string, any> = details?.manifest?.manifest ?? {};
  const allocationValues = Object.values(manifestData?.allocations ?? {}) as Array<Record<string, any>>;
  const primaryAllocation = allocationValues[0] ?? {};

  const statusText = pickString(details?.status?.deployment_status, deployment.status) ?? "N/A";
  const typeText = pickString(
    deployment.type,
    primaryAllocation?.type,
    manifestData?.type,
    manifestData?.deployment_type,
    manifestData?.deployment?.type,
    details?.status?.deployment_type
  ) ?? "N/A";
  const sanitizedTypeText = (() => {
    const candidate = typeText.trim().toLowerCase();
    if (!candidate || candidate === "n/a" || candidate === "active" || candidate === "historical") {
      return null;
    }
    return typeText;
  })();
  const timestampText = ((ts) => (ts ? new Date(ts).toLocaleString() : "N/A"))(
    pickString(deployment.timestamp)
  );
  const ensembleText = pickString(
    deployment.ensemble_file,
    manifestData?.ensemble_file,
    details?.manifest?.ensemble_file
  ) ?? "N/A";
  const relativeCandidate = pickString(
    deployment.ensemble_file_relative,
    deployment.ensemble_file,
    manifestData?.ensemble_file,
    details?.manifest?.ensemble_file
  );
  const hasEnsembleFile = ensembleText !== "N/A";
  const ensembleDisplayText = hasEnsembleFile
    ? (ensembleText.split(/[\\/]/).pop() ?? ensembleText)
    : "N/A";
  const fullFilePath = fileMeta?.path ?? fileMeta?.relative ?? null;
  const shortFilePath = fullFilePath ? (fullFilePath.split(/[\\/]/).pop() ?? fullFilePath) : null;

  const handleFileModalChange = (open: boolean) => {
    setIsFileModalOpen(open);
    if (!open) {
      setFileLoading(false);
      setFileContent(null);
      setFileError(null);
      setFileCandidates([]);
    }
  };

  const scheduleStatusRefresh = () => {
    if (shutdownRefreshTimeoutRef.current) {
      clearTimeout(shutdownRefreshTimeoutRef.current);
    }

    // Refresh deployment info only; the deployments list refetches when the user
    // opens Deployments or uses browser back (DeploymentsTable refetchOnMount).
    shutdownRefreshTimeoutRef.current = setTimeout(() => {
      void refetch();
      shutdownRefreshTimeoutRef.current = null;
    }, 10_000);
  };

  useEffect(() => {
    return () => {
      if (shutdownRefreshTimeoutRef.current) {
        clearTimeout(shutdownRefreshTimeoutRef.current);
      }
    };
  }, []);

  const handleViewFile = async () => {
    if (!hasEnsembleFile) {
      return;
    }

    const baseMeta = {
      name: deployment?.ensemble_file_name ?? relativeCandidate ?? ensembleText,
      path: deployment?.ensemble_file_path ?? undefined,
      relative: relativeCandidate ?? ensembleText,
    };

    setFileMeta(baseMeta);
    setIsFileModalOpen(true);
    setFileLoading(true);
    setFileError(null);
    setFileContent(null);
    setFileCandidates([]);

    try {
      const res = await getDeploymentFile(deployment.id);
      const nextMeta = {
        name: res?.file_name ?? baseMeta.name,
        path: res?.file_path ?? baseMeta.path,
        relative: res?.file_relative_path ?? baseMeta.relative,
      };
      setFileMeta(nextMeta);
      setFileContent(res?.content ?? "");
      setFileCandidates(Array.isArray(res?.candidates) ? res.candidates : []);
      setFileError(null);
    } catch (error: any) {
      const detail = error?.response?.data ?? {};
      const message =
        detail?.message ||
        error?.message ||
        "Unable to load deployment file.";
      setFileError(message);
      setFileCandidates(Array.isArray(detail?.candidates) ? detail.candidates : []);
      const fallbackMeta = {
        name: detail?.file_name ?? baseMeta.name,
        path: baseMeta.path,
        relative: baseMeta.relative,
      };
      setFileMeta(fallbackMeta);
      setFileContent(null);
    } finally {
      setFileLoading(false);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-4 px-4 my-4 w-full">
      <Card
        className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border rounded-lg animate-[neonPulse_1.5s_infinite] text-wrap break-words w-full"
        data-testid="deployment-info-card"
      >
        <CardHeader className="w-full flex flex-row flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 flex-1 items-center gap-2 sm:flex-none">
            <CardTitle className="font-semibold tabular-nums max-w-[250px] sm:max-w-full break-words min-w-0">
              <LeftTruncatedText
                text={deployment.id}
                title={deployment.id}
                className="sm:overflow-visible sm:whitespace-normal sm:max-w-full"
              />
            </CardTitle>
            <CopyButton text={deployment.id} className={undefined} />
          </div>
          <div className="flex shrink-0 flex-row items-center gap-2">
            {details?.status?.deployment_status === "running" && (
              <Button
                onClick={async () => {
                  setIsShuttingDown(true);
                  try {
                    const didShutdown = await handleShutdown(deployment.id);
                    if (didShutdown) {
                      scheduleStatusRefresh();
                    }
                  } finally {
                    setIsShuttingDown(false);
                  }
                }}
                className="bg-red-500 hover:bg-red-600 text-white flex flex-row gap-2"
                disabled={isShuttingDown}
              >
                {isShuttingDown ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Shutting down...
                  </>
                ) : (
                  "Shut Down Deployment"
                )}
              </Button>
            )}
            <RefreshButton
              onClick={async () => {
                await refetch();
              }}
              isLoading={!!isFetching}
              tooltip="Refresh Deployment Info"
              children="Refresh Info..."
            />
          </div>
        </CardHeader>
        <CardFooter className="flex-col items-start gap-1.5 text-sm">
          <div className="text-muted-foreground space-y-0.5">
            <p data-testid="deployment-info-status">
              <b>Status:</b> {statusText}
            </p>
            {sanitizedTypeText ? (
              <p data-testid="deployment-info-type">
                <b>Type:</b> {sanitizedTypeText}
              </p>
            ) : null}
            <p data-testid="deployment-info-timestamp">
              <b>Timestamp:</b> {timestampText}
            </p>
            <p className="flex items-center gap-2 flex-wrap" data-testid="deployment-info-ensemble-file">
              <span className="flex items-center gap-2">
                <b>Ensemble File:</b>
                {hasEnsembleFile ? (
                  <span
                    className="font-mono text-sm break-all"
                    title={ensembleText}
                  >
                    {ensembleDisplayText}
                  </span>
                ) : (
                  "N/A"
                )}
              </span>
              {hasEnsembleFile ? (
                <>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="outline"
                        size="icon"
                        className="h-7 w-7"
                        onClick={handleViewFile}
                        data-testid="deployment-view-file-button"
                      >
                        <FileText className="h-3.5 w-3.5" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>View deployment file</TooltipContent>
                  </Tooltip>
                  <CopyButton text={ensembleText} className="h-7 w-7" />
                </>
              ) : null}
            </p>
          </div>
        </CardFooter>
      </Card>

      <Dialog open={isFileModalOpen} onOpenChange={handleFileModalChange}>
        <DialogContent className="sm:max-w-4xl" data-testid="deployment-file-modal">
          <DialogHeader>
            <DialogTitle>{fileMeta?.name ?? "Deployment File"}</DialogTitle>
            {shortFilePath ? (
              <p className="text-xs text-muted-foreground break-all" title={fullFilePath ?? undefined}>
                {shortFilePath}
              </p>
            ) : null}
          </DialogHeader>
          {fileLoading ? (
            <div className="flex items-center justify-center py-10 text-sm text-muted-foreground">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading file...
            </div>
          ) : fileError ? (
            <div className="space-y-3">
              <p className="text-sm text-red-500">{fileError}</p>
              {fileCandidates.length ? (
                <div className="text-xs text-muted-foreground space-y-1">
                  <p>Checked locations:</p>
                  <ul className="list-disc pl-4 space-y-1">
                    {fileCandidates.map((candidate) => (
                      <li key={candidate} className="break-all">
                        {candidate}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-end">
                <CopyButton text={fileContent ?? ""} className="text-xs" />
              </div>
              <YamlViewer
                value={fileContent ?? ""}
                className="max-h-[60vh]"
                maxHeight="60vh"
              />
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}


// ?? Deployment Progress
export function DeploymentProgressCard({ details }: { details: any }) {
  const deploymentStatus = details?.status?.deployment_status ?? "unknown";
  const deploymentStatusUpper = String(deploymentStatus).toUpperCase();

  // Render skeleton only on first load; background refetches keep previous data
  // so toggling usage/logs in the allocations card doesn't blank this card.
  if (!details) {
    return (
      <Card className="@container/card lg:col-span-1" data-testid="deployment-progress-card">
        <CardHeader>
          <Skeleton className="h-4 w-32 mb-2" /> {/* CardDescription */}
          <Skeleton className="h-8 w-48 mb-1" /> {/* CardTitle */}
          <Skeleton className="h-6 w-6 rounded-full" /> {/* CardAction icon */}
        </CardHeader>
        <CardFooter className="flex-col items-start gap-1.5 text-sm">
          <Skeleton className="h-4 w-24 mb-1" /> {/* Report label */}
          <Skeleton className="h-4 w-full max-w-xs" /> {/* Report message */}
        </CardFooter>
      </Card>
    );
  }

  // Render actual content
  return (
    <Card className="@container/card lg:col-span-1" data-testid="deployment-progress-card">
      <CardHeader>
        <CardDescription>Deployment Progress</CardDescription>
        <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl flex flex-row gap-2 items-center">
          <span
            className={
              deploymentStatus === "completed"
                ? "text-green-500"
                : deploymentStatus === "running"
                ? "text-blue-500"
                : "text-red-500"
            }
            data-testid="deployment-progress-status"
          >
            {deploymentStatusUpper}
          </span>
        </CardTitle>
        <CardAction>
          {deploymentStatus === "completed" ? (
            <CheckCircle className="text-green-500" />
          ) : deploymentStatus === "running" ? (
            <Repeat2Icon className="text-blue-500 animate-spin" />
          ) : (
            <XCircleIcon className="text-red-500" />
          )}
        </CardAction>
      </CardHeader>
      <CardFooter className="flex-col items-start gap-1.5 text-sm">
        <div className="line-clamp-1 flex gap-2 font-medium">Report:</div>
        <div className="text-muted-foreground">
          {details?.status?.message || "No report available."}
        </div>
      </CardFooter>
    </Card>
  );
}

// ?? Deployment Allocations
function DeploymentAllocationsCard({
  selectedAllocation,
  details,
  isFetching,
  isLoading,
  includeUsage,
  setIncludeUsage,
}: {
  selectedAllocation?: string | null;
  details: any;
  isFetching: boolean;
  isLoading: boolean;
  includeUsage: boolean;
  setIncludeUsage: (next: boolean) => void;
}) {
  const allocations = (details?.allocations ?? []) as string[];

  const manifestAllocations = (details?.manifest?.manifest?.allocations ??
    {}) as Record<string, any>;

  const allocationInfo = useMemo(() => {
    const base = (details?.allocations_info ?? {}) as Record<string, any>;
    return { ...base };
  }, [details?.allocations_info]);

  const formatBytes = (value: unknown) => {
    if (value === null || value === undefined) return "N/A";
    const n = typeof value === "number" ? value : Number(value);
    if (!Number.isFinite(n)) return "N/A";
    if (n === 0) return "0 B";
    if (n < 0) return "N/A";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let idx = 0;
    let v = n;
    while (v >= 1024 && idx < units.length - 1) {
      v /= 1024;
      idx += 1;
    }
    const precision = idx === 0 ? 0 : idx <= 2 ? 1 : 2;
    return `${v.toFixed(precision)} ${units[idx]}`;
  };

  const isUsageBusy = includeUsage && (isFetching || isLoading);

  return (
    <Card className="@container/card lg:col-span-2" data-testid="deployment-allocations-card">
      <CardHeader className="border-b">
        <CardDescription>Allocations</CardDescription>
        <CardAction>
          <div className="flex flex-wrap items-center justify-end gap-3">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="cursor-help">Usage</span>
                </TooltipTrigger>
                <TooltipContent className="max-w-[280px] text-xs">
                  Fetch resource usage stats from DMS. This can take a bit; 0 values usually mean DMS did not report
                  metrics for that allocation.
                </TooltipContent>
              </Tooltip>
              <Switch
                checked={includeUsage}
                onCheckedChange={setIncludeUsage}
                data-testid="deployment-allocations-toggle-usage"
              />
              {isUsageBusy ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : null}
            </div>
          </div>
        </CardAction>
      </CardHeader>
      <CardContent>

        {allocations.length > 0 ? (
          <div className="space-y-3">
            {allocations.map((name: string) => {
              const staticAlloc = manifestAllocations?.[name] ?? {};
              const runtime = allocationInfo?.[name] ?? {};
              const statusText =
                runtime?.status ??
                staticAlloc?.status ??
                "unknown";
              const dnsName = runtime?.dns_name ?? staticAlloc?.dns_name ?? "N/A";
              const ip = runtime?.ip ?? runtime?.private_address ?? staticAlloc?.priv_addr ?? "N/A";
              const usage = includeUsage ? runtime?.resource_usage ?? null : null;
              const allocationIdRaw = runtime?.allocation_id ?? staticAlloc?.id ?? null;
              const allocationId = typeof allocationIdRaw === "string" ? allocationIdRaw : allocationIdRaw ? String(allocationIdRaw) : "";
              const allocationIdDisplay = allocationId || "N/A";

              return (
                <div
                  key={name}
                  className={`rounded-lg border bg-background/50 p-3 space-y-2 ${
                    selectedAllocation && name === selectedAllocation ? "ring-1 ring-primary/30" : ""
                  }`}
                  data-testid={`deployment-allocation-${name}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-mono text-xs break-all">{name}</div>
                    <div className="text-xs text-muted-foreground">{String(statusText)}</div>
                  </div>

                  <div className="grid grid-cols-1 gap-1 text-xs text-muted-foreground sm:grid-cols-3">
                    <div className="min-w-0">
                      <span className="font-medium text-foreground/80">DNS:</span>{" "}
                      <span className="break-all">{String(dnsName)}</span>
                    </div>
                    <div className="min-w-0">
                      <span className="font-medium text-foreground/80">IP:</span>{" "}
                      <span className="break-all">{String(ip)}</span>
                    </div>
                    <div className="min-w-0 flex items-center gap-2">
                      <span className="font-medium text-foreground/80 shrink-0">Allocation ID:</span>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <div className="min-w-0 flex-1">
                            <LeftTruncatedText
                              text={allocationIdDisplay}
                              title={allocationIdDisplay}
                              className="w-full font-mono text-xs"
                            />
                          </div>
                        </TooltipTrigger>
                        <TooltipContent className="max-w-[min(80vw,720px)]">
                          <div className="font-mono text-xs break-all">{allocationIdDisplay}</div>
                        </TooltipContent>
                      </Tooltip>
                      {allocationId ? (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <div>
                              <CopyButton text={allocationId} className="h-6 w-6" />
                            </div>
                          </TooltipTrigger>
                          <TooltipContent className="text-xs">Copy allocation id</TooltipContent>
                        </Tooltip>
                      ) : null}
                    </div>
                  </div>

                  {usage ? (
                    <div className="grid grid-cols-1 gap-1 text-xs text-muted-foreground sm:grid-cols-3">
                      <div>
                        <span className="font-medium text-foreground/80">CPU:</span>{" "}
                        {Number.isFinite(Number(usage?.cpu_usage_percent))
                          ? `${Number(usage?.cpu_usage_percent).toFixed(1)}%`
                          : "N/A"}
                      </div>
                      <div>
                        <span className="font-medium text-foreground/80">Memory:</span>{" "}
                        {formatBytes(usage?.memory_used_bytes)} / {formatBytes(usage?.memory_limit_bytes)}
                      </div>
                      <div>
                        <span className="font-medium text-foreground/80">Network:</span>{" "}
                        RX {formatBytes(usage?.network_rx_bytes)} / TX {formatBytes(usage?.network_tx_bytes)}
                      </div>
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-muted-foreground text-center mt-2">
            No allocations found.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

// ?? Deployment Manifest
function DeploymentManifestCard({
  _setAlloc,
  manifest,
  isLoading,
}: {
  _setAlloc: (alloc: string | null) => void;
  manifest: any;
  isLoading: boolean;
}) {
  return (
    <ManifestPanel
      manifest={manifest}
      isLoading={isLoading}
      _setAlloc={_setAlloc}
    />
  );
}

// ?? Deployment Logs
function DeploymentLogsCard({
  deploymentId,
  alloc,
  details,
  isLoadingDetails,
}: {
  deploymentId: string;
  alloc: string | null;
  details: any;
  isLoadingDetails: boolean;
}) {
  const logQuery = useMemo(() => {
    const allocationsList = (details?.allocations ?? []) as string[];
    if (!details || allocationsList.length === 0) return null;

    const csv = allocationsList.join(",");
    let targetAlloc = alloc?.trim() || null;
    if (!targetAlloc && allocationsList.length === 1) {
      targetAlloc = allocationsList[0];
    }
    if (!targetAlloc) return null;

    const runtime = (details.allocations_info as Record<string, any>)?.[targetAlloc];
    const logs = runtime?.logs;
    const stdoutPath = typeof logs?.stdout_path === "string" ? logs.stdout_path.trim() : "";
    const stderrPath = typeof logs?.stderr_path === "string" ? logs.stderr_path.trim() : "";
    if (!stdoutPath || !stderrPath) return null;

    return {
      allocationsCsv: csv,
      stdoutPath,
      stderrPath,
      allocation: targetAlloc,
    };
  }, [details, alloc]);

  const logQueryKey = logQuery
    ? `${logQuery.allocation}|${logQuery.allocationsCsv}|${logQuery.stdoutPath}|${logQuery.stderrPath}`
    : "__pending__";

  const [isAsyncActionPending, setIsAsyncActionPending] = useState(false);
  const dmsLevels = [
    {
      value: "all",
      label: "All",
      query: null,
      hint: "All log levels for this deployment",
    },
    {
      value: "info",
      label: "Info",
      query: '(.level // "" | ascii_upcase) == "INFO"',
      hint: "Info-level entries",
    },
    {
      value: "debug",
      label: "Debug",
      query: '(.level // "" | ascii_upcase) == "DEBUG"',
      hint: "Debug-level entries",
    },
    {
      value: "warn",
      label: "Warn",
      query:
        '((.level // "" | ascii_upcase) == "WARN" or (.level // "" | ascii_upcase) == "WARNING")',
      hint: "Warning-level entries",
    },
    {
      value: "error",
      label: "Error",
      query:
        '((.level // "" | ascii_upcase) == "ERROR" or (.level // "" | ascii_upcase) == "ERR")',
      hint: "Error-level entries",
    },
  ];
  const dmsViewOptions = [
    {
      value: "folded",
      label: "Folded",
      hint: "Timestamp, level, msg only",
    },
    {
      value: "compact",
      label: "Compact",
      hint: "Timestamp, level, msg, key IDs",
    },
    {
      value: "expanded",
      label: "Expanded",
      hint: "Pretty JSON per entry",
    },
    {
      value: "map",
      label: "Map",
      hint: "Message only",
    },
    {
      value: "raw",
      label: "Raw",
      hint: "Single-line JSON per entry",
    },
  ];
  const dmsLineOptions = [
    { value: "400", label: "400" },
    { value: "1000", label: "1k" },
    { value: "2000", label: "2k" },
    { value: "5000", label: "5k" },
  ];
  const [dmsLevel, setDmsLevel] = useState(dmsLevels[0].value);
  const [dmsView, setDmsView] = useState<DmsLogView>("folded");
  const [dmsLines, setDmsLines] = useState("1000");
  const [isDmsTailEnabled, setIsDmsTailEnabled] = useState(false);
  const activeDmsLevel = dmsLevels.find((filter) => filter.value === dmsLevel) ?? dmsLevels[0];
  const dmsQuery = activeDmsLevel.query;
  const dmsLinesValue = Number(dmsLines) || 1000;
  const activeDmsView =
    dmsViewOptions.find((option) => option.value === dmsView) ?? dmsViewOptions[0];
  const isDmsTailActive = isDmsTailEnabled;

  const {
    data: asyncLogsStatus,
    refetch: refetchAsyncLogsStatus,
    isFetching: isFetchingAsyncStatus,
  } = useQuery({
    queryKey: ["deployment-logs-async-status", deploymentId, logQueryKey],
    queryFn: () =>
      getDeploymentLogsAsyncStatus(deploymentId, {
        allocation: logQuery!.allocation,
        allocations: logQuery!.allocationsCsv,
      }),
    enabled: Boolean(logQuery),
    refetchOnMount: "always",
    refetchOnWindowFocus: false,
    staleTime: Infinity,
    gcTime: Infinity,
  });

  const isAsyncRunning =
    (asyncLogsStatus?.fetch_status ?? "").trim().toLowerCase() === "running";

  const {
    data: baseLogsData,
    refetch: refetchBaseLogs,
    isFetching: isFetchingBaseLogs,
  } = useQuery<DeploymentLogsResponse>({
    queryKey: ["deployment-logs-base", deploymentId, logQueryKey],
    queryFn: () =>
      getDeploymentLogs(deploymentId, {
        allocation: logQuery!.allocation,
        allocations: logQuery!.allocationsCsv,
        stdoutPath: logQuery!.stdoutPath,
        stderrPath: logQuery!.stderrPath,
        refreshAlloc: false,
        dmsLines: 400,
        dmsView: "compact",
        includeAlloc: true,
      }),
    enabled: Boolean(logQuery),
    refetchOnMount: "always",
    refetchOnWindowFocus: false,
    refetchInterval: isAsyncRunning ? 30000 : false,
    refetchIntervalInBackground: true,
    staleTime: Infinity,
    gcTime: Infinity,
  });

  const {
    data: dmsLogsData,
    refetch: refetchDmsLogs,
    isFetching: isFetchingDmsLogs,
  } = useQuery<DeploymentLogsResponse>({
    queryKey: ["deployment-logs-dms", deploymentId, logQuery?.allocation ?? "_", dmsLevel, dmsLinesValue],
    queryFn: () =>
      getDeploymentLogs(deploymentId, {
        allocation: logQuery?.allocation ?? null,
        dmsQuery,
        refreshAlloc: false,
        dmsLines: dmsLinesValue,
        dmsView: "raw",
        includeAlloc: false,
      }),
    enabled: Boolean(deploymentId),
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    refetchInterval: isDmsTailActive ? 15000 : false,
    refetchIntervalInBackground: true,
    staleTime: Infinity,
    gcTime: Infinity,
    placeholderData: keepPreviousData,
  });

  // Re-read file logs immediately when the selected allocation changes (do not wait for 30s poll).
  useEffect(() => {
    if (!logQuery) return;
    void refetchAsyncLogsStatus();
    void refetchBaseLogs();
  }, [logQueryKey, logQuery, refetchAsyncLogsStatus, refetchBaseLogs]);

  useEffect(() => {
    if (isDmsTailActive) {
      void refetchDmsLogs();
    }
  }, [isDmsTailActive, dmsLevel, dmsLinesValue, refetchDmsLogs]);

  const handleStartAsyncLogs = async () => {
    if (!logQuery || isAsyncRunning || isAsyncActionPending) return;
    setIsAsyncActionPending(true);
    try {
      await startDeploymentLogsAsync(deploymentId, {
        allocation: logQuery.allocation,
        allocations: logQuery.allocationsCsv,
      });
      await Promise.all([
        refetchAsyncLogsStatus({ throwOnError: true }),
        refetchBaseLogs({ throwOnError: true }),
      ]);
    } catch (error: any) {
      toast.error("Failed to start log streaming", {
        description: error?.response?.data?.detail?.message || error?.message || "Unexpected error",
      });
    } finally {
      setIsAsyncActionPending(false);
    }
  };

  const handleStopAsyncLogs = async () => {
    if (!logQuery || !isAsyncRunning || isAsyncActionPending) return;
    setIsAsyncActionPending(true);
    try {
      await stopDeploymentLogsAsync(deploymentId, {
        allocation: logQuery.allocation,
        allocations: logQuery.allocationsCsv,
      });
      await refetchAsyncLogsStatus({ throwOnError: true });
    } catch (error: any) {
      toast.error("Failed to stop log streaming", {
        description: error?.response?.data?.detail?.message || error?.message || "Unexpected error",
      });
    } finally {
      setIsAsyncActionPending(false);
    }
  };

  const handleDownload = () => {
    const content = [
      "=== STDOUT ===",
      stdout || "No STDOUT logs available.",
      "",
      "=== STDERR ===",
      stderr || "No STDERR logs available.",
      "",
      "=== DMS LOGS ===",
      dms || dmsPlaceholderText,
      "",
    ].join("\n");
    const blob = new Blob([content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "deployment-logs.txt";
    link.click();
    URL.revokeObjectURL(url);
  };

  function parseLogs(logMessage: string) {
    if (!logMessage) return { stdout: "", stderr: "", dms: "" };

    const extractSection = (text: string, start: string, end: string): string => {
      const startSplit = text.split(start);
      if (startSplit.length < 2) return "";
      const section = end ? startSplit[1].split(end)[0] : startSplit[1];
      return section?.trim() || "";
    };

    const stripMetadata = (value: string, type: "std" | "dms"): string => {
      if (!value) return "";
      const metadataPrefixes =
        type === "dms"
          ? ["Source:", "Lines:", "Return Code:", "[returncode]", "[stderr]"]
          : [
              "Path:",
              "Tail Lines:",
              "Readable:",
              "Exists:",
              "Size:",
              "Updated:",
              "Error:",
              "(error:",
              "No log file found.",
            ];

      const filtered = value
        .split(/\r?\n/)
        .map((line) => line.trimEnd())
        .filter((line) => {
          if (!line) return false;
          return !metadataPrefixes.some((prefix) => line.startsWith(prefix));
        });

      return filtered.join("\n").trim();
    };

    const stdoutRaw = extractSection(logMessage, "=== STDOUT ===", "=== STDERR ===");
    const stderrRaw = extractSection(logMessage, "=== STDERR ===", "=== DMS LOG ENTRIES ===");
    const dmsRaw = extractSection(logMessage, "=== DMS LOG ENTRIES ===", "");

    return {
      stdout: stripMetadata(stdoutRaw, "std"),
      stderr: stripMetadata(stderrRaw, "std"),
      dms: stripMetadata(dmsRaw, "dms"),
    };
  }

  const parsedStdLogs = useMemo(() => {
    if (!baseLogsData) return { stdout: "", stderr: "" };
    if (baseLogsData.stdout !== undefined || baseLogsData.stderr !== undefined) {
      return {
        stdout: baseLogsData.stdout ?? "",
        stderr: baseLogsData.stderr ?? "",
      };
    }
    const parsed = parseLogs(baseLogsData.message || "");
    return {
      stdout: parsed.stdout,
      stderr: parsed.stderr,
    };
  }, [baseLogsData]);

  const parsedDmsLogs = useMemo(() => {
    if (!dmsLogsData) return { dms: "", hasFilteredDms: false };
    const source = dmsLogsData.dms_logs?.source ?? "";
    const hasFilteredDms = source !== "" && source !== "journalctl";
    if (dmsLogsData.dms !== undefined) {
      return {
        dms: hasFilteredDms ? dmsLogsData.dms ?? "" : "",
        hasFilteredDms,
      };
    }
    const parsed = parseLogs(dmsLogsData.message || "");
    return {
      dms: hasFilteredDms ? parsed.dms : "",
      hasFilteredDms,
    };
  }, [dmsLogsData]);

  const { stdout, stderr } = parsedStdLogs;
  const { dms, hasFilteredDms } = parsedDmsLogs;
  const dmsEntries = useMemo(() => parseDmsLogEntries(dms), [dms]);
  const dmsPlaceholderText = isFetchingDmsLogs
    ? "Loading DMS logs..."
    : hasFilteredDms
      ? "No DMS logs available yet."
      : "Filtered DMS logs unavailable.";

  const isAsyncControlsBusy = isAsyncActionPending || isFetchingAsyncStatus;
  const canStartAsyncLogs = Boolean(logQuery) && !isAsyncRunning && !isAsyncControlsBusy;
  const canStopAsyncLogs = Boolean(logQuery) && isAsyncRunning && !isAsyncControlsBusy;

  const renderDmsControls = () => (
    <div className="rounded-xl border border-border/50 bg-gradient-to-br from-muted/60 via-muted/30 to-background/80 px-4 py-3 shadow-sm backdrop-blur-sm">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
            <span className="h-1.5 w-1.5 rounded-full bg-primary/70" />
            <span>DMS Controls</span>
          </div>
          <div className="text-xs text-muted-foreground/85">{activeDmsLevel.hint}</div>
          <div className="text-[11px] text-muted-foreground/70">
            View: {activeDmsView.label} — {activeDmsView.hint}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <ToggleGroup
            type="single"
            value={dmsLevel}
            onValueChange={(value) => value && setDmsLevel(value)}
            variant="default"
            size="sm"
            className="flex flex-wrap gap-1 rounded-full border border-border/50 bg-background/80 p-1 shadow-xs"
            aria-label="DMS log level"
          >
            {dmsLevels.map((filter) => (
              <Tooltip key={filter.value}>
                <TooltipTrigger asChild>
                  <ToggleGroupItem
                    value={filter.value}
                    className="text-[11px] whitespace-nowrap !rounded-full !first:rounded-l-full !last:rounded-r-full data-[state=on]:bg-primary/15 data-[state=on]:text-primary px-3"
                  >
                    {filter.label}
                  </ToggleGroupItem>
                </TooltipTrigger>
                <TooltipContent>{filter.hint}</TooltipContent>
              </Tooltip>
            ))}
          </ToggleGroup>
          <div className="flex items-center gap-2 rounded-full border border-border/50 bg-background/80 px-2 py-1 shadow-xs">
            <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
              View
            </span>
            <Select value={dmsView} onValueChange={(value) => setDmsView(value as DmsLogView)}>
              <SelectTrigger className="h-7 w-[110px] border-transparent bg-transparent px-2 text-[11px] shadow-none hover:bg-muted/40">
                <SelectValue placeholder="View" />
              </SelectTrigger>
              <SelectContent>
                {dmsViewOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2 rounded-full border border-border/50 bg-background/80 px-2 py-1 shadow-xs">
            <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Lines
            </span>
            <Select value={dmsLines} onValueChange={setDmsLines}>
              <SelectTrigger className="h-7 w-[88px] border-transparent bg-transparent px-2 text-[11px] shadow-none hover:bg-muted/40">
                <SelectValue placeholder="Lines" />
              </SelectTrigger>
              <SelectContent>
                {dmsLineOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2 rounded-full border border-border/50 bg-background/80 px-3 py-1 shadow-xs">
            <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Tail
            </span>
            <Switch
              checked={isDmsTailEnabled}
              onCheckedChange={(checked) => setIsDmsTailEnabled(checked)}
              aria-label="Toggle DMS log tailing"
            />
          </div>
        </div>
      </div>
    </div>
  );

  const logSections = useMemo(
    () => [
      {
        key: "stdout",
        title: "STDOUT",
        textClass: "text-emerald-300",
        log: stdout,
        placeholder: isFetchingBaseLogs ? "Loading STDOUT logs..." : "No STDOUT logs available yet.",
      },
      {
        key: "stderr",
        title: "STDERR",
        textClass: "text-white",
        log: stderr,
        placeholder: isFetchingBaseLogs ? "Loading STDERR logs..." : "No STDERR logs available yet.",
      },
    ],
    [stdout, stderr, isFetchingBaseLogs]
  );

  return (
    <div className="grid grid-cols-1 gap-4 px-4 my-4">
      <Card
        className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border rounded-lg"
        data-testid="deployment-logs-card"
      >
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardDescription>
              Deployment Logs ({logQuery?.allocation ?? alloc ?? "auto"})
            </CardDescription>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleStartAsyncLogs}
                disabled={!canStartAsyncLogs}
                className="flex items-center gap-1"
                data-testid="deployment-logs-start"
              >
                {isAsyncActionPending && !isAsyncRunning ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Play className="h-4 w-4" />
                )}
                Start
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleStopAsyncLogs}
                disabled={!canStopAsyncLogs}
                className="flex items-center gap-1"
                data-testid="deployment-logs-stop"
              >
                {isAsyncActionPending && isAsyncRunning ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Square className="h-4 w-4" />
                )}
                Stop
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleDownload}
                className="flex items-center gap-1"
              >
                <Download className="h-4 w-4" /> Download
              </Button>
            </div>
          </div>
          <Separator className="my-2" />

          {!logQuery ? (
            <p className="text-sm text-muted-foreground mb-4">
              {isLoadingDetails && !details
                ? "Loading deployment details…"
                : ((details?.allocations ?? []) as string[]).length > 1
                  ? "Select an allocation in the manifest panel to load stdout/stderr file logs."
                  : "Log paths from deployment info are not available yet. Try refreshing the page."}
            </p>
          ) : null}

          {logQuery ? (
            logSections.map((section) => (
              <LogSection
                key={section.key}
                sectionKey={section.key}
                title={section.title}
                log={section.log}
                textClass={section.textClass}
                placeholder={section.placeholder}
                isLoading={isFetchingBaseLogs}
              />
            ))
          ) : (
            <>
              <LogSection
                sectionKey="stdout"
                title="STDOUT"
                textClass="text-emerald-300"
                log=""
                placeholder={
                  isLoadingDetails && !details
                    ? "Loading STDOUT logs..."
                    : "Select an allocation in the manifest to load file logs."
                }
                isLoading={Boolean(isLoadingDetails && !details)}
              />
              <LogSection
                sectionKey="stderr"
                title="STDERR"
                textClass="text-white"
                log=""
                placeholder={
                  isLoadingDetails && !details
                    ? "Loading STDERR logs..."
                    : "Select an allocation in the manifest to load file logs."
                }
                isLoading={Boolean(isLoadingDetails && !details)}
              />
            </>
          )}

          <div className="mt-4" data-testid="deployment-logs-dms">
            {renderDmsControls()}
            <DmsLogSection
              title="DMS Logs"
              entries={dmsEntries}
              view={dmsView}
              copyText={dms}
              placeholder={dmsPlaceholderText}
              isLoading={isFetchingDmsLogs}
              autoScroll={isDmsTailActive}
              modalControls={renderDmsControls()}
            />
          </div>
        </CardHeader>
      </Card>
    </div>
  );
}

// ?? Log section component
function LogSection({
  sectionKey,
  title,
  log,
  textClass,
  placeholder,
  isLoading = false,
}: {
  sectionKey: string;
  title: string;
  log: string;
  textClass: string;
  placeholder?: string;
  isLoading?: boolean;
}) {
  const [isModalOpen, setIsModalOpen] = useState(false);

  const rawLog = log ?? "";
  const friendlyPlaceholder = placeholder || "No logs available yet.";
  const hasContent = rawLog.trim().length > 0;
  const sanitizedLines = useMemo(
    () =>
      hasContent
        ? rawLog.replace(/\r\n/g, "\n").split("\n")
        : [friendlyPlaceholder],
    [rawLog, hasContent, friendlyPlaceholder]
  );

  return (
    <div data-testid={`deployment-logs-${sectionKey}`}>
      <div className="flex items-center justify-between mt-4">
        <div className="flex items-center gap-2">
          <p className="font-semibold">{title}</p>
          {isLoading ? (
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" />
              Loading
            </span>
          ) : null}
        </div>
        {hasContent ? (
          <div className="flex items-center gap-2">
            <CopyButton text={log} className="text-xs" />
          </div>
        ) : null}
      </div>
      {hasContent ? (
        <>
          <StdLogBody
            sizeClass="h-40"
            textClass={textClass}
            linesToRender={sanitizedLines}
            scrollKey={rawLog}
            onExpand={() => setIsModalOpen(true)}
          />
          <Dialog open={isModalOpen} onOpenChange={setIsModalOpen}>
            <DialogContent className="!max-w-[95vw] !w-[95vw] max-h-[90vh] sm:!max-w-[95vw]">
              <DialogHeader>
                <DialogTitle>{title} Logs</DialogTitle>
              </DialogHeader>
              <div className="flex justify-end mb-2">
                <CopyButton text={log} className="text-xs" />
              </div>
              <StdLogBody
                sizeClass="max-h-[70vh] min-h-[50vh]"
                textClass={textClass}
                linesToRender={sanitizedLines}
                scrollKey={rawLog}
                showExpandButton={false}
              />
            </DialogContent>
          </Dialog>
        </>
      ) : (
        <StdLogBody
          sizeClass="h-40"
          textClass={textClass}
          linesToRender={sanitizedLines}
          showExpandButton={false}
          scrollKey={rawLog}
          isPlaceholder
        />
      )}
    </div>
  );
}

type StdLogBodyProps = {
  sizeClass: string;
  textClass: string;
  linesToRender: string[];
  scrollKey: string;
  showExpandButton?: boolean;
  isPlaceholder?: boolean;
  onExpand?: () => void;
};

function StdLogBody({
  sizeClass,
  textClass,
  linesToRender,
  scrollKey,
  showExpandButton = true,
  isPlaceholder = false,
  onExpand,
}: StdLogBodyProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const node = scrollRef.current;
    if (node) {
      node.scrollTop = node.scrollHeight;
    }
  }, [scrollKey]);

  return (
    <div
      ref={scrollRef}
      className={`relative bg-black ${textClass} font-mono text-sm rounded-md p-3 shadow-inner ${sizeClass}`}
      style={{
        overflowX: "hidden",
        overflowY: "auto",
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
        overflowWrap: "anywhere",
        width: "100%",
        maxWidth: "100%",
      }}
    >
      {showExpandButton ? (
        <div className="sticky top-2 flex justify-end pr-2">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={onExpand}
            aria-label="Expand logs"
            className="size-8 rounded-full bg-black/40 hover:bg-black/60 focus-visible:ring-offset-0"
          >
            <Maximize2 className="h-4 w-4" />
          </Button>
        </div>
      ) : null}
      <div
        className={`${showExpandButton ? "pr-10" : ""} ${
          isPlaceholder ? "text-muted-foreground" : ""
        }`}
      >
        {linesToRender.map((line, idx) => (
          <div key={idx} className="whitespace-pre-wrap break-words">
            {line}
          </div>
        ))}
      </div>
    </div>
  );
}
