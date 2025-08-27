"use client";

import { Badge } from "../ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "../ui/card";
import { allInfo, allSysInfo, getDockerContainer } from "../../api/api";
import {
  CircleMinusIcon,
  CirclePlusIcon,
  DownloadCloudIcon,
  LoaderPinwheelIcon,
  XIcon,
} from "lucide-react";
import { Separator } from "../ui/separator";
import { useQuery } from "@tanstack/react-query";
import { SectionCardsSkeleton } from "./DashboardSkeleton";
import { CopyButton } from "../ui/CopyButton";
import { cn } from "../../lib/utils";
import { RefreshButton } from "../ui/RefreshButton";

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

  const {
    data: docker,
    isLoading: loadDocker,
    refetch: refetchDocker,
    isRefetching: isRefetchingDocker,
  } = useQuery({
    queryKey: ["docker_containers"],
    queryFn: getDockerContainer,
    refetchOnMount: true,
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
  });

  if (load1 || loadSys || loadDocker) return <SectionCardsSkeleton />;

  return (
    <>
      <div className="grid grid-cols-1 gap-4 px-4">
        <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border border-blue-500 rounded-lg animate-[neonPulse_1.5s_infinite] text-wrap break-words">
          <CardHeader className="flex items-center justify-between">
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
            {/* Refresh sysInfo button */}
            <RefreshButton
              onClick={() => refetchSys()}
              isLoading={isRefetchingSys}
              tooltip="Refresh System Info"
            />
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
              <p>
                <b>Version:</b> <code>{info?.dms_version}</code>
              </p>
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
                <div
                  className={cn(
                    "main_board_info",
                    info?.onboarding_status.includes("not") ||
                      info?.onboarding_status.includes("NOT")
                      ? "text-yellow-500"
                      : "text-green-500"
                  )}
                >
                  {info?.onboarding_status.replace(/\x1b\[[0-9;]*m/g, "")}
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
                  <span>{sysinfo?.applianceVersion}</span>
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

      {!info?.free_resources.includes("not") && (
        <div className="grid grid-cols-1 gap-4 px-4 lg:grid-cols-2 xl:grid-cols-3 lg:px-6">
          <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border border-blue-500 rounded-lg animate-[neonPulse_1.5s_infinite]">
            <CardHeader>
              <CardDescription className="text-green-500 flex items-center gap-1 py-1">
                <CirclePlusIcon className="size-4" /> Free{" "}
                {info?.free_resources.split(",")[0].split(":")[0]}
              </CardDescription>
              <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
                {info?.free_resources.split(",")[0].split(":")[1]}
              </CardTitle>
              <Separator />
              <CardDescription className="text-green-500 flex items-center gap-1 py-1">
                <CirclePlusIcon className="size-4" />
                Free {info?.free_resources.split(",")[1].split(":")[0]}
              </CardDescription>
              <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
                {info?.free_resources.split(",")[1].split(":")[1]}
              </CardTitle>
              <Separator />
              <CardDescription className="text-green-500 flex items-center gap-1 py-1">
                <CirclePlusIcon className="size-4" />
                Free {info?.free_resources.split(",")[2].split(":")[0]}
              </CardDescription>
              <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
                {info?.free_resources.split(",")[2].split(":")[1]}
              </CardTitle>
            </CardHeader>
          </Card>

          <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border border-blue-500 rounded-lg animate-[neonPulse_1.5s_infinite]">
            <CardHeader>
              <CardDescription className="text-red-500 flex items-center gap-1 py-1">
                <CircleMinusIcon className="size-4" /> Allocated{" "}
                {info?.allocated_resources.split(",")[0].split(":")[0]}
              </CardDescription>
              <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
                {info?.allocated_resources.split(",")[0].split(":")[1]}
              </CardTitle>
              <Separator />
              <CardDescription className="text-red-500 flex items-center gap-1 py-1">
                <CircleMinusIcon className="size-4" />
                Allocated{" "}
                {info?.allocated_resources.split(",")[1].split(":")[0]}
              </CardDescription>
              <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
                {info?.allocated_resources.split(",")[1].split(":")[1]}
              </CardTitle>
              <Separator />
              <CardDescription className="text-red-500 flex items-center gap-1 py-1">
                <CircleMinusIcon className="size-4" />
                Allocated{" "}
                {info?.allocated_resources.split(",")[2].split(":")[0]}
              </CardDescription>
              <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
                {info?.allocated_resources.split(",")[2].split(":")[1]}
              </CardTitle>
            </CardHeader>
          </Card>

          <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border border-blue-500 rounded-lg animate-[neonPulse_1.5s_infinite]">
            <CardHeader>
              <CardDescription className="text-blue-500 flex items-center gap-1 py-1">
                <CircleMinusIcon className="size-4" /> Onboarded{" "}
                {info?.onboarded_resources.split(",")[0].split(":")[0]}
              </CardDescription>
              <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
                {info?.onboarded_resources.split(",")[0].split(":")[1]}
              </CardTitle>
              <Separator />
              <CardDescription className="text-blue-500 flex items-center gap-1 py-1">
                <CircleMinusIcon className="size-4" />
                Onboarded{" "}
                {info?.onboarded_resources.split(",")[1].split(":")[0]}
              </CardDescription>
              <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
                {info?.onboarded_resources.split(",")[1].split(":")[1]}
              </CardTitle>
              <Separator />
              <CardDescription className="text-blue-500 flex items-center gap-1 py-1">
                <CircleMinusIcon className="size-4" />
                Onboarded{" "}
                {info?.onboarded_resources.split(",")[2].split(":")[0]}
              </CardDescription>
              <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
                {info?.onboarded_resources.split(",")[2].split(":")[1]}
              </CardTitle>
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
              {docker?.containers.length === 0 && (
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
