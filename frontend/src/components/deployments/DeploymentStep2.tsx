"use client";

import { useState } from "react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { useConnectedPeers } from "../../hooks/getConnectedPeers";

export default function DeploymentStepTwo({
  deployment_type,
  peer_id,
  set_deployment_type,
  set_peer_id,
}) {
  const [search, setSearch] = useState("");

  const { data: peers = [], isLoading, error } = useConnectedPeers();

  const filteredPeers = peers.filter((p) =>
    p.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="flex flex-col items-center w-full">
      <h2 className="text-2xl font-semibold mb-6">Deployment Target</h2>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full max-w-6xl">
        {/* Card 1: Deploy locally */}
        <Card
          onClick={() => {
            set_deployment_type("local");
            set_peer_id("");
          }}
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
                {deployment_type === "local"
                  ? "Deployed Locally"
                  : "Not Selected"}
              </span>
            </div>
          </CardContent>
        </Card>

        {/* Card 2: Target deployment */}
        <Card
          onClick={() => set_deployment_type("targeted")}
          className={cn(
            "cursor-pointer transition-all duration-1000 border-2 relative",
            deployment_type === "targeted"
              ? "bg-gradient-to-br from-yellow-500/60 to-transparent border-yellow-500 shadow-md"
              : "hover:border-yellow-400"
          )}
        >
          <CardHeader>
            <div className="flex justify-between items-center">
              <div>
                <CardTitle>Target Deployment</CardTitle>
                <CardDescription>Deploy to a specific peer</CardDescription>
              </div>
              <Badge className="bg-blue-500 text-white">
                {peers.length} Peers
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between mb-3 gap-2">
              <Input
                placeholder="Filter peers..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="max-w-xs"
              />
            </div>

            {/* Table of peers */}
            <div className="overflow-auto max-h-48 max-w-xs border rounded-md">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-full">Peer ID</TableHead>
                    <TableHead className="w-10 text-center">Select</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredPeers.map((peer) => (
                    <TableRow
                      key={peer}
                      className="cursor-pointer"
                      onClick={() => set_peer_id(peer)}
                    >
                      <TableCell className="font-mono">
                        <span title={peer}>{"..." + peer.slice(-9)}</span>
                      </TableCell>
                      <TableCell className="text-center">
                        {peer_id === peer ? (
                          <span className="text-blue-600 font-bold text-lg">
                            ●
                          </span>
                        ) : (
                          <span className="text-muted-foreground text-lg">
                            ○
                          </span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            {/* Muted box showing selected peer */}
            <div className="mt-3 p-2 rounded-md bg-muted text-xs text-muted-foreground">
              Selected Peer ID:{" "}
              <span className="font-mono">
                {deployment_type === "targeted" && peer_id
                  ? "..." + peer_id.slice(-9)
                  : "Not Selected"}
              </span>
            </div>
          </CardContent>
        </Card>

        <Card
          onClick={() => {
            set_deployment_type("non_targeted");
            set_peer_id("");
          }}
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
                {deployment_type === "non_targeted"
                  ? "Network decides"
                  : "Not Selected"}
              </span>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
