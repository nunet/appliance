import { useQuery } from "@tanstack/react-query";
import { getConnectedPeers } from "../api/api"; // the helper we wrote earlier

export function useConnectedPeers() {
  return useQuery({
    queryKey: ["connected-peers"],
    queryFn: getConnectedPeers,
    refetchInterval: 10_000,
    refetchOnMount: "always",
    refetchOnWindowFocus: true,
    staleTime: 0,
    retry: 1, // force at least one retry if first attempt fails
  });
}
