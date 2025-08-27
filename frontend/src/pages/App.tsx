import { useEffect } from "react";
import { SectionCards } from "../components/dashboard/section-cards";
import { getConnectedPeers } from "../api/api";
import { useQuery } from "@tanstack/react-query";
import { PeersList } from "../components/dashboard/PeersList";
import { Card } from "../components/ui/card";

export default function Page() {
  const {
    data: peers = [],
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ["connected-peers-main"],
    queryFn: getConnectedPeers,
    staleTime: Infinity, // ✅ data stays "fresh" for 30s
    gcTime: Infinity, // ♾️ never garbage collect
  });

  return (
    <div className="flex flex-1 flex-col">
      <div className="container/main flex flex-1 flex-col gap-2">
        <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
          <SectionCards />
          {isLoading && (
            <div className="grid grid-cols-1 gap-4 px-4">
              <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border rounded-lg animate-[neonPulse_1.5s_infinite] text-wrap break-words p-2">
                <p>Loading peers...</p>
              </Card>
            </div>
          )}
          {error && (
            <div className="grid grid-cols-1 gap-4 px-4">
              <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border rounded-lg animate-[neonPulse_1.5s_infinite] text-wrap break-words p-2">
                <p className="text-red-500">Error loading peers</p>
              </Card>
            </div>
          )}
          {!isLoading && !error && <PeersList peers={peers} />}
        </div>
      </div>
    </div>
  );
}
