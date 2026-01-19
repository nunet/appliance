"use client";

import { useState, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
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
import { deleteDeployment, getDeployments } from "@/api/deployments";
import { useNavigate } from "react-router-dom";
import { CopyButton } from "../ui/CopyButton";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";

const STATUS_QUERY_MAP: Record<string, string> = {
  submitted: "Submitted",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
};
const TIME_FILTER_MAP: Record<string, string | undefined> = {
  all: undefined,
  "24h": "1d",
  "7d": "7d",
  "30d": "30d",
};

export default function DeploymentsCards() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);
  const toastStyles = {
    className: "text-white [&_*]:!text-white",
    descriptionClassName: "text-white/90",
  };

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [timeFilter, setTimeFilter] = useState<string>("all");
  const [timeOrder, setTimeOrder] = useState<"newest" | "oldest">("newest");
  const [page, setPage] = useState(1);
  const [pageSize] = useState(6); // cards per page

  const statusParam =
    statusFilter === "all"
      ? undefined
      : STATUS_QUERY_MAP[statusFilter] ?? statusFilter;
  const createdAfter = TIME_FILTER_MAP[timeFilter];
  const sortParam = timeOrder === "oldest" ? "created_at" : "-created_at";
  const offset = (page - 1) * pageSize;

  const {
    data,
    isLoading,
  } = useQuery({
    queryKey: ["deployments", page, pageSize, statusParam, timeFilter, timeOrder],
    queryFn: () =>
      getDeployments({
        limit: pageSize,
        offset,
        sort: sortParam,
        status: statusParam,
        created_after: createdAfter,
        status_ordered: statusFilter === "all",
      }),
    staleTime: Infinity, // cache forever
    gcTime: Infinity, // never garbage collect
    refetchInterval: 0, // no auto refetch
    refetchOnWindowFocus: false, // no refresh when tab focuses
  });

  const deployments = data?.deployments || [];

  const getFileDisplayName = (value?: string) => {
    if (!value || typeof value !== "string") return "";
    const parts = value.split(/[\\/]/);
    return parts.pop() || value;
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTargetId) return;
    setDeletingId(deleteTargetId);
    try {
      const res = await deleteDeployment(deleteTargetId);
      toast.success("Deployment deleted", {
        description: res.message || "Deployment removed from DMS.",
        ...toastStyles,
      });
      queryClient.refetchQueries({ queryKey: ["deployments"] });
    } catch (error: any) {
      toast.error("Delete failed", {
        description: error?.response?.data?.message || "An unexpected error occurred",
      });
    } finally {
      setDeletingId(null);
      setDeleteTargetId(null);
    }
  };

  const getStatusRank = (status?: string) => {
    const normalized = (status || "").toLowerCase();
    if (normalized === "submitted") return 0;
    if (normalized === "running") return 1;
    if (normalized === "completed" || normalized === "complete" || normalized === "success") return 2;
    if (normalized === "failed" || normalized === "error") return 3;
    return 4;
  };

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
        // submitted -> running -> completed -> failed
        const rankDiff = getStatusRank(a.status) - getStatusRank(b.status);
        if (rankDiff !== 0) return rankDiff;

        // Then sort by timestamp within status
        const aTime = new Date(a.timestamp).getTime();
        const bTime = new Date(b.timestamp).getTime();
        return timeOrder === "oldest" ? aTime - bTime : bTime - aTime;
      });
  }, [deployments, search, statusFilter, timeOrder]);

  const paginatedData = filteredData;
  const hasNextPage = deployments.length === pageSize;

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
        <Select
          value={timeFilter}
          onValueChange={(val) => {
            setTimeFilter(val);
            setPage(1);
          }}
        >
          <SelectTrigger className="w-[160px]">
            <SelectValue placeholder="Time range" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All time</SelectItem>
            <SelectItem value="24h">Last 24h</SelectItem>
            <SelectItem value="7d">Last 7 days</SelectItem>
            <SelectItem value="30d">Last 30 days</SelectItem>
          </SelectContent>
        </Select>
        <Select
          value={timeOrder}
          onValueChange={(val) => {
            setTimeOrder(val as "newest" | "oldest");
            setPage(1);
          }}
        >
          <SelectTrigger className="w-[150px]">
            <SelectValue placeholder="Order" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="newest">Newest first</SelectItem>
            <SelectItem value="oldest">Oldest first</SelectItem>
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
                        <b>Ensemble:</b>{" "}
                        <span title={d.ensemble_file} className="font-mono">
                          {getFileDisplayName(d.ensemble_file)}
                        </span>
                      </p>
                      <p>
                        <b>Timestamp:</b>{" "}
                        {new Date(d.timestamp).toLocaleString()}
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
                    <Button
                      variant="destructive"
                      size="sm"
                      className="w-full md:w-auto"
                      onClick={() => setDeleteTargetId(d.id)}
                      disabled={deletingId === d.id}
                    >
                      {deletingId === d.id ? "Deleting..." : "Delete"}
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
              Page {page}
            </span>

            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((old) => old + 1)}
              disabled={!hasNextPage}
            >
              Next
            </Button>
          </div>
        </>
      )}

      <Dialog
        open={Boolean(deleteTargetId)}
        onOpenChange={(open) => {
          if (!open && !deletingId) {
            setDeleteTargetId(null);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete deployment?</DialogTitle>
            <DialogDescription>
              This will permanently remove the deployment from DMS.
            </DialogDescription>
          </DialogHeader>
          <div className="text-sm text-muted-foreground">
            Deployment ID:{" "}
            <span className="font-mono break-all">{deleteTargetId}</span>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteTargetId(null)}
              disabled={Boolean(deletingId)}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteConfirm}
              disabled={Boolean(deletingId)}
            >
              {deletingId ? "Deleting..." : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
