"use client";

import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "../ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "../ui/dialog";
import {
  allInfo,
  allSysInfo,
  getDockerContainer,
  offboardCompute,
  onboardCompute,
  triggerUpdate,
  updateDms,
} from "../../api/api";
import {
  CircleMinusIcon,
  CirclePlusIcon,
  ChevronDownIcon,
  DownloadCloudIcon,
  Loader2,
  LoaderPinwheelIcon,
  XIcon,
  type LucideIcon,
} from "lucide-react";
import { Separator } from "../ui/separator";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { SectionCardsSkeleton } from "./DashboardSkeleton";
import { CopyButton } from "../ui/CopyButton";
import { cn } from "../../lib/utils";
import { RefreshButton } from "../ui/RefreshButton";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "../ui/collapsible";

type ResourcePair = { label: string; value: string };

const parseResourcePairs = (input?: string): ResourcePair[] => {
  if (!input) return [];
  return input
    .split(",")
    .map((segment) => segment.trim())
    .filter(Boolean)
    .map((segment) => {
      const [rawLabel, ...rest] = segment.split(":");
      const label = (rawLabel ?? "").trim();
      const value = rest.join(":").trim();
      return {
        label,
        value: value || "N/A",
      };
    })
    .filter((pair) => pair.label.length > 0);
};

const normalizeVersion = (value?: string | null) =>
  (value ?? "").trim().replace(/^v/i, "").toLowerCase();

const parseVersionParts = (value?: string | null) => {
  if (!value) return null;
  const match = value.trim().match(/(\d+)(?:\.(\d+))?(?:\.(\d+))?/);
  if (!match) return null;
  return [
    Number(match[1] ?? 0),
    Number(match[2] ?? 0),
    Number(match[3] ?? 0),
  ];
};

const compareVersionParts = (current: number[], latest: number[]) => {
  for (let i = 0; i < 3; i += 1) {
    if (current[i] !== latest[i]) {
      return current[i] - latest[i];
    }
  }
  return 0;
};

const parseUpdateAvailable = (value: unknown) => {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (normalized === "true") return true;
    if (normalized === "false") return false;
  }
  if (typeof value === "number") return value > 0;
  return false;
};

const compareVersions = (current?: string | null, latest?: string | null) => {
  const currentParts = parseVersionParts(current);
  const latestParts = parseVersionParts(latest);
  if (currentParts && latestParts) {
    const numericComparison = compareVersionParts(currentParts, latestParts);
    if (numericComparison !== 0) {
      return numericComparison;
    }
    // Same numeric core (e.g. 1.2.3), but different suffix/build metadata:
    // treat as indeterminate so backend "available" flag can decide.
    if (current && latest && normalizeVersion(current) !== normalizeVersion(latest)) {
      return null;
    }
    return 0;
  }
  if (current && latest) {
    return normalizeVersion(current) === normalizeVersion(latest) ? 0 : null;
  }
  return null;
};

const normalizeResourceLabel = (label: string) => label.trim().toLowerCase();

const getResourceValue = (pairs: ResourcePair[], acceptedLabels: string[]) => {
  const accepted = acceptedLabels.map(normalizeResourceLabel);
  const match = pairs.find((pair) => accepted.includes(normalizeResourceLabel(pair.label)));
  if (!match) return null;
  const value = (match.value ?? "").trim();
  if (!value || value.toUpperCase() === "N/A") return null;
  return value;
};

const getGpuCountValue = (pairs: ResourcePair[]) => {
  const explicit = getResourceValue(pairs, ["gpu count", "gpus", "gpu"]);
  if (explicit) return explicit;
  const enumeratedGpus = pairs.filter((pair) => /^gpu\s+\d+/i.test(pair.label)).length;
  return enumeratedGpus > 0 ? `${enumeratedGpus}` : null;
};

const buildResourceSummaryBadges = (pairs: ResourcePair[]) => {
  const entries: Array<{ label: string; value: string | null }> = [
    { label: "CPU", value: getResourceValue(pairs, ["cores", "cpu cores"]) },
    { label: "RAM", value: getResourceValue(pairs, ["ram", "memory", "ram size"]) },
    { label: "Disk", value: getResourceValue(pairs, ["disk", "disk size", "storage"]) },
    { label: "GPU", value: getGpuCountValue(pairs) },
  ];
  return entries.filter((entry): entry is { label: string; value: string } => Boolean(entry.value));
};

