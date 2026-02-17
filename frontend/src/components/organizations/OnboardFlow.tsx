import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, CheckCircle2, AlertCircle, RefreshCw, Eye } from "lucide-react";
import { organizationsApi } from "../../api/organizations";
import { contractsApi, extractHostDid, type ContractMetadata } from "../../api/contracts";
import { Button } from "../ui/button";
import { ContractDetailsDrawer } from "../contracts/ContractDetailsDrawer";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
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
import { RenewalModal } from "./RenewalModal";
import { toast } from "sonner";

const COMPLETE_STATUS_MESSAGE = "Onboarding complete! Restart DMS to apply the new configuration.";

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
  const processedOk = Boolean(status?.raw?.processed_ok) || Boolean(status?.raw?.completed);
  const completeIndex = useMemo(() => stepStates.findIndex((s) => s.id === "complete"), [stepStates]);
  const displayStepStates = useMemo(() => {
    if (!processedOk || completeIndex === -1) {
      return stepStates;
    }
    return stepStates.map((step, idx) => {
      if (idx < completeIndex) {
        return step.state === "done" ? step : { ...step, state: "done" };
      }
      if (idx === completeIndex) {
        return step.state === "active" ? step : { ...step, state: "active" };
      }
      return step.state === "todo" ? step : { ...step, state: "todo" };
    });
  }, [processedOk, stepStates, completeIndex]);
  const displayIndex = processedOk && completeIndex >= 0 ? completeIndex : currentIndex;
  const displayStep = processedOk ? "complete" : currentStep;
  const isApproved = apiStatus === "ready" || apiStatus === "approved";
  const isRejected = displayStep === "rejected";
  const isContractRequiredMismatch =
    status?.api_status === "contract_required_mismatch" ||
    status?.raw?.contract_required_mismatch === true;
  const isComplete = displayStep === "complete";

  const [isCancelDialogOpen, setIsCancelDialogOpen] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [forceOrgSelect, setForceOrgSelect] = useState(false);
  const [contractDetailsOpen, setContractDetailsOpen] = useState(false);
  const [renewingOrgDid, setRenewingOrgDid] = useState<string | null>(null);
  const [renewalModal, setRenewalModal] = useState<{
    open: boolean;
    orgDid: string | null;
    orgName?: string;
  }>({
    open: false,
    orgDid: null,
    orgName: undefined,
  });
  const isRenewalModalOpen = renewalModal.open && Boolean(renewalModal.orgDid);
  const previousStepRef = useRef<string | null>(null);

  const goToOrgSelect = () => {
    setForceOrgSelect(true);
    setStartOperation(false);
    setRenewingOrgDid(null);
    setRenewalModal({ open: false, orgDid: null, orgName: undefined });
  };

  const resetOnboarding = async () => {
    const response = await organizationsApi.reset();
    goToOrgSelect();
    try {
      const latestStatus = await organizationsApi.getStatus();
      qc.setQueryData(["org-status"], latestStatus);
    } catch (statusError) {
      console.warn("Failed to refresh onboarding status after reset", statusError);
    }
    await qc.invalidateQueries({ queryKey: ["org-status"] });
    return response;
  };

  const handleCancelConfirm = async () => {
    setIsCancelling(true);
    try {
      await resetOnboarding();
      toast.success("Join request cancelled.");
      setIsCancelDialogOpen(false);
    } catch (error) {
      console.error("Failed to cancel organization onboarding", error);
      toast.error("Failed to cancel the join request. Please try again.");
    } finally {
      setIsCancelling(false);
    }
  };

  const shouldPoll =
    currentStep === "join_data_sent" ||
    currentStep === "pending_authorization" ||
    currentStep === "contract_caps_applied" ||
    currentStep === "contract_created" ||
    currentStep === "contract_received" ||
    currentStep === "contract_signing" ||
    currentStep === "contract_signed" ||
    currentStep === "deployment_caps_applied" ||
    apiStatus === "email_sent" ||
    apiStatus === "email_verified" ||
    apiStatus === "pending" ||
    apiStatus === "processing" ||
    apiStatus === "contract_caps_ready" ||
    apiStatus === "contract_caps_confirmed" ||
    apiStatus === "contract_created" ||
    apiStatus === "contract_received" ||
    apiStatus === "contract_signed" ||
    apiStatus === "deployment_caps_ready" ||
    apiStatus === "";

  useQuery({
    queryKey: ["email-poll", currentStep, apiStatus],
    queryFn: () => organizationsApi.poll(),
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
    mutationFn: (org_did: string) => organizationsApi.postSelectOrg(org_did),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["org-status"] }),
  });

  const joinMutation = useMutation({
    mutationFn: (data: any) => organizationsApi.postJoinSubmit(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["org-status"] }),
  });

  const signContractMutation = useMutation({
    mutationFn: (contractDid: string) => organizationsApi.signContract(contractDid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["org-status"] });
      setContractDetailsOpen(false);
      toast.success("Contract signed. Onboarding will continue automatically.");
    },
    onError: (error: Error) => {
      toast.error(error?.message ?? "Failed to sign contract. Please try again.");
    },
  });

  const pendingContractDid = status?.raw?.contract_did ?? null;
  const incomingContractsQuery = useQuery({
    queryKey: ["contracts", "incoming", pendingContractDid],
    queryFn: ({ signal }) =>
      contractsApi.getContracts("incoming", signal, pendingContractDid ?? undefined),
    enabled: Boolean(displayStep === "contract_received" && pendingContractDid),
  });
  // Only use the contract that matches the onboarding contract_did (incoming list can have several)
  const wantDid = pendingContractDid?.trim() ?? "";
  const matchingContractFromList = useMemo(() => {
    const contracts = incomingContractsQuery.data?.contracts ?? [];
    if (!wantDid) return null;
    return (
      contracts.find((c) => {
        const did = (c as ContractMetadata).contract_did ?? (c as { did?: string }).did;
        return typeof did === "string" && did.trim() === wantDid;
      }) ?? null
    );
  }, [incomingContractsQuery.data?.contracts, wantDid]);
  const contractDataFromState = status?.raw?.contract_data as Record<string, unknown> | null | undefined;
  const contractDataMatchesDid = useMemo(() => {
    if (!contractDataFromState || !wantDid) return false;
    const did = contractDataFromState.contract_did ?? contractDataFromState.did;
    return typeof did === "string" && String(did).trim() === wantDid;
  }, [contractDataFromState, wantDid]);
  const matchingContract = useMemo(() => {
    if (matchingContractFromList) return matchingContractFromList;
    if (contractDataMatchesDid && contractDataFromState) return contractDataFromState;
    return null;
  }, [matchingContractFromList, contractDataMatchesDid, contractDataFromState]);
  // Contract host DID (solution enabler) from the matching contract only; same as Contracts page
  const pendingHostDid = useMemo(
    () => (matchingContract ? extractHostDid(matchingContract as ContractMetadata) : null),
    [matchingContract]
  );
  const contractStateQuery = useQuery({
    queryKey: ["contracts", pendingContractDid, "state", pendingHostDid],
    queryFn: ({ signal }) =>
      contractsApi.getContractState(pendingContractDid!, {
        hostDid: pendingHostDid ?? undefined,
        signal,
      }),
    enabled: Boolean(contractDetailsOpen && pendingContractDid && pendingHostDid),
  });

  // --- UI flags ---
  const showSelect =
    forceOrgSelect ||
    displayStep === "init" ||
    displayStep === "select_org";
  const showForm =
    !forceOrgSelect &&
    !isRenewalModalOpen &&
    (displayStep === "collect_join_data" || displayStep === "submit_data");

  const showComplete = !forceOrgSelect && isComplete;
  const canCancel = !forceOrgSelect && displayStep !== "init" && !isComplete && !isRenewalModalOpen;
  const activeOrgDid = status?.raw?.org_data?.did;
  const backendRenewalFlag =
    Boolean(status?.raw?.org_data?.renewal) || Boolean(status?.raw?.form_data?.renewal) || Boolean(status?.raw?.renewal);
  const isRenewingActive =
    Boolean(activeOrgDid) &&
    (backendRenewalFlag || (renewingOrgDid !== null && renewingOrgDid === activeOrgDid));

  const statusForBanner = useMemo(() => {
    if (!status) {
      return status;
    }
    if (!processedOk || status.current_step === "complete") {
      return status;
    }
    return {
      ...status,
      current_step: "complete",
      current_index: displayIndex,
      step_states: displayStepStates,
      progress: status.progress && status.progress > 0 ? status.progress : 100,
      ui_state: status.ui_state ?? "complete",
      ui_message: status.ui_message || COMPLETE_STATUS_MESSAGE,
    };
  }, [status, processedOk, displayIndex, displayStepStates]);

  useEffect(() => {
    if (!status) {
      return;
    }
    const payload = {
      prevStep: previousStepRef.current,
      currentStep,
      displayStep,
      apiStatus,
      progress: status.progress,
      forceOrgSelect,
      showSelect,
      showForm,
      showComplete,
      isComplete,
      isRenewalModalOpen,
    };
    console.debug("[OnboardFlow] status update", payload, status);
    previousStepRef.current = currentStep;
  }, [
    status,
    currentStep,
    displayStep,
    apiStatus,
    forceOrgSelect,
    showSelect,
    showForm,
    showComplete,
    isComplete,
    isRenewalModalOpen,
  ]);

  return (
    <div className="space-y-4">
      {canCancel && (
        <>
          <div className="flex justify-end">
            <Button
              variant="outline"
              onClick={() => setIsCancelDialogOpen(true)}
              disabled={isCancelling}
            >
              Cancel
            </Button>
          </div>
          <Dialog
            open={isCancelDialogOpen}
            onOpenChange={(open) => {
              if (isCancelling) {
                return;
              }
              setIsCancelDialogOpen(open);
            }}
          >
            <DialogContent showCloseButton={!isCancelling}>
              <DialogHeader>
                <DialogTitle>
                  Cancel joining {status?.raw?.org_data?.name ?? "this organization"}?
                </DialogTitle>
                <DialogDescription>
                  Cancelling will discard your current onboarding progress. You can start again at any time.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => setIsCancelDialogOpen(false)}
                  disabled={isCancelling}
                >
                  Keep Joining
                </Button>
                <Button
                  variant="destructive"
                  onClick={handleCancelConfirm}
                  disabled={isCancelling}
                >
                  {isCancelling && (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  )}
                  Cancel Onboarding
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </>
      )}
      {!forceOrgSelect &&
        displayStep !== "init" &&
        displayStep !== "select_org" &&
        !isContractRequiredMismatch && (
        <>
          <div className="text-muted-foreground text-sm mb-2">
            Joining {status?.raw?.org_data?.name ?? "organization"}
            {activeOrgDid && knownOrgs?.[activeOrgDid]?.contract_required === false && (
              <span className="ml-2 text-muted-foreground/80">(This organization does not require a contract)</span>
            )}
          </div>
          <Card>
            <CardContent className="py-4">
              <Stepper
                steps={displayStepStates}
                currentIndex={displayIndex}
                currentStep={displayStep}
              />
            </CardContent>
          </Card>
          <StatusBanner status={statusForBanner ?? status} />
        </>
      )}

      {showSelect && (
        <OrgSelect
          known={knownOrgs}
          disabled={selectMutation.isPending || joinMutation.isPending || isRenewalModalOpen}
          onSelect={(did) => {
            setRenewingOrgDid(null);
            selectMutation.mutate(did);
          }}
          onRenew={(did) => {
            const orgEntry = knownOrgs?.[did];
            setRenewingOrgDid(did);
            setRenewalModal({
              open: true,
              orgDid: did,
              orgName: orgEntry?.name ?? did,
            });
            setForceOrgSelect(true);
            setStartOperation(true);
          }}
          setStartOperation={setStartOperation}
          onBeginOnboarding={() => setForceOrgSelect(false)}
        />
      )}

      {showForm && (
        <JoinForm
          orgDid={activeOrgDid}
          submitting={joinMutation.isPending}
          onSubmit={(data) =>
            joinMutation.mutate({
              ...data,
              renewal: isRenewingActive,
            })
          }
          knownOrgs={knownOrgs}
          onCancel={() => setIsCancelDialogOpen(true)}
          renewal={isRenewingActive}
        />
      )}

      {!showSelect && !showForm && !showComplete && !isRejected && displayStep === "contract_received" && (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Next Steps</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="text-muted-foreground">
                The contract has been received. Review the details and approve the contract to continue onboarding.
              </div>
            </CardContent>
            <CardFooter className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                onClick={() => setContractDetailsOpen(true)}
                disabled={!pendingContractDid}
                className="gap-2"
              >
                <Eye className="w-4 h-4" />
                Details
              </Button>
              <Button
                onClick={() => {
                  if (pendingContractDid) signContractMutation.mutate(pendingContractDid);
                }}
                disabled={!pendingContractDid || signContractMutation.isPending}
                className="gap-2"
              >
                {signContractMutation.isPending ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Approving...
                  </>
                ) : (
                  "Approve"
                )}
              </Button>
            </CardFooter>
          </Card>
          <ContractDetailsDrawer
            open={contractDetailsOpen}
            onOpenChange={(open) => setContractDetailsOpen(open)}
            baseContract={
              matchingContract ??
              contractStateQuery.data?.contract ??
              (pendingContractDid ? { contract_did: pendingContractDid, current_state: "DRAFT" } : null)
            }
            state={contractStateQuery.data ?? null}
            isLoading={contractStateQuery.isFetching && Boolean(pendingContractDid)}
            error={
              contractStateQuery.error
                ? contractStateQuery.error instanceof Error
                  ? contractStateQuery.error.message
                  : String(contractStateQuery.error)
                : null
            }
            onRefresh={pendingContractDid ? () => contractStateQuery.refetch() : undefined}
          />
        </>
      )}

      {!showSelect && !showForm && !showComplete && !isRejected && displayStep !== "contract_received" && (
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
        <Card data-testid="onboarding-complete-card">
          <CardHeader>
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 text-green-600" />
              <CardTitle>All Set!</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Onboarding is complete.
            <RestartDmsButton
              setStartOperation={setStartOperation}
              qc={qc}
              onAfterRestart={goToOrgSelect}
            />
          </CardContent>
        </Card>
      )}

      {!forceOrgSelect && isContractRequiredMismatch && (
        <Card className="border-amber-300">
          <CardHeader>
            <div className="flex items-center gap-2">
              <AlertCircle className="w-5 h-5 text-amber-600 shrink-0" />
              <CardTitle className="text-base md:text-lg">
                Request Pending Manual Review
              </CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="text-amber-700 dark:text-amber-400 break-words whitespace-pre-wrap">
              {status?.raw?.status_message || status?.ui_message || "Contract required setting mismatch between organization and appliance. An administrator will resolve this; no action needed from you."}
            </div>
          </CardContent>
          <CardFooter className="flex flex-col gap-2 sm:flex-row sm:justify-end">
            <Button
              variant="outline"
              className="w-full sm:w-auto"
              onClick={() => setIsCancelDialogOpen(true)}
              disabled={isCancelling}
            >
              Cancel
            </Button>
          </CardFooter>
        </Card>
      )}

      {!forceOrgSelect && isRejected && !isContractRequiredMismatch && (
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
          <CardFooter className="flex flex-col gap-2 sm:flex-row sm:justify-end">
            <Button
              variant="outline"
              className="w-full sm:w-auto"
              onClick={() => setIsCancelDialogOpen(true)}
              disabled={isCancelling}
            >
              Cancel
            </Button>
            <Button
              className="w-full sm:w-auto"
              onClick={async () => {
                try {
                  await resetOnboarding();
                  toast.success("Ready when you are. Start the join process again anytime.");
                } catch (error) {
                  console.error("Failed to reset onboarding after rejection", error);
                  toast.error("Failed to reset the join flow. Please try again.");
                }
              }}
            >
              <RefreshCw className="w-4 h-4 mr-2" />
              Retry
            </Button>
          </CardFooter>
        </Card>
      )}

      <RenewalModal
        open={renewalModal.open}
        orgDid={renewalModal.orgDid}
        orgName={renewalModal.orgName}
        qc={qc}
        onClose={(wasSuccessful) => {
          const succeeded = Boolean(wasSuccessful);
          setRenewalModal({ open: false, orgDid: null, orgName: undefined });
          setStartOperation(false);
          setRenewingOrgDid(null);
          if (succeeded) {
            toast.success("Renewal finished successfully.");
            setForceOrgSelect(true);
            qc.invalidateQueries({ queryKey: ["org-status"] });
            qc.invalidateQueries({ queryKey: ["orgs-known"] });
          } else if (wasSuccessful === false) {
            toast.error("Renewal did not complete. Please check the status and try again.");
          }
        }}
      />
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
