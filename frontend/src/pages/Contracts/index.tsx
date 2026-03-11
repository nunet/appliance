import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { AxiosError } from "axios";
import { ContractListView, ContractMetadata, ContractTerminatePayload, contractsApi, extractHostDid } from "@/api/contracts";
import { getDmsStatus } from "@/api/api";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Loader2, Search, RefreshCw, Plus } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { ContractsTable } from "@/components/contracts/ContractsTable";
import { ContractDetailsDrawer } from "@/components/contracts/ContractDetailsDrawer";
import { toast } from "sonner";

const INCOMING_STATES = new Set<ContractMetadata["current_state"]>(["DRAFT"]);
const SIGNED_STATES = new Set<ContractMetadata["current_state"]>(["ACCEPTED", "APPROVED", "SIGNED"]);

const FILTER_TABS: Array<{ view: ContractListView; label: string; description: string }> = [
  {
    view: "all",
    label: "All",
    description: "Every contract that this appliance can access.",
  },
  {
    view: "incoming",
    label: "Incoming",
    description: "Draft contracts waiting for acceptance or approval.",
  },
  {
    view: "outgoing",
    label: "Outgoing",
    description: "Contracts created from this appliance.",
  },
  {
    view: "active",
    label: "Signed",
    description: "Accepted or signed contracts that no longer require approval.",
  },
];

function extractContractDid(entry: unknown): string | null {
  if (!entry || typeof entry !== "object") {
    return null;
  }

  const record = entry as Record<string, unknown>;
  const keys = ["contract_did", "ContractDID", "contractDid", "contract_id", "ContractID"];

  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim().length > 0) {
      return value.trim();
    }
  }

  return null;
}

function extractContractState(entry: unknown): string | null {
  if (!entry || typeof entry !== "object") {
    return null;
  }

  const record = entry as Record<string, unknown>;
  const keys = ["current_state", "CurrentState", "state", "State"];

  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim().length > 0) {
      return value.trim().toUpperCase();
    }
  }

  return null;
}

function extractErrorMessage(error: unknown): string {
  if (error && typeof error === "object") {
    if ((error as AxiosError).isAxiosError) {
      const axiosError = error as AxiosError;
      const payload = axiosError.response?.data as { detail?: unknown; message?: string } | undefined;
      if (typeof payload === "string") {
        return payload;
      }
      if (payload?.detail) {
        if (typeof payload.detail === "string") {
          return payload.detail;
        }
        if (typeof (payload.detail as { message?: string }).message === "string") {
          return (payload.detail as { message: string }).message;
        }
      }
      if (typeof payload?.message === "string") {
        return payload.message;
      }
      return axiosError.message;
    }
    if (error instanceof Error) {
      return error.message;
    }
  }
  return "Unexpected error";
}

function matchesStatus(contract: ContractMetadata, filter: ContractListView): boolean {
  if (filter === "incoming") {
    if (contract.list_view && contract.list_view !== "incoming") {
      return false;
    }
    return INCOMING_STATES.has(contract.current_state);
  }
  if (filter === "outgoing") {
    return contract.list_view === "outgoing";
  }
  if (filter === "active") {
    return SIGNED_STATES.has(contract.current_state);
  }
  return true;
}

function matchesSearch(contract: ContractMetadata, query: string): boolean {
  if (!query) {
    return true;
  }
  const lower = query.toLowerCase();
  if (contract.contract_did.toLowerCase().includes(lower)) {
    return true;
  }
  const requestor = contract.participants?.requestor?.uri?.toLowerCase() ?? "";
  const provider = contract.participants?.provider?.uri?.toLowerCase() ?? "";
  return requestor.includes(lower) || provider.includes(lower);
}

function canApproveContract(contract: ContractMetadata, machineDid?: string): boolean {
  if (contract.current_state !== "DRAFT") {
    return false;
  }
  const normalizedMachineDid = machineDid?.trim().toLowerCase();
  if (!normalizedMachineDid) {
    return true;
  }
  const requestor = contract.participants?.requestor?.uri?.trim().toLowerCase();
  if (!requestor) {
    return true;
  }
  return requestor !== normalizedMachineDid;
}

