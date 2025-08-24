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

  // ---- guard key (unique per org; include user id if you have it)
  const finalizeKey = useMemo(() => {
    const did = status?.raw?.org_data?.did ?? "global";
    return `onboarding:finalize:${did}`;
  }, [status?.raw?.org_data?.did]);

  // ---- in-memory lock (per component instance)
  const finalizeLockRef = useRef(false);

  // --- poll every 3s only if we're in join_data_sent step ---
  const shouldPoll =
    currentStep === "join_data_sent" ||
    currentStep === "pending_authorization" ||
    apiStatus === "email_sent" ||
    apiStatus === "email_verified" ||
    apiStatus === "pending" ||
    apiStatus === "processing" ||
    apiStatus === null ||
    apiStatus === "";

  useQuery({
    queryKey: ["email-poll", currentStep, apiStatus],
    queryFn: () => api.poll(),
    refetchInterval: 3000,
    refetchIntervalInBackground: true,
    staleTime: 0,
    enabled: shouldPoll,
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

  // ✅ Make finalize mutation explicit and non-retrying
  const finalizeMutation = useMutation({
    // If your API can accept an idempotency key, pass finalizeKey below
    // mutationFn: () => api.postProcess({ idempotencyKey: finalizeKey }),
    mutationFn: () => api.postProcess(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["org-status"] }),
    retry: 0, // do not auto-retry mutations
  });

  /**
   * SINGLE-SHOT FINALIZE
   * - runs once when `isApproved` first becomes true
   * - guarded by ref + localStorage to survive Strict Mode remounts/refresh
   */
  useEffect(() => {
    if (!isApproved) return;

    const stored =
      typeof window !== "undefined" ? localStorage.getItem(finalizeKey) : null;

    // do nothing if we are already inflight or done (this tab or another)
    if (
      finalizeLockRef.current ||
      stored === "inflight" ||
      stored === "success"
    )
      return;

    finalizeLockRef.current = true;
    if (typeof window !== "undefined")
      localStorage.setItem(finalizeKey, "inflight");

    finalizeMutation.mutate(undefined, {
      onSuccess: () => {
        if (typeof window !== "undefined")
          localStorage.setItem(finalizeKey, "success");
      },
      onError: () => {
        // allow a future retry (manual or automatic) if it truly failed
        finalizeLockRef.current = false;
        if (typeof window !== "undefined") localStorage.removeItem(finalizeKey);
      },
    });
  }, [isApproved, finalizeKey, finalizeMutation.mutate]);

  // Clear the guard if the flow is rejected/reset so user can try again
  useEffect(() => {
    if (!isRejected) return;
    finalizeLockRef.current = false;
    if (typeof window !== "undefined") {
      localStorage.removeItem(finalizeKey);
      setStartOperation(false);
    }
  }, [isRejected, finalizeKey]);

  // --- UI flags ---
  const showSelect = currentStep === "init" || currentStep === "select_org";
  const showForm =
    currentStep === "collect_join_data" || currentStep === "submit_data";

  // Consider "success" from storage so a refresh still shows the final card
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
            <RestartDmsButton
              finalizeKey={finalizeKey}
              setStartOperation={setStartOperation}
              qc={qc}
            />
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
                // also clear finalize guard on reset
                if (typeof window !== "undefined")
                  localStorage.removeItem(finalizeKey);
                finalizeLockRef.current = false;
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
