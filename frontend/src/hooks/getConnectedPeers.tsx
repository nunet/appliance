import { useQuery } from "@tanstack/react-query";
import { getConnectedPeers } from "../api/api"; // the helper we wrote earlier

export function useConnectedPeers() {
  return useQuery({
    queryKey: ["connected-peers"],
    queryFn: getConnectedPeers,
    refetchInterval: 30_000,
  });
}
