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

const steps = [
  { id: 1, title: "Select Ensemble" },
  { id: 2, title: "Deployment Target" },
  { id: 3, title: "Configure" },
  { id: 4, title: "Deploy" },
];

export default function NewDeployment() {
  const [currentStep, setCurrentStep] = useState(1);

  const nextStep = () => {
    if (currentStep < steps.length) setCurrentStep(currentStep + 1);
  };

  const prevStep = () => {
    if (currentStep > 1) setCurrentStep(currentStep - 1);
  };

  const handleSubmit = () => {
    alert("Form submitted ✅");
  };

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
            <div className="space-y-4">
              <DeploymentStepOne onNext={() => {}} />
            </div>
          )}
          {currentStep === 2 && (
            <div className="space-y-4">
              <DeploymentStepTwo />
            </div>
          )}
          {currentStep === 3 && (
            <div className="space-y-4">
              <DeploymentStepThree />
            </div>
          )}
          {currentStep === 4 && (
            <div className="space-y-4">
              <DeploymentStepFour />
            </div>
          )}
          <Separator className="mt-7" />
        </CardContent>

        <CardFooter className="flex justify-between">
          <Button
            variant="outline"
            onClick={prevStep}
            disabled={currentStep === 1}
          >
            Back
          </Button>
          {currentStep < steps.length ? (
            <Button onClick={nextStep}>Next</Button>
          ) : (
            <Button onClick={handleSubmit}>Deploy</Button>
          )}
        </CardFooter>
      </Card>
    </div>
  );
}
