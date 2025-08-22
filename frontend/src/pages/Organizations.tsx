import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/organizations";
import {
  type StatusResponse,
  OnboardingFlow,
} from "../components/organizations/OnboardFlow";

export default function OrganizationOnboardingPage() {
  const qc = useQueryClient();

  const knownQuery = useQuery({
    queryKey: ["orgs-known"],
    queryFn: api.getKnownOrgs,
  });

  const statusQuery = useQuery<StatusResponse>({
    queryKey: ["org-status"],
    queryFn: api.getStatus,
    refetchInterval: 3000,
  });

  const status = statusQuery.data;
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
        />
      </div>
    </div>
  );
}
