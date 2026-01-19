"use client";

import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useIsFetching, useQueryClient } from "@tanstack/react-query";
import {
  getDeployments,
  getDeploymentDetails,
  getDeploymentLogs,
  requestDeploymentLogs,
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
} from "lucide-react";
import {
  Card,
  CardHeader,
  CardDescription,
  CardTitle,
  CardFooter,
  CardAction,
} from "../components/ui/card";
import { Separator } from "../components/ui/separator";
import { Button } from "../components/ui/button";
import { toast } from "sonner";
import DeploymentDetailsSkeleton from "../components/deployments/DeploymentsSkeleton";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";

export default function DeploymentDetailsPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [isShuttingDown, setIsShuttingDown] = useState(false);

  const [_alloc, _setAlloc] = useState<string | null>(null);

  // ?? Shutdown handler
  const handleShutdown = async (deploymentId: string) => {
    try {
      setIsShuttingDown(true);
      const res = await shutdownDeployment(deploymentId);
      toast.success(res.status, { description: res.message });
      return true;
    } catch (error: any) {
      toast.error("Shutdown Failed", {
        description:
          error?.response?.data?.message || "An unexpected error occurred",
      });
      return false;
    } finally {
      setIsShuttingDown(false);
    }
  };

  // ?? Fetch deployments (for lookup)
  const { data: deploymentsData, isLoading: isLoadingDeployments } = useQuery({
    queryKey: ["deployments"],
    queryFn: getDeployments,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    staleTime: Infinity,
    gcTime: Infinity,
  });
  const deployment = deploymentsData?.deployments?.find((d) => d.id === id);


  if (!deployment && !isLoadingDeployments && id)
    return (
      <div className="flex flex-col items-center justify-center mt-20 text-center">
        <p className="text-lg font-medium mb-4">
          Deployment with ID <span className="font-mono">{id}</span> not found.
        </p>
        <Button
          variant="outline"
          onClick={() => navigate("/deploy")}
          className="flex items-center gap-2"
        >
          <ArrowLeft className="h-4 w-4" /> Back to Deployments
        </Button>
      </div>
    );

  return (
    <>
      {/* Deployment Info Card */}
      {deployment && (
        <DeploymentInfoCard
          deployment={deployment}
          handleShutdown={handleShutdown}
        />
      )}

      {/* Deployment Progress + Allocations */}
      <div className="grid grid-cols-1 gap-4 px-4 lg:grid-cols-3 xl:grid-cols-3 lg:px-6 my-4">
        <DeploymentProgressCard deploymentId={id!} />
        <DeploymentAllocationsCard deploymentId={id!} />
      </div>

      {/* Manifest */}
      <DeploymentManifestCard deploymentId={id!} _setAlloc={_setAlloc} />

      {/* Logs */}
      <DeploymentLogsCard deploymentId={id!} alloc={_alloc} />
    </>
  );
}


