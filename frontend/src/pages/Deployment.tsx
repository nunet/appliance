"use client";

import { useNavigate, useParams } from "react-router-dom"; // if Next.js, use `useParams` from next/navigation
import { useQuery } from "@tanstack/react-query";
import { getDeployments, getDeploymentDetails } from "@/api/deployments";
import {
  ArrowLeft,
  Badge,
  Check,
  CheckCircle,
  Download,
  DownloadCloudIcon,
  LoaderPinwheelIcon,
  Repeat2Icon,
  XCircleIcon,
  XIcon,
} from "lucide-react";
import {
  Card,
  CardHeader,
  CardDescription,
  CardTitle,
  CardFooter,
  CardAction,
} from "../components/ui/card";
import { IconTrendingUp } from "@tabler/icons-react";
import { Separator } from "../components/ui/separator";
import { Button } from "../components/ui/button";
import { toast } from "sonner";
import { shutdownDeployment } from "../api/deployments";
import DeploymentDetailsSkeleton from "../components/deployments/DeploymentsSkeleton";

export default function DeploymentDetailsPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const handleShutdown = async (deploymentId: string) => {
    try {
      const res = await shutdownDeployment(deploymentId);
      toast.success(res.status, {
        description: res.message,
      });
    } catch (error: any) {
      toast.error("Shutdown Failed", {
        description:
          error?.response?.data?.message || "An unexpected error occurred",
      });
    }
  };
  // 1. Fetch all deployments
  const { data: deploymentsData, isLoading: isLoadingDeployments } = useQuery({
    queryKey: ["deployments"],
    queryFn: getDeployments,
    refetchInterval: 1000 * 10, // auto-refresh every 10s
  });

  // 2. Check if ID exists in deployments array
  const deployment = deploymentsData?.deployments?.find((d) => d.id === id);

  // 3. If deployment exists, fetch details in parallel
  const { data: details, isLoading: isLoadingDetails } = useQuery({
    queryKey: ["deployment-details", id],
    queryFn: () => getDeploymentDetails(id!),
    enabled: !!deployment, // only fetch if deployment exists
  });

  const handleDownload = () => {
    const blob = new Blob([details.logs.message], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "deployment-logs.txt";
    link.click();
    URL.revokeObjectURL(url);
  };

  if (isLoadingDeployments) return <DeploymentDetailsSkeleton />;
  if (!deployment)
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
          <ArrowLeft className="h-4 w-4" />
          Back to Deployments
        </Button>
      </div>
    );
  if (isLoadingDetails) return <DeploymentDetailsSkeleton />;

  const lines = details.logs?.message ? details.logs.message.split("\n") : [];
  const manifest = details.manifest?.message
    ? details.manifest.message.split("\n")
    : [];

  return (
    <>
      <div className="grid grid-cols-1 gap-4 px-4 my-4">
        <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border rounded-lg animate-[neonPulse_1.5s_infinite] text-wrap break-words">
          <CardHeader>
            <Button
              variant="outline"
              onClick={() => navigate("/deploy")}
              className="my-2"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to Deployments
            </Button>
            <CardDescription>Deployment Details: </CardDescription>
            <CardTitle className=" font-semibold tabular-nums @[250px]/card:text-xl text-wrap break-words">
              {deployment.id}
            </CardTitle>
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
            <Button
              onClick={() => handleShutdown(deployment.id)}
              className="w-full lg:w-4/5 mx-auto block bg-red-500 hover:bg-red-600 text-white mt-3"
            >
              Shut Down Deployment
            </Button>
          </CardFooter>
        </Card>
      </div>
      <div className="grid grid-cols-1 gap-4 px-4 lg:grid-cols-3 xl:grid-cols-3 lg:px-6 my-4">
        <Card className="@container/card lg:col-span-1">
          <CardHeader>
            <CardDescription>Deployment Progress</CardDescription>
            <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
              <span
                className={
                  details.status.status === "success"
                    ? "text-green-500"
                    : details.status.status === "running"
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

      <div className="grid grid-cols-1 gap-4 px-4 my-4">
        <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border rounded-lg animate-[neonPulse_1.5s_infinite] text-wrap break-words">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardDescription>Deployment Manifest</CardDescription>
            </div>
            <Separator className="my-2" />
            {manifest.length > 0 ? (
              <div className="bg-black text-white font-mono text-sm rounded-md p-3 h-64 overflow-y-auto shadow-inner">
                {manifest.map((line, idx) => (
                  <div key={idx} className="whitespace-pre-wrap">
                    {line}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-muted-foreground text-center">
                No Manifest found.
              </p>
            )}
          </CardHeader>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 px-4 my-4">
        <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border rounded-lg animate-[neonPulse_1.5s_infinite] text-wrap break-words">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardDescription>Deployment Logs</CardDescription>
              <Button
                variant="outline"
                size="sm"
                onClick={handleDownload}
                className="flex items-center gap-1"
              >
                <Download className="w-4 h-4" />
                Download
              </Button>
            </div>
            <Separator className="my-2" />
            {lines.length > 0 ? (
              <div className="bg-black text-green-400 font-mono text-sm rounded-md p-3 h-64 overflow-y-auto shadow-inner">
                {lines.map((line, idx) => (
                  <div key={idx} className="whitespace-pre-wrap">
                    {line}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-muted-foreground text-center">
                No logs found.
              </p>
            )}
          </CardHeader>
        </Card>
      </div>
    </>
  );
}
