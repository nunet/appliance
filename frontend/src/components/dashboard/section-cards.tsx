"use client";

import { IconTrendingDown, IconTrendingUp } from "@tabler/icons-react";
import { Badge } from "../ui/badge";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "../ui/card";
import { useEffect, useState } from "react";
import {
  allInfo,
  allSysInfo,
  disableDms,
  enableDms,
  initDms,
  offboardCompute,
  onboardCompute,
  restartDms,
  stopDms,
  updateDms,
} from "../../api/api";
import {
  Check,
  Circle,
  CircleMinusIcon,
  CirclePlusIcon,
  Copy,
  DownloadCloud,
  DownloadCloudIcon,
  LoaderPinwheelIcon,
  Power,
  PowerOff,
  RefreshCw,
  Scissors,
  Square,
  UploadCloud,
  Wrench,
  XIcon,
} from "lucide-react";
import { Separator } from "../ui/separator";
import { Button } from "../ui/button";
import { toast } from "sonner";
import { useQuery } from "@tanstack/react-query";
import { SectionCardsSkeleton } from "./DashboardSkeleton";
import { CopyButton } from "../ui/CopyButton";
import { cn } from "../../lib/utils";

type DockerContainer = {
  id: string;
  name: string;
  image: string;
  running_for: string;
};

