import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { organizationsApi } from "../api/organizations";
import {
  type StatusResponse,
  OnboardingFlow,
} from "../components/organizations/OnboardFlow";
import React from "react";
import { RefreshButton } from "../components/ui/RefreshButton";
import { toast } from "sonner";

export default function OrganizationOnboardingPage() {
  const [startOperation, setStartOperation] = React.useState(false);

  const qc = useQueryClient();

  const knownQuery = useQuery({
    queryKey: ["orgs-known"],
    queryFn: organizationsApi.getKnownOrgs,
  });

  const statusQuery = useQuery<StatusResponse>({
    queryKey: ["org-status"],
    queryFn: organizationsApi.getStatus,
    refetchInterval: (last) =>
      last?.current_step === "complete" ? false : 5000,
    refetchIntervalInBackground: true, // keep polling even if tab is hidden
    refetchOnWindowFocus: false, // don't wake polling on focus (we already poll)
    // Optional: only start polling after known orgs load
    // enabled: knownQuery.isSuccess,
    // enabled: startOperation,
  });

  const status = statusQuery.data || { current_step: "init", current_index: 0 };
  //const isOnboarded = status?.current_step === "complete";

  const warningSignatureRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    const data = knownQuery.data;
    if (!data) {
      warningSignatureRef.current = null;
      return;
    }

    const warnings: Array<{ org: string; message: string }> = [];
    Object.entries(data).forEach(([did, entry]) => {
      const roleWarnings = Array.isArray(entry?.role_warnings)
        ? entry.role_warnings
        : [];
      roleWarnings.forEach((warning: string) => {
        warnings.push({
          org: entry?.name ?? did,
          message: warning,
        });
      });
    });

    if (warnings.length > 0) {
      const signature = warnings
        .map((w) => `${w.org}:${w.message}`)
        .join("|");
      if (warningSignatureRef.current !== signature) {
        warningSignatureRef.current = signature;
        warnings.forEach((warning) => {
          toast.warning(`Role configuration issue: ${warning.org}`, {
            description: warning.message,
          });
        });
      }
    } else {
      warningSignatureRef.current = null;
    }
  }, [knownQuery.data]);

  return (
    <div className="grid grid-cols-1 gap-4 px-4 my-4">
      <div className="w-full max-w-7xl mx-auto p-4 md:p-6 overflow-x-hidden">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-4">
          <h1 className="text-2xl md:text-3xl font-semibold">
            Organizations
          </h1>
        </div>

        <OnboardingFlow
          status={status}
          knownOrgs={knownQuery.data ?? {}}
          qc={qc}
          setStartOperation={setStartOperation}
        />
      </div>
    </div>
  );
}
