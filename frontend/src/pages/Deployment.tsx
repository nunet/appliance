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
import { useEffect } from "react";

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
    cacheTime: 0, // don’t keep cache after the query is unused
    staleTime: 0, // data is always considered stale → always refetch
  });

  const deployment = deploymentsData?.deployments?.find((d) => d.id === id);

  const { data: details, isLoading: isLoadingDetails } = useQuery({
    queryKey: ["deployment-details", id],
    queryFn: () => getDeploymentDetails(id!),
    enabled: !!deployment,
    refetchOnMount: "always",
    refetchOnWindowFocus: true,
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
      <div className="grid grid-cols-1 gap-4 px-4 my-4 w-full">
        <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border rounded-lg animate-[neonPulse_1.5s_infinite] break-words w-full">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardDescription>Deployment Manifest</CardDescription>
            </div>
            <Separator className="my-2" />

            {isLoadingDeployments ? (
              <p className="text-center py-10">Loading Manifest...</p>
            ) : manifest && Object.keys(manifest).length > 0 ? (
              <div className="flex flex-col gap-4 w-full">
                {/* Deployment Info */}
                <Card className="bg-gray-50 dark:bg-gray-800 p-3 rounded-md shadow-inner w-full">
                  <CardTitle className="text-sm font-semibold">
                    Deployment Info
                  </CardTitle>
                  <CardContent className="font-mono text-xs space-y-2 overflow-x-auto">
                    <div className="flex items-center gap-2">
                      <b>ID:</b>
                      <span
                        className="truncate max-w-[200px] sm:max-w-full"
                        title={manifest.manifest.id || "N/A"}
                      >
                        {manifest.manifest.id || "N/A"}
                      </span>
                      <CopyButton text={manifest.manifest.id || ""} />
                    </div>
                    <div>
                      <b>Subnet:</b>
                      <pre className="whitespace-pre-wrap break-all">
                        {JSON.stringify(manifest.manifest.subnet, null, 2)}
                      </pre>
                    </div>
                    {manifest.manifest.contracts && (
                      <div>
                        <b>Contracts:</b>
                        <pre className="whitespace-pre-wrap break-all">
                          {JSON.stringify(manifest.manifest.contracts, null, 2)}
                        </pre>
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* Orchestrator */}
                <Card className="bg-gray-50 dark:bg-gray-800 p-3 rounded-md shadow-inner w-full">
                  <CardTitle className="text-sm font-semibold">
                    Orchestrator
                  </CardTitle>
                  <CardContent className="font-mono text-xs space-y-2 overflow-x-auto">
                    {["pub", "did?.uri", "addr?.host", "addr?.inbox"].map(
                      (field, i) => {
                        const label = ["Pub", "DID", "Host", "Inbox"][i];
                        const value =
                          field === "pub"
                            ? manifest.manifest.orchestrator?.id?.pub
                            : field === "did?.uri"
                            ? manifest.manifest.orchestrator?.did?.uri
                            : field === "addr?.host"
                            ? manifest.manifest.orchestrator?.addr?.host
                            : manifest.manifest.orchestrator?.addr?.inbox;

                        return (
                          <div
                            key={label}
                            className="flex items-center gap-2 my-2"
                          >
                            <b>{label}:</b>
                            <span
                              className="truncate max-w-[200px] sm:max-w-full"
                              title={value || "N/A"}
                            >
                              {value || "N/A"}
                            </span>
                            <CopyButton text={value || ""} />
                          </div>
                        );
                      }
                    )}
                  </CardContent>
                </Card>

                {/* Allocations */}
                <Card className="bg-gray-50 dark:bg-gray-800 p-3 rounded-md shadow-inner w-full">
                  <CardTitle className="text-sm font-semibold">
                    Allocations
                  </CardTitle>
                  <CardContent className="font-mono text-xs space-y-2 max-h-64 overflow-y-auto">
                    {manifest.manifest.allocations ? (
                      Object.entries(manifest.manifest.allocations).map(
                        ([key, alloc]: any) => (
                          <div
                            key={key}
                            className="mb-2 border-b border-gray-200 dark:border-gray-700 pb-2"
                          >
                            <div className="flex items-center gap-2">
                              <b>ID:</b>
                              <span
                                className="truncate max-w-[200px] sm:max-w-full"
                                title={alloc.id}
                              >
                                {alloc.id}
                              </span>
                              <CopyButton text={alloc.id || ""} />
                            </div>
                            <div>
                              <b>Type:</b> {alloc.type}
                            </div>
                            <div className="flex items-center gap-2">
                              <b>DNS:</b>
                              <span
                                className="truncate max-w-[200px] sm:max-w-full"
                                title={alloc.dns_name}
                              >
                                {alloc.dns_name}
                              </span>
                              <CopyButton text={alloc.dns_name || ""} />
                            </div>
                            <div>
                              <b>Status:</b> {alloc.status}
                            </div>
                            <div className="flex items-center gap-2">
                              <b>Node ID:</b>
                              <span
                                className="truncate max-w-[200px] sm:max-w-full"
                                title={alloc.node_id || "N/A"}
                              >
                                {alloc.node_id || "N/A"}
                              </span>
                              <CopyButton text={alloc.node_id || ""} />
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
                <Card className="bg-gray-50 dark:bg-gray-800 p-3 rounded-md shadow-inner w-full">
                  <CardTitle className="text-sm font-semibold">Nodes</CardTitle>
                  <CardContent className="font-mono text-xs space-y-2 max-h-64 overflow-y-auto">
                    {manifest.manifest.nodes ? (
                      Object.entries(manifest.manifest.nodes).map(
                        ([key, node]: any) => (
                          <div
                            key={key}
                            className="mb-2 border-b border-gray-200 dark:border-gray-700 pb-2"
                          >
                            <div className="flex items-center gap-2">
                              <b>ID:</b>
                              <span
                                className="truncate max-w-[200px] sm:max-w-full"
                                title={node.id}
                              >
                                {node.id}
                              </span>
                              <CopyButton text={node.id || ""} />
                            </div>
                            <div>
                              <b>Peer:</b> {node.peer}
                            </div>
                            <div>
                              <b>Allocations:</b>{" "}
                              {node.allocations?.join(", ") || "N/A"}
                            </div>
                            <div>
                              <b>Location:</b>
                              <pre className="whitespace-pre-wrap break-all">
                                {JSON.stringify(node.location, null, 2)}
                              </pre>
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