// ?? Deployment Info
function DeploymentInfoCard({ deployment, handleShutdown }: any) {
  const [isShuttingDown, setIsShuttingDown] = useState(false);
  const [isFileModalOpen, setIsFileModalOpen] = useState(false);
  const [fileLoading, setFileLoading] = useState(false);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [fileMeta, setFileMeta] = useState<{ name?: string; path?: string; relative?: string } | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [fileCandidates, setFileCandidates] = useState<string[]>([]);
  const shutdownRefreshTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const queryClient = useQueryClient();

  const {
    data: details,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ["deployment-details", deployment.id],
    queryFn: () => getDeploymentDetails(deployment.id),
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    staleTime: Infinity,
    gcTime: Infinity,
  });

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

    shutdownRefreshTimeoutRef.current = setTimeout(() => {
      void refetch().finally(() => {
        void queryClient.invalidateQueries({ queryKey: ["deployments"] });
      });
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
      <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border rounded-lg animate-[neonPulse_1.5s_infinite] text-wrap break-words w-full">
        <CardHeader className="w-full flex flex-col gap-2">
          <div className="flex items-center gap-2 flex-1 sm:flex-none min-w-0">
            <CardTitle className="font-semibold tabular-nums max-w-[250px] sm:max-w-full break-words min-w-0">
              <LeftTruncatedText
                text={deployment.id}
                title={deployment.id}
                className="sm:overflow-visible sm:whitespace-normal sm:max-w-full"
              />
            </CardTitle>
            <CopyButton text={deployment.id} className={undefined} />
          </div>
        </CardHeader>
        <CardFooter className="flex-col items-start gap-1.5 text-sm">
          <div className="text-muted-foreground space-y-0.5">
            <p>
              <b>Status:</b> {statusText}
            </p>
            {sanitizedTypeText ? (
              <p>
                <b>Type:</b> {sanitizedTypeText}
              </p>
            ) : null}
            <p>
              <b>Timestamp:</b> {timestampText}
            </p>
            <p className="flex items-center gap-2 flex-wrap">
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

          <div className="mt-3 flex flex-col sm:flex-row sm:gap-2">
            <RefreshButton
              onClick={() => void refetch()}
              isLoading={!!isFetching}
              tooltip="Refresh Deployment Info"
              children="Refresh Info..."
            />

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
                className="block bg-red-500 hover:bg-red-600 text-white mt-3 sm:mt-0 flex flex-row gap-2"
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
          </div>
        </CardFooter>
      </Card>

      <Dialog open={isFileModalOpen} onOpenChange={handleFileModalChange}>
        <DialogContent className="sm:max-w-4xl">
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
export function DeploymentProgressCard({
  deploymentId,
}: {
  deploymentId: string;
}) {
  const {
    data: details,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ["deployment-details", deploymentId],
    queryFn: () => getDeploymentDetails(deploymentId),
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    staleTime: Infinity,
    gcTime: Infinity,
  });

  // Render skeleton while loading
  if (!details || isFetching) {
    return (
      <Card className="@container/card lg:col-span-1">
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
    <Card className="@container/card lg:col-span-1">
      <CardHeader>
        <CardDescription>Deployment Progress</CardDescription>
        <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl flex flex-row gap-2 items-center">
          <span
            className={
              details.status.deployment_status === "completed"
                ? "text-green-500"
                : details.status.deployment_status === "running"
                ? "text-blue-500"
                : "text-red-500"
            }
          >
            {details.status.deployment_status.toUpperCase()}
          </span>
          <RefreshButton
            onClick={() => void refetch()}
            isLoading={!!isFetching}
            tooltip="Refresh Deployment Info"
          />
        </CardTitle>
        <CardAction>
          {details.status.deployment_status === "completed" ? (
            <CheckCircle className="text-green-500" />
          ) : details.status.deployment_status === "running" ? (
            <Repeat2Icon className="text-blue-500 animate-spin" />
          ) : (
            <XCircleIcon className="text-red-500" />
          )}
        </CardAction>
      </CardHeader>
      <CardFooter className="flex-col items-start gap-1.5 text-sm">
        <div className="line-clamp-1 flex gap-2 font-medium">Report:</div>
        <div className="text-muted-foreground">
          {details.status.message || "No report available."}
        </div>
      </CardFooter>
    </Card>
  );
}

// ?? Deployment Allocations
function DeploymentAllocationsCard({ deploymentId }: { deploymentId: string }) {
  const {
    data: details,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ["deployment-allocations", deploymentId],
    queryFn: () =>
      getDeploymentDetails(deploymentId).then((d) => d.allocations),
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    staleTime: Infinity,
    gcTime: Infinity,
  });

  return (
    <Card className="@container/card lg:col-span-2">
      <CardHeader>
        <CardDescription className="flex items-center gap-2 justify-between w-full">
          <span>Allocations</span>
          <RefreshButton
            onClick={() => void refetch()}
            isLoading={!!isFetching}
            tooltip="Refresh Allocations"
          />
        </CardDescription>
        <Separator className="my-2" />

        {details?.length > 0 ? (
          <ul className="mt-2">
            {details.map((allocation: any) => (
              <li key={allocation.id} className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">
                  {allocation}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-center mt-2">
            No allocations found.
          </p>
        )}
      </CardHeader>
    </Card>
  );
}

// ?? Deployment Manifest
function DeploymentManifestCard({ deploymentId, _setAlloc }: { deploymentId: string, _setAlloc: (alloc: string | null) => void }) {
  const {
    data: details,
    refetch,
    isFetching,
    isLoading,
  } = useQuery({
    queryKey: ["deployment-manifest", deploymentId],
    queryFn: () => getDeploymentDetails(deploymentId).then((d) => d.manifest),
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    staleTime: Infinity,
    gcTime: Infinity,
  });

  return (
    <ManifestPanel
      manifest={details}
      isLoading={isLoading}
      onRefresh={() => void refetch()}
      isRefreshing={isFetching}
      _setAlloc={_setAlloc}
    />
  );
}

// ?? Deployment Logs
function DeploymentLogsCard({ deploymentId, alloc }: { deploymentId: string, alloc: string | null }) {
  const allocKey = alloc ?? "__default__";
  const [isRequesting, setIsRequesting] = useState(false);
  const dmsFilters = [
    {
      value: "all",
      label: "All",
      query: null,
      hint: "All logs for this deployment",
    },
    {
      value: "errors",
      label: "Errors",
      query: '.error and .level == "ERROR"',
      hint: "Error-level lines with error details",
    },
    {
      value: "errors-all",
      label: "Errors (All)",
      query: ".error",
      hint: "Errors across all log levels",
    },
    {
      value: "bids",
      label: "Bids",
      query: '.msg | IN("deployment_bid", "bid_request")',
      hint: "Bid requests and bid responses",
    },
    {
      value: "dispatch",
      label: "Dispatch",
      query: '.msg == "dispatching_message"',
      hint: "Message dispatch activity",
    },
    {
      value: "sandbox",
      label: "Sandbox",
      query: '.msg == "dispatching_message" and (.msg_from != null or .from != null)',
      hint: "Dispatch lines with message sender info",
    },
  ];
  const dmsViewOptions = [
    {
      value: "compact",
      label: "Compact",
      hint: "Timestamp, level, msg, key IDs",
    },
    {
      value: "folded",
      label: "Folded",
      hint: "Timestamp, level, msg only",
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
  const [dmsFilter, setDmsFilter] = useState(dmsFilters[0].value);
  const [dmsView, setDmsView] = useState(dmsViewOptions[0].value);
  const [dmsLines, setDmsLines] = useState("2000");
  const activeDmsFilter =
    dmsFilters.find((filter) => filter.value === dmsFilter) ?? dmsFilters[0];
  const dmsQuery = activeDmsFilter.query;
  const dmsLinesValue = Number(dmsLines) || 2000;
  const activeDmsView =
    dmsViewOptions.find((option) => option.value === dmsView) ?? dmsViewOptions[0];

  const {
    data: baseLogsData,
    refetch: refetchBaseLogs,
    isFetching: isFetchingBaseLogs,
  } = useQuery({
    queryKey: ["deployment-logs-base", deploymentId, allocKey],
    queryFn: () =>
      getDeploymentLogs(deploymentId, alloc ?? null, null, false, 400, "compact", true),
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    staleTime: Infinity,
    gcTime: Infinity,
    keepPreviousData: true,
  });

  const {
    data: dmsLogsData,
    refetch: refetchDmsLogs,
    isFetching: isFetchingDmsLogs,
  } = useQuery({
    queryKey: ["deployment-logs-dms", deploymentId, allocKey, dmsFilter, dmsLinesValue, dmsView],
    queryFn: () =>
      getDeploymentLogs(
        deploymentId,
        alloc ?? null,
        dmsQuery,
        false,
        dmsLinesValue,
        dmsView,
        false
      ),
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    staleTime: Infinity,
    gcTime: Infinity,
    keepPreviousData: true,
  });

  const handleRefresh = async () => {
    setIsRequesting(true);
    try {
      await requestDeploymentLogs(deploymentId, alloc ?? null, false);
      await Promise.all([
        refetchBaseLogs({ throwOnError: true }),
        refetchDmsLogs({ throwOnError: true }),
      ]);
    } catch (error) {
      throw error;
    } finally {
      setIsRequesting(false);
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
  const dmsPlaceholderText = isFetchingDmsLogs
    ? "Loading DMS logs..."
    : hasFilteredDms
      ? "No DMS logs available yet."
      : "Filtered DMS logs unavailable. Refresh to retry.";

  const logSections = useMemo(
    () => [
      {
        key: "stdout",
        title: "STDOUT",
        color: "green",
        log: stdout,
        placeholder: isFetchingBaseLogs ? "Loading STDOUT logs..." : "No STDOUT logs available yet.",
      },
      {
        key: "stderr",
        title: "STDERR",
        color: "red",
        log: stderr,
        placeholder: isFetchingBaseLogs ? "Loading STDERR logs..." : "No STDERR logs available yet.",
      },
    ],
    [stdout, stderr, isFetchingBaseLogs]
  );

  return (
    <div className="grid grid-cols-1 gap-4 px-4 my-4">
      <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border rounded-lg">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardDescription>Deployment Logs ({alloc ?? "auto"})</CardDescription>
            <div className="flex gap-2">
              <RefreshButton
                onClick={handleRefresh}
                isLoading={isFetchingBaseLogs || isFetchingDmsLogs || isRequesting}
                tooltip="Refresh Logs"
              />
              <Button
                variant="outline"
                size="sm"
                onClick={handleDownload}
                className="flex items-center gap-1"
              >
                <Download className="w-4 h-4" /> Download
              </Button>
            </div>
          </div>
          <Separator className="my-2" />

          {logSections.map((section) => (
            <LogSection
              key={section.key}
              title={section.title}
              log={section.log}
              color={section.color}
              placeholder={section.placeholder}
              isLoading={isFetchingBaseLogs}
            />
          ))}

          <div className="mt-4">
            <div className="rounded-xl border border-border/50 bg-gradient-to-br from-muted/60 via-muted/30 to-background/80 px-4 py-3 shadow-sm backdrop-blur-sm">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div className="space-y-1">
                  <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
                    <span className="h-1.5 w-1.5 rounded-full bg-primary/70" />
                    <span>DMS Controls</span>
                  </div>
                  <div className="text-xs text-muted-foreground/85">{activeDmsFilter.hint}</div>
                  <div className="text-[11px] text-muted-foreground/70">
                    View: {activeDmsView.label} — {activeDmsView.hint}
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <ToggleGroup
                    type="single"
                    value={dmsFilter}
                    onValueChange={(value) => value && setDmsFilter(value)}
                    variant="default"
                    size="sm"
                    className="flex flex-wrap gap-1 rounded-full border border-border/50 bg-background/80 p-1 shadow-xs"
                    aria-label="DMS log filter"
                  >
                    {dmsFilters.map((filter) => (
                      <Tooltip key={filter.value}>
                        <TooltipTrigger asChild>
                          <ToggleGroupItem
                            value={filter.value}
                            className={`text-[11px] whitespace-nowrap !rounded-full !first:rounded-l-full !last:rounded-r-full data-[state=on]:bg-primary/15 data-[state=on]:text-primary ${
                              filter.value === "errors-all" ? "px-4 min-w-[110px]" : "px-3"
                            }`}
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
                    <Select value={dmsView} onValueChange={setDmsView}>
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
                </div>
              </div>
            </div>
            <LogSection
              title="DMS Logs"
              log={dms}
              color="blue"
              placeholder={dmsPlaceholderText}
              isLoading={isFetchingDmsLogs}
            />
          </div>
        </CardHeader>
      </Card>
    </div>
  );
}

// ?? Log section component
function LogSection({
  title,
  log,
  color,
  placeholder,
  isLoading = false,
}: {
  title: string;
  log: string;
  color: string;
  placeholder?: string;
  isLoading?: boolean;
}) {
  const [isModalOpen, setIsModalOpen] = useState(false);

  const rawLog = log ?? "";
  const normalizedLog = rawLog.trim();
  const hasContent = normalizedLog.length > 0;
  const friendlyPlaceholder = placeholder || "No logs available yet.";
  const sanitizedLines = hasContent
    ? rawLog.replace(/\r\n/g, "\n").split("\n")
    : [friendlyPlaceholder];

  const LogBody = ({
    sizeClass,
    showExpandButton = true,
    linesToRender: bodyLines,
    isPlaceholder = false,
  }: {
    sizeClass: string;
    showExpandButton?: boolean;
    linesToRender: string[];
    isPlaceholder?: boolean;
  }) => {
    const scrollRef = useRef<HTMLDivElement | null>(null);

    useEffect(() => {
      const node = scrollRef.current;
      if (node) {
        node.scrollTop = node.scrollHeight;
      }
    }, [log]);

    return (
      <div
        ref={scrollRef}
        className={`relative bg-black text-${color}-400 font-mono text-sm rounded-md p-3 shadow-inner ${sizeClass}`}
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
              onClick={() => setIsModalOpen(true)}
              aria-label={`Expand ${title} logs`}
              className="size-8 rounded-full bg-black/40 hover:bg-black/60 focus-visible:ring-offset-0"
            >
              <Maximize2 className="h-4 w-4" />
            </Button>
          </div>
        ) : null}
        <div className={`${showExpandButton ? "pr-10" : ""} ${isPlaceholder ? "text-muted-foreground" : ""}`}>
          {bodyLines.map((line, idx) => (
            <div key={idx} className="whitespace-pre-wrap break-words">
              {line}
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <>
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
          <LogBody sizeClass="h-40" linesToRender={sanitizedLines} />
          <Dialog open={isModalOpen} onOpenChange={setIsModalOpen}>
            <DialogContent className="!max-w-[95vw] !w-[95vw] max-h-[90vh] sm:!max-w-[95vw]">
              <DialogHeader>
                <DialogTitle>{title} Logs</DialogTitle>
              </DialogHeader>
              <div className="flex justify-end mb-2">
                <CopyButton text={log} className="text-xs" />
              </div>
              <LogBody
                sizeClass="max-h-[70vh] min-h-[50vh]"
                showExpandButton={false}
                linesToRender={sanitizedLines}
              />
            </DialogContent>
          </Dialog>
        </>
      ) : (
        <LogBody
          sizeClass="h-40"
          showExpandButton={false}
          linesToRender={sanitizedLines}
          isPlaceholder
        />
      )}
    </>
  );
}
