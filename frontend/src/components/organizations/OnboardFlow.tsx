import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef } from "react";
import { Loader2, CheckCircle2, AlertCircle, RefreshCw } from "lucide-react";
import { api } from "../../api/organizations";
import { Button } from "../ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardFooter,
} from "../ui/card";
import { JoinForm } from "./JoinForm";
import { OrgSelect } from "./OrgSelect";
import { Stepper } from "./Stepper";
import { StatusBanner } from "./StatusBanner";
import RestartDmsButton from "./RestartDMSButton";
import { toast } from "sonner";

export function OnboardingFlow({
  status,
  knownOrgs,
  qc,
  setStartOperation,
}: {
  status?: StatusResponse;
  knownOrgs: Record<string, any>;
  qc: any;
  setStartOperation: (val: boolean) => void;
}) {
  const stepStates = status?.step_states ?? [
    {
      id: "init",
      label: "Init",
      virtual: false,
      state: "done",
    },
    {
      id: "select_org",
      label: "Select Organization",
      virtual: false,
      state: "done",
    },
    {
      id: "collect_join_data",
      label: "Fill Join Form",
      virtual: false,
      state: "active",
    },
    {
      id: "submit_data",
      label: "Submit Data",
      virtual: false,
      state: "todo",
    },
    {
      id: "join_data_sent",
      label: "Data Sent",
      virtual: false,
      state: "todo",
    },
    {
      id: "email_verified",
      label: "Email Verified",
      virtual: true,
      state: "todo",
    },
    {
      id: "pending_authorization",
      label: "Pending Authorization",
      virtual: false,
      state: "todo",
    },
    {
      id: "join_data_received",
      label: "Join Data Received",
      virtual: false,
      state: "todo",
    },
    {
      id: "capabilities_applied",
      label: "Capabilities Applied",
      virtual: false,
      state: "todo",
    },
    {
      id: "telemetry_configured",
      label: "Telemetry Configured",
      virtual: false,
      state: "todo",
    },
    {
      id: "mtls_certs_saved",
      label: "mTLS Certs Saved",
      virtual: false,
      state: "todo",
    },
    {
      id: "complete",
      label: "Complete",
      virtual: false,
      state: "todo",
    },
    {
      id: "rejected",
      label: "Rejected",
      virtual: false,
      state: "todo",
    },
  ];
  const currentIndex = status?.current_index ?? 0;
  const currentStep = status?.current_step ?? "init";
  const apiStatus = status?.api_status ?? null;
  const isApproved = apiStatus === "ready" || apiStatus === "approved";
  const isRejected = currentStep === "rejected";
  const isComplete = currentStep === "complete";

  const shouldPoll =
    currentStep === "join_data_sent" ||
    currentStep === "pending_authorization" ||
    apiStatus === "email_sent" ||
    apiStatus === "email_verified" ||
    apiStatus === "pending" ||
    apiStatus === "processing" ||
    // apiStatus === null ||
    apiStatus === "";

  useQuery({
    queryKey: ["email-poll", currentStep, apiStatus],
    queryFn: () => api.poll(),
    refetchInterval: 5000,
    refetchIntervalInBackground: true,
    staleTime: 0,
    enabled:
      shouldPoll &&
      currentStep !== "complete" &&
      currentStep !== "rejected" &&
      currentStep !== "init" &&
      currentStep !== "select_org",
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["org-status"] });
    },
  });

  const selectMutation = useMutation({
    mutationFn: (org_did: string) => api.postSelectOrg(org_did),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["org-status"] }),
  });

  const joinMutation = useMutation({
    mutationFn: (data: any) => api.postJoinSubmit(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["org-status"] }),
  });

  // --- UI flags ---
  const showSelect = currentStep === "init" || currentStep === "select_org";
  const showForm =
    currentStep === "collect_join_data" || currentStep === "submit_data";

  const showComplete = isComplete;

  return (
    <div className="space-y-4">
      {currentStep !== "init" && currentStep !== "select_org" && (
        <>
          <div className="text-muted-foreground text-sm mb-2">
            Joining {status?.raw?.org_data?.name ?? "organization"}
          </div>
          <Card>
            <CardContent className="py-4">
              <Stepper
                steps={stepStates}
                currentIndex={currentIndex}
                currentStep={currentStep}
              />
            </CardContent>
          </Card>
          <StatusBanner status={status} />
        </>
      )}

      {showSelect && (
        <OrgSelect
          known={knownOrgs}
          disabled={selectMutation.isPending}
          onSelect={(did) => selectMutation.mutate(did)}
          setStartOperation={setStartOperation}
        />
      )}

      {showForm && (
        <JoinForm
          setStartOperation={setStartOperation}
          orgDid={status?.raw?.org_data?.did}
          submitting={joinMutation.isPending}
          onSubmit={(data) => joinMutation.mutate(data)}
          knownOrgs={knownOrgs}
          qc={qc}
        />
      )}

      {!showSelect && !showForm && !showComplete && !isRejected && (
        <Card>
          <CardHeader>
            <CardTitle>Next Steps</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="text-muted-foreground">
              The UI will advance automatically as the status changes.
            </div>
          </CardContent>
          <CardFooter>
            <Button className="flex-1 cursor-not-allowed" disabled>
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              Waiting for approval...
            </Button>
          </CardFooter>
        </Card>
      )}

      {showComplete && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 text-green-600" />
              <CardTitle>All Set!</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Onboarding is complete.
            <RestartDmsButton setStartOperation={setStartOperation} qc={qc} />
          </CardContent>
        </Card>
      )}

      {isRejected && (
        <Card className="border-red-300">
          <CardHeader>
            <div className="flex items-center gap-2">
              <AlertCircle className="w-5 h-5 text-red-600 shrink-0" />
              <CardTitle className="text-base md:text-lg">
                Request Rejected
              </CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="text-red-600 break-words break-all whitespace-pre-wrap">
              {status?.rejection_reason || "The request was rejected."}
            </div>
          </CardContent>
          <CardFooter>
            <Button
              className="w-full"
              onClick={() => {
                api
                  .reset()
                  .then(() =>
                    qc.invalidateQueries({ queryKey: ["org-status"] })
                  );
                setStartOperation(false);
              }}
            >
              <RefreshCw className="w-4 h-4 mr-2" />
              Retry
            </Button>
          </CardFooter>
        </Card>
      )}
    </div>
  );
}

/** Types coming from backend */
export type StepState = {
  id: string;
  label: string;
  virtual?: boolean;
  state: "done" | "active" | "todo";
};
export type StatusResponse = {
  current_step: string;
  current_index: number;
  progress: number; // 0-100
  api_status?: string | null;
  ui_state: string;
  ui_message: string;
  step_states: StepState[];
  rejection_reason?: string | null;
  logs?: Array<any>;
  raw?: any;
};
