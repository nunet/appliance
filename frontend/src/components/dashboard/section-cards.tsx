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
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "../ui/tooltip";
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
  ArrowUp,
  CircleMinusIcon,
  CirclePlusIcon,
  DownloadCloudIcon,
  Loader2,
  LoaderPinwheelIcon,
  RefreshCw,
  XIcon,
  type LucideIcon,
} from "lucide-react";
import { Separator } from "../ui/separator";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { SectionCardsSkeleton } from "./DashboardSkeleton";
import { CopyButton } from "../ui/CopyButton";
import { cn } from "../../lib/utils";
import { RefreshButton } from "../ui/RefreshButton";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

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

const renderResourceGroup = (
  pairs: ResourcePair[],
  Icon: LucideIcon,
  prefix: string,
  colorClass: string
) =>
  pairs.map((pair, idx) => (
    <Fragment key={`${prefix}-${pair.label}-${idx}`}>
      <CardDescription
        className={`${colorClass} flex items-center gap-1 py-1`}
      >
        <Icon className="size-4" />
        {prefix} {pair.label}
      </CardDescription>
      <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
        {pair.value}
      </CardTitle>
      {idx < pairs.length - 1 && <Separator />}
    </Fragment>
  ));

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

  const {
    mutateAsync: doTriggerUpdate,
    isPending: isUpdating,
  } = useMutation({
    mutationFn: triggerUpdate,
    onSuccess: () => {
      toast.info("Appliance is being updated. Please refresh the page.", {
        duration: Infinity,
        closeButton: true,
        action: {
          label: "Refresh",
          onClick: () => window.location.reload(),
        },
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
              {/* Refresh sysInfo button */}
              <RefreshButton
                onClick={() => refetchSys()}
                isLoading={isRefetchingSys}
                tooltip="Refresh System Info"
              />
            </div>
          </CardHeader>
          <CardFooter className="flex-col items-start gap-1.5 text-sm">
            <div className="text-muted-foreground w-full">
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
              <div className="flex items-center gap-2">
                <p>
                  <b>Version:</b> <code>{info?.dms_version}</code>
                </p>
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
                      <TooltipContent>
                        <p>Check for DMS updates</p>
                      </TooltipContent>
                    </Tooltip>
                  )}
                </TooltipProvider>
              </div>
              <p className="flex items-center gap-2 w-full">
                <b>Peer ID:</b>{" "}
                <code
                  className="truncate max-w-[250px] md:max-w-none"
                  title={info?.dms_peer_id}
                >
                  {info?.dms_peer_id}{" "}
                </code>
                <CopyButton text={info?.dms_peer_id} className="ml-2" />
              </p>
            </div>

            <div className="w-full mt-2 flex flex-col lg:flex-row gap-4 items-start">
              {/* Left column */}
              <div className="flex-1 flex flex-col border-2 p-2 gap-2 main_board flex-grow-1 w-full">
                <h2 className="font-bold text-sm lg:text-lg my-2">Status:</h2>
                <Separator />
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

              {/* Right column (sysInfo) */}
              <div className="flex-1 flex flex-col border-2 p-2 gap-2 main_board flex-grow-1 w-full">
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
                  <span className="font-bold">Appliance Version</span>
                  <TooltipProvider>
                    <div className="flex items-center gap-2">
                      <span>{sysinfo?.applianceVersion}</span>
                      {sysinfo?.updateInfo?.available ? (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              size="sm"
                              className="h-auto w-auto p-1 bg-emerald-600 hover:bg-emerald-700 text-white"
                              onClick={handleTriggerUpdate}
                              disabled={isUpdating}
                            >
                              {isUpdating ? (
                                <Loader2 className="size-4 animate-spin" />
                              ) : (
                                <ArrowUp className="size-4" />
                              )}
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>
                            <p>Update to {sysinfo.updateInfo.latest}</p>
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
                          <TooltipContent>
                            <p>Check for updates</p>
                          </TooltipContent>
                        </Tooltip>
                      )}
                    </div>
                  </TooltipProvider>
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
          </CardFooter>
        </Card>
      </div>

      {!((info?.free_resources ?? "").toLowerCase().includes("not")) && (
        <div className="grid grid-cols-1 gap-4 px-4 lg:grid-cols-2 xl:grid-cols-3 lg:px-6">
          <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border border-blue-500 rounded-lg animate-[neonPulse_1.5s_infinite]">
            <CardHeader>
              {renderResourceGroup(
                freeResourcePairs,
                CirclePlusIcon,
                "Free",
                "text-green-500"
              )}
            </CardHeader>
          </Card>

          <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border border-blue-500 rounded-lg animate-[neonPulse_1.5s_infinite]">
            <CardHeader>
              {renderResourceGroup(
                allocatedResourcePairs,
                CircleMinusIcon,
                "Allocated",
                "text-red-500"
              )}
            </CardHeader>
          </Card>

          <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border border-blue-500 rounded-lg animate-[neonPulse_1.5s_infinite]">
            <CardHeader>
              {renderResourceGroup(
                onboardedResourcePairs,
                CircleMinusIcon,
                "Onboarded",
                "text-blue-500"
              )}
            </CardHeader>
          </Card>
        </div>
      )}

      {/* Docker section */}
      <div className="grid grid-cols-1 gap-4 px-4">
        <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border border-blue-500 rounded-lg animate-[neonPulse_1.5s_infinite]">
          <CardHeader className="flex items-center justify-between">
            <CardDescription className="flex items-center gap-2 py-1">
              Docker
              <Badge className="bg-blue-500/20 text-blue-600 dark:text-blue-300 border border-blue-500/40">
                {docker?.count} containers
              </Badge>
            </CardDescription>
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
