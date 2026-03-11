import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Card, CardTitle } from "../components/ui/card";
import {
  ArrowUp,
  RefreshCw,
  Square,
  Power,
  PowerOff,
  Wrench,
  LucideIcon,
  Loader2,
} from "lucide-react";
import {
  restartDms,
  stopDms,
  enableDms,
  disableDms,
  initDms,
  updateDms,
  getFilteredDmsLogs,
  onboardCompute,
  offboardCompute,
  allInfo,
  allSysInfo,
} from "../api/api";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { Separator } from "../components/ui/separator";
import { ToggleGroup, ToggleGroupItem } from "../components/ui/toggle-group";
import { Switch } from "../components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "../components/ui/tooltip";
import { RefreshButton } from "../components/ui/RefreshButton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "../components/ui/dialog";
import { DmsLogSection } from "../components/logging/DmsLogSection";
import { DmsLogView, parseDmsLogEntries } from "../lib/dmsLogs";

type Action = {
  label: string;
  icon: LucideIcon;
  color: string;
  api: () => Promise<{ status: string; message?: string }>;
};

const actions: Action[] = [
  {
    label: "Restart",
    icon: RefreshCw,
    color: "bg-blue-500 hover:bg-blue-600",
    api: restartDms,
  },
  {
    label: "Stop",
    icon: Square,
    color: "bg-red-500 hover:bg-red-600",
    api: stopDms,
  },
  {
    label: "Enable",
    icon: Power,
    color: "bg-green-500 hover:bg-green-600",
    api: enableDms,
  },
  {
    label: "Disable",
    icon: PowerOff,
    color: "bg-gray-500 hover:bg-gray-600",
    api: disableDms,
  },
  {
    label: "Init",
    icon: Wrench,
    color: "bg-purple-500 hover:bg-purple-600",
    api: initDms,
  },
];

