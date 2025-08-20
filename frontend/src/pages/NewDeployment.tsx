import React, { useState } from "react";
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
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  deployFromTemplate,
  fetchTemplates,
  type Template,
} from "../api/deployments";

import { toast } from "sonner";

const steps = [
  { id: 1, title: "Select Ensemble" },
  { id: 2, title: "Deployment Target" },
  { id: 3, title: "Configure" },
  { id: 4, title: "Deploy" },
];

export default function NewDeployment() {
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState(1);

  const nextStep = () => {
    if (currentStep < steps.length) setCurrentStep(currentStep + 1);
  };

  const prevStep = () => {
    if (currentStep > 1) setCurrentStep(currentStep - 1);
  };

  const handleSubmit = async () => {
    try {
      const payload = {
        template_path: yaml_path,
        deployment_type,
        timeout: 60,
        peer_id: peer_id || "",
        values: {
          peer_id: peer_id || "",
          dns_name: formData.domain || "0.0.0.0", // fallback if empty
          proxy_port: Number(formData.proxyPort),
          bird_color: "blue",
          allocations_alloc1_resources_cpu_cores: Number(formData.cpu),
          allocations_alloc1_resources_ram_size: Number(formData.ram),
          allocations_alloc1_resources_disk_size: Number(formData.disk),
          domain_name: formData.domain || "",
          private_key: formData.privateKey || "",
          log_level: formData.logLevel || "info",
        },
      };

      const res = await deployFromTemplate(payload);
      console.log("Deployment response:", res);
      navigate("/deploy/" + res.deployment_id); // Redirect to the deployment details page
      toast.success("Deployment started successfully!");

      // you might want to navigate to a "success" screen
    } catch (err) {
      console.error("Deployment failed:", err);
      toast.error("Deployment failed. Please check the console for details.");
      console.log("Deployment error:", err);
      // Optionally, you can handle specific error cases here
    }
  };

  const [template_path, set_template_path] = useState("");
  const [yaml_path, set_yaml_path] = useState("");
  const [category, setCategory] = useState("");
  const [deployment_type, set_deployment_type] = useState("");
  const [peer_id, set_peer_id] = useState("");

  const [formData, setFormData] = useState({
    cpu: "",
    disk: "",
    ram: "",
    domain: "",
    logLevel: "",
    peerId: "",
    privateKey: "",
    proxyPort: "",
  });
  const [formValid, setFormValid] = useState(false);

  return (
    <div className="flex flex-col items-center justify-center mt-10 px-4 py-1">
      {/* Title */}
      <h1 className="text-2xl font-bold mb-8 text-center">
        Deploy a New Ensemble
      </h1>

      {/* Timeline */}
      <div className="flex items-center justify-center space-x-8 mb-10">
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
              <span>{step.title}</span>
            </div>
          );
        })}
      </div>

      {/* Card */}
      <Card className="w-full mb-4 shadow-lg">
        <CardHeader>
          <CardTitle>{steps[currentStep - 1].title}</CardTitle>
        </CardHeader>
        <CardContent>
          {/* Dummy form inputs for demo */}
          {currentStep === 1 && (
            <div>
              <DeploymentStepOne
                path={template_path}
                set_yaml_path={set_yaml_path}
                setter={set_template_path}
                category={category}
                setCategory={setCategory}
              />
            </div>
          )}
          {currentStep === 2 && (
            <div className="space-y-4">
              <DeploymentStepTwo
                deployment_type={deployment_type}
                peer_id={peer_id}
                set_deployment_type={set_deployment_type}
                set_peer_id={set_peer_id}
              />
            </div>
          )}
          {currentStep === 3 && (
            <div className="space-y-4">
              <DeploymentStepThree
                template={template_path}
                formData={formData}
                setFormData={setFormData}
                formValid={formValid}
                setFormValid={setFormValid}
                peer_id={peer_id}
                deployment_type={deployment_type}
              />
            </div>
          )}
          {currentStep === 4 && (
            <div className="space-y-4">
              <DeploymentStepFour
                template_path={template_path}
                category={category}
                formData={formData}
                deployment_type={deployment_type}
                peer_id={peer_id}
              />
            </div>
          )}
          <Separator className="mt-7" />
        </CardContent>

        <CardFooter className="flex justify-between">
          <Button
            variant="outline"
            onClick={() =>
              currentStep === 1 ? navigate("/deploy") : prevStep()
            }
          >
            Back
          </Button>
          {currentStep < steps.length ? (
            <Button
              onClick={nextStep}
              disabled={
                (currentStep === 1 && template_path.length === 0) ||
                (currentStep === 2 && deployment_type.length === 0) ||
                (deployment_type === "target" && peer_id.length === 0) ||
                (currentStep === 3 && !formValid)
              }
            >
              Next
            </Button>
          ) : (
            <Button onClick={handleSubmit}>Deploy</Button>
          )}
        </CardFooter>
      </Card>
    </div>
  );
}
