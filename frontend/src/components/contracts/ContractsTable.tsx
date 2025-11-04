import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { ContractMetadata } from "@/api/contracts";
import { Loader2, Eye } from "lucide-react";
import { cn } from "@/lib/utils";
import * as React from "react";
import { DidDisplay } from "@/components/contracts/DidDisplay";

function formatContractDuration(start?: string | null, end?: string | null): string {
  const parsedStart = start ? new Date(start) : null;
  const parsedEnd = end ? new Date(end) : null;

  const startValid = parsedStart && !Number.isNaN(parsedStart.getTime());
  const endValid = parsedEnd && !Number.isNaN(parsedEnd.getTime());

  if (!startValid && !endValid) {
    const raw = [start, end].filter(Boolean).join(" -> ");
    return raw || "--";
  }

  const formatter = new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  const labels: string[] = [];
  if (startValid && parsedStart) {
    labels.push(formatter.format(parsedStart));
  } else if (start) {
    labels.push(start);
  }

  if (endValid && parsedEnd) {
    labels.push(formatter.format(parsedEnd));
  } else if (end) {
    labels.push(end);
  }

  const rangeLabel = labels.join(" -> ");

  if (startValid && endValid && parsedStart && parsedEnd) {
    const deltaMs = parsedEnd.getTime() - parsedStart.getTime();
    if (deltaMs > 0) {
      const totalDays = Math.floor(deltaMs / 86_400_000);
      const years = Math.floor(totalDays / 365);
      const months = Math.floor((totalDays % 365) / 30);
      const days = totalDays % 30;

      const summary: string[] = [];
      if (years) summary.push(`${years} year${years === 1 ? "" : "s"}`);
      if (months && summary.length < 2) summary.push(`${months} month${months === 1 ? "" : "s"}`);
      if (days && summary.length < 2) summary.push(`${days} day${days === 1 ? "" : "s"}`);

      if (summary.length === 0) {
        summary.push("< 1 month");
      }

      return `${rangeLabel} (${summary.join(", ")})`;
    }
  }

  return rangeLabel || "--";
}

function getParticipantDid(contract: ContractMetadata, role: "provider" | "requestor") {
  return contract.participants?.[role]?.uri ?? null;
}

function LoadingTablePlaceholder() {
  return (
    <div className="space-y-3">
      {[0, 1, 2].map((key) => (
        <Skeleton key={key} className="h-12 w-full rounded-md" />
      ))}
    </div>
  );
}

export interface ContractsTableProps {
  title: string;
  contracts: ContractMetadata[] | undefined;
  isLoading?: boolean;
  emptyMessage?: string;
  error?: string | null;
  approvingMap?: Record<string, boolean>;
  onApprove?: (contract: ContractMetadata) => void;
  onSelect?: (contract: ContractMetadata) => void;
  showListSource?: boolean;
  listSourceKey?: string;
  canApprove?: (contract: ContractMetadata) => boolean;
}

export function ContractsTable({
  title,
  contracts,
  isLoading,
  emptyMessage,
  error,
  approvingMap,
  onApprove,
  onSelect,
  showListSource,
  listSourceKey,
  canApprove,
}: ContractsTableProps) {
  const hasData = (contracts?.length ?? 0) > 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>{title}</span>
          {hasData ? (
            <Badge variant="outline" className="font-mono text-xs">
              {contracts?.length ?? 0} total
            </Badge>
          ) : null}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading ? <LoadingTablePlaceholder /> : null}

        {!isLoading && error ? (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        ) : null}

        {!isLoading && !error && !hasData ? (
          <div className="grid h-28 place-items-center rounded-md border border-dashed border-muted-foreground/20 text-sm text-muted-foreground">
            {emptyMessage ?? "No contracts to display yet."}
          </div>
        ) : null}

        {!isLoading && !error && hasData ? (
          <div className="space-y-4">
            {contracts?.map((contract) => {
              const approving = Boolean(approvingMap?.[contract.contract_did]);
              const durationLabel = formatContractDuration(
                contract.duration?.start_date,
                contract.duration?.end_date
              );
              const rowSource = listSourceKey
                ? (contract as Record<string, unknown>)[listSourceKey]
                : undefined;
              const canApproveRow =
                Boolean(onApprove) &&
                (typeof canApprove === "function" ? canApprove(contract) : true);
              const requestorDid = getParticipantDid(contract, "requestor");
              const providerDid = getParticipantDid(contract, "provider");

              return (
                <div
                  key={contract.contract_did}
                  className={cn(
                    "rounded-md border border-border/40 bg-muted/5 p-3 transition",
                    onSelect ? "hover:border-primary/60" : ""
                  )}
                >
                    <div className="flex flex-col gap-3">
                      <div className="flex flex-wrap items-center gap-2 text-xs">
                        <span className="text-[11px] uppercase tracking-wide text-muted-foreground/80">
                          Contract DID:
                        </span>
                        <DidDisplay value={contract.contract_did} />
                        <span className="text-[11px] uppercase tracking-wide text-muted-foreground/80">
                          Requester DID:
                        </span>
                        <DidDisplay value={requestorDid} muted />
                        <span className="text-[11px] uppercase tracking-wide text-muted-foreground/80">
                          Provider DID:
                        </span>
                        <DidDisplay value={providerDid} muted />
                        {showListSource && typeof rowSource === "string" ? (
                          <Badge variant="outline" className="uppercase">
                            {rowSource}
                          </Badge>
                        ) : null}
                      </div>
                      <div className="flex flex-wrap items-center gap-2 text-xs">
                        <span className="text-[11px] uppercase tracking-wide text-muted-foreground/80">
                          Duration:
                        </span>
                        <span className="text-xs text-foreground/80">{durationLabel}</span>
                      </div>
                    </div>
                  <div className="mt-2 flex flex-wrap gap-2 md:justify-end">
                    {onApprove && canApproveRow ? (
                      <Button
                        size="sm"
                        onClick={(event) => {
                          event.stopPropagation();
                          onApprove(contract);
                        }}
                        disabled={approving}
                        className="gap-1"
                      >
                        {approving ? (
                          <>
                            <Loader2 className="h-4 w-4 animate-spin" />
                            Approving...
                          </>
                        ) : (
                          "Approve"
                        )}
                      </Button>
                    ) : null}
                    {onSelect ? (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={(event) => {
                          event.stopPropagation();
                          onSelect(contract);
                        }}
                        className="gap-1"
                      >
                        <Eye className="h-4 w-4" />
                        Details
                      </Button>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
