import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/organizations";
import {
  type StatusResponse,
  OnboardingFlow,
} from "../components/organizations/OnboardFlow";
import React from "react";

export default function OrganizationOnboardingPage() {
  const [startOperation, setStartOperation] = React.useState(false);

  const qc = useQueryClient();

  const knownQuery = useQuery({
    queryKey: ["orgs-known"],
    queryFn: api.getKnownOrgs,
  });

  const statusQuery = useQuery<StatusResponse>({
    queryKey: ["org-status"],
    queryFn: api.getStatus,
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

  return (
    <div className="grid grid-cols-1 gap-4 px-4 my-4">
      <div className="w-full max-w-7xl mx-auto p-4 md:p-6 overflow-x-hidden">
        <h1 className="text-2xl md:text-3xl font-semibold mb-4">
          Organizations
        </h1>

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