export default function ContractsPage(): JSX.Element {
  const [statusFilter, setStatusFilter] = React.useState<ContractListView>("all");
  const [searchValue, setSearchValue] = React.useState("");
  const [selectedContract, setSelectedContract] = React.useState<ContractMetadata | null>(null);
  const [detailsOpen, setDetailsOpen] = React.useState(false);
  const selectedHostDid = React.useMemo(() => extractHostDid(selectedContract), [selectedContract]);

  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const contractsQuery = useQuery({
    queryKey: ["contracts", "all"],
    queryFn: ({ signal }) => contractsApi.getContracts("all", signal),
    refetchOnWindowFocus: false,
  });
  const dmsStatusQuery = useQuery({
    queryKey: ["dms", "status", "contracts", "list"],
    queryFn: getDmsStatus,
    staleTime: 1000 * 60 * 5,
    refetchOnWindowFocus: false,
  });
  const cachedDashboardInfo = queryClient.getQueryData<{ dms_did?: string }>(["apiData"]);
  const machineDid = dmsStatusQuery.data?.dms_did ?? cachedDashboardInfo?.dms_did ?? "";
  const machineDidLower = machineDid.trim().toLowerCase();

  const allContracts = React.useMemo<ContractMetadata[]>(() => {
    const baseContracts = contractsQuery.data?.contracts ?? [];
    const raw = contractsQuery.data?.raw as Record<string, unknown> | null | undefined;
    const overrides = new Map<string, string>();

    const register = (entries: unknown[]) => {
      for (const entry of entries) {
        const did = extractContractDid(entry);
        if (!did) {
          continue;
        }
        const state = extractContractState(entry);
        if (!state || state === "UNKNOWN") {
          continue;
        }
        const current = overrides.get(did);
        if (!current) {
          overrides.set(did, state);
          continue;
        }
        if ((current === "UNKNOWN" && state !== "UNKNOWN") || (current === "DRAFT" && state !== "DRAFT")) {
          overrides.set(did, state);
        }
      }
    };

    const rawSections = raw as any;
    const incomingEntries = Array.isArray(rawSections?.incoming?.contracts)
      ? (rawSections.incoming.contracts as unknown[])
      : [];
    const activeEntries = Array.isArray(rawSections?.active?.contracts)
      ? (rawSections.active.contracts as unknown[])
      : [];
    const outgoingEntries = Array.isArray(rawSections?.outgoing?.contracts)
      ? (rawSections.outgoing.contracts as unknown[])
      : [];

    register(incomingEntries);
    register(activeEntries);
    register(outgoingEntries);

    return baseContracts.map((contract) => {
      const overrideState = overrides.get(contract.contract_did);
      if (!overrideState || overrideState === contract.current_state) {
        return contract;
      }
      return {
        ...contract,
        current_state: overrideState as ContractMetadata["current_state"],
      };
    });
  }, [contractsQuery.data]);

  const incomingCount = React.useMemo(
    () => allContracts.filter((contract) => matchesStatus(contract, "incoming")).length,
    [allContracts],
  );
  const outgoingCount = React.useMemo(
    () => allContracts.filter((contract) => matchesStatus(contract, "outgoing")).length,
    [allContracts],
  );
  const signedCount = React.useMemo(
    () => allContracts.filter((contract) => matchesStatus(contract, "active")).length,
    [allContracts],
  );

  const filteredContracts = React.useMemo(() => {
    const query = searchValue.trim().toLowerCase();
    return allContracts.filter(
      (contract) => matchesStatus(contract, statusFilter) && matchesSearch(contract, query),
    );
  }, [allContracts, statusFilter, searchValue]);

  const listError = contractsQuery.error ? extractErrorMessage(contractsQuery.error) : null;
  const isInitialLoading = contractsQuery.isLoading;
  const isRefreshing = contractsQuery.isFetching && !contractsQuery.isLoading;

  const contractStateQuery = useQuery({
    queryKey: ["contracts", selectedContract?.contract_did, "state", selectedHostDid],
    queryFn: ({ signal }) =>
      contractsApi.getContractState(selectedContract!.contract_did, {
        hostDid: selectedHostDid ?? undefined,
        signal,
      }),
    enabled: Boolean(detailsOpen && selectedContract),
  });

  const [approvingId, setApprovingId] = React.useState<string | null>(null);
  const approveMutation = useMutation({
    mutationFn: (contractDid: string) => contractsApi.approveContract({ contract_did: contractDid }),
    onMutate: (contractDid) => {
      setApprovingId(contractDid);
    },
    onSuccess: (data, contractDid) => {
      toast.success("Contract approval submitted", {
        description: data.message ?? `Approval request sent for ${contractDid}.`,
      });
      queryClient.invalidateQueries({ queryKey: ["contracts"] });
      queryClient.invalidateQueries({ queryKey: ["contracts", contractDid, "state"] });
    },
    onError: (error, contractDid) => {
      toast.error(`Failed to approve ${contractDid}`, {
        description: extractErrorMessage(error),
      });
    },
    onSettled: () => {
      setApprovingId(null);
    },
  });

  const [terminatingId, setTerminatingId] = React.useState<string | null>(null);
  const terminateMutation = useMutation({
    mutationFn: (payload: ContractTerminatePayload) => contractsApi.terminateContract(payload),
    onMutate: (payload) => {
      setTerminatingId(payload.contract_did);
    },
    onSuccess: (data, payload) => {
      toast.success("Termination requested", {
        description: data.message ?? `Termination dispatched for ${payload.contract_did}.`,
      });
      queryClient.invalidateQueries({ queryKey: ["contracts"] });
      queryClient.invalidateQueries({ queryKey: ["contracts", payload.contract_did, "state"] });
    },
    onError: (error, payload) => {
      toast.error(`Failed to terminate ${payload.contract_did}`, {
        description: extractErrorMessage(error),
      });
    },
    onSettled: () => {
      setTerminatingId(null);
    },
  });

  const handleApprove = React.useCallback(
    (contract: ContractMetadata) => {
      approveMutation.mutate(contract.contract_did);
    },
    [approveMutation],
  );

  const handleSelect = React.useCallback((contract: ContractMetadata) => {
    setSelectedContract(contract);
    setDetailsOpen(true);
  }, []);

  const handleDetailsOpenChange = React.useCallback((open: boolean) => {
    setDetailsOpen(open);
    if (!open) {
      setSelectedContract(null);
    }
  }, []);

  const handleTerminate = React.useCallback(
    (payload: ContractTerminatePayload) => {
      terminateMutation.mutate(payload);
    },
    [terminateMutation],
  );

  const canApproveSelf = React.useCallback(
    (contract: ContractMetadata) => canApproveContract(contract, machineDidLower),
    [machineDidLower],
  );

  return (
    <div className="flex flex-1 flex-col">
      <div className="container/main flex flex-1 flex-col gap-2">
        <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
          <div className="grid grid-cols-1 gap-4 px-4 lg:grid-cols-3 lg:px-6 items-start">
            <Card className="lg:col-span-3 px-3 py-4">
              <CardHeader className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between px-0">
                <div className="space-y-1">
                  <CardTitle className="text-2xl md:text-3xl">Contracts</CardTitle>
                  <CardDescription>
                    Search by DID, filter by lifecycle, and take action directly from the overview.
                  </CardDescription>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline" className="font-mono text-xs">
                    {filteredContracts.length} shown
                  </Badge>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => contractsQuery.refetch()}
                    disabled={isRefreshing}
                    className="gap-2"
                  >
                    {isRefreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                    Refresh
                  </Button>
                  <Button
                    className="gap-2 bg-emerald-500 text-white hover:bg-emerald-500/90"
                    onClick={() => navigate("/contracts/new")}
                  >
                    <Plus className="h-4 w-4" />
                    New Contract
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-4 px-0 pb-0">
                <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                  <div className="relative w-full md:max-w-sm">
                    <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      value={searchValue}
                      onChange={(event) => setSearchValue(event.target.value)}
                      placeholder="Search by contract DID or participant DID"
                      className="pl-10"
                    />
                  </div>
                  <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                    <Badge variant="secondary" className="gap-1">
                      All
                      <span className="font-mono">{allContracts.length}</span>
                    </Badge>
                    <Badge variant="secondary" className="gap-1">
                      Incoming
                      <span className="font-mono">{incomingCount}</span>
                    </Badge>
                    <Badge variant="secondary" className="gap-1">
                      Outgoing
                      <span className="font-mono">{outgoingCount}</span>
                    </Badge>
                    <Badge variant="secondary" className="gap-1">
                      Signed
                      <span className="font-mono">{signedCount}</span>
                    </Badge>
                  </div>
                </div>

                <Tabs value={statusFilter} onValueChange={(value) => setStatusFilter(value as ContractListView)}>
                  <TabsList className="w-full justify-start overflow-x-auto">
                    {FILTER_TABS.map((tab) => (
                      <TabsTrigger key={tab.view} value={tab.view} className="px-4 py-2 text-sm">
                        {tab.label}
                      </TabsTrigger>
                    ))}
                  </TabsList>
                </Tabs>

                <ContractsTable
                  title="Contracts"
                  contracts={filteredContracts}
                  isLoading={isInitialLoading}
                  emptyMessage="No contracts match your filters yet."
                  error={listError}
                  approvingMap={approvingId ? { [approvingId]: true } : undefined}
                  onApprove={handleApprove}
                  onSelect={handleSelect}
                  canApprove={canApproveSelf}
                  showListSource={statusFilter === "all"}
                  listSourceKey="list_view"
                />
              </CardContent>
            </Card>
          </div>
        </div>
      </div>

      <ContractDetailsDrawer
        open={detailsOpen}
        onOpenChange={handleDetailsOpenChange}
        baseContract={selectedContract}
        state={contractStateQuery.data ?? null}
        isLoading={contractStateQuery.isFetching && Boolean(selectedContract)}
        error={contractStateQuery.error ? extractErrorMessage(contractStateQuery.error) : null}
        onRefresh={selectedContract ? () => contractStateQuery.refetch() : undefined}
        onTerminate={handleTerminate}
        isTerminating={terminatingId === selectedContract?.contract_did}
      />
    </div>
  );
}