type ResourceOverviewCardProps = {
  resourceKey: "free" | "allocated" | "onboarded";
  title: string;
  description: string;
  pairs: ResourcePair[];
  Icon: LucideIcon;
  colorClass: string;
  accentClass: string;
  cardClassName: string;
  defaultOpen?: boolean;
};

function ResourceOverviewCard({
  resourceKey,
  title,
  description,
  pairs,
  Icon,
  colorClass,
  accentClass,
  cardClassName,
  defaultOpen = false,
}: ResourceOverviewCardProps) {
  const [open, setOpen] = useState(defaultOpen);
  const summaryBadges = useMemo(() => buildResourceSummaryBadges(pairs), [pairs]);
  const hasPairs = pairs.length > 0;

  return (
    <Card className={cardClassName} data-testid={`${resourceKey}-resources-card`}>
      <CardHeader className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <div className={cn("rounded-md border p-2", accentClass)}>
              <Icon className="size-4" />
            </div>
            <div>
              <CardTitle className="text-base font-semibold">{title} Resources</CardTitle>
              <CardDescription className="text-xs">{description}</CardDescription>
            </div>
          </div>
          <Badge variant="outline" className="text-xs">
            {pairs.length} {pairs.length === 1 ? "metric" : "metrics"}
          </Badge>
        </div>

        <div className="flex flex-wrap gap-2">
          {summaryBadges.length > 0 ? (
            summaryBadges.map((entry) => (
              <Badge
                key={`${resourceKey}-summary-${entry.label}`}
                variant="outline"
                className={cn("text-xs", accentClass)}
              >
                <span className="font-semibold">{entry.label}:</span>&nbsp;
                {entry.value}
              </Badge>
            ))
          ) : (
            <CardDescription className="text-xs text-muted-foreground">
              No structured summary metrics available.
            </CardDescription>
          )}
        </div>
      </CardHeader>

      <CardContent className="pt-0">
        <Collapsible open={open} onOpenChange={setOpen}>
          <CollapsibleTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="w-full justify-between border border-blue-500/20 bg-muted/20 px-3"
              data-testid={`${resourceKey}-resources-toggle`}
              disabled={!hasPairs}
            >
              <span>{open ? "Hide details" : "Show details"}</span>
              <ChevronDownIcon
                className={cn("size-4 transition-transform", open && "rotate-180")}
              />
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent
            className="mt-3 space-y-2"
            data-testid={`${resourceKey}-resources-details`}
          >
            {hasPairs ? (
              pairs.map((pair, idx) => (
                <div
                  key={`${resourceKey}-${pair.label}-${idx}`}
                  className="flex items-start justify-between gap-3 rounded-md border border-blue-500/20 bg-muted/20 px-3 py-2"
                >
                  <span
                    className={cn(
                      "text-[11px] font-semibold uppercase tracking-wide",
                      colorClass
                    )}
                  >
                    {pair.label}
                  </span>
                  <span className="max-w-[70%] break-words text-right text-sm font-semibold">
                    {pair.value}
                  </span>
                </div>
              ))
            ) : (
              <CardDescription className="text-xs text-muted-foreground">
                No resource details reported.
              </CardDescription>
            )}
          </CollapsibleContent>
        </Collapsible>
      </CardContent>
    </Card>
  );
}

