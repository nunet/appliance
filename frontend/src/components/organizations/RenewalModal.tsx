import { useEffect, useMemo, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog";
import { Button } from "../ui/button";
import { organizationsApi } from "../../api/organizations";
import { restartDms } from "../../api/api";
import { toast } from "sonner";
import { AlertCircle, CheckCircle2, Circle, Loader2 } from "lucide-react";
import type { StatusResponse } from "./OnboardFlow";

type RenewalPhase = "idle" | "submitting" | "waiting" | "processing" | "restarting" | "complete" | "error";

type RenewalModalProps = {
  open: boolean;
  orgDid: string | null;
  orgName?: string;
  qc: any;
  onClose: (success: boolean) => void;
};

type StepDescriptor = {
  id: Exclude<RenewalPhase, "idle" | "error">;
  label: string;
};

const STEP_SEQUENCE: StepDescriptor[] = [
  { id: "submitting", label: "Submitting renewal request" },
  { id: "waiting", label: "Awaiting organization response" },
  { id: "processing", label: "Applying new capabilities" },
  { id: "restarting", label: "Restarting DMS service" },
  { id: "complete", label: "Renewal complete" },
];

const phaseOrder = STEP_SEQUENCE.map((step) => step.id);

const extractErrorMessage = (err: unknown): string => {
  if (!err) return "Unknown error";
  const asAny = err as any;
  const responseDetail =
    asAny?.response?.data?.detail ??
    asAny?.response?.data?.error ??
    asAny?.response?.data?.message;
  if (responseDetail && typeof responseDetail === "string") {
    return responseDetail;
  }
  if (asAny?.message && typeof asAny.message === "string") {
    return asAny.message;
  }
  return "Unexpected error during renewal.";
};

export function RenewalModal({ open, orgDid, orgName, qc, onClose }: RenewalModalProps) {
  const [phase, setPhase] = useState<RenewalPhase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [statusSnapshot, setStatusSnapshot] = useState<StatusResponse | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [dmsRestarted, setDmsRestarted] = useState(false);
  const [refreshingKnown, setRefreshingKnown] = useState(false);

  // Reset modal state whenever it is closed or the target org changes.
  useEffect(() => {
    if (!open || !orgDid) {
      setPhase("idle");
      setError(null);
      setStatusSnapshot(null);
      setSubmitted(false);
      setDmsRestarted(false);
      setRefreshingKnown(false);
      return;
    }
    setPhase("submitting");
    setError(null);
    setStatusSnapshot(null);
    setSubmitted(false);
    setDmsRestarted(false);
    setRefreshingKnown(false);
  }, [open, orgDid]);

  // Kick off the renewal once the modal opens.
  useEffect(() => {
    if (!open || !orgDid || phase !== "submitting" || submitted) {
      return;
    }
    let cancelled = false;
    const startRenewal = async () => {
      try {
        await organizationsApi.startRenewal(orgDid);
        if (cancelled) {
          return;
        }
        setSubmitted(true);
        setPhase("waiting");
      } catch (err) {
        console.error("Failed to start renewal", err);
        if (!cancelled) {
          setError(extractErrorMessage(err));
          setPhase("error");
        }
      }
    };
    startRenewal();
    return () => {
      cancelled = true;
    };
  }, [open, orgDid, phase, submitted]);

  // Poll backend status while the renewal is running.
  useEffect(() => {
    if (!open || !orgDid || !submitted || phase === "idle" || phase === "error") {
      return;
    }
    let cancelled = false;
    let statusTimer: ReturnType<typeof setInterval> | undefined;
    let pollTimer: ReturnType<typeof setInterval> | undefined;

    const fetchStatus = async () => {
      try {
        const latest = await organizationsApi.getStatus();
        if (!cancelled) {
          setStatusSnapshot(latest);
        }
      } catch (err) {
        if (!cancelled) {
          console.debug("Renewal status fetch failed", err);
        }
      }
    };

    const pollRemote = async () => {
      try {
        await organizationsApi.poll();
      } catch (err) {
        if (!cancelled) {
          console.debug("Renewal poll failed", err);
        }
      }
    };

    fetchStatus();
    pollRemote();
    statusTimer = setInterval(fetchStatus, 3000);
    pollTimer = setInterval(pollRemote, 4000);

    return () => {
      cancelled = true;
      if (statusTimer) clearInterval(statusTimer);
      if (pollTimer) clearInterval(pollTimer);
    };
  }, [open, orgDid, submitted, phase]);

  // React to step transitions from the backend.
  useEffect(() => {
    if (!statusSnapshot || phase === "error") {
      return;
    }
    const step = statusSnapshot.current_step;
    const apiStatus = statusSnapshot.api_status;

    if (step === "rejected") {
      setError(
        statusSnapshot.rejection_reason ||
          statusSnapshot.raw?.error ||
          "Renewal was rejected by the organization."
      );
      setPhase("error");
      return;
    }

    if (
      phase === "waiting" &&
      ["join_data_received", "capabilities_applied", "capabilities_onboarded", "telemetry_configured", "mtls_certs_saved"].includes(
        step
      )
    ) {
      setPhase("processing");
      return;
    }

    if (
      ["complete"].includes(step) ||
      apiStatus === "approved" ||
      apiStatus === "ready"
    ) {
      if (!dmsRestarted && phase !== "complete") {
        setPhase("restarting");
      }
    }
  }, [statusSnapshot, phase, dmsRestarted]);

  // Restart DMS automatically once processing is complete.
  useEffect(() => {
    if (!open || phase !== "restarting" || dmsRestarted || error) {
      return;
    }
    let cancelled = false;
    const restart = async () => {
      try {
        await restartDms();
        if (cancelled) {
          return;
        }
        setDmsRestarted(true);
        setPhase("complete");
        toast.success("Renewal completed and DMS restart initiated.");
        try {
          setRefreshingKnown(true);
          const refreshed = await organizationsApi.refreshKnownOrgs();
          if (refreshed?.known) {
            qc.setQueryData(["orgs-known"], refreshed.known);
          }
        } catch (refreshErr) {
          console.warn("Failed to refresh known organizations after renewal", refreshErr);
        } finally {
          setRefreshingKnown(false);
        }
        await qc.invalidateQueries({ queryKey: ["org-status"] });
        await qc.invalidateQueries({ queryKey: ["orgs-known"] });
      } catch (err) {
        console.error("Failed to restart DMS automatically", err);
        if (!cancelled) {
          setError("Failed to restart DMS automatically. Please restart manually.");
          setPhase("error");
        }
      }
    };
    restart();
    return () => {
      cancelled = true;
    };
  }, [open, phase, dmsRestarted, error, qc]);

  const normalizedPhase: StepDescriptor["id"] =
    phase === "idle" || phase === "error" ? "submitting" : (phase as StepDescriptor["id"]);

  const currentIndex = phaseOrder.findIndex((step) => step === normalizedPhase);

  const steps = useMemo(() => {
    return STEP_SEQUENCE.map((step, index) => {
      const done = phase === "complete" || index < currentIndex;
      const active = index === currentIndex && phase !== "complete" && phase !== "error";
      return { ...step, done, active };
    });
  }, [currentIndex, phase]);

  const statusMessage =
    statusSnapshot?.ui_message ??
    statusSnapshot?.raw?.status_message ??
    statusSnapshot?.raw?.error ??
    null;

  const canClose = phase === "complete" || phase === "error";
  const closeLabel = phase === "complete" && !error ? "Done" : "Close";

  const handleClose = () => {
    if (canClose) {
      onClose(phase === "complete" && !error);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          handleClose();
        }
      }}
    >
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Renew {orgName ?? orgDid}</DialogTitle>
          <DialogDescription>
            We&apos;ll handle the renewal automatically. Sit tight while we refresh your access.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-3">
            {steps.map(({ id, label, done, active }) => {
              let icon = <Circle className="h-4 w-4 text-muted-foreground" />;
              if (done) {
                icon = <CheckCircle2 className="h-4 w-4 text-green-500" />;
              } else if (active) {
                icon = <Loader2 className="h-4 w-4 animate-spin text-primary" />;
              }
              if (phase === "error" && id === normalizedPhase) {
                icon = <AlertCircle className="h-4 w-4 text-red-500" />;
              }
              return (
                <div key={id} className="flex items-center gap-3 text-sm">
                  {icon}
                  <span>{label}</span>
                </div>
              );
            })}
          </div>

          {statusMessage && (
            <div className="rounded-md bg-muted/60 px-3 py-2 text-sm text-muted-foreground">
              {statusMessage}
            </div>
          )}

          {refreshingKnown && (
            <div className="flex items-center gap-2 rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" />
              Updating organization list...
            </div>
          )}

          {error && (
            <div className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              <AlertCircle className="mt-0.5 h-4 w-4" />
              <span>{error}</span>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button onClick={handleClose} disabled={!canClose}>
            {closeLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
