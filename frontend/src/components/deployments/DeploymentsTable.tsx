"use client";

import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

import {
  MoreHorizontal,
  ExternalLink,
  Trash2,
  Search,
  RefreshCw,
} from "lucide-react";

import { useNavigate } from "react-router-dom";

import {
  deleteDeployment,
  getDeployments,
} from "@/api/deployments";

import { CopyButton } from "../ui/CopyButton";

import { toast } from "sonner";

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

  const [deletingId, setDeletingId] =
    useState<string | null>(null);

  const [deleteTargetId, setDeleteTargetId] =
    useState<string | null>(null);

  const [search, setSearch] = useState("");

  const [statusFilter, setStatusFilter] =
    useState<string>("all");

  const [timeFilter, setTimeFilter] =
    useState<string>("all");

  const [timeOrder, setTimeOrder] =
    useState<"newest" | "oldest">("newest");

  const [page, setPage] = useState(1);

  const [pageSize] = useState(20);

  // Used only to force a brand new query
  const [refreshKey, setRefreshKey] =
    useState(0);

  const toastStyles = {
    className:
      "text-white [&_*]:!text-white",

    descriptionClassName:
      "text-white/90",
  };

  const statusParam =
    statusFilter === "all"
      ? undefined
      : STATUS_QUERY_MAP[statusFilter] ??
        statusFilter;

  const createdAfter =
    TIME_FILTER_MAP[timeFilter];

  const sortParam =
    timeOrder === "oldest"
      ? "created_at"
      : "-created_at";

  const offset =
    (page - 1) * pageSize;

  const {
    data,
    isLoading,
  } = useQuery({
    queryKey: [
      "deployments",
      refreshKey,
      page,
      pageSize,
      statusParam,
      timeFilter,
      timeOrder,
    ],

    queryFn: () =>
      getDeployments({
        limit: pageSize,
        offset,
        sort: sortParam,
        status: statusParam,
        created_after: createdAfter,
      }),

    staleTime: 0,
    gcTime: 0,

    placeholderData: undefined,

    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    refetchOnMount: true,

    retry: false,
  });

  const deployments =
    isLoading
      ? []
      : (data?.deployments || []);

  // Search ONLY inside current page
  const filteredData = useMemo(() => {
    if (!search.trim()) {
      return deployments;
    }

    return deployments.filter((d: any) => {
      return (
        d.id
          .toLowerCase()
          .includes(
            search.toLowerCase()
          ) ||

        d.ensemble_file
          ?.toLowerCase()
          .includes(
            search.toLowerCase()
          )
      );
    });
  }, [
    deployments,
    search,
  ]);

  const totalCount =
    search.trim()
      ? filteredData.length
      : typeof data?.total === "number"
        ? data.total
        : deployments.length;

  const totalPages = Math.max(
    1,
    Math.ceil(totalCount / pageSize)
  );

  const hasNextPage =
    search.trim()
      ? false
      : typeof data?.has_more === "boolean"
        ? data.has_more
        : page < totalPages;

  const getFileDisplayName = (
    value?: string
  ) => {
    if (
      !value ||
      typeof value !== "string"
    ) {
      return "Unnamed deployment";
    }

    const parts =
      value.split(/[\\/]/);

    return parts.pop() || value;
  };

  const truncateId = (
    id: string
  ) => {
    if (!id) return "";

    return `${id.slice(
      0,
      10
    )}...${id.slice(-6)}`;
  };

  const formatRelativeTime = (
    date: string
  ) => {
    const now = new Date();

    const target =
      new Date(date);

    const diffMs =
      now.getTime() -
      target.getTime();

    const minutes = Math.floor(
      diffMs / 60000
    );

    const hours = Math.floor(
      minutes / 60
    );

    const days = Math.floor(
      hours / 24
    );

    if (minutes < 1) {
      return "just now";
    }

    if (minutes < 60) {
      return `${minutes}m ago`;
    }

    if (hours < 24) {
      return `${hours}h ago`;
    }

    return `${days}d ago`;
  };

  const handleRefresh = () => {
    // Reset everything
    setSearch("");

    // Force brand new query
    setRefreshKey((v) => v + 1);
  };

  const handleDeleteConfirm =
    async () => {
      if (!deleteTargetId) {
        return;
      }

      setDeletingId(
        deleteTargetId
      );

      try {
        const res =
          await deleteDeployment(
            deleteTargetId
          );

        toast.success(
          "Deployment deleted",
          {
            description:
              res.message ||
              "Deployment removed from DMS.",

            ...toastStyles,
          }
        );

        handleRefresh();
      } catch (error: any) {
        toast.error(
          "Delete failed",
          {
            description:
              error?.response?.data
                ?.message ||
              "An unexpected error occurred",
          }
        );
      } finally {
        setDeletingId(null);

        setDeleteTargetId(null);
      }
    };

  const statusColors: Record<
    string,
    string
  > = {
    submitted:
      "bg-blue-500/15 text-blue-300 border border-blue-500/20",

    running:
      "bg-yellow-500/15 text-yellow-300 border border-yellow-500/20",

    completed:
      "bg-green-500/15 text-green-300 border border-green-500/20",

    failed:
      "bg-red-500/15 text-red-300 border border-red-500/20",
  };

  return (
    <div className="space-y-4">

      {/* Top controls */}
      <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">

        <div className="flex flex-1 flex-col gap-3 xl:flex-row xl:items-center">

          {/* Search */}
          <div className="relative w-full max-w-sm">

            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />

            <Input
              placeholder="Search file name or ID within current page..."
              value={search}
              onChange={(e) => {
                setSearch(
                  e.target.value
                );
              }}
              className="pl-9"
              data-testid="deployment-search-input"
            />
          </div>

          {/* Status filters */}
          <div className="flex flex-wrap items-center gap-2">

            <Button
              variant={
                statusFilter ===
                "all"
                  ? "default"
                  : "ghost"
              }
              size="sm"
              className="h-8"
              onClick={() => {
                setStatusFilter(
                  "all"
                );

                setPage(1);
              }}
            >
              All
            </Button>

            <Button
              variant={
                statusFilter ===
                "running"
                  ? "default"
                  : "ghost"
              }
              size="sm"
              className="h-8"
              onClick={() => {
                setStatusFilter(
                  "running"
                );

                setPage(1);
              }}
            >
              Running
            </Button>

            <Button
              variant={
                statusFilter ===
                "completed"
                  ? "default"
                  : "ghost"
              }
              size="sm"
              className="h-8"
              onClick={() => {
                setStatusFilter(
                  "completed"
                );

                setPage(1);
              }}
            >
              Completed
            </Button>

            <Button
              variant={
                statusFilter ===
                "failed"
                  ? "default"
                  : "ghost"
              }
              size="sm"
              className="h-8"
              onClick={() => {
                setStatusFilter(
                  "failed"
                );

                setPage(1);
              }}
            >
              Failed
            </Button>

          </div>
        </div>

        {/* Right controls */}
        <div className="flex flex-wrap items-center gap-2">

          <Select
            value={timeFilter}
            onValueChange={(val) => {
              setTimeFilter(val);

              setPage(1);
            }}
          >
            <SelectTrigger className="h-8 w-[150px]">
              <SelectValue placeholder="Time range" />
            </SelectTrigger>

            <SelectContent>

              <SelectItem value="all">
                All time
              </SelectItem>

              <SelectItem value="24h">
                Last 24h
              </SelectItem>

              <SelectItem value="7d">
                Last 7 days
              </SelectItem>

              <SelectItem value="30d">
                Last 30 days
              </SelectItem>

            </SelectContent>
          </Select>

          <Select
            value={timeOrder}
            onValueChange={(val) => {
              setTimeOrder(
                val as
                  | "newest"
                  | "oldest"
              );

              setPage(1);
            }}
          >
            <SelectTrigger className="h-8 w-[150px]">
              <SelectValue placeholder="Sort order" />
            </SelectTrigger>

            <SelectContent>

              <SelectItem value="newest">
                Newest first
              </SelectItem>

              <SelectItem value="oldest">
                Oldest first
              </SelectItem>

            </SelectContent>
          </Select>

          <Button
            variant="outline"
            size="sm"
            className="h-8"
            onClick={handleRefresh}
          >
            <RefreshCw className="mr-2 h-3.5 w-3.5" />
            Refresh
          </Button>

        </div>
      </div>

      {/* List */}
      {isLoading ? (
        <div className="rounded-lg border p-6 text-sm text-muted-foreground">
          Loading deployments...
        </div>
      ) : filteredData.length === 0 ? (
        <div className="rounded-lg border p-6 text-sm text-muted-foreground">
          No deployments found
        </div>
      ) : (
        <>
          <div className="overflow-hidden rounded-xl border border-border/60 bg-card/30 backdrop-blur-sm">
          {filteredData.map((d: any, index: number) => (
            <div
              key={d.id}
              data-testid="deployment-row"
              data-deployment-id={d.id}
              className={`group rounded-lg border border-border/50 bg-card/40 px-3 py-2 transition-colors hover:bg-muted/30 ${
                index !== filteredData.length - 1
                  ? "mb-2"
                  : ""
              }`}
            >
              <div className="flex items-center justify-between gap-3">

                {/* Left side */}
                <div
                  className="min-w-0 flex-1 cursor-pointer"
                  onClick={() =>
                    navigate(`/deploy/${d.id}`)
                  }
                >
                  <div className="flex min-w-0 items-center gap-2 text-sm">

                    {/* Status */}
                    <span
                      className={`shrink-0 inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                        statusColors[d.status] ||
                        "bg-muted text-muted-foreground"
                      }`}
                    >
                      {d.status}
                    </span>

                    {/* File */}
                    <span
                      className="truncate font-medium text-foreground"
                      title={d.ensemble_file}
                    >
                      {getFileDisplayName(d.ensemble_file)}
                    </span>

                    {/* Secondary info */}
                    <div className="hidden lg:flex items-center gap-2">

                      <span className="opacity-40">•</span>

                      {/* Type */}
                      <span className="shrink-0 text-muted-foreground capitalize">
                        {d.type}
                      </span>

                      <span className="opacity-40">•</span>

                      {/* Time */}
                      <span className="shrink-0 text-muted-foreground">
                        {formatRelativeTime(d.timestamp)}
                      </span>

                      <span className="opacity-40">•</span>

                      {/* ID */}
                      <div
                        className="flex shrink-0 items-center gap-1 font-mono text-muted-foreground"
                        onClick={(e) => {
                          e.stopPropagation();
                        }}
                      >
                        <span title={d.id}>
                          {truncateId(d.id)}
                        </span>

                        <CopyButton text={d.id} />
                      </div>
                    </div>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex shrink-0 items-center gap-1.5">

                  <Button
                    variant="outline"
                    size="sm"
                    className="h-8"
                    onClick={() =>
                      navigate(`/deploy/${d.id}`)
                    }
                  >
                    <ExternalLink className="mr-1.5 h-3.5 w-3.5" />
                    Details
                  </Button>

                  <DropdownMenu>

                    <DropdownMenuTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                      >
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>

                    <DropdownMenuContent align="end">

                      <DropdownMenuItem
                        className="text-red-400 focus:text-red-400"
                        onClick={() =>
                          setDeleteTargetId(d.id)
                        }
                      >
                        <Trash2 className="mr-2 h-4 w-4" />
                        Delete deployment
                      </DropdownMenuItem>
          
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </div>
            </div>
          ))}
          </div>

          {/* Pagination */}
          {!search.trim() && (
            <div
              className="flex items-center justify-between"
              data-testid="deployment-pagination"
            >

              <Button
                variant="outline"
                size="sm"
                disabled={page === 1}
                onClick={() =>
                  setPage((old) =>
                    Math.max(
                      old - 1,
                      1
                    )
                  )
                }
              >
                Previous
              </Button>

              <div className="text-sm text-muted-foreground">
                Page {page} of{" "}
                {totalPages}
              </div>

              <Button
                variant="outline"
                size="sm"
                disabled={!hasNextPage}
                onClick={() =>
                  setPage((old) =>
                    old + 1
                  )
                }
              >
                Next
              </Button>

            </div>
          )}
        </>
      )}

      {/* Delete dialog */}
      <Dialog
        open={Boolean(
          deleteTargetId
        )}
        onOpenChange={(open) => {
          if (
            !open &&
            !deletingId
          ) {
            setDeleteTargetId(
              null
            );
          }
        }}
      >

        <DialogContent>

          <DialogHeader>

            <DialogTitle>
              Delete deployment?
            </DialogTitle>

            <DialogDescription>
              This will permanently
              remove the deployment
              from DMS.
            </DialogDescription>

          </DialogHeader>

          <div className="text-sm text-muted-foreground">

            Deployment ID:{" "}

            <span className="break-all font-mono">
              {deleteTargetId}
            </span>

          </div>

          <DialogFooter>

            <Button
              variant="outline"
              disabled={Boolean(
                deletingId
              )}
              onClick={() =>
                setDeleteTargetId(
                  null
                )
              }
            >
              Cancel
            </Button>

            <Button
              variant="destructive"
              disabled={Boolean(
                deletingId
              )}
              onClick={
                handleDeleteConfirm
              }
            >
              {deletingId
                ? "Deleting..."
                : "Delete"}
            </Button>

          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