export function SectionCards() {
  const {
    data: info,
    isLoading: load1,
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
    isLoading: loadSys,
    refetch: refetchSys,
    isRefetching: isRefetchingSys,
  } = useQuery({
    queryKey: ["sysInfo"],
    queryFn: allSysInfo,
    staleTime: Infinity,
    gcTime: Infinity,
    refetchInterval: 1000 * 120, // 2 mins
    refetchOnWindowFocus: false,
  });

  const queryClient = useQueryClient();
  const [confirmOffboardOpen, setConfirmOffboardOpen] = useState(false);

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
  const onboardingStatusTone = useMemo(() => {
    if (!normalizedOnboardingStatus) {
      return "text-yellow-500";
    }
    if (
      normalizedOnboardingStatus.includes("FAIL") ||
      normalizedOnboardingStatus.includes("ERROR")
    ) {
      return "text-red-500";
    }
    if (normalizedOnboardingStatus.includes("NOT")) {
      return "text-yellow-500";
    }
    return "text-green-500";
  }, [normalizedOnboardingStatus]);

  const freeResourcePairs = useMemo(
    () => parseResourcePairs(info?.free_resources),
    [info?.free_resources]
  );
  const allocatedResourcePairs = useMemo(
    () => parseResourcePairs(info?.allocated_resources),
    [info?.allocated_resources]
  );
  const onboardedResourcePairs = useMemo(
    () => parseResourcePairs(info?.onboarded_resources),
    [info?.onboarded_resources]
  );

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
      // Error handled via onError toast
    }
  };

  const handleOffboardConfirm = async () => {
    try {
      await triggerOffboard();
    } catch {
      // Error handled via onError toast
    }
  };

  const [isPollingApplianceVersion, setIsPollingApplianceVersion] = useState(false);
  const [targetApplianceVersion, setTargetApplianceVersion] = useState<string | null>(null);
  const appliancePollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const appliancePollingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const {
    mutateAsync: doTriggerUpdate,
    isPending: isUpdating,
  } = useMutation({
    mutationFn: triggerUpdate,
    onSuccess: () => {
      if (appliancePollingIntervalRef.current) {
        clearInterval(appliancePollingIntervalRef.current);
      }
      if (appliancePollingTimeoutRef.current) {
        clearTimeout(appliancePollingTimeoutRef.current);
      }
      setIsPollingApplianceVersion(true);
      setTargetApplianceVersion(sysinfo?.updateInfo?.latest ?? null);
      appliancePollingIntervalRef.current = setInterval(() => {
        refetchSys();
      }, 10000);
      appliancePollingTimeoutRef.current = setTimeout(() => {
        if (appliancePollingIntervalRef.current) {
          clearInterval(appliancePollingIntervalRef.current);
          appliancePollingIntervalRef.current = null;
        }
        setIsPollingApplianceVersion(false);
        setTargetApplianceVersion(null);
      }, 600000);
      toast.info("Appliance update started. This can take a few minutes.", {
        duration: 10000,
        closeButton: true,
      });
    },
    onError: (error) => {
      toast.error(extractErrorMessage(error, "Failed to start update"));
    },
  });

  const handleTriggerUpdate = async () => {
    try {
      await doTriggerUpdate();
    } catch {
      // Error handled via onError toast
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
      if (targetVersion) {
        setTargetDmsVersion(targetVersion);
        setIsPollingDmsVersion(true);
        toast.success(res?.message || "DMS update started successfully");
        
        // Start polling for version update
        pollingIntervalRef.current = setInterval(() => {
          refetchInfo();
          refetchSys();
        }, 10000); // Poll every 10 seconds

        // Stop polling after 60 seconds
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
        // Fallback: just refetch once after delay
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

  // Check if version has updated and stop polling
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
        // Final refetch to ensure UI is up to date
        refetchInfo();
        refetchSys();
      }
    }
  }, [info?.dms_version, targetDmsVersion, isPollingDmsVersion, refetchInfo, refetchSys]);

  // Cleanup polling on unmount
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

  // Cleanup appliance polling on unmount
  useEffect(() => {
    return () => {
      if (appliancePollingIntervalRef.current) {
        clearInterval(appliancePollingIntervalRef.current);
      }
      if (appliancePollingTimeoutRef.current) {
        clearTimeout(appliancePollingTimeoutRef.current);
      }
    };
  }, []);

  const handleTriggerDmsUpdate = async () => {
    try {
      await doTriggerDmsUpdate();
    } catch {
      // Error handled via onError toast
    }
  };

  useEffect(() => {
    const timer = setTimeout(() => {
      queryClient.prefetchQuery({
        queryKey: ["docker_containers"],
        queryFn: getDockerContainer,
      });
    }, 4000);

    return () => clearTimeout(timer);
  }, [queryClient]);

  useEffect(() => {
    if (!isOnboarded && confirmOffboardOpen) {
      setConfirmOffboardOpen(false);
    }
  }, [isOnboarded, confirmOffboardOpen]);

  const currentDmsVersion = sysinfo?.dmsUpdateInfo?.current ?? info?.dms_version;
  const latestDmsVersion = sysinfo?.dmsUpdateInfo?.latest;
  const dmsVersionComparison = compareVersions(currentDmsVersion, latestDmsVersion);
  const dmsBackendAvailable = parseUpdateAvailable(sysinfo?.dmsUpdateInfo?.available);
  const dmsUpdateAvailable =
    dmsVersionComparison === null ? dmsBackendAvailable : dmsVersionComparison < 0 || dmsBackendAvailable;
  const isDmsUpdateInProgress = isUpdatingDms || isPollingDmsVersion;
  const dmsUpdateLabel = isDmsUpdateInProgress
    ? "Updating..."
    : dmsUpdateAvailable
      ? "Update your DMS"
      : "DMS up to date";

  const currentApplianceVersion =
    sysinfo?.updateInfo?.current ?? sysinfo?.applianceVersion;
  const latestApplianceVersion = sysinfo?.updateInfo?.latest;
  const applianceVersionComparison = compareVersions(
    currentApplianceVersion,
    latestApplianceVersion
  );
  const applianceBackendAvailable = parseUpdateAvailable(sysinfo?.updateInfo?.available);
  const applianceUpdateAvailable =
    applianceVersionComparison === null
      ? applianceBackendAvailable
      : applianceVersionComparison < 0 || applianceBackendAvailable;
  const isApplianceUpdateInProgress = isUpdating || isPollingApplianceVersion;
  const applianceUpdateLabel = isApplianceUpdateInProgress
    ? "Updating..."
    : applianceUpdateAvailable
      ? "Update appliance"
      : "Appliance up to date";

  useEffect(() => {
    if (!isPollingApplianceVersion) {
      return;
    }
    const targetReached =
      targetApplianceVersion &&
      compareVersions(currentApplianceVersion, targetApplianceVersion) === 0;
    if (targetReached || (!targetApplianceVersion && !applianceUpdateAvailable)) {
      if (appliancePollingIntervalRef.current) {
        clearInterval(appliancePollingIntervalRef.current);
        appliancePollingIntervalRef.current = null;
      }
      if (appliancePollingTimeoutRef.current) {
        clearTimeout(appliancePollingTimeoutRef.current);
        appliancePollingTimeoutRef.current = null;
      }
      setIsPollingApplianceVersion(false);
      setTargetApplianceVersion(null);
      const resolvedVersion = targetApplianceVersion ?? currentApplianceVersion;
      toast.success(
        resolvedVersion
          ? `Appliance updated to version ${resolvedVersion}`
          : "Appliance update completed"
      );
      refetchSys();
    }
  }, [
    isPollingApplianceVersion,
    targetApplianceVersion,
    currentApplianceVersion,
    applianceUpdateAvailable,
    refetchSys,
  ]);

  const {
    data: docker,
    isLoading: loadDocker,
    refetch: refetchDocker,
    isRefetching: isRefetchingDocker,
  } = useQuery({
    queryKey: ["docker_containers"],
    queryFn: getDockerContainer,
    enabled: false, // disabled by default, will run when prefetch/ refetch is called
    refetchOnMount: true,
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
  });

  if (load1 || loadSys) return <SectionCardsSkeleton />;

  return (
    <>
      <div className="grid grid-cols-1 gap-4 px-4">
        <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border border-blue-500 rounded-lg animate-[neonPulse_1.5s_infinite] text-wrap break-words">
          <CardHeader className="flex items-center justify-between gap-2">
            <div>
              <CardDescription>Peer ID:</CardDescription>
              <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl text-wrap break-words">
                {info?.dms_peer_id.slice(-6)}
                <CopyButton
                  text={info?.dms_peer_id.slice(-6)}
                  className="ml-2"
                />
              </CardTitle>
            </div>
            <div className="flex items-center gap-2">
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
                      data-testid="offboard-button"
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
                  <DialogContent showCloseButton={!isOffboarding} data-testid="offboard-dialog">
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
                        data-testid="offboard-cancel-button"
                      >
                        Cancel
                      </Button>
                      <Button
                        variant="destructive"
                        className="bg-red-600 hover:bg-red-700 text-white"
                        onClick={handleOffboardConfirm}
                        disabled={isOffboarding}
                        data-testid="offboard-confirm-button"
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
                  data-testid="onboard-button"
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
              {/* Refresh sysInfo button */}
              <RefreshButton
                onClick={() => refetchSys()}
                isLoading={isRefetchingSys}
                tooltip="Refresh System Info"
              />
            </div>
          </CardHeader>
          <CardFooter className="flex-col items-start gap-1.5 text-sm">
            <div className="text-muted-foreground w-full space-y-2">
              <div className="flex items-center gap-2 flex-wrap">
                <b>DID Key:</b>
                <code
                  className="text-sm truncate max-w-[250px] md:max-w-none"
                  title={info?.dms_did}
                >
                  {info?.dms_did}
                </code>
                <CopyButton text={info?.dms_did} className="ml-2" />
              </div>
              <div className="flex items-center gap-2 w-full">
                <b>Peer ID:</b>{" "}
                <code
                  className="truncate max-w-[250px] md:max-w-none"
                  title={info?.dms_peer_id}
                >
                  {info?.dms_peer_id}{" "}
                </code>
                <CopyButton text={info?.dms_peer_id} className="ml-2" />
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                  <b>DMS Version:</b>
		  <code
		    className="text-sm truncate max-w-[250px] md:max-w-none"
		    title={info?.dms_version}
		  >
		  	{info?.dms_version}
		  </code>
                <Button
                  size="sm"
                  variant={dmsUpdateAvailable || isDmsUpdateInProgress ? "default" : "outline"}
                  className={cn(
                    "h-6 px-3 text-xs",
                    dmsUpdateAvailable || isDmsUpdateInProgress
                      ? "bg-emerald-600 hover:bg-emerald-700 text-white disabled:opacity-100"
                      : "text-muted-foreground"
                  )}
                  onClick={handleTriggerDmsUpdate}
                  disabled={!dmsUpdateAvailable || isDmsUpdateInProgress}
                >
                  {isDmsUpdateInProgress ? (
                    <>
                      <Loader2 className="size-4 animate-spin" />
                      {dmsUpdateLabel}
                    </>
                  ) : (
                    dmsUpdateLabel
                  )}
                </Button>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
                  <b>Appliance Version:</b>
		  <code
		    className="text-sm truncate max-w-[250px] md:max-w-none"
		    title={sysinfo?.applianceVersion}
		  >
		  	{sysinfo?.applianceVersion}
		  </code>
                <Button
                  size="sm"
                  variant={
                    applianceUpdateAvailable || isApplianceUpdateInProgress
                      ? "default"
                      : "outline"
                  }
                  className={cn(
                    "h-6 px-3 text-xs",
                    applianceUpdateAvailable || isApplianceUpdateInProgress
                      ? "bg-emerald-600 hover:bg-emerald-700 text-white disabled:opacity-100"
                      : "text-muted-foreground"
                  )}
                  onClick={handleTriggerUpdate}
                  disabled={!applianceUpdateAvailable || isApplianceUpdateInProgress}
                  title={
                    applianceUpdateAvailable && latestApplianceVersion
                      ? `Update to ${latestApplianceVersion}`
                      : undefined
                  }
                >
                  {isApplianceUpdateInProgress ? (
                    <>
                      <Loader2 className="size-4 animate-spin" />
                      {applianceUpdateLabel}
                    </>
                  ) : (
                    applianceUpdateLabel
                  )}
                </Button>
              </div>
            </div>

            <div className="w-full mt-2 flex flex-col lg:flex-row gap-4">
              {/* Left column */}
              <div className="flex-1 flex flex-col border border-blue-500 p-2 main_board flex-grow-1 w-full">
                <h2 className="font-bold text-sm lg:text-lg my-2">Status:</h2>
                <Separator />
                <div className="flex-grow flex flex-col justify-center gap-2 mt-2">
                  <div
                  className={cn(
                    "main_board_info",
                    info?.dms_status.includes("not")
                      ? "text-red-500"
                      : "text-green-500"
                  )}
                >
                  <DownloadCloudIcon className="size-3" />
                  <span>{info?.dms_status}</span>
                </div>
                <div
                  className={
                    info?.dms_running
                      ? "main_board_info text-green-500"
                      : "main_board_info text-yellow-500"
                  }
                >
                  {info?.dms_running ? (
                    <LoaderPinwheelIcon className="size-3" />
                  ) : (
                    <XIcon className="size-3" />
                  )}
                  <span>{info?.dms_running ? "Running" : "Not Running"}</span>
                </div>
                <div className={cn("main_board_info", onboardingStatusTone)}>
                  {displayOnboardingStatus}
                </div>
                <div
                  className={cn(
                    "main_board_info",
                    !info?.dms_status ? "text-yellow-500" : "text-green-500"
                  )}
                >
                  {info?.dms_is_relayed ? "Relayed" : "Not Relayed"}
                </div>
                </div>
              </div>

              {/* Right column (sysInfo) */}
              <div className="flex-1 flex flex-col border border-blue-500 p-2 main_board flex-grow-1 w-full">
                <h2 className="font-bold text-sm lg:text-lg my-2">System Info:</h2>
                <Separator />
                <div className="flex-grow flex flex-col justify-center gap-2 mt-2">
                  <div className="flex main_board_info">
                  <span className="font-bold">Public IP</span>
                  <div className="flex items-center gap-1">
                    <span className="truncate max-w-[120px]">
                      {sysinfo?.publicIp}
                    </span>
                    <CopyButton
                      text={sysinfo?.publicIp}
                      className={undefined}
                    />
                  </div>
                </div>

                <div className="flex main_board_info">
                  <span className="font-bold">Local IP</span>
                  <div className="flex items-center gap-1">
                    <span className="truncate max-w-[120px]">
                      {sysinfo?.localIp}
                    </span>
                    <CopyButton text={sysinfo?.localIp} className={undefined} />
                  </div>
                </div>


                <div className="flex main_board_info">
                  <span className="font-bold">SSH</span>
                  <span>
                    {sysinfo?.sshStatus.running ? "Running" : "Not Running"}
                  </span>
                </div>

                <div className="flex main_board_info">
                  <span className="font-bold">
                    {sysinfo?.sshStatus.authorized_keys} SSH Authorized Keys
                  </span>
                </div>
                </div>
              </div>
            </div>
          </CardFooter>
        </Card>
      </div>

      {!((info?.free_resources ?? "").toLowerCase().includes("not")) && (
        <div className="grid grid-cols-1 gap-4 px-4 lg:grid-cols-2 xl:grid-cols-3 lg:px-6">
          <ResourceOverviewCard
            resourceKey="free"
            title="Free"
            description="Capacity currently available for new jobs."
            pairs={freeResourcePairs}
            Icon={CirclePlusIcon}
            colorClass="text-green-500"
            accentClass="border-green-500/40 bg-green-500/10 text-green-400"
            cardClassName="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border border-blue-500 rounded-lg animate-[neonPulse_1.5s_infinite]"
          />

          <ResourceOverviewCard
            resourceKey="allocated"
            title="Allocated"
            description="Capacity currently consumed by running jobs."
            pairs={allocatedResourcePairs}
            Icon={CircleMinusIcon}
            colorClass="text-red-500"
            accentClass="border-red-500/40 bg-red-500/10 text-red-400"
            cardClassName="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border border-blue-500 rounded-lg animate-[neonPulse_1.5s_infinite]"
          />

          <ResourceOverviewCard
            resourceKey="onboarded"
            title="Onboarded"
            description="Capacity currently published to NuNet."
            pairs={onboardedResourcePairs}
            Icon={CircleMinusIcon}
            colorClass="text-blue-500"
            accentClass="border-blue-500/40 bg-blue-500/10 text-blue-400"
            cardClassName="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border border-blue-500 rounded-lg animate-[neonPulse_1.5s_infinite]"
          />
        </div>
      )}

      {/* Docker section */}
      <div className="grid grid-cols-1 gap-4 px-4">
        <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border border-blue-500 rounded-lg animate-[neonPulse_1.5s_infinite]">
          <CardHeader className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h2 className="font-semibold text-sm lg:text-lg">
                Docker
              </h2>
              <Badge className="bg-blue-500/20 text-blue-600 dark:text-blue-300 border border-blue-500/40">
                {docker?.count} containers
              </Badge>
            </div>
            {/* Refresh Docker button */}
            <RefreshButton
              onClick={() => refetchDocker()}
              isLoading={isRefetchingDocker}
              tooltip="Refresh Docker Containers"
            />
          </CardHeader>

          <CardContent className="mt-4">
            <div className="grid gap-3">
              {(docker?.containers.length === 0 || loadDocker) && (
                <div className="text-center text-muted-foreground">
                  No Docker containers found.
                </div>
              )}
              {docker?.containers.map((c) => (
                <div
                  key={c.id}
                  className="flex flex-col md:flex-row md:items-center justify-between rounded-lg border border-gray-200 dark:border-gray-700 p-3 bg-muted/30"
                >
                  <div className="flex-1 min-w-0">
                    <p className="font-mono text-sm truncate">{c.name}</p>
                    <p className="text-xs text-muted-foreground truncate">
                      <span className="font-bold">Image:</span> {c.image}
                    </p>
                  </div>

                  <div className="flex items-center gap-3 mt-2 md:mt-0">
                    <Badge variant="outline" className="text-xs">
                      {c.running_for}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
