import React, { useEffect, useMemo, useState } from "react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Separator } from "../components/ui/separator";
import DeploymentStepOne from "../components/deployments/DeploymentStep1";
import DeploymentStepTwo from "../components/deployments/DeploymentStep2";
import DeploymentStepThree from "../components/deployments/DeploymentStep3";
import DeploymentStepFour from "../components/deployments/DeploymentStep4";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { deployFromTemplate, getTemplateNodesCount } from "../api/deployments";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react"; // ⬅️ loader icon

const steps = [
  { id: 1, title: "Select Ensemble" },
  { id: 2, title: "Deployment Target" },
  { id: 3, title: "Configure" },
  { id: 4, title: "Deploy" },
];

export default function NewDeployment() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const [currentStep, setCurrentStep] = useState(1);

  const [templatePath, setTemplatePath] = useState("");
  const [yamlPath, setYamlPath] = useState("");
  const [category, setCategory] = useState("");
  const [deploymentType, setDeploymentType] = useState("");
  const [peerId, setPeerId] = useState("");

  // per-node assignments for targeted mode (node_id -> peer_id). Missing key means "undecided".
  const [nodePeerMap, setNodePeerMap] = useState<Record<string, string>>({});

  const [formData, setFormData] = useState<Record<string, any>>({});
  const [formValid, setFormValid] = useState(false);

  const [isSubmitting, setIsSubmitting] = useState(false); // ⬅️ new state

  const { data: nodesData, isLoading: isNodesLoading } = useQuery({
    queryKey: ["template-nodes-count", yamlPath],
    queryFn: () => getTemplateNodesCount(yamlPath),
    enabled: !!yamlPath,
    staleTime: 30_000,
  });

  const nodesCount: number | null =
    typeof nodesData?.nodes_count === "number" ? nodesData.nodes_count : null;

  const nodes: string[] = useMemo(() => {
    if (Array.isArray(nodesData?.nodes) && nodesData.nodes.length) {
      return nodesData.nodes.map((n) => String(n));
    }
    if (typeof nodesCount === "number" && nodesCount > 0) {
      // Fallback if backend doesn't provide nodes list for some reason
      return Array.from({ length: nodesCount }, (_, i) => String(i));
    }
    return [];
  }, [nodesData?.nodes, nodesCount]);

  // Handle template from URL query param
  useEffect(() => {
    const templateFromUrl = searchParams.get("template");
    if (templateFromUrl) {
      setTemplatePath(templateFromUrl);
      setYamlPath(templateFromUrl);
      setCurrentStep(2);
    }
  }, [searchParams]);

  // Reset targeted selection when template changes
  useEffect(() => {
    setNodePeerMap({});
    setPeerId("");
  }, [yamlPath]);

  // Prefill targeted node assignments from template-defined peers (if present)
  useEffect(() => {
    const raw = nodesData?.node_peers;
    if (!raw || typeof raw !== "object") return;

    // Only prefill when there are no user assignments yet for the current template
    if (Object.keys(nodePeerMap).length > 0) return;

    const nextMap: Record<string, string> = {};
    for (const [nodeId, peerVal] of Object.entries(raw as Record<string, unknown>)) {
      if (typeof peerVal === "string" && peerVal.trim()) {
        nextMap[String(nodeId)] = peerVal.trim();
      }
    }

    if (Object.keys(nextMap).length === 0) return;

    setNodePeerMap(nextMap);

    // Keep legacy peerId aligned to the first node (DeploymentStep2 also syncs this)
    const firstNode = nodes[0];
    setPeerId(firstNode ? nextMap[firstNode] || "" : "");
  }, [nodesData?.node_peers, nodePeerMap, nodes]);

  const nextStep = () => {
    if (currentStep < steps.length) setCurrentStep(currentStep + 1);
  };

  const prevStep = () => {
    if (currentStep > 1) setCurrentStep(currentStep - 1);
  };

  const targetedCount = useMemo(() => {
    if (!nodes.length) return 0;
    return nodes.reduce((acc, nodeId) => acc + (nodePeerMap[nodeId] ? 1 : 0), 0);
  }, [nodes, nodePeerMap]);

  // Targeted mode rule: you may leave nodes undecided, but you must target at least one node.
  const isTargetedSelectionValid =
    deploymentType !== "targeted"
      ? true
      : !isNodesLoading && nodes.length > 0 && targetedCount > 0;

  const handleSubmit = async () => {
    try {
      setIsSubmitting(true); // start loader

      // Build a positional peer_ids list aligned to `nodes`.
      // null means "undecided" => backend should omit the peer key for that node.
      const peerIds: Array<string | null> =
        deploymentType === "targeted"
          ? nodes.map((nodeId) => (nodePeerMap[nodeId] ? nodePeerMap[nodeId] : null))
          : [];

      const firstTargetedPeer =
        deploymentType === "targeted"
          ? (peerIds.find((p) => typeof p === "string" && p.trim().length > 0) as string | undefined)
          : undefined;

      const targetedPeerId = (firstTargetedPeer || peerId || "").trim();

      const payload: any = {
        template_path: yamlPath,
        deployment_type: deploymentType,
        timeout: 60,
        peer_id: targetedPeerId,
        values: {
          ...formData,
          peer_id: targetedPeerId,
        },
      };

      if (deploymentType === "targeted") {
        payload.peer_ids = peerIds;
      }

      const res = await deployFromTemplate(payload);

      queryClient.invalidateQueries({ queryKey: ["deployments"] });

      console.log("Deployment response:", res);
      navigate("/deploy");
      toast.success("Deployment started successfully!");
    } catch (err) {
      console.error("Deployment failed:", err);
      toast.error("Deployment failed. Check console for details.");
    } finally {
      setIsSubmitting(false); // stop loader
    }
  };

  return (
    <div className="flex flex-col items-center justify-center mt-10 px-4 py-1" data-testid="deployment-wizard">
      <h1 className="text-2xl font-bold mb-8 text-center">
        Deploy a New Ensemble
      </h1>

      {/* Timeline */}
      <div className="flex items-center justify-center space-x-8 mb-10 flex-wrap">
        {steps.map((step, index) => {
          const isCompleted = index + 1 < currentStep;
          const isActive = index + 1 === currentStep;
          return (
            <div key={step.id} className="flex flex-row gap-4 items-center">
              <div
                className={cn(
                  "flex items-center justify-center w-10 h-10 rounded-full border-2 font-semibold transition",
                  isCompleted
                    ? "bg-green-500 border-green-500 text-white"
                    : isActive
                      ? "bg-blue-500 border-blue-500 text-white"
                      : "border-gray-700 text-white bg-gray-700"
                )}
              >
                {step.id}
              </div>
              <span className="hidden md:inline">{step.title}</span>
            </div>
          );
        })}
      </div>

      {/* Card */}
      <Card className="w-full mb-4 shadow-lg" data-testid="deployment-wizard-card">
        <CardHeader>
          <CardTitle>{steps[currentStep - 1].title}</CardTitle>
        </CardHeader>
        <CardContent>
          {currentStep === 1 && (
            <DeploymentStepOne
              path={templatePath}
              set_yaml_path={setYamlPath}
              setter={setTemplatePath}
              category={category}
              setCategory={setCategory}
            />
          )}
          {currentStep === 2 && (
            <DeploymentStepTwo
              deployment_type={deploymentType}
              peer_id={peerId}
              set_deployment_type={setDeploymentType}
              set_peer_id={setPeerId}
              yaml_path={yamlPath}
              nodes={nodes}
              nodes_count={nodesCount}
              is_nodes_loading={isNodesLoading}
              node_peer_map={nodePeerMap}
              set_node_peer_map={setNodePeerMap}
            />
          )}
          {currentStep === 3 && (
            <DeploymentStepThree
              template={templatePath}
              formData={formData}
              setFormData={setFormData}
              formValid={formValid}
              setFormValid={setFormValid}
              deployment_type={deploymentType}
            />
          )}
          {currentStep === 4 && (
            <DeploymentStepFour
              template_path={templatePath}
              category={category}
              formData={formData}
              deployment_type={deploymentType}
              peer_id={peerId}
            />
          )}
          <Separator className="my-7" />
        </CardContent>

        <CardFooter className="flex justify-between mt-4">
          <Button
            variant="outline"
            onClick={() =>
              currentStep === 1 ? navigate("/deploy") : prevStep()
            }
            data-testid="deployment-back-button"
          >
            Back
          </Button>
          {currentStep < steps.length ? (
            <Button
              onClick={nextStep}
              disabled={
                (currentStep === 1 && !templatePath) ||
                (currentStep === 2 && !deploymentType) ||
                (currentStep === 2 &&
                  deploymentType === "targeted" &&
                  !isTargetedSelectionValid) ||
                (currentStep === 3 && !formValid)
              }
              data-testid="deployment-next-button"
            >
              Next
            </Button>
          ) : (
            <Button
              onClick={handleSubmit}
              disabled={!formValid || isSubmitting}
              data-testid="deployment-deploy-button"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Deploying...
                </>
              ) : (
                "Deploy"
              )}
            </Button>
          )}
        </CardFooter>
      </Card>
    </div>
  );
}
