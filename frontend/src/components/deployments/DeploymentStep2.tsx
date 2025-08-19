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

export default function DeploymentStepTwo() {
  const [selected, setSelected] = useState<string | null>(null);
  const [selectedPeer, setSelectedPeer] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const peers = [
    { id: "peer-1" },
    { id: "peer-3" },
    { id: "peer-2" },
    { id: "peer-10" },
    { id: "peer-20" },
    { id: "peer-12" },
  ];

  const filteredPeers = peers.filter((p) =>
    p.id.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="flex flex-col items-center w-full">
      <h2 className="text-2xl font-semibold mb-6">Deployment Target</h2>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full max-w-6xl">
        {/* Card 1: Deploy locally */}
        <Card
          onClick={() => {
            setSelected("local");
            setSelectedPeer("current-peer-id-123");
          }}
          className={cn(
            "cursor-pointer transition-all duration-500 border-2 relative",
            selected === "local"
              ? "bg-gradient-to-r from-green-500/60 to-transparent border-green-500 shadow-md"
              : "hover:border-blue-400"
          )}
        >
          <CardHeader>
            <CardTitle>Deploy Locally</CardTitle>
            <CardDescription>Deploy to this appliance</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="p-2 rounded-md bg-muted text-xs text-muted-foreground">
              Current Peer ID:{" "}
              <span className="font-mono">
                {selected === "local" ? selectedPeer : "Not Selected"}
              </span>
            </div>
          </CardContent>
        </Card>

        {/* Card 2: Target deployment */}
        <Card
          onClick={() => setSelected("target")}
          className={cn(
            "cursor-pointer transition-all duration-500 border-2 relative",
            selected === "target"
              ? "bg-gradient-to-r from-green-500/60 to-transparent border-green-500 shadow-md"
              : "hover:border-blue-400"
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
                      key={peer.id}
                      className="cursor-pointer"
                      onClick={() => setSelectedPeer(peer.id)}
                    >
                      <TableCell className="font-mono">{peer.id}</TableCell>
                      <TableCell className="text-center">
                        {selectedPeer === peer.id ? (
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
                {selected === "target" && selectedPeer
                  ? selectedPeer
                  : "Not Selected"}
              </span>
            </div>
          </CardContent>
        </Card>

        {/* Card 3: Non-targeted deployment */}
        <Card
          onClick={() => {
            setSelected("non-target");
            setSelectedPeer(null);
          }}
          className={cn(
            "cursor-pointer transition-all duration-500 border-2 relative",
            selected === "non-target"
              ? "bg-gradient-to-r from-green-500/60 to-transparent border-green-500 shadow-md"
              : "hover:border-blue-400"
          )}
        >
          <CardHeader>
            <CardTitle>Non-Targeted Deployment</CardTitle>
            <CardDescription>Let the network decide</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="p-2 rounded-md bg-muted text-xs text-muted-foreground">
              Selection:{" "}
              <span className="font-mono">
                {selected === "non-target" ? "Network decides" : "Not Selected"}
              </span>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
