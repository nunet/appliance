import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/components/ui/data-table";
import { Input } from "@/components/ui/input";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { getDeployments } from "../../api/deployments";
import { Link, useNavigate } from "react-router-dom";

// Define table columns
const columns: ColumnDef<any>[] = [
  {
    accessorKey: "id",
    header: "ID",
    cell: ({ row }) => (
      <Link
        to={`/deploy/${row.original.id}`}
        className="text-blue-600 hover:underline"
      >
        <span className="truncate max-w-[200px]">{row.original.id}</span>
      </Link>
    ),
  },
  {
    accessorKey: "status",
    header: "Status",
  },
  {
    accessorKey: "type",
    header: "Type",
  },
  {
    accessorKey: "timestamp",
    header: "Timestamp",
  },
  {
    accessorKey: "ensemble_file",
    header: "Ensemble File",
  },
];

export default function DeploymentsTable() {
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ["deployments"],
    queryFn: getDeployments,
    refetchInterval: 10000 * 10, // auto-refresh every 10s
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

  return (
    <Card className="w-full">
      <CardHeader>
        <div className="flex items-center gap-3 mt-2">
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
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-muted-foreground">Loading deployments...</p>
        ) : data?.count === 0 ? (
          <p className="text-muted-foreground">No deployments found</p>
        ) : (
          <DataTable
            columns={columns}
            data={filteredData}
            onRowClick={(row) => navigate(`/deploy/${row.original.id}`)}
          />
        )}
      </CardContent>
    </Card>
  );
}
