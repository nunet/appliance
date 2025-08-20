import { useQuery } from "@tanstack/react-query";
import { getConnectedPeers } from "../api/api"; // the helper we wrote earlier

export function useConnectedPeers() {
  return useQuery({
    queryKey: ["connected-peers"],
    queryFn: getConnectedPeers,
    refetchInterval: 10_000, // optional: auto-refresh every 10s
  });
}
