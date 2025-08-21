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

export default function DeploymentDetailsPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const handleShutdown = async (deploymentId: string) => {
    try {
      const res = await shutdownDeployment(deploymentId);
      toast.success(res.status, { description: res.message });
    } catch (error: any) {
      toast.error("Shutdown Failed", {
        description:
          error?.response?.data?.message || "An unexpected error occurred",
      });
    }
  };

  const { data: deploymentsData, isLoading: isLoadingDeployments } = useQuery({
    queryKey: ["deployments"],
    queryFn: getDeployments,
    refetchOnMount: "always",
    refetchInterval: 10000,
  });

  const deployment = deploymentsData?.deployments?.find((d) => d.id === id);

  const { data: details, isLoading: isLoadingDetails } = useQuery({
    queryKey: ["deployment-details", id],
    queryFn: () => getDeploymentDetails(id!),
    enabled: !!deployment,
    refetchOnMount: "always",
  });

  // const { data: manifestData, isLoading: isLoadingManifest } = useQuery({
  //   queryKey: ["deployment-manifest", id],
  //   queryFn: () => getDeploymentManifest(id!),
  //   enabled: !!deployment,
  // });

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
          <ArrowLeft className="h-4 w-4" /> Back to Deployments
        </Button>
      </div>
    );

  const lines = details.logs?.message?.split("\n") || [];
  const manifest = details || null;

  return (
    <>
      {/* Deployment Info */}
      <div className="grid grid-cols-1 gap-4 px-4 my-4">
        <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border rounded-lg animate-[neonPulse_1.5s_infinite] text-wrap break-words">
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
            {details.status.status === "running" && (
              <Button
                onClick={() => handleShutdown(deployment.id)}
                className="w-full lg:w-4/5 mx-auto block bg-red-500 hover:bg-red-600 text-white mt-3"
              >
                Shut Down Deployment
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

      {/* Manifest */}
      <div className="grid grid-cols-1 gap-4 px-4 my-4">
        <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border rounded-lg animate-[neonPulse_1.5s_infinite] text-wrap break-words">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardDescription>Deployment Manifest</CardDescription>
            </div>
            <Separator className="my-2" />
            {isLoadingDeployments ? (
              <p className="text-center py-10">Loading Manifest...</p>
            ) : manifest && Object.keys(manifest).length > 0 ? (
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
                {/* Deployment Info */}
                <Card className="bg-gray-50 dark:bg-gray-800 p-3 rounded-md shadow-inner">
                  <CardTitle className="text-sm font-semibold">
                    Deployment Info
                  </CardTitle>
                  <CardContent className="font-mono text-xs">
                    <div>
                      <b>ID:</b> {manifest.manifest.id || "N/A"}
                    </div>
                    <div>
                      <b>Subnet:</b> {JSON.stringify(manifest.manifest.subnet)}
                    </div>
                    {manifest.manifest.contracts && (
                      <div>
                        <b>Contracts:</b>{" "}
                        {JSON.stringify(manifest.manifest.contracts)}
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* Orchestrator */}
                <Card className="bg-gray-50 dark:bg-gray-800 p-3 rounded-md shadow-inner">
                  <CardTitle className="text-sm font-semibold">
                    Orchestrator
                  </CardTitle>
                  <CardContent className="font-mono text-xs">
                    <div>
                      <b>Pub:</b>{" "}
                      {manifest.manifest.orchestrator?.id?.pub || "N/A"}
                    </div>
                    <div>
                      <b>DID:</b>{" "}
                      {manifest.manifest.orchestrator?.did?.uri || "N/A"}
                    </div>
                    <div>
                      <b>Host:</b>{" "}
                      {manifest.manifest.orchestrator?.addr?.host || "N/A"}
                    </div>
                    <div>
                      <b>Inbox:</b>{" "}
                      {manifest.manifest.orchestrator?.addr?.inbox || "N/A"}
                    </div>
                  </CardContent>
                </Card>

                {/* Allocations */}
                <Card className="bg-gray-50 dark:bg-gray-800 p-3 rounded-md shadow-inner">
                  <CardTitle className="text-sm font-semibold">
                    Allocations
                  </CardTitle>
                  <CardContent className="font-mono text-xs max-h-48 overflow-y-auto">
                    {manifest.manifest.allocations ? (
                      Object.entries(manifest.manifest.allocations).map(
                        ([key, alloc]: any) => (
                          <div
                            key={key}
                            className="mb-2 border-b border-gray-200 dark:border-gray-700 pb-1"
                          >
                            <div>
                              <b>ID:</b> {alloc.id}
                            </div>
                            <div>
                              <b>Type:</b> {alloc.type}
                            </div>
                            <div>
                              <b>DNS:</b> {alloc.dns_name}
                            </div>
                            <div>
                              <b>Status:</b> {alloc.status}
                            </div>
                            <div>
                              <b>Node ID:</b> {alloc.node_id || "N/A"}
                            </div>
                          </div>
                        )
                      )
                    ) : (
                      <p className="text-muted-foreground text-center">
                        No Allocations
                      </p>
                    )}
                  </CardContent>
                </Card>

                {/* Nodes */}
                <Card className="bg-gray-50 dark:bg-gray-800 p-3 rounded-md shadow-inner lg:col-span-2">
                  <CardTitle className="text-sm font-semibold">Nodes</CardTitle>
                  <CardContent className="font-mono text-xs max-h-48 overflow-y-auto">
                    {manifest.manifest.nodes ? (
                      Object.entries(manifest.manifest.nodes).map(
                        ([key, node]: any) => (
                          <div
                            key={key}
                            className="mb-2 border-b border-gray-200 dark:border-gray-700 pb-1"
                          >
                            <div>
                              <b>ID:</b> {node.id}
                            </div>
                            <div>
                              <b>Peer:</b> {node.peer}
                            </div>
                            <div>
                              <b>Allocations:</b>{" "}
                              {node.allocations?.join(", ") || "N/A"}
                            </div>
                            <div>
                              <b>Location:</b> {JSON.stringify(node.location)}
                            </div>
                          </div>
                        )
                      )
                    ) : (
                      <p className="text-muted-foreground text-center">
                        No Nodes
                      </p>
                    )}
                  </CardContent>
                </Card>
              </div>
            ) : (
              <p className="text-muted-foreground text-center py-10">
                No manifest available
              </p>
            )}
          </CardHeader>
        </Card>
      </div>

      {/* Logs */}
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
                <Download className="w-4 h-4" /> Download
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