export default function Page() {
  const [logs, setLogs] = useState<string[]>([]);
  const [confirmOffboardOpen, setConfirmOffboardOpen] = useState(false);

  const {
    data: info,
    refetch: refetchInfo,
    isRefetching: isRefetchingInfo,
  } = useQuery({
    queryKey: ["apiData"],
    queryFn: allInfo,
    refetchOnMount: true,
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
  });

  const {
    data: sysinfo,
    refetch: refetchSys,
    isRefetching: isRefetchingSys,
  } = useQuery({
    queryKey: ["sysInfo"],
    queryFn: allSysInfo,
    staleTime: Infinity,
    gcTime: Infinity,
    refetchInterval: 1000 * 120,
    refetchOnWindowFocus: false,
  });

  const cleanedOnboardingStatus = useMemo(() => {
    const raw = info?.onboarding_status ?? "";
    return raw.replace(/\x1b\[[0-9;]*m/g, "");
  }, [info?.onboarding_status]);

  const normalizedOnboardingStatus = cleanedOnboardingStatus.trim().toUpperCase();
  const isExplicitlyNotOnboarded = normalizedOnboardingStatus.includes("NOT ONBOARD");
  const isOnboarded =
    normalizedOnboardingStatus.includes("ONBOARDED") && !isExplicitlyNotOnboarded;
  const displayOnboardingStatus =
    cleanedOnboardingStatus || info?.onboarding_status || "Unknown";

  const extractErrorMessage = (error: any, fallback: string) =>
    error?.response?.data?.message ??
    error?.response?.data?.detail ??
    error?.message ??
    fallback;

  const {
    mutateAsync: triggerOnboard,
    isPending: isOnboarding,
  } = useMutation({
    mutationFn: onboardCompute,
    onSuccess: async (res) => {
      toast.success(res?.message || "Compute onboarding started");
      appendLog(`[Onboard] ${res?.message ?? "Onboarding started"}`);
      await Promise.allSettled([refetchInfo(), refetchSys()]);
    },
    onError: (error) => {
      toast.error(extractErrorMessage(error, "Failed to start onboarding"));
    },
  });

  const {
    mutateAsync: triggerOffboard,
    isPending: isOffboarding,
  } = useMutation({
    mutationFn: offboardCompute,
    onSuccess: async (res) => {
      toast.success(res?.message || "Compute offboarding started");
      appendLog(`[Offboard] ${res?.message ?? "Offboarding started"}`);
      setConfirmOffboardOpen(false);
      await Promise.allSettled([refetchInfo(), refetchSys()]);
    },
    onError: (error) => {
      toast.error(extractErrorMessage(error, "Failed to start offboarding"));
    },
  });

  const handleOnboardClick = async () => {
    try {
      await triggerOnboard();
    } catch {
      // handled via onError
    }
  };

  const handleOffboardConfirm = async () => {
    try {
      await triggerOffboard();
    } catch {
      // handled via onError
    }
  };

  const [isPollingDmsVersion, setIsPollingDmsVersion] = useState(false);
  const [targetDmsVersion, setTargetDmsVersion] = useState<string | null>(null);
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const {
    mutateAsync: doTriggerDmsUpdate,
    isPending: isUpdatingDms,
  } = useMutation({
    mutationFn: updateDms,
    onSuccess: (res) => {
      const targetVersion = sysinfo?.dmsUpdateInfo?.latest;
      appendLog(`[Update] ${res?.message ?? "DMS update started"}`);
      if (targetVersion) {
        setTargetDmsVersion(targetVersion);
        setIsPollingDmsVersion(true);
        toast.success(res?.message || "DMS update started successfully");

        pollingIntervalRef.current = setInterval(() => {
          refetchInfo();
          refetchSys();
        }, 10000);

        pollingTimeoutRef.current = setTimeout(() => {
          if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current);
            pollingIntervalRef.current = null;
          }
          setIsPollingDmsVersion(false);
          setTargetDmsVersion(null);
        }, 60000);
      } else {
        toast.success(res?.message || "DMS update started successfully");
        setTimeout(() => {
          refetchInfo();
          refetchSys();
        }, 5000);
      }
    },
    onError: (error) => {
      toast.error(extractErrorMessage(error, "Failed to start DMS update"));
    },
  });

  useEffect(() => {
    if (isPollingDmsVersion && targetDmsVersion && info?.dms_version) {
      if (info.dms_version === targetDmsVersion) {
        if (pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current);
          pollingIntervalRef.current = null;
        }
        if (pollingTimeoutRef.current) {
          clearTimeout(pollingTimeoutRef.current);
          pollingTimeoutRef.current = null;
        }
        setIsPollingDmsVersion(false);
        setTargetDmsVersion(null);
        toast.success(`DMS updated to version ${targetDmsVersion}`);
        refetchInfo();
        refetchSys();
      }
    }
  }, [info?.dms_version, targetDmsVersion, isPollingDmsVersion, refetchInfo, refetchSys]);

  useEffect(() => {
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
      if (pollingTimeoutRef.current) {
        clearTimeout(pollingTimeoutRef.current);
      }
    };
  }, []);

  const handleTriggerDmsUpdate = async () => {
    try {
      await doTriggerDmsUpdate();
    } catch {
      // handled via onError
    }
  };
  const dmsLevels = [
    {
      value: "all",
      label: "All",
      query: null,
      hint: "All log levels",
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
    data: dmsLogsData,
    refetch: refetchDmsLogs,
    isFetching: isFetchingDmsLogs,
  } = useQuery({
    queryKey: ["dms-logs", dmsLevel, dmsLinesValue],
    queryFn: () => getFilteredDmsLogs(dmsQuery, dmsLinesValue, "raw"),
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    refetchInterval: isDmsTailActive ? 15000 : false,
    refetchIntervalInBackground: true,
    staleTime: Infinity,
    gcTime: Infinity,
    keepPreviousData: true,
  });

  const dmsContent = dmsLogsData?.dms ?? "";
  const dmsEntries = useMemo(() => parseDmsLogEntries(dmsContent), [dmsContent]);
  const dmsSource = dmsLogsData?.dms_logs?.source ?? "";
  const hasFilteredDms = dmsSource !== "" && dmsSource !== "journalctl";
  const dmsPlaceholderText = isFetchingDmsLogs
    ? "Loading DMS logs..."
    : hasFilteredDms
      ? "No DMS logs available yet."
      : "Filtered DMS logs unavailable. Refresh to retry.";

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

  useEffect(() => {
    if (isDmsTailActive) {
      void refetchDmsLogs();
    }
  }, [isDmsTailActive, dmsLevel, dmsLinesValue, refetchDmsLogs]);

  const appendLog = (entry: string) => {
    setLogs((prev) => {
      const next = [entry, ...prev];
      return next.slice(0, 100);
    });
  };

  const runAction = async (action: Action) => {
    try {
      const res = await action.api();
      const status = res?.status ?? "success";
      const description = res?.message ?? "Command completed.";
      toast(status, { description });
      appendLog(`[${action.label}] ${description}`);
    } catch (err) {
      console.error(`Failed to run ${action.label}:`, err);
      const description =
        err instanceof Error
          ? err.message
          : typeof err === "object" && err !== null && "message" in err
          ? String((err as any).message)
          : "Unexpected error";
      toast("error", { description });
      appendLog(`[${action.label}] ERROR: ${description}`);
    }
  };

  return (
    <div className="flex flex-1 flex-col">
      <div className="container/main flex flex-1 flex-col gap-2">
        <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
          <div className="grid grid-cols-1 gap-4 px-4 lg:grid-cols-1 lg:px-6">
            <Card>
              <div className="flex flex-col gap-4 p-6">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <CardTitle className="text-lg font-semibold">DMS Status</CardTitle>
                    <div className="mt-1 text-xs text-muted-foreground">
                      Onboarding: {displayOnboardingStatus}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      Version: <code>{info?.dms_version ?? "--"}</code>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {isOnboarded ? (
                      <Dialog
                        open={confirmOffboardOpen}
                        onOpenChange={(open) => {
                          if (isOffboarding) return;
                          setConfirmOffboardOpen(open);
                        }}
                      >
                        <DialogTrigger asChild>
                          <Button
                            variant="destructive"
                            className="bg-red-600 hover:bg-red-700 text-white"
                            disabled={isOffboarding || isOnboarding}
                          >
                            {isOffboarding ? (
                              <>
                                <Loader2 className="size-4 animate-spin" />
                                Offboarding...
                              </>
                            ) : (
                              "Offboard"
                            )}
                          </Button>
                        </DialogTrigger>
                        <DialogContent showCloseButton={!isOffboarding}>
                          <DialogHeader>
                            <DialogTitle>Confirm offboarding</DialogTitle>
                            <DialogDescription>
                              This will release all onboarded resources for this node.
                              Active workloads may be interrupted. Continue?
                            </DialogDescription>
                          </DialogHeader>
                          <DialogFooter>
                            <Button
                              variant="outline"
                              onClick={() => setConfirmOffboardOpen(false)}
                              disabled={isOffboarding}
                            >
                              Cancel
                            </Button>
                            <Button
                              variant="destructive"
                              className="bg-red-600 hover:bg-red-700 text-white"
                              onClick={handleOffboardConfirm}
                              disabled={isOffboarding}
                            >
                              {isOffboarding ? (
                                <>
                                  <Loader2 className="size-4 animate-spin" />
                                  Offboarding...
                                </>
                              ) : (
                                "Yes, offboard"
                              )}
                            </Button>
                          </DialogFooter>
                        </DialogContent>
                      </Dialog>
                    ) : (
                      <Button
                        className="bg-emerald-600 hover:bg-emerald-700 text-white"
                        disabled={isOnboarding || isOffboarding}
                        onClick={handleOnboardClick}
                      >
                        {isOnboarding ? (
                          <>
                            <Loader2 className="size-4 animate-spin" />
                            Onboarding...
                          </>
                        ) : (
                          "Onboard"
                        )}
                      </Button>
                    )}
                    <TooltipProvider>
                      {sysinfo?.dmsUpdateInfo?.available ? (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              size="sm"
                              className="h-auto w-auto p-1 bg-emerald-600 hover:bg-emerald-700 text-white"
                              onClick={handleTriggerDmsUpdate}
                              disabled={isUpdatingDms}
                            >
                              {isUpdatingDms ? (
                                <Loader2 className="size-4 animate-spin" />
                              ) : (
                                <ArrowUp className="size-4" />
                              )}
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>
                            <p>Update to {sysinfo.dmsUpdateInfo.latest}</p>
                          </TooltipContent>
                        </Tooltip>
                      ) : (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              size="sm"
                              variant="outline"
                              className="h-auto w-auto p-1"
                              onClick={() => refetchSys()}
                              disabled={isRefetchingSys}
                            >
                              {isRefetchingSys ? (
                                <Loader2 className="size-4 animate-spin" />
                              ) : (
                                <RefreshCw className="size-4" />
                              )}
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Check for DMS updates</TooltipContent>
                        </Tooltip>
                      )}
                    </TooltipProvider>
                    <RefreshButton
                      onClick={() => refetchInfo()}
                      isLoading={isRefetchingInfo}
                      tooltip="Refresh DMS status"
                    />
                  </div>
                </div>
                <Separator />
                <div className="flex flex-wrap justify-center w-full gap-4">
                  {actions.map((action) => {
                    const Icon = action.icon;
                    return (
                      <Button
                        key={action.label}
                        onClick={() => runAction(action)}
                        className={`${action.color} text-white px-5 py-6 rounded-xl flex flex-row items-center justify-center shadow-md hover:scale-105 transition-transform`}
                      >
                        <Icon className="w-6 h-6 mr-2" />
                        <span className="text-sm font-medium">{action.label}</span>
                      </Button>
                    );
                  })}
                </div>
              </div>
            </Card>

            <Card className="p-4 rounded-xl shadow-md border border-gray-200">
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg font-semibold">DMS Logs</CardTitle>
                <RefreshButton
                  onClick={() => void refetchDmsLogs()}
                  isLoading={isFetchingDmsLogs}
                  tooltip="Refresh DMS Logs"
                />
              </div>
              <Separator className="my-3" />
              {renderDmsControls()}
              <DmsLogSection
                title="Service Logs"
                entries={dmsEntries}
                view={dmsView}
                copyText={dmsContent}
                placeholder={dmsPlaceholderText}
                isLoading={isFetchingDmsLogs}
                autoScroll={isDmsTailActive}
                modalControls={renderDmsControls()}
              />
            </Card>

            {logs.length > 0 && (
              <Card className="p-4 rounded-xl shadow-md border border-gray-200">
                <CardTitle className="text-lg font-semibold mb-3">
                  Recent Activity
                </CardTitle>
                <div className="space-y-2 max-h-64 overflow-y-auto p-3 rounded-lg text-sm font-mono bg-slate-50">
                  {logs.map((msg, index) => (
                    <div key={index} className="p-1 break-words">
                      {msg}
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
