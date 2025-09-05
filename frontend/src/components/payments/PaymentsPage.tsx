"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getPaymentsConfig,
  getPaymentsList,
  DmsPaymentItem,
  reportToDms,
} from "@/api/api";
import { Card, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { CopyButton } from "@/components/ui/CopyButton";
import { CheckCheckIcon, Loader2, RefreshCw, Send, Wallet } from "lucide-react";
import { sendNTX } from "@/lib/sendNTX";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { useWallet } from "./useWallet";


function shorten(addr: string) {
  if (!addr) return "";
  return addr.slice(0, 6) + "…" + addr.slice(-4);
}

type StatusFilter = "all" | "paid" | "unpaid";

export default function PaymentsPage() {
  const [search, setSearch] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [sending, setSending] = useState<Record<string, boolean>>({});
  const [sent, setSent] = useState<Record<string, string>>({});
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");

  const { address, connect, isConnected } = useWallet();

  const cfgQ = useQuery({
    queryKey: ["payments", "config"],
    queryFn: getPaymentsConfig,
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
  });

  const listQ = useQuery({
    queryKey: ["payments", "list"],
    queryFn: getPaymentsList,
    refetchInterval: autoRefresh ? 30000 : false,
    refetchOnWindowFocus: false,
  });

  const config = cfgQ.data;
  const list = listQ.data;
  const items = list?.items ?? [];

  const filtered = useMemo(() => {
    const term = search.toLowerCase();
    return items.filter((p) => {
      const matchesSearch =
        !term ||
        p.unique_id.toLowerCase().includes(term) ||
        p.to_address.toLowerCase().includes(term) ||
        p.status.toLowerCase().includes(term);
      const matchesStatus =
        statusFilter === "all" ? true : p.status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  }, [items, search, statusFilter]);

  async function handlePay(p: DmsPaymentItem) {
    if (!config) {
      toast.error("Missing token config");
      return;
    }
    if (p.status === "paid") {
      toast.info("This item is already marked paid");
      return;
    }

    // Require wallet connection first
    if (!isConnected) {
      try {
        await connect();
      } catch (err: any) {
        toast.error("Connect wallet to pay", {
          description: err?.message,
        });
        return;
      }
    }

    try {
      setSending((s) => ({ ...s, [p.unique_id]: true }));
      const { token_address, token_decimals, chain_id, explorer_base_url } =
        config;

      // Send native or ERC-20 depending on token_address
      const { hash } = await sendNTX({
        tokenAddress: token_address,
        to: p.to_address,
        amountHuman: p.amount,
        decimals: token_decimals,
        chainIdWanted: chain_id,
      });

      setSent((s) => ({ ...s, [p.unique_id]: hash }));

      // Report to backend -> DMS
      await reportToDms({
        tx_hash: hash,
        to_address: p.to_address,
        amount: p.amount,
        payment_provider: p.unique_id,
      });

      toast.success("Transaction sent", {
        description: explorer_base_url ? `Tx: ${hash}` : undefined,
      });

      listQ.refetch();
    } catch (err: any) {
      console.error(err);
      toast.error("Payment failed", {
        description: err?.message ?? "Something went wrong",
      });
    } finally {
      setSending((s) => ({ ...s, [p.unique_id]: false }));
    }
  }

  const isLoading = cfgQ.isLoading || listQ.isLoading;

  return (
    <div className="flex flex-1 flex-col">
      <div className="container/main flex flex-1 flex-col gap-2">
        <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6 px-4 md:px-6">
          {/* Header row */}
          <div className="flex flex-col md:flex-row md:items-center gap-3">
            <div className="flex items-center gap-2">
              <Wallet className="h-5 w-5" />
              <h2 className="text-lg font-semibold">Payments</h2>

              {!!list && (
                <div className="flex items-center gap-2 ml-2">
                  {/* Clickable tags that filter */}
                  <Badge
                    role="button"
                    tabIndex={0}
                    onClick={() => setStatusFilter("all")}
                    onKeyDown={(e) => e.key === "Enter" && setStatusFilter("all")}
                    className={cn(
                      "cursor-pointer select-none",
                      statusFilter === "all" && "ring-2 ring-primary"
                    )}
                    variant="secondary"
                    title="Show all"
                  >
                    total {list.total_count}
                  </Badge>

                  <Badge
                    role="button"
                    tabIndex={0}
                    onClick={() => setStatusFilter("paid")}
                    onKeyDown={(e) => e.key === "Enter" && setStatusFilter("paid")}
                    className={cn(
                      "cursor-pointer select-none bg-green-100 text-green-800 border border-green-200",
                      statusFilter === "paid" && "ring-2 ring-green-500"
                    )}
                    title="Show paid only"
                  >
                    paid {list.paid_count}
                  </Badge>

                  <Badge
                    role="button"
                    tabIndex={0}
                    onClick={() => setStatusFilter("unpaid")}
                    onKeyDown={(e) => e.key === "Enter" && setStatusFilter("unpaid")}
                    className={cn(
                      "cursor-pointer select-none bg-yellow-100 text-yellow-800 border border-yellow-200",
                      statusFilter === "unpaid" && "ring-2 ring-yellow-500"
                    )}
                    title="Show unpaid only"
                  >
                    unpaid {list.unpaid_count}
                  </Badge>
                </div>
              )}
            </div>

            <div className="flex items-center gap-2 md:ml-auto">
              <Input
                placeholder="Search by id address or status"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-[240px]"
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() => listQ.refetch()}
                disabled={listQ.isFetching}
              >
                {listQ.isFetching ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Refreshing
                  </>
                ) : (
                  <>
                    <RefreshCw className="mr-2 h-4 w-4" /> Refresh
                  </>
                )}
              </Button>
              <Separator orientation="vertical" className="h-6" />
              <div className="flex items-center gap-2">
                <Switch
                  id="auto-refresh"
                  checked={autoRefresh}
                  onCheckedChange={setAutoRefresh}
                />
                <Label htmlFor="auto-refresh" className="text-sm">
                  Auto refresh
                </Label>
              </div>
            </div>
          </div>

          {/* Content */}
          {isLoading ? (
            <div className="grid grid-cols-1 gap-4">
              {Array.from({ length: 3 }).map((_, i) => (
                <Card key={i} className="p-4">
                  <div className="h-6 w-40 bg-muted animate-pulse rounded mb-2" />
                  <div className="h-4 w-64 bg-muted animate-pulse rounded mb-1" />
                  <div className="h-4 w-48 bg-muted animate-pulse rounded mb-4" />
                  <div className="h-9 w-28 bg-muted animate-pulse rounded" />
                </Card>
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <Card className="p-4">
              <div className="text-muted-foreground">Try clearing the filter or search</div>
            </Card>
          ) : (
            <div className="grid grid-cols-1 gap-3">
              {filtered.map((p) => {
                const isSending = !!sending[p.unique_id];
                const txHash = sent[p.unique_id];
                const explorer =
                  config?.explorer_base_url && (txHash || p.tx_hash)
                    ? `${config.explorer_base_url!.replace(/\/$/, "")}/tx/${txHash || p.tx_hash}`
                    : null;

                return (
                  <Card key={p.unique_id} className="hover:shadow-md transition">
                    <CardHeader className="py-3">
                      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
                        {/* Left: single wrapping line of details (+ optional last tx line) */}
                        <div className="flex-1 min-w-0">
                          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 min-w-0">
                            <div className="flex items-center gap-2 min-w-0">
                              <CopyButton text={p.unique_id} className="mr-1" />
                              <span
                                className="truncate max-w-[180px] md:max-w-[280px] font-mono text-sm"
                                title={p.unique_id}
                              >
                                {p.unique_id}
                              </span>
                            </div>

                            <Separator orientation="vertical" className="hidden md:inline-flex h-4" />

                            <div className="flex items-center gap-2 min-w-0">
                              <span className="text-xs text-muted-foreground">To</span>
                              <code
                                className="bg-muted px-2 py-0.5 rounded truncate max-w-[200px] md:max-w-[320px]"
                                title={p.to_address}
                              >
                                {p.to_address}
                              </code>
                              <CopyButton text={p.to_address} />
                            </div>

                            <Separator orientation="vertical" className="hidden md:inline-flex h-4" />

                            <div className="flex items-center gap-2">
                              <span className="text-xs text-muted-foreground">Amount</span>
                              <code className="bg-muted px-2 py-0.5 rounded text-green-600">
                                {config?.token_symbol ?? "NTX"} {p.amount}
                              </code>
                            </div>
                          </div>

                          {(txHash || p.tx_hash) && (
                            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                              <span className="font-medium text-foreground">Last TX</span>
                              <code className="bg-muted px-2 py-0.5 rounded">
                                {shorten(txHash || p.tx_hash)}
                              </code>
                              {explorer && (
                                <a
                                  href={explorer}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="text-primary hover:underline"
                                >
                                  View on explorer
                                </a>
                              )}
                            </div>
                          )}
                        </div>

                        {/* Right: Status + Action stacked, compact */}
                        <div className="flex flex-col items-start md:items-end gap-2 shrink-0">
                          <Badge
                            variant="outline"
                            className={cn(
                              "uppercase",
                              p.status === "paid"
                                ? "bg-green-100 text-green-800 border-green-200"
                                : "bg-yellow-100 text-yellow-800 border-yellow-200"
                            )}
                          >
                            {p.status.toUpperCase()}
                          </Badge>

                          <Button
                            size="sm"
                            className="w-full md:w-auto"
                            onClick={() => handlePay(p)}
                            disabled={
                              isSending || p.status === "paid" || !config || !isConnected
                            }
                            title={!isConnected ? "Connect wallet to pay" : undefined}
                          >
                            {isSending ? (
                              <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                Sending…
                              </>
                            ) : p.status === "unpaid" ? (
                              <>
                                <Send className="mr-2 h-4 w-4" />
                                Pay Now
                              </>
                            ) : (
                              <>
                                <CheckCheckIcon className="mr-2 h-4 w-4" />
                                Paid
                              </>
                            )}
                          </Button>

                          {!isConnected && (
                            <span className="text-xs text-muted-foreground">
                              Connect wallet to pay
                            </span>
                          )}
                        </div>
                      </div>
                    </CardHeader>
                  </Card>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
