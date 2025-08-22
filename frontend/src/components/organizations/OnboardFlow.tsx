import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
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

export function OnboardingFlow({
  status,
  knownOrgs,
  qc,
}: {
  status?: StatusResponse;
  knownOrgs: Record<string, any>;
  qc: any;
}) {
  const stepStates = status?.step_states ?? [];
  const currentIndex = status?.current_index ?? 0;
  const currentStep = status?.current_step ?? "init";
  const apiStatus = status?.api_status ?? null;
  const isApproved = apiStatus === "ready" || apiStatus === "approved";
  const isRejected = currentStep === "rejected";
  const isComplete = currentStep === "complete";

  // --- poll every 5s only if we're in email_sent step ---
  useQuery({
    queryKey: ["email-poll"],
    queryFn: () => api.poll(), // <-- implement api.poll hitting /poll
    refetchInterval: 5000,
    enabled: currentStep === "join_data_sent", // only active at this step
    onSuccess: () => {
      // force refresh org-status after every poll
      qc.invalidateQueries({ queryKey: ["org-status"] });
    },
  });
  // react-query automatically stops polling once enabled=false (when step changes)

  const selectMutation = useMutation({
    mutationFn: (org_did: string) => api.postSelectOrg(org_did),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["org-status"] }),
  });

  const joinMutation = useMutation({
    mutationFn: (data: any) => api.postJoinSubmit(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["org-status"] }),
  });

  const finalizeMutation = useMutation({
    mutationFn: () => api.postProcess(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["org-status"] }),
  });

  const showSelect = currentStep === "init" || currentStep === "select_org";
  const showForm =
    currentStep === "collect_join_data" || currentStep === "submit_data";

  return (
    <div className="space-y-4">
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

      {showSelect && (
        <OrgSelect
          known={knownOrgs}
          disabled={selectMutation.isPending}
          onSelect={(did) => selectMutation.mutate(did)}
        />
      )}

      {showForm && (
        <JoinForm
          orgDid={status?.raw?.org_data?.did}
          submitting={joinMutation.isPending}
          onSubmit={(data) => joinMutation.mutate(data)}
          knownOrgs={knownOrgs}
        />
      )}

      {!showSelect && !showForm && !isComplete && !isRejected && (
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
            <Button
              className="flex-1"
              disabled={!isApproved || finalizeMutation.isPending}
              onClick={() => finalizeMutation.mutate()}
            >
              {finalizeMutation.isPending && (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              )}
              {isApproved ? "Finalize" : "Waiting for approval"}
            </Button>
          </CardFooter>
        </Card>
      )}

      {isComplete && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 text-green-600" />
              <CardTitle>All Set!</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Onboarding is complete.
          </CardContent>
        </Card>
      )}

      {isRejected && (
        <Card className="border-red-300">
          <CardHeader>
            <div className="flex items-center gap-2">
              <AlertCircle className="w-5 h-5 text-red-600" />
              <CardTitle>Request Rejected</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="text-red-600">
              {status?.rejection_reason || "The request was rejected."}
            </div>
          </CardContent>
          <CardFooter>
            <Button
              className="w-full"
              onClick={() => qc.invalidateQueries({ queryKey: ["org-status"] })}
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
