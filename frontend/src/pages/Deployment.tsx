"use client";

import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  getDeployments,
  getDeploymentDetails,
  getDeploymentManifest,
  shutdownDeployment,
} from "@/api/deployments";
import {
  ArrowLeft,
  CheckCircle,
  Repeat2Icon,
  XCircleIcon,
  Download,
  Loader2,
} from "lucide-react";
import {
  Card,
  CardHeader,
  CardDescription,
  CardTitle,
  CardFooter,
  CardAction,
  CardContent,
} from "../components/ui/card";
import { Separator } from "../components/ui/separator";
import { Button } from "../components/ui/button";
import { toast } from "sonner";
import DeploymentDetailsSkeleton from "../components/deployments/DeploymentsSkeleton";
import { CopyButton } from "../components/ui/CopyButton";
import { useEffect, useState } from "react";
import { ManifestPanel } from "../components/deployments/ManifestPanel";

export default function DeploymentDetailsPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [isShuttingDown, setIsShuttingDown] = useState(false); // ⬅️ new state

  const handleShutdown = async (deploymentId: string) => {
    try {
      setIsShuttingDown(true);
      const res = await shutdownDeployment(deploymentId);
      toast.success(res.status, { description: res.message });
    } catch (error: any) {
      toast.error("Shutdown Failed", {
        description:
          error?.response?.data?.message || "An unexpected error occurred",
      });
    } finally {
      setIsShuttingDown(false);
    }
  };

  const {
    data: deploymentsData,
    isLoading: isLoadingDeployments,
    refetch,
  } = useQuery({
    queryKey: ["deployments"],
    queryFn: getDeployments,
    refetchOnMount: "always",
    refetchInterval: 5000,
    refetchOnWindowFocus: true,
    cacheTime: 0,
    staleTime: 0,
  });

  const deployment = deploymentsData?.deployments?.find((d) => d.id === id);

  const { data: details, isLoading: isLoadingDetails } = useQuery({
    queryKey: ["deployment-details", id],
    queryFn: () => getDeploymentDetails(id!),
    enabled: !!deployment,
    refetchOnMount: "always",
    refetchOnWindowFocus: true,
    refetchInterval: 5000,
    staleTime: 0,
  });

  useEffect(() => {
    refetch();
  }, []);

  const handleDownload = () => {
    if (!details?.logs?.message) return;
    const blob = new Blob([details.logs.message], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "deployment-logs.txt";
    link.click();
    URL.revokeObjectURL(url);
  };

  if (isLoadingDeployments || isLoadingDetails)
    return <DeploymentDetailsSkeleton />;
  if (!deployment && !isLoadingDeployments && !isLoadingDetails && id)
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

  const lines = details.logs?.message?.split("\n") || [];
  const manifest = details?.manifest || null;

  function parseLogs(logMessage: string) {
    if (!logMessage) return { stdout: "", stderr: "", dms: "" };

    const stdout =
      logMessage
        .split("=== STDERR ===")[0]
        ?.split("=== STDOUT ===")[1]
        ?.trim() || "";
    const stderr =
      logMessage
        .split("=== DMS LOG ENTRIES ===")[0]
        ?.split("=== STDERR ===")[1]
        ?.trim() || "";
    const dms = logMessage.split("=== DMS LOG ENTRIES ===")[1]?.trim() || "";

    return { stdout, stderr, dms };
  }

  const { stdout, stderr, dms } = parseLogs(details.logs?.message || "");

  return (
    <>
      {/* Deployment Info */}
      <div className="grid grid-cols-1 gap-4 px-4 my-4 w-full">
        <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border rounded-lg animate-[neonPulse_1.5s_infinite] text-wrap break-words w-full">
          <CardHeader className="w-full flex flex-col gap-2">
            <Button
              variant="outline"
              onClick={() => navigate("/deploy")}
              className="flex-1 sm:flex-none w-full sm:w-auto flex items-center gap-2"
            >
              <ArrowLeft className="h-4 w-4" /> Back to Deployments
            </Button>
            <div className="flex items-center gap-2 flex-1 sm:flex-none min-w-0">
              <CardTitle className="font-semibold tabular-nums truncate max-w-[300px] sm:overflow-visible sm:whitespace-normal sm:max-w-full break-words min-w-0">
                <span title={deployment.id}>{deployment.id}</span>
              </CardTitle>
              <CopyButton text={deployment.id} className={""} />
            </div>
          </CardHeader>
          <CardFooter className="flex-col items-start gap-1.5 text-sm">
            <div className="text-muted-foreground">
              <p>
                <b>Status:</b> <code>{deployment.status}</code>
              </p>
              <p>
                <b>Type:</b> <code>{deployment.type}</code>
              </p>
              <p>
                <b>Timestamp:</b> <code>{deployment.timestamp}</code>
              </p>
              <p>
                <b>Ensemble File:</b> <code>{deployment.ensemble_file}</code>
              </p>
            </div>
            {details.status.deployment_status === "running" && (
              <Button
                onClick={() => handleShutdown(deployment.id)}
                className="block bg-red-500 hover:bg-red-600 text-white mt-3 text-right flex flex-row gap-2"
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
          </CardFooter>
        </Card>
      </div>

      {/* Deployment Progress + Allocations */}
      <div className="grid grid-cols-1 gap-4 px-4 lg:grid-cols-3 xl:grid-cols-3 lg:px-6 my-4">
        <Card className="@container/card lg:col-span-1">
          <CardHeader>
            <CardDescription>Deployment Progress</CardDescription>
            <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
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
            </CardTitle>
            <CardAction>
              {details.status.status === "success" ? (
                <CheckCircle className="text-green-500" />
              ) : details.status.status === "running" ? (
                <Repeat2Icon className="text-blue-500" />
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

        <Card className="@container/card lg:col-span-2">
          <CardHeader>
            <CardDescription>Allocations</CardDescription>
            <Separator className="my-2" />
            {details.allocations.length > 0 ? (
              <ul>
                {details.allocations.map((allocation) => (
                  <li key={allocation.id} className="flex items-center gap-2">
                    <span className="text-sm text-muted-foreground">
                      {allocation}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted-foreground text-center">
                No allocations found.
              </p>
            )}
          </CardHeader>
        </Card>
      </div>

      {/* Manifest */}
      <ManifestPanel manifest={manifest} isLoading={isLoadingDeployments} />

      {/* Logs */}
      <div className="grid grid-cols-1 gap-4 px-4 my-4">
        <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border rounded-lg">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardDescription>Deployment Logs</CardDescription>
              <Button
                variant="outline"
                size="sm"
                onClick={handleDownload}
                className="flex items-center gap-1"
              >
                <Download className="w-4 h-4" /> Download
              </Button>
            </div>
            <Separator className="my-2" />

            {/* STDOUT */}
            <div className="flex items-center justify-between mt-2">
              <p className="font-semibold">STDOUT</p>
              {stdout && <CopyButton text={stdout} className="text-xs" />}
            </div>
            {stdout ? (
              <div className="bg-black text-green-400 font-mono text-sm rounded-md p-3 h-40 overflow-y-auto shadow-inner">
                {stdout.split("\n").map((line, idx) => (
                  <div key={idx} className="whitespace-pre-wrap">
                    {line}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-muted-foreground text-center">
                No stdout logs found.
              </p>
            )}

            {/* STDERR */}
            <div className="flex items-center justify-between mt-4">
              <p className="font-semibold">STDERR</p>
              {stderr && <CopyButton text={stderr} className="text-xs" />}
            </div>
            {stderr ? (
              <div className="bg-black text-red-400 font-mono text-sm rounded-md p-3 h-40 overflow-y-auto shadow-inner">
                {stderr.split("\n").map((line, idx) => (
                  <div key={idx} className="whitespace-pre-wrap">
                    {line}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-muted-foreground text-center">
                No stderr logs found.
              </p>
            )}

            {/* DMS */}
            <div className="flex items-center justify-between mt-4">
              <p className="font-semibold">DMS Logs</p>
              {dms && <CopyButton text={dms} className="text-xs" />}
            </div>
            {dms ? (
              <div className="bg-black text-blue-400 font-mono text-sm rounded-md p-3 h-40 overflow-y-auto shadow-inner">
                {dms.split("\n").map((line, idx) => (
                  <div key={idx} className="whitespace-pre-wrap">
                    {line}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-muted-foreground text-center">
                No DMS logs found.
              </p>
            )}
          </CardHeader>
        </Card>
      </div>
    </>
  );
}
