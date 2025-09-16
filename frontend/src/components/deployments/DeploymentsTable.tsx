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

  const {
    data,
    isLoading,
    refetch, // 👈 grab refetch function
  } = useQuery({
    queryKey: ["deployments"],
    queryFn: getDeployments,
    staleTime: Infinity, // cache forever
    gcTime: Infinity, // never garbage collect
    refetchInterval: 0, // no auto refetch
    refetchOnWindowFocus: false, // no refresh when tab focuses
  });

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [page, setPage] = useState(1);
  const [pageSize] = useState(6); // cards per page

  const deployments = data?.deployments || [];

  // Apply search + filter
  const filteredData = useMemo(() => {
    return deployments
      .filter((d: any) => {
        const matchesSearch =
          d.id.toLowerCase().includes(search.toLowerCase()) ||
          d.ensemble_file.toLowerCase().includes(search.toLowerCase());

        const matchesStatus =
          statusFilter === "all" ? true : d.status === statusFilter;

        return matchesSearch && matchesStatus;
      })
      .sort((a: any, b: any) => {
        // 1️⃣ Running always comes first
        if (a.status === "running" && b.status !== "running") return -1;
        if (b.status === "running" && a.status !== "running") return 1;

        // 2️⃣ Then sort by timestamp (descending)
        return (
          new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
        );
      });
  }, [deployments, search, statusFilter]);

  // Pagination
  const totalItems = filteredData.length;
  const totalPages = Math.ceil(totalItems / pageSize);
  const paginatedData = filteredData.slice(
    (page - 1) * pageSize,
    page * pageSize
  );

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
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1); // reset to page 1 on search
          }}
          className="max-w-sm"
        />
        <Select
          value={statusFilter}
          onValueChange={(val) => {
            setStatusFilter(val);
            setPage(1); // reset to page 1 on filter change
          }}
        >
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

      {/* Cards list */}
      {isLoading ? (
        <p className="text-muted-foreground">Loading deployments...</p>
      ) : filteredData.length === 0 ? (
        <p className="text-muted-foreground">No deployments found</p>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4">
            {paginatedData.map((d: any) => (
              <Card key={d.id} className="hover:shadow-md transition-shadow">
                {/* Responsive layout: col on mobile, row on desktop */}
                <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 p-4">
                  {/* Left side: ID + details */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <CopyButton text={d.id} className="mr-2" />
                      <CardTitle className="truncate font-mono text-base">
                        {d.id}
                      </CardTitle>
                    </div>
                    <div className="text-sm text-muted-foreground mt-1 space-y-0.5">
                      <p>
                        <b>Type:</b> {d.type}
                      </p>
                      <p>
                        <b>Ensemble:</b> {d.ensemble_file}
                      </p>
                      <p>
                        <b>Timestamp:</b> {d.timestamp}
                      </p>
                    </div>
                  </div>

                  {/* Right side: status + actions */}
                  <div className="flex flex-col md:items-end gap-2 shrink-0">
                    <span
                      className={`px-2 py-1 rounded-full text-xs font-medium self-start md:self-end ${
                        statusColors[d.status] || "bg-gray-100 text-gray-800"
                      }`}
                    >
                      {d.status.toUpperCase()}
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full md:w-auto mt-2 md:mt-8"
                      onClick={() => navigate(`/deploy/${d.id}`)}
                    >
                      View Details
                    </Button>
                  </div>
                </div>
              </Card>
            ))}
          </div>

          {/* Pagination Controls */}
          <div className="flex justify-between items-center mt-4">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((old) => Math.max(old - 1, 1))}
              disabled={page === 1}
            >
              Previous
            </Button>

            <span className="text-sm text-gray-600">
              Page {page} of {totalPages}
            </span>

            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((old) => Math.min(old + 1, totalPages))}
              disabled={page === totalPages}
            >
              Next
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
