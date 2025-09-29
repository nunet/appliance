"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getPaymentsConfig,
  getPaymentsList,
  DmsPaymentItem,
  reportToDms,
} from "@/api/api";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from "@/components/ui/card";
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

function middleEllipsis(value: string, head = 6, tail = 4) {
  if (!value) return "";
  if (value.length <= head + tail + 3) {
    return value;
  }

  return `${value.slice(0, head)}...${value.slice(-tail)}`;
}

function shorten(addr: string) {
  return middleEllipsis(addr);
}

type StatusFilter = "all" | "paid" | "unpaid";

export default function PaymentsPage() {
  const [search, setSearch] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [sending, setSending] = useState<Record<string, boolean>>({});
  const [sent, setSent] = useState<Record<string, string>>({});
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");

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

  const errorToastStyles = {
    className: "text-white [&_*]:!text-white",
    descriptionClassName: "text-white/80",
    style: { color: "#fff", "--normal-text": "#fff", "--error-text": "#fff" },
  };

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
      toast.error("Missing token config", errorToastStyles);
      return;
    }
    if (p.status === "paid") {
      toast.info("This item is already marked paid");
      return;
    }

    try {
      setSending((s) => ({ ...s, [p.unique_id]: true }));
      const { token_address, token_decimals, chain_id, explorer_base_url } =
        config;

      const { hash } = await sendNTX({
        tokenAddress: token_address,
        to: p.to_address,
        amountHuman: p.amount,
        decimals: token_decimals,
        chainIdWanted: chain_id,
      });

      setSent((s) => ({ ...s, [p.unique_id]: hash }));

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
        ...errorToastStyles,
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
                      "cursor-pointer select-none bg-yellow-100 text-yellow-800 border-yellow-200",
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
            <Card>
              <CardHeader>
                <CardTitle>Nothing to show</CardTitle>
              </CardHeader>
              <CardContent className="text-muted-foreground">
                Try clearing the filter or search
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 gap-3 lg:gap-2.5">
              {filtered.map((p) => {
                const isSending = !!sending[p.unique_id];
                const txHash = sent[p.unique_id];
                const explorer =
                  config?.explorer_base_url && (txHash || p.tx_hash)
                    ? `${config.explorer_base_url!.replace(/\/$/, "")}/tx/${txHash || p.tx_hash}`
                    : null;

                return (
                  <Card key={p.unique_id} className="rounded-lg border border-border/60 shadow-sm hover:shadow-md transition">
                    {/* Lean padding keeps the layout compact without feeling cramped */}
                    <CardHeader className="px-3 py-2 sm:px-4 sm:py-2.5 lg:px-4 lg:py-1.5 xl:px-5 xl:py-1.5">
                      {/* MOBILE/TABLET: original stacked layout */}
                      <div className="block lg:hidden">
                        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
                          {/* Left: ID + details */}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 min-w-0">
                              <CopyButton text={p.unique_id} className="mr-1.5" />
                              <CardTitle
                                className="truncate max-w-[260px] md:max-w-none font-mono text-base"
                                title={p.unique_id}
                              >
                                {middleEllipsis(p.unique_id, 12, 6)}
                              </CardTitle>
                            </div>
                            <div className="mt-2 text-sm text-muted-foreground space-y-2">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="font-medium text-foreground">To:</span>
                                <code
                                  className="bg-muted px-2 py-1 rounded truncate max-w-[260px] md:max-w-none"
                                  title={p.to_address}
                                >
                                  {middleEllipsis(p.to_address, 12, 6)}
                                </code>
                                <CopyButton text={p.to_address} />
                              </div>
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="font-medium text-foreground">Amount:</span>
                                <code className="bg-muted px-2 py-1 rounded text-green-500">
                                  {config?.token_symbol ?? "NTX"} {p.amount}
                                </code>
                              </div>
                              {(txHash || p.tx_hash) && (
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="font-medium text-foreground">Last TX:</span>
                                  <code className="bg-muted px-2 py-1 rounded">
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
                          </div>

                          {/* Right: Action */}
                          <div className="flex flex-col items-start md:items-end shrink-0">
                            <Button
                              size="sm"
                              className="w-full md:w-auto h-8 px-3"
                              onClick={() => handlePay(p)}
                              disabled={isSending || p.status === "paid" || !config}
                            >
                              {isSending ? (
                                <>
                                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                  Sending...
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
                          </div>
                        </div>
                      </div>

                      {/* DESKTOP/LAPTOP (>=1024px): horizontal row */}
                      <div className="hidden lg:flex lg:w-full lg:items-center lg:justify-between lg:gap-3 xl:gap-4 overflow-hidden">
                        <div className="flex items-center gap-3 xl:gap-4 flex-1 min-w-0">
                          <div className="flex items-center gap-2 min-w-0 shrink-0">
                            <CopyButton text={p.unique_id} className="shrink-0" />
                            <CardTitle
                              className="font-mono text-xs"
                              title={p.unique_id}
                            >
                              {middleEllipsis(p.unique_id, 10, 6)}
                            </CardTitle>
                          </div>

                          <div className="flex items-center gap-2 min-w-0 flex-1">
                            <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                              To
                            </span>
                            <code
                              className="bg-muted px-1 py-0.5 rounded text-xs font-mono"
                              title={p.to_address}
                            >
                              {middleEllipsis(p.to_address, 10, 6)}
                            </code>
                            <CopyButton text={p.to_address} className="shrink-0" />
                            <span className="ml-3 text-[10px] uppercase tracking-wide text-muted-foreground">
                              Amount
                            </span>
                            <code className="bg-muted px-1 py-0.5 rounded text-green-600 text-xs">
                              {config?.token_symbol ?? "NTX"} {p.amount}
                            </code>
                          </div>

                          {(txHash || p.tx_hash) && (
                            <div className="flex items-center gap-2 min-w-0 shrink-0 max-w-[220px]">
                              <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                                Last TX
                              </span>
                              <code
                                className="bg-muted px-1 py-0.5 rounded text-xs font-mono"
                                title={txHash || p.tx_hash}
                              >
                                {shorten(txHash || p.tx_hash)}
                              </code>
                              {explorer && (
                                <a
                                  href={explorer}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="text-primary hover:underline text-xs"
                                  title="View on explorer"
                                >
                                  View
                                </a>
                              )}
                            </div>
                          )}
                        </div>

                        {/* Action button (inline) */}
                        <div className="flex items-center justify-end shrink-0 pl-3 xl:pl-4">
                          <Button
                            size="sm"
                            className="h-8 px-3 text-xs"
                            onClick={() => handlePay(p)}
                            disabled={isSending || p.status === "paid" || !config}
                          >
                            {isSending ? (
                              <>
                                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                                Sending...
                              </>
                            ) : p.status === "unpaid" ? (
                              <>
                                <Send className="mr-1.5 h-4 w-4" />
                                Pay Now
                              </>
                            ) : (
                              <>
                                <CheckCheckIcon className="mr-1.5 h-4 w-4" />
                                Paid
                              </>
                            )}
                          </Button>
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

