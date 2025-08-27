import { useState, useMemo } from "react";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { CopyButton } from "../ui/CopyButton";
import { RefreshButton } from "../ui/RefreshButton";
import { useQueryClient, useIsFetching } from "@tanstack/react-query";

type PeersListProps = {
  peers: string[];
};

export function PeersList({ peers }: PeersListProps) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 10;

  const queryClient = useQueryClient();

  const filteredPeers = useMemo(() => {
    return peers.filter((p) => p.toLowerCase().includes(search.toLowerCase()));
  }, [peers, search]);

  const totalPages = Math.ceil(filteredPeers.length / pageSize);
  const paginatedPeers = filteredPeers.slice(
    (page - 1) * pageSize,
    page * pageSize
  );

  // Check if the "connected-peers-main" query is currently fetching
  const isFetching = useIsFetching({ queryKey: ["connected-peers-main"] }) > 0;

  const handleRefresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["connected-peers-main"] });
  };

  return (
    <div className="grid grid-cols-1 gap-4 px-4">
      <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border rounded-lg animate-[neonPulse_1.5s_infinite] text-wrap break-words">
        <CardHeader>
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-2 sm:flex-3">
              <h2 className="font-semibold text-sm lg:text-lg">
                Connected Peers
              </h2>
              <Badge
                variant="secondary"
                className="px-2 py-0.5 rounded-full text-xs font-medium"
              >
                {filteredPeers.length}
              </Badge>
            </div>

            {/* Search + Refresh */}
            <div className="flex items-center gap-2 flex-1 justify-end">
              <Input
                placeholder="Search peers..."
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
                className="max-w-xs flex-1"
              />
              <RefreshButton
                onClick={handleRefresh}
                isLoading={isFetching}
                tooltip="Refresh Peers List"
              />
            </div>
          </div>
        </CardHeader>

        <CardContent>
          <ul className="divide-y divide-gray-600">
            {paginatedPeers.map((peer) => (
              <li
                key={peer}
                className="flex items-center justify-between py-2 px-1"
              >
                <span className="truncate text-sm font-mono">{peer}</span>
                <CopyButton text={peer} className="" />
              </li>
            ))}
          </ul>

          {/* Pagination controls */}
          <div className="flex justify-between items-center mt-4">
            <Button
              variant="outline"
              size="sm"
              disabled={page === 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </Button>
            <span className="text-sm">
              Page {page} of {totalPages || 1}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page === totalPages || totalPages === 0}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
