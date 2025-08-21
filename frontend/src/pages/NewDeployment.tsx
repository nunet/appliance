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
import { toast } from "sonner";
import { deployFromTemplate } from "../api/deployments";

const steps = [
  { id: 1, title: "Select Ensemble" },
  { id: 2, title: "Deployment Target" },
  { id: 3, title: "Configure" },
  { id: 4, title: "Deploy" },
];

export default function NewDeployment() {
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState(1);

  const [templatePath, setTemplatePath] = useState("");
  const [yamlPath, setYamlPath] = useState("");
  const [category, setCategory] = useState("");
  const [deploymentType, setDeploymentType] = useState("");
  const [peerId, setPeerId] = useState("");

  const [formData, setFormData] = useState<Record<string, any>>({});
  const [formValid, setFormValid] = useState(false);

  const nextStep = () => {
    if (currentStep < steps.length) setCurrentStep(currentStep + 1);
  };

  const prevStep = () => {
    if (currentStep > 1) setCurrentStep(currentStep - 1);
  };

  const handleSubmit = async () => {
    try {
      // Merge general info into formData dynamically
      const payload = {
        template_path: yamlPath,
        deployment_type: deploymentType,
        timeout: 60,
        peer_id: peerId || "",
        values: {
          ...formData,
          peer_id: peerId || "",
        },
      };

      const res = await deployFromTemplate(payload);
      console.log("Deployment response:", res);
      navigate("/deploy/" + res.deployment_id);
      toast.success("Deployment started successfully!");
    } catch (err) {
      console.error("Deployment failed:", err);
      toast.error("Deployment failed. Check console for details.");
    }
  };

  return (
    <div className="flex flex-col items-center justify-center mt-10 px-4 py-1">
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
          >
            Back
          </Button>
          {currentStep < steps.length ? (
            <Button
              onClick={nextStep}
              disabled={
                (currentStep === 1 && !templatePath) ||
                (currentStep === 2 && !deploymentType) ||
                (deploymentType === "targeted" && !peerId) ||
                (currentStep === 3 && !formValid)
              }
            >
              Next
            </Button>
          ) : (
            <Button onClick={handleSubmit} disabled={!formValid}>
              Deploy
            </Button>
          )}
        </CardFooter>
      </Card>
    </div>
  );
}
