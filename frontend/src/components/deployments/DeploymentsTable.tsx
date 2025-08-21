"use client";

import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { getDeployments } from "@/api/deployments";
import { useNavigate } from "react-router-dom";
import { CopyButton } from "../ui/CopyButton";

export default function DeploymentsCards() {
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ["deployments"],
    queryFn: getDeployments,
    refetchInterval: 10000,
    staleTime: Infinity,
  });

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const deployments = data?.deployments || [];

  // Apply search + filter
  const filteredData = useMemo(() => {
    return deployments.filter((d: any) => {
      const matchesSearch =
        d.id.toLowerCase().includes(search.toLowerCase()) ||
        d.ensemble_file.toLowerCase().includes(search.toLowerCase());

      const matchesStatus =
        statusFilter === "all" ? true : d.status === statusFilter;

      return matchesSearch && matchesStatus;
    });
  }, [deployments, search, statusFilter]);

  // Status badge color mapping
  const statusColors: Record<string, string> = {
    submitted: "bg-blue-100 text-blue-800",
    running: "bg-yellow-100 text-yellow-800",
    completed: "bg-green-100 text-green-800",
    failed: "bg-red-100 text-red-800",
  };

  return (
    <div className="space-y-4">
      {/* Search + filter */}
      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
        <Input
          placeholder="Search by ID or file..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-sm"
        />
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Filter by status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="submitted">Submitted</SelectItem>
            <SelectItem value="running">Running</SelectItem>
            <SelectItem value="completed">Completed</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Cards grid */}
      {isLoading ? (
        <p className="text-muted-foreground">Loading deployments...</p>
      ) : filteredData.length === 0 ? (
        <p className="text-muted-foreground">No deployments found</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredData.map((d: any) => (
            <Card key={d.id} className="hover:shadow-lg transition-shadow">
              <CardHeader className="flex items-center justify-between gap-2 flex-wrap">
                <CardTitle className="truncate max-w-[180px] sm:max-w-full font-mono">
                  <CopyButton text={d.id} className={"mr-2"} />
                  <span title={d.id}>{d.id}</span>
                </CardTitle>

                <span
                  className={`px-2 py-1 rounded-full text-xs font-medium ${
                    statusColors[d.status] || "bg-gray-100 text-gray-800"
                  }`}
                >
                  {d.status.toUpperCase()}
                </span>
              </CardHeader>
              <CardContent className="space-y-1 text-sm text-muted-foreground">
                <p>
                  <b>Type:</b> {d.type}
                </p>
                <p>
                  <b>Ensemble:</b> {d.ensemble_file}
                </p>
                <p>
                  <b>Timestamp:</b> {d.timestamp}
                </p>
              </CardContent>
              <CardFooter>
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full"
                  onClick={() => navigate(`/deploy/${d.id}`)}
                >
                  View Details
                </Button>
              </CardFooter>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