export function SectionCards() {
  const { data: info, isLoading: load1 } = useQuery({
    queryKey: ["apiData"],
    queryFn: async () => {
      const data = await allInfo();
      console.log(data);
      return data;
    },
    staleTime: Infinity, // always fresh
    refetchInterval: 3000, // still refetches in background if you want
  });

  const [copied, setCopied] = useState<"all" | "id" | null>(null);
  const handleCopy = (text: string, type: "all" | "id") => {
    navigator.clipboard.writeText(text);
    setCopied(type);
    setTimeout(() => setCopied(null), 1500); // reset after 1.5s
  };

  const { data: sysinfo, isLoading: load2 } = useQuery({
    queryKey: ["sysInfo"],
    queryFn: async () => {
      const data = await allSysInfo();
      console.log(data);
      return data;
    },
    staleTime: Infinity, // always fresh
    refetchInterval: 10000, // still refetches in background if you want
  });

  if (load1 || load2) {
    return <SectionCardsSkeleton />;
  }

  return (
    !load1 &&
    info &&
    info.did && (
      <>
        <div className="grid grid-cols-1 gap-4 px-4">
          <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border border-blue-500 rounded-lg animate-[neonPulse_1.5s_infinite] text-wrap break-words">
            <CardHeader>
              <CardDescription>DMS:</CardDescription>
              <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl text-wrap break-words">
                {info.dms_peer_id.slice(-6)}
                <CopyButton
                  text={info.dms_peer_id.slice(-6)}
                  className={"ml-2"}
                />
              </CardTitle>
            </CardHeader>
            <CardFooter className="flex-col items-start gap-1.5 text-sm">
              <div className="text-muted-foreground w-full">
                <p className="flex items-center gap-2 flex-wrap">
                  <b>DID Key:</b>
                  <code
                    className="text-sm  truncate max-w-[250px]"
                    title={info.dms_did}
                  >
                    {info.dms_did}
                  </code>
                  <div className="flex gap-1">
                    <Button
                      variant="outline"
                      size="icon"
                      className="h-7 w-7 ml-2"
                      onClick={() => handleCopy(info.dms_did, "all")}
                    >
                      {copied === "all" ? (
                        <Check className="w-3 h-3 text-green-600" />
                      ) : (
                        <Copy className="w-3 h-3" />
                      )}
                    </Button>
                    <Button
                      variant="outline"
                      size="icon"
                      className="h-7 w-7"
                      onClick={() =>
                        handleCopy(info.dms_did.replace("did:key:", ""), "id")
                      }
                    >
                      {copied === "id" ? (
                        <Check className="w-3 h-3 text-green-600" />
                      ) : (
                        <Scissors className="w-3 h-3" />
                      )}
                    </Button>
                  </div>
                </p>
                <p>
                  <b>Version:</b> <code>{info.dms_version}</code>
                </p>
                <p className="flex items-center gap-2 w-full">
                  <b>Peer ID:</b>{" "}
                  <code
                    className="truncate max-w-[250px]"
                    title={info.dms_peer_id}
                  >
                    {info.dms_peer_id}{" "}
                  </code>
                  <CopyButton text={info.dms_peer_id} className={"ml-2"} />
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
                      info.dms_status.includes("not")
                        ? "text-red-500"
                        : "text-green-500"
                    )}
                  >
                    <span>
                      <DownloadCloudIcon className="size-3" />
                    </span>
                    <span>{info.dms_status}</span>
                  </div>
                  <div
                    className={
                      info.dms_running
                        ? "main_board_info text-green-500"
                        : "main_board_info text-yellow-500"
                    }
                  >
                    <span>
                      {info.dms_running ? (
                        <LoaderPinwheelIcon className="size-3" />
                      ) : (
                        <XIcon className="size-3" />
                      )}
                    </span>
                    <span>{info.dms_running ? "Running" : "Not Running"}</span>
                  </div>
                  <div
                    className={cn(
                      "main_board_info",
                      info.onboarding_status.includes("not") ||
                        info.onboarding_status.includes("NOT")
                        ? "text-yellow-500"
                        : "text-green-500"
                    )}
                  >
                    {info.onboarding_status.replace(/\x1b\[[0-9;]*m/g, "")}
                  </div>
                  <div
                    className={cn(
                      "main_board_info",
                      !info.dms_status ? "text-yellow-500" : "text-green-500"
                    )}
                  >
                    {info.dms_is_relayed ? "Relayed" : "Not Relayed"}
                  </div>
                </div>

                {/* Right column */}
                {!load2 && (
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
                        <CopyButton
                          text={sysinfo?.localIp}
                          className={undefined}
                        />
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
                )}
              </div>
            </CardFooter>
          </Card>
        </div>
        {!info.free_resources.includes("not") && (
          <div className="grid grid-cols-1 gap-4 px-4 lg:grid-cols-2 xl:grid-cols-3 lg:px-6">
            <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border border-blue-500 rounded-lg animate-[neonPulse_1.5s_infinite]">
              <CardHeader>
                <CardDescription className="text-green-500 flex items-center gap-1 py-1">
                  <CirclePlusIcon className="size-4" /> Free{" "}
                  {info.free_resources.split(",")[0].split(":")[0]}
                </CardDescription>
                <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
                  {info.free_resources.split(",")[0].split(":")[1]}
                </CardTitle>
                <Separator />
                <CardDescription className="text-green-500 flex items-center gap-1 py-1">
                  <CirclePlusIcon className="size-4" />
                  Free {info.free_resources.split(",")[1].split(":")[0]}
                </CardDescription>
                <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
                  {info.free_resources.split(",")[1].split(":")[1]}
                </CardTitle>
                <Separator />
                <CardDescription className="text-green-500 flex items-center gap-1 py-1">
                  <CirclePlusIcon className="size-4" />
                  Free {info.free_resources.split(",")[2].split(":")[0]}
                </CardDescription>
                <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
                  {info.free_resources.split(",")[2].split(":")[1]}
                </CardTitle>
              </CardHeader>
            </Card>

            <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border border-blue-500 rounded-lg animate-[neonPulse_1.5s_infinite]">
              <CardHeader>
                <CardDescription className="text-red-500 flex items-center gap-1 py-1">
                  <CircleMinusIcon className="size-4" /> Allocated{" "}
                  {info.allocated_resources.split(",")[0].split(":")[0]}
                </CardDescription>
                <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
                  {info.allocated_resources.split(",")[0].split(":")[1]}
                </CardTitle>
                <Separator />
                <CardDescription className="text-red-500 flex items-center gap-1 py-1">
                  <CircleMinusIcon className="size-4" />
                  Allocated{" "}
                  {info.allocated_resources.split(",")[1].split(":")[0]}
                </CardDescription>
                <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
                  {info.allocated_resources.split(",")[1].split(":")[1]}
                </CardTitle>
                <Separator />
                <CardDescription className="text-red-500 flex items-center gap-1 py-1">
                  <CircleMinusIcon className="size-4" />
                  Allocated{" "}
                  {info.allocated_resources.split(",")[2].split(":")[0]}
                </CardDescription>
                <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
                  {info.allocated_resources.split(",")[2].split(":")[1]}
                </CardTitle>
              </CardHeader>
            </Card>

            <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border border-blue-500 rounded-lg animate-[neonPulse_1.5s_infinite]">
              <CardHeader>
                <CardDescription className="text-blue-500 flex items-center gap-1 py-1">
                  <CircleMinusIcon className="size-4" /> Onboarded{" "}
                  {info.onboarded_resources.split(",")[0].split(":")[0]}
                </CardDescription>
                <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
                  {info.onboarded_resources.split(",")[0].split(":")[1]}
                </CardTitle>
                <Separator />
                <CardDescription className="text-blue-500 flex items-center gap-1 py-1">
                  <CircleMinusIcon className="size-4" />
                  Onboarded{" "}
                  {info.onboarded_resources.split(",")[1].split(":")[0]}
                </CardDescription>
                <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
                  {info.onboarded_resources.split(",")[1].split(":")[1]}
                </CardTitle>
                <Separator />
                <CardDescription className="text-blue-500 flex items-center gap-1 py-1">
                  <CircleMinusIcon className="size-4" />
                  Onboarded{" "}
                  {info.onboarded_resources.split(",")[2].split(":")[0]}
                </CardDescription>
                <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
                  {info.onboarded_resources.split(",")[2].split(":")[1]}
                </CardTitle>
              </CardHeader>
            </Card>
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 px-4">
          <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border border-blue-500 rounded-lg animate-[neonPulse_1.5s_infinite]">
            <CardHeader className="p-0 px-3">
              <CardDescription className="flex items-center gap-2 py-1">
                Docker
                <Badge className="bg-blue-500/20 text-blue-600 dark:text-blue-300 border border-blue-500/40">
                  {sysinfo?.docker.count} containers
                </Badge>
              </CardDescription>{" "}
            </CardHeader>

            <CardContent className="mt-4">
              <div className="grid gap-3">
                {sysinfo?.docker.containers.length === 0 && (
                  <div className="text-center text-muted-foreground">
                    No Docker containers found.
                  </div>
                )}
                {sysinfo?.docker.containers.map((c) => (
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
    )
  );
}
