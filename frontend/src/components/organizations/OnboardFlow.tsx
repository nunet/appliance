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
import { restartDms } from "../../api/api";
import { toast } from "sonner";

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

  // --- poll every 3s only if we're in join_data_sent step ---
  useQuery({
    queryKey: ["email-poll"],
    queryFn: () => api.poll(),
    refetchInterval: 3000,
    refetchIntervalInBackground: true,
    staleTime: 0,
    enabled: currentStep === "join_data_sent",
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

  const finalizeMutation = useMutation({
    mutationFn: () => api.postProcess(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["org-status"] }),
  });

  // Trigger finalize step only once after approval
  useEffect(() => {
    if (
      isApproved &&
      !finalizeMutation.isPending &&
      !finalizeMutation.isSuccess
    ) {
      finalizeMutation.mutate();
    }
  }, [
    isApproved,
    finalizeMutation.isPending,
    finalizeMutation.isSuccess,
    finalizeMutation.mutate,
  ]);

  // --- UI flags ---
  const showSelect = currentStep === "init" || currentStep === "select_org";
  const showForm =
    currentStep === "collect_join_data" || currentStep === "submit_data";

  // ✅ Fix 1: only show final "All Set" card if backend says complete
  // AND finalize mutation has finished successfully
  const showComplete = isComplete && finalizeMutation.isSuccess;

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
        />
      )}

      {showForm && (
        <>
          <JoinForm
            orgDid={status?.raw?.org_data?.did}
            submitting={joinMutation.isPending}
            onSubmit={(data) => joinMutation.mutate(data)}
            knownOrgs={knownOrgs}
            qc={qc}
          />
        </>
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
              {finalizeMutation.isPending && (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              )}
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
            <Button
              className="w-full bg-white text-black border border-gray-300 hover:bg-gray-50 mt-3"
              onClick={() => {
                restartDms().then(() => {
                  toast.success("DMS is restarting");
                  qc.invalidateQueries({ queryKey: ["org-status"] });
                });
              }}
            >
              Restart DMS
            </Button>
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
              onClick={() => {
                api
                  .reset()
                  .then(() =>
                    qc.invalidateQueries({ queryKey: ["org-status"] })
                  );
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
