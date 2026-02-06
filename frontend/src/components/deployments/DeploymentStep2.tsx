"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import { useConnectedPeers } from "../../hooks/getConnectedPeers";

type Props = {
  deployment_type: string;
  peer_id: string;
  set_deployment_type: (v: string) => void;
  set_peer_id: (v: string) => void;
  yaml_path: string;

  nodes: string[];
  nodes_count: number | null;
  is_nodes_loading: boolean;

  node_peer_map: Record<string, string>;
  set_node_peer_map: (v: Record<string, string>) => void;
};

function peerSuffix(peer: string, tail = 9) {
  if (!peer) return "";
  if (peer.length <= tail) return peer;
  return "..." + peer.slice(-tail);
}

export default function DeploymentStepTwo({
  deployment_type,
  peer_id,
  set_deployment_type,
  set_peer_id,
  nodes,
  is_nodes_loading,
  node_peer_map,
  set_node_peer_map,
}: Props) {
  const [search, setSearch] = useState("");
  const [activeNode, setActiveNode] = useState<string | null>(null);

  const { data: peers = [] } = useConnectedPeers();

  // Ensure we always have an active node in targeted mode (if nodes exist)
  useEffect(() => {
    if (deployment_type !== "targeted") {
      setActiveNode(null);
      return;
    }

    if (!nodes.length) {
      setActiveNode(null);
      return;
    }

    if (!activeNode || !nodes.includes(activeNode)) {
      setActiveNode(nodes[0]);
    }
  }, [deployment_type, nodes, activeNode]);

  // Keep peer_id in sync with first node selection for backwards compatibility
  useEffect(() => {
    const firstNode = nodes[0];
    if (!firstNode) {
      if (peer_id) set_peer_id("");
      return;
    }

    const nextPeerId = node_peer_map[firstNode] || "";
    if (peer_id !== nextPeerId) set_peer_id(nextPeerId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, node_peer_map]);


  const targetedCount = useMemo(() => {
    if (!nodes.length) return 0;
    return nodes.reduce(
      (acc, nodeId) => acc + (node_peer_map[nodeId] ? 1 : 0),
      0
    );
  }, [nodes, node_peer_map]);

  const undecidedCount = useMemo(() => {
    if (!nodes.length) return 0;
    return nodes.length - targetedCount;
  }, [nodes.length, targetedCount]);

  const filteredPeers = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return peers;
    return peers.filter((p) => p.toLowerCase().includes(q));
  }, [peers, search]);

  const peerMatches = useMemo(() => {
    // Render-limit for performance
    return filteredPeers.slice(0, 50);
  }, [filteredPeers]);

  const assignPeerToActiveNode = (peer: string) => {
    if (deployment_type !== "targeted") return;

    const nodeId = activeNode || nodes[0];
    if (!nodeId) return;

    const next = { ...node_peer_map, [nodeId]: peer };
    set_node_peer_map(next);

    // Maintain legacy peer_id as first node peer
    const firstNode = nodes[0];
    set_peer_id(firstNode ? next[firstNode] || "" : "");
  };

  const clearNode = (nodeId: string) => {
    const next = { ...node_peer_map };
    delete next[nodeId];
    set_node_peer_map(next);

    // Maintain legacy peer_id as first node peer
    const firstNode = nodes[0];
    set_peer_id(firstNode ? next[firstNode] || "" : "");
  };

  return (
    <div className="flex flex-col items-center w-full" data-testid="deployment-step2">
      <div className="flex items-center w-full max-w-6xl mb-6 gap-4 flex-wrap">
        <h2 className="text-2xl font-semibold">Deployment Target</h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full max-w-6xl">
        {/* Card 1: Deploy locally */}
        <Card
          onClick={() => {
            set_deployment_type("local");
            set_peer_id("");
            set_node_peer_map({});
          }}
          data-testid="deployment-target-local"
          className={cn(
            "cursor-pointer transition-all duration-1000 border-2 relative",
            deployment_type === "local"
              ? "bg-gradient-to-br from-blue-500/60 to-transparent border-blue-500 shadow-md"
              : "hover:border-blue-400"
          )}
        >
          <CardHeader>
            <CardTitle>Deploy Locally</CardTitle>
            <CardDescription>Deploy to this appliance</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="p-2 rounded-md bg-muted text-xs text-muted-foreground">
              <span className="font-mono">
                {deployment_type === "local" ? "Deployed Locally" : "Not Selected"}
              </span>
            </div>
          </CardContent>
        </Card>

        {/* Card 2: Target deployment */}
        <Card
          onClick={() => set_deployment_type("targeted")}
          data-testid="deployment-target-targeted"
          className={cn(
            "cursor-pointer transition-all duration-1000 border-2 relative",
            deployment_type === "targeted"
              ? "bg-gradient-to-br from-yellow-500/60 to-transparent border-yellow-500 shadow-md"
              : "hover:border-yellow-400"
          )}
        >
          <CardHeader>
            <div className="flex justify-between items-center gap-3">
              <div className="space-y-1.5">
                <CardTitle>Target Deployment</CardTitle>
                <CardDescription>
                  Pick a node, then choose a peer
                </CardDescription>
              </div>
              {deployment_type === "targeted" && nodes.length > 0 && (
                <div className="flex gap-2">
                  <Badge className="bg-slate-700 text-white">
                    Targeted {targetedCount}/{nodes.length}
                  </Badge>
                  <Badge className="bg-slate-700 text-white">
                    Undecided {undecidedCount}
                  </Badge>
                </div>
              )}
            </div>
          </CardHeader>

          <CardContent>
            {deployment_type === "targeted" ? (
              <>
                {(!nodes.length || is_nodes_loading) && (
                  <div className="mb-3 text-xs text-muted-foreground">
                    Waiting for node list from the selected ensemble...
                  </div>
                )}

                {nodes.length > 0 && (
                  <div className="space-y-4">
                    {/* Nodes list (top) */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between gap-3 flex-wrap">
                        <div className="text-sm font-medium">Nodes</div>
                        <div className="text-xs text-muted-foreground">
                          You must target at least one node to continue.
                        </div>
                      </div>

                      <div className="max-h-56 overflow-auto border rounded-md">
                        <div className="divide-y">
                          {nodes.map((nodeId) => {
                            const assignedPeer = node_peer_map[nodeId];
                            const isActive = activeNode === nodeId;

                            return (
                              <div
                                key={nodeId}
                                role="button"
                                tabIndex={0}
                                onClick={() => setActiveNode(nodeId)}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter" || e.key === " ") setActiveNode(nodeId);
                                }}
                                className={cn(
                                  "flex items-center justify-between gap-3 px-3 py-2 cursor-pointer",
                                  isActive ? "bg-blue-500/10" : "hover:bg-muted/50"
                                )}
                              >
                                <div className="flex items-center gap-2 min-w-0">
                                  <Badge className="bg-slate-700 text-white">{nodeId}</Badge>
                                  <div className="text-xs text-muted-foreground truncate">
                                    {assignedPeer ? (
                                      <span className="font-mono" title={assignedPeer}>
                                        {peerSuffix(assignedPeer)}
                                      </span>
                                    ) : (
                                      "Undecided"
                                    )}
                                  </div>
                                </div>

                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="sm"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    clearNode(nodeId);
                                  }}
                                  disabled={!assignedPeer}
                                  className="text-xs"
                                >
                                  Clear
                                </Button>
                              </div>
                            );
                          })}
                        </div>
                      </div>

                      <div className="text-xs text-muted-foreground">
                        Assigning peer for:{" "}
                        <span className="font-mono">
                          {activeNode || nodes[0]}
                        </span>
                      </div>
                    </div>

                    {/* Peer picker (bottom) */}
                    <div className="space-y-2">
                      <div className="text-sm font-medium">Peers</div>

                      <Input
                        placeholder="Search peers (suffix match)"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        data-testid="deployment-peer-filter"
                      />

                      <div className="max-h-56 overflow-auto border rounded-md">
                        {peerMatches.length === 0 ? (
                          <div className="p-3 text-xs text-muted-foreground">
                            No peers match your search.
                          </div>
                        ) : (
                          <div className="divide-y">
                            {peerMatches.map((peer) => (
                              <div
                                key={peer}
                                className="px-3 py-2 cursor-pointer hover:bg-muted/50"
                                onClick={() => assignPeerToActiveNode(peer)}
                                title={peer}
                                data-testid="deployment-peer-row"
                                data-peer-id={peer}
                              >
                                <span className="font-mono text-sm">
                                  {peerSuffix(peer)}
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>

                      <div className="text-xs text-muted-foreground">
                        Showing {peerMatches.length} of {filteredPeers.length} matches
                        {filteredPeers.length !== peers.length
                          ? ` (filtered from ${peers.length})`
                          : ` (total ${peers.length})`}
                        .
                      </div>
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="space-y-2">
                <div className="text-sm font-medium">Nodes available:</div>
                {is_nodes_loading ? (
                  <div className="text-xs text-muted-foreground">Loading node list...</div>
                ) : nodes.length === 0 ? (
                  <div className="text-xs text-muted-foreground">No nodes available.</div>
                ) : (
                  <div
                    className="font-mono text-sm text-muted-foreground overflow-hidden [display:-webkit-box] [-webkit-line-clamp:2] [-webkit-box-orient:vertical]"
                    title={nodes.join(", ")}
                  >
                    {nodes.join(", ")}
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Card 3: Non-targeted */}
        <Card
          onClick={() => {
            set_deployment_type("non_targeted");
            set_peer_id("");
            set_node_peer_map({});
          }}
          data-testid="deployment-target-non-targeted"
          className={cn(
            "cursor-pointer transition-all duration-1000 border-2 relative",
            deployment_type === "non_targeted"
              ? "bg-gradient-to-br from-pink-500/60 to-transparent border-pink-500 shadow-md"
              : "hover:border-pink-400"
          )}
        >
          <CardHeader>
            <CardTitle>Non-Targeted Deployment</CardTitle>
            <CardDescription>Let the network decide</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="p-2 rounded-md bg-muted text-xs text-muted-foreground">
              <span className="font-mono">
                {deployment_type === "non_targeted" ? "Network decides" : "Not Selected"}
              </span>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
