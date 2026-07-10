"use client";

import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { flushSync } from "react-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  cancelPaymentQuote,
  getPaymentsConfig,
  getPaymentQuote,
  getPaymentsList,
  DmsPaymentMetadata,
  DmsPaymentItem,
  PaymentsConfig,
  reportToDms,
  buildCardanoTx,
  submitCardanoTx,
  validatePaymentQuote,
} from "@/api/api";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { CopyButton } from "@/components/ui/CopyButton";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  CheckCheckIcon,
  ChevronDown,
  ChevronUp,
  CircleHelp,
  Filter,
  Loader2,
  RefreshCw,
  Send,
  Wallet,
  X
} from "lucide-react";
import { sendNTX } from "@/lib/sendNTX";
import { buildCardanoConnection, getEternlNamespace } from "@/lib/cardano";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { useWalletStore, type WalletType } from "@/stores/walletStore";

const ACTIVE_QUOTES_STORAGE_KEY = "nunet-payments-active-quotes-v1";

type StoredPaymentQuote = {
  uniqueId: string;
  quoteId: string;
  originalAmount: string;
  convertedAmount: string;
  pricingCurrency: string;
  paymentCurrency: string;
  exchangeRate: string;
  expiresAt: string;
};

type QuoteConfirmationState = {
  payment: DmsPaymentItem;
  quote: StoredPaymentQuote;
};

type QuoteIssueState = {
  payment: DmsPaymentItem;
  message: string;
};

type FilterState = {
  deploymentId: string;
  uniqueId: string;
  contractDid: string;
  toAddress: string;
  fromAddress: string;
  txHash: string;
  blockchain: "all" | "ETHEREUM" | "CARDANO";
  status: "all" | "paid" | "unpaid";
};

const DEFAULT_FILTERS: FilterState = {
  deploymentId: "",
  uniqueId: "",
  contractDid: "",
  toAddress: "",
  fromAddress: "",
  txHash: "",
  blockchain: "all",
  status: "all",
};

// --- Funções Auxiliares ---
function readActiveQuotesFromStorage(): Record<string, StoredPaymentQuote> {
  try {
    const raw = localStorage.getItem(ACTIVE_QUOTES_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    const output: Record<string, StoredPaymentQuote> = {};
    for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (!value || typeof value !== "object" || Array.isArray(value)) continue;
      const entry = value as Record<string, unknown>;
      const uniqueId = typeof entry.uniqueId === "string" ? entry.uniqueId.trim() : "";
      const quoteId = typeof entry.quoteId === "string" ? entry.quoteId.trim() : "";
      if (!key.trim() || !uniqueId || !quoteId) continue;
      output[key] = {
        uniqueId,
        quoteId,
        originalAmount: typeof entry.originalAmount === "string" ? entry.originalAmount : "",
        convertedAmount: typeof entry.convertedAmount === "string" ? entry.convertedAmount : "",
        pricingCurrency: typeof entry.pricingCurrency === "string" ? entry.pricingCurrency : "",
        paymentCurrency: typeof entry.paymentCurrency === "string" ? entry.paymentCurrency : "",
        exchangeRate: typeof entry.exchangeRate === "string" ? entry.exchangeRate : "",
        expiresAt: typeof entry.expiresAt === "string" ? entry.expiresAt : "",
      };
    }
    return output;
  } catch {
    return {};
  }
}

function writeActiveQuotesToStorage(quotes: Record<string, StoredPaymentQuote>): void {
  try {
    localStorage.setItem(ACTIVE_QUOTES_STORAGE_KEY, JSON.stringify(quotes));
  } catch {}
}

function middleEllipsis(value: string, head = 6, tail = 4) {
  if (!value) return "";
  if (value.length <= head + tail + 3) return value;
  return `${value.slice(0, head)}...${value.slice(-tail)}`;
}

function shorten(addr: string) {
  return middleEllipsis(addr, 8, 4);
}

function inferWalletType(address: string): WalletType | null {
  const value = address?.trim() ?? "";
  if (/^0x[a-fA-F0-9]{40}$/.test(value)) return "ethereum";
  if (/^(addr|stake)[0-9a-z]+$/i.test(value)) return "cardano";
  return null;
}

function walletDisplayName(type: WalletType) {
  return type === "ethereum" ? "MetaMask" : "Eternl";
}

function isConversionPayment(item: DmsPaymentItem): boolean {
  if (typeof item.requires_conversion === "boolean") return item.requires_conversion;
  const pricingCurrency = (item.pricing_currency ?? "").trim();
  if (!pricingCurrency) return false;
  const originalAmount = (item.original_amount ?? "").trim();
  if (!originalAmount) return true;
  const convertedAmount = (item.amount ?? "").trim();
  if (!convertedAmount) return true;
  const originalNum = Number(originalAmount);
  const convertedNum = Number(convertedAmount);
  if (Number.isFinite(originalNum) && Number.isFinite(convertedNum)) return originalNum !== convertedNum;
  return originalAmount !== convertedAmount;
}

function extractQuoteId(message: string): string | null {
  const match = message.match(/quote[_\s-]?id[:=]\s*([A-Za-z0-9._:-]+)/i);
  return match?.[1] ?? null;
}

function getRawErrorMessage(error: unknown): string {
  const errorLike = error as { response?: { data?: { detail?: unknown; message?: string } }; message?: string; };
  const detail = errorLike?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    const nestedMessage = (detail as { message?: unknown }).message;
    if (typeof nestedMessage === "string" && nestedMessage.trim()) return nestedMessage;
  }
  const message = errorLike?.response?.data?.message;
  if (typeof message === "string" && message.trim()) return message;
  return errorLike?.message || "Something went wrong";
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : null;
}

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim().length > 0) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  const parts: string[] = [];
  if (days > 0) parts.push(`${days}d`);
  if (hours > 0) parts.push(`${hours}h`);
  if (minutes > 0) parts.push(`${minutes}m`);
  if (secs > 0 && parts.length === 0) parts.push(`${secs}s`);
  if (parts.length === 0) return "0s";
  return parts.slice(0, 3).join(" ");
}

function formatTime(value: unknown): string | null {
  const raw = asString(value);
  if (!raw) return null;
  let parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime()) && /^-?\d+(\.\d+)?$/.test(raw.trim())) {
    const numeric = Number(raw.trim());
    if (Number.isFinite(numeric)) {
      const absNumeric = Math.abs(numeric);
      let epochMillis = numeric;
      if (absNumeric >= 1e18) epochMillis = numeric / 1e6;
      else if (absNumeric >= 1e15) epochMillis = numeric / 1e3;
      else if (absNumeric >= 1e12) epochMillis = numeric;
      else epochMillis = numeric * 1e3;
      parsed = new Date(epochMillis);
    }
  }
  if (Number.isNaN(parsed.getTime())) return raw;
  return parsed.toLocaleString(undefined, {
    year: "numeric", month: "short", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false,
  });
}

function pluralize(count: number, singular: string, plural?: string): string {
  const noun = count === 1 ? singular : (plural ?? `${singular}s`);
  return `${count} ${noun}`;
}

function summarizePaymentMetadata(metadata: DmsPaymentMetadata | null | undefined): string[] {
  const data = asRecord(metadata);
  if (!data) return [];
  const details: string[] = [];
  const allocationCount = asNumber(data.allocation_count);
  if (allocationCount !== null) details.push(pluralize(allocationCount, "allocation"));
  const totalUtilizationSec = asNumber(data.total_utilization_sec);
  if (totalUtilizationSec !== null) details.push(`runtime ${formatDuration(totalUtilizationSec)}`);
  const deploymentCount = asNumber(data.deployment_count);
  if (deploymentCount !== null) details.push(pluralize(deploymentCount, "deployment"));
  const periodsInvoiced = asNumber(data.periods_invoiced);
  if (periodsInvoiced !== null) details.push(`${pluralize(periodsInvoiced, "period")} invoiced`);
  const periodStart = formatTime(data.period_start);
  const periodEnd = formatTime(data.period_end);
  if (periodStart || periodEnd) details.push(`period ${periodStart ?? "?"} to ${periodEnd ?? "?"}`);
  const lastInvoiceAt = formatTime(data.last_invoice_at);
  if (lastInvoiceAt) details.push(`last invoice ${lastInvoiceAt}`);
  return details;
}

type PaymentDetailField = { label: string; value: string; tooltip: string; };

function addDetailField(fields: PaymentDetailField[], label: string, value: unknown, tooltip: string): void {
  if (value === null || value === undefined) return;
  const text = typeof value === "string" ? value.trim() : String(value);
  if (!text) return;
  fields.push({ label, value: text, tooltip });
}

function buildMetadataDetailFields(metadata: DmsPaymentMetadata | null | undefined): PaymentDetailField[] {
  const data = asRecord(metadata);
  if (!data) return [];
  const fields: PaymentDetailField[] = [];
  addDetailField(fields, "Deployment ID", asString(data.deployment_id), "Deployment identifier associated with this payment.");
  addDetailField(fields, "Allocation Count", asNumber(data.allocation_count), "Number of allocations included in this payment.");
  addDetailField(fields, "Deployment Count", asNumber(data.deployment_count), "Number of deployments invoiced in this payment.");
  const totalUtilization = asNumber(data.total_utilization_sec);
  if (totalUtilization !== null) {
    addDetailField(fields, "Total Runtime", `${formatDuration(totalUtilization)} (${totalUtilization.toFixed(6)} sec)`, "Total resource utilization duration used to calculate this payment.");
  }
  addDetailField(fields, "Periods Invoiced", asNumber(data.periods_invoiced), "Billing periods covered by this transaction.");
  addDetailField(fields, "Period Start", formatTime(data.period_start), "Start of the invoiced period.");
  addDetailField(fields, "Period End", formatTime(data.period_end), "End of the invoiced period.");
  addDetailField(fields, "Last Invoice At", formatTime(data.last_invoice_at), "Timestamp of the previous invoice for this contract.");

  const allocationsRaw = Array.isArray(data.allocations) ? data.allocations : [];
  const allocations = allocationsRaw.map(asRecord).filter(Boolean) as Record<string, unknown>[];
  allocations.forEach((allocation, idx) => {
    const prefix = `Allocation ${idx + 1}`;
    addDetailField(fields, `${prefix} ID`, asString(allocation.allocation_id), "Unique allocation identifier.");
    const duration = asNumber(allocation.duration_sec);
    if (duration !== null) {
      addDetailField(fields, `${prefix} Runtime`, `${formatDuration(duration)} (${duration.toFixed(6)} sec)`, "Runtime duration for this allocation.");
    }
    addDetailField(fields, `${prefix} Start`, formatTime(allocation.start_time), "Allocation start timestamp.");
    addDetailField(fields, `${prefix} End`, formatTime(allocation.end_time), "Allocation end timestamp.");
    addDetailField(fields, `${prefix} CPU Cost`, asString(allocation.cpu_cost), "CPU usage cost component.");
    addDetailField(fields, `${prefix} RAM Cost`, asString(allocation.ram_cost), "RAM usage cost component.");
    addDetailField(fields, `${prefix} Disk Cost`, asString(allocation.disk_cost), "Disk usage cost component.");
    addDetailField(fields, `${prefix} GPU Cost`, asString(allocation.gpu_cost), "GPU usage cost component.");
    addDetailField(fields, `${prefix} Total Cost`, asString(allocation.total_cost), "Total cost for this allocation.");

    const resources = asRecord(allocation.resources);
    if (resources) {
      addDetailField(fields, `${prefix} CPU Cores`, asNumber(resources.cpu_cores), "Allocated CPU cores.");
      addDetailField(fields, `${prefix} RAM GB`, asNumber(resources.ram_gb), "Allocated RAM in gigabytes.");
      addDetailField(fields, `${prefix} Disk GB`, asNumber(resources.disk_gb), "Allocated disk in gigabytes.");
      addDetailField(fields, `${prefix} GPU Count`, asNumber(resources.gpu_count), "Allocated GPU count.");
    }
  });
  return fields;
}

function metadataPrettyJson(metadata: DmsPaymentMetadata | null | undefined): string | null {
  const data = asRecord(metadata);
  if (!data) return null;
  try { return JSON.stringify(data, null, 2); } catch { return null; }
}

function DetailFieldRow({ field }: { field: PaymentDetailField }) {
  return (
    <div className="rounded border border-border/60 bg-muted/20 p-2">
      <div className="mb-1 flex items-center gap-1 text-[11px] uppercase tracking-wide text-muted-foreground">
        <span>{field.label}</span>
        <Tooltip>
          <TooltipTrigger asChild>
            <button type="button" className="inline-flex items-center">
              <CircleHelp className="h-3.5 w-3.5" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="top" className="max-w-xs text-xs">
            {field.tooltip}
          </TooltipContent>
        </Tooltip>
      </div>
      <div className="font-mono text-xs break-all">{field.value}</div>
    </div>
  );
}

const PAYMENTS_LIST_REFRESH_MS = 60 * 60 * 1000;

export default function PaymentsPage() {
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [sending, setSending] = useState<Record<string, boolean>>({});
  const [sent, setSent] = useState<Record<string, string>>({});
  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({});
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);

  const [isFiltersOpen, setIsFiltersOpen] = useState(false);
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [draftFilters, setDraftFilters] = useState<FilterState>(DEFAULT_FILTERS);

  const [activeQuotes, setActiveQuotes] = useState<Record<string, StoredPaymentQuote>>(() => readActiveQuotesFromStorage());
  const [quoteConfirmation, setQuoteConfirmation] = useState<QuoteConfirmationState | null>(null);
  const [quoteConfirming, setQuoteConfirming] = useState(false);
  const [quoteIssue, setQuoteIssue] = useState<QuoteIssueState | null>(null);
  const recoveryCheckedRef = useRef(false);

  const activeWalletType = useWalletStore((state) => state.active);
  const walletConnections = useWalletStore((state) => state.connections);
  const setWalletConnection = useWalletStore((state) => state.setConnection);
  const activateWallet = useWalletStore((state) => state.activate);
  const queryClient = useQueryClient();

  // --- Funções de Ação dos Filtros ---
  const handleApplyFilters = () => {
    setFilters(draftFilters);
    setPage(1);
    setIsFiltersOpen(false);
  };

  const handleClearFilters = () => {
    // Preserve the top-level explicitly visible select values
    const reset = { ...DEFAULT_FILTERS, blockchain: filters.blockchain, status: filters.status };
    setDraftFilters(reset);
    setFilters(reset);
    setPage(1);
  };

  const removeFilter = (key: keyof FilterState) => {
    setFilters(prev => ({ ...prev, [key]: DEFAULT_FILTERS[key] }));
    setDraftFilters(prev => ({ ...prev, [key]: DEFAULT_FILTERS[key] }));
    setPage(1);
  };

  const handleFilterTextKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleApplyFilters();
    }
  };

  function handlePaymentsRefresh() {
    void queryClient.refetchQueries({ queryKey: ["payments", "summary"], exact: true });
    void queryClient.refetchQueries({ queryKey: ["payments", "list"], exact: false, type: "active" });
  }

  const cfgQ = useQuery({
    queryKey: ["payments", "config"],
    queryFn: getPaymentsConfig,
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
  });

  const summaryQ = useQuery({
    queryKey: ["payments", "summary"],
    queryFn: () => getPaymentsList(),
    staleTime: PAYMENTS_LIST_REFRESH_MS,
    gcTime: PAYMENTS_LIST_REFRESH_MS,
    refetchInterval: autoRefresh ? PAYMENTS_LIST_REFRESH_MS : false,
    refetchOnWindowFocus: false,
  });

  const pageQ = useQuery({
    queryKey: [
      "payments",
      "list",
      page,
      pageSize,
      filters.deploymentId,
      filters.uniqueId,
      filters.contractDid,
      filters.blockchain,
      filters.status,
      filters.toAddress,
      filters.fromAddress,
      filters.txHash,
    ],
    queryFn: () =>
      getPaymentsList({
        limit: pageSize,
        offset: (page - 1) * pageSize,
        sort: "-created_at",
        ...(filters.deploymentId ? { deploymentId: filters.deploymentId } : {}),
        ...(filters.uniqueId ? { uniqueId: filters.uniqueId } : {}),
        ...(filters.contractDid ? { contractDid: filters.contractDid } : {}),
        ...(filters.blockchain !== "all" ? { blockchain: filters.blockchain } : {}),
        ...(filters.status !== "all" ? { status: filters.status } : {}),
        ...(filters.toAddress ? { toAddress: filters.toAddress } : {}),
        ...(filters.fromAddress ? { fromAddress: filters.fromAddress } : {}),
        ...(filters.txHash ? { txHash: filters.txHash } : {}),
      }),
    staleTime: PAYMENTS_LIST_REFRESH_MS,
    gcTime: PAYMENTS_LIST_REFRESH_MS,
    refetchInterval: autoRefresh ? PAYMENTS_LIST_REFRESH_MS : false,
    refetchOnWindowFocus: false,
  });

  const config = cfgQ.data as PaymentsConfig | undefined;
  const summary = summaryQ.data;
  const ethConfig = config?.ethereum;
  const cardanoConfig = config?.cardano;

  const ignoredToastRef = useRef<number | null>(null);

  useEffect(() => {
    const ignoredCount = summary?.ignored_count ?? 0;
    if (ignoredCount > 0 && ignoredToastRef.current !== ignoredCount) {
      const plural = ignoredCount === 1 ? "" : "s";
      toast.warning(`${ignoredCount} transaction${plural} skipped due to incomplete DMS data.`);
      ignoredToastRef.current = ignoredCount;
      return;
    }
    if (ignoredToastRef.current !== ignoredCount) {
      ignoredToastRef.current = ignoredCount;
    }
  }, [summary?.ignored_count]);

  const summaryItems = useMemo(() => summary?.items ?? [], [summary?.items]);
  const pageItems = useMemo(() => pageQ.data?.items ?? [], [pageQ.data?.items]);

  useEffect(() => {
    writeActiveQuotesToStorage(activeQuotes);
  }, [activeQuotes]);

  useEffect(() => {
    if (!summary || recoveryCheckedRef.current) return;
    recoveryCheckedRef.current = true;

    const runRecovery = async () => {
      const entries = Object.values(activeQuotes);
      if (entries.length === 0) return;
      const unpaidIds = new Set(summaryItems.filter((entry) => entry.status === "unpaid").map((entry) => entry.unique_id));
      const paymentsById = new Map(summaryItems.map((entry) => [entry.unique_id, entry]));
      const recovered: Record<string, StoredPaymentQuote> = {};

      for (const quote of entries) {
        if (!unpaidIds.has(quote.uniqueId)) continue;
        const payment = paymentsById.get(quote.uniqueId);
        const validatorDid = (payment?.payment_validator_did ?? "").trim();
        if (!validatorDid) {
          toast.info(`Recovered quote ${quote.quoteId} is missing validator DID and was cancelled.`);
          continue;
        }
        try {
          const validation = await validatePaymentQuote({ quote_id: quote.quoteId, dest: validatorDid });
          if (!validation.valid) {
            await cancelQuoteForValidator(quote.quoteId, validatorDid);
            toast.info(`Recovered quote ${quote.quoteId} is no longer valid and was cancelled.`);
            continue;
          }
          recovered[quote.uniqueId] = {
            uniqueId: quote.uniqueId,
            quoteId: validation.quote_id ?? quote.quoteId,
            originalAmount: validation.original_amount ?? quote.originalAmount,
            convertedAmount: validation.converted_amount ?? quote.convertedAmount,
            pricingCurrency: validation.pricing_currency ?? quote.pricingCurrency,
            paymentCurrency: validation.payment_currency ?? quote.paymentCurrency,
            exchangeRate: validation.exchange_rate ?? quote.exchangeRate,
            expiresAt: validation.expires_at ?? quote.expiresAt,
          };
        } catch {
          await cancelQuoteForValidator(quote.quoteId, validatorDid);
          toast.info(`Recovered quote ${quote.quoteId} could not be validated and was cancelled.`);
        }
      }
      setActiveQuotes(recovered);

      const count = Object.keys(recovered).length;
      if (count > 0) {
        const plural = count === 1 ? "" : "s";
        toast.info(`${count} active quote${plural} recovered. Resume payment to continue.`);
      }
    };
    void runRecovery();
  }, [activeQuotes, summaryItems, summary]);

  const errorToastStyles = {
    className: "text-white [&_*]:!text-white",
    descriptionClassName: "text-white/80",
    style: { color: "#fff", "--normal-text": "#fff", "--error-text": "#fff" },
  };

  const hasEthereumProvider = typeof window !== "undefined" && Boolean((window as unknown as { ethereum?: { request?: unknown } }).ethereum?.request);
  const hasCardanoProvider = typeof window !== "undefined" && Boolean((window as unknown as { cardano?: { eternl?: unknown } }).cardano?.eternl);

  function walletTypeForPayment(item: DmsPaymentItem): WalletType | null {
    const bc = (item.blockchain || "").toUpperCase();
    if (bc === "CARDANO") return "cardano";
    if (bc === "ETHEREUM") return "ethereum";
    return inferWalletType(item.to_address);
  }

  function upsertActiveQuote(quote: StoredPaymentQuote): void {
    setActiveQuotes((prev) => ({ ...prev, [quote.uniqueId]: quote }));
  }

  function removeActiveQuote(uniqueId: string): void {
    setActiveQuotes((prev) => {
      if (!Object.prototype.hasOwnProperty.call(prev, uniqueId)) return prev;
      const next = { ...prev };
      delete next[uniqueId];
      return next;
    });
  }

  async function cancelQuoteForValidator(quoteId: string, validatorDid: string): Promise<void> {
    const normalizedDid = (validatorDid ?? "").trim();
    if (!normalizedDid) return;
    await cancelPaymentQuote({ quote_id: quoteId, dest: normalizedDid }).catch(() => {});
  }

  async function executePayment(p: DmsPaymentItem, amountToPay: string, quoteId?: string): Promise<boolean> {
    const chain = (p.blockchain || "ETHEREUM").toUpperCase();
    const isCardano = chain === "CARDANO";
    const chainConfig = isCardano ? cardanoConfig : ethConfig;
    if (!chainConfig) {
      toast.error("Missing token config", errorToastStyles);
      return false;
    }
    if (p.status === "paid") {
      toast.info("This item is already marked paid");
      return false;
    }

    const requiredWallet = walletTypeForPayment(p);
    if (requiredWallet === "ethereum" && !hasEthereumProvider) {
      toast.error("MetaMask extension not detected", { ...errorToastStyles, description: "Install MetaMask to continue with Ethereum payments." });
      return false;
    }
    if (requiredWallet === "cardano" && !hasCardanoProvider) {
      toast.error("Eternl extension not detected", { ...errorToastStyles, description: "Install Eternl to continue with Cardano payments." });
      return false;
    }

    try {
      setSending((s) => ({ ...s, [p.unique_id]: true }));

      if (isCardano) {
        let connection = walletConnections.cardano;
        let api = connection?.cardanoApi as { signTx?: (tx: string, partialSign?: boolean) => Promise<string> } | undefined;
        if (!connection || !api?.signTx) {
          const namespace = getEternlNamespace();
          if (!namespace) throw new Error("Eternl wallet not found");
          const enabledApi = await namespace.enable();
          connection = await buildCardanoConnection(enabledApi);
          setWalletConnection("cardano", connection);
          activateWallet("cardano");
          api = connection.cardanoApi as { signTx?: (tx: string, partialSign?: boolean) => Promise<string> } | undefined;
        }
        if (!connection || !api?.signTx) throw new Error("Cardano wallet connection missing");

        const build = await buildCardanoTx({
          from_address: connection.address,
          change_address: connection.changeAddress ?? connection.address,
          to_address: p.to_address,
          amount: amountToPay,
          payment_provider: p.unique_id,
        });

        const witness = await api.signTx(build.tx_cbor, true);
        const submitRes = await submitCardanoTx({
          tx_body_cbor: build.tx_body_cbor,
          witness_set_cbor: witness,
          payment_provider: p.unique_id,
          to_address: p.to_address,
          amount: amountToPay,
          quote_id: quoteId,
        });

        const txHash = submitRes.tx_hash ?? build.tx_hash;
        setSent((s) => ({ ...s, [p.unique_id]: txHash }));
        toast.success("Transaction sent", { description: chainConfig.explorer_base_url ? `Tx: ${txHash}` : undefined });
      } else {
        const { hash } = await sendNTX({
          tokenAddress: chainConfig.token_address,
          to: p.to_address,
          amountHuman: amountToPay,
          decimals: chainConfig.token_decimals,
          chainIdWanted: chainConfig.chain_id,
        });

        setSent((s) => ({ ...s, [p.unique_id]: hash }));
        await reportToDms({
          tx_hash: hash,
          to_address: p.to_address,
          amount: amountToPay,
          payment_provider: p.unique_id,
          blockchain: chain,
          quote_id: quoteId,
        });
        toast.success("Transaction sent", { description: chainConfig.explorer_base_url ? `Tx: ${hash}` : undefined });
      }
      void queryClient.invalidateQueries({ queryKey: ["payments"] });
      return true;
    } catch (err: unknown) {
      const rawMessage = getRawErrorMessage(err);
      const toAda = (lovelace: number | string | null | undefined) => {
        const n = Number(lovelace);
        if (Number.isFinite(n) && n > 0) return `${(n / 1_000_000).toFixed(3)} ADA`;
        return null;
      };
      const formatError = (msg: string): string => {
        const lovelaceMatch = msg.match(/have\s+(\d+)\s+lovelace.*need\s*>=\s*(\d+).*min-utxo\s+(\d+)/i);
        if (lovelaceMatch) {
          const [, have, need, min] = lovelaceMatch;
          return `Not enough ADA to send. You have ${toAda(have) ?? have}, need at least ${toAda(need) ?? need} (min-utxo ${toAda(min) ?? min}).`;
        }
        const tokenMatch = msg.match(/Insufficient token balance.*have\s+([0-9]+(?:\.[0-9]+)?),\s*need\s+([0-9]+(?:\.[0-9]+)?)/i);
        if (tokenMatch) return `Not enough NTX to cover the payment (have ${tokenMatch[1]}, need ${tokenMatch[2]}).`;
        if (msg.includes("0xe450d38c")) return "Not enough NTX to cover this payment in the currently connected MetaMask account.";
        return msg;
      };
      console.error(err);
      toast.error("Payment failed", { ...errorToastStyles, description: formatError(String(rawMessage)) });
      return false;
    } finally {
      setSending((s) => ({ ...s, [p.unique_id]: false }));
    }
  }

  async function validateStoredQuoteForPayment(p: DmsPaymentItem, quote: StoredPaymentQuote): Promise<StoredPaymentQuote | null> {
    const validatorDid = (p.payment_validator_did ?? "").trim();
    if (!validatorDid) {
      removeActiveQuote(p.unique_id);
      setQuoteIssue({ payment: p, message: "Missing payment validator DID for quote validation." });
      return null;
    }
    try {
      const validation = await validatePaymentQuote({ quote_id: quote.quoteId, dest: validatorDid });
      if (!validation.valid) {
        await cancelQuoteForValidator(quote.quoteId, validatorDid);
        removeActiveQuote(p.unique_id);
        setQuoteIssue({ payment: p, message: validation.error || "Quote expired or is no longer valid." });
        return null;
      }
      const convertedAmount = (validation.converted_amount ?? quote.convertedAmount).trim();
      if (!convertedAmount) {
        await cancelQuoteForValidator(quote.quoteId, validatorDid);
        removeActiveQuote(p.unique_id);
        setQuoteIssue({ payment: p, message: "Quote did not include a converted amount." });
        return null;
      }
      const refreshed: StoredPaymentQuote = {
        uniqueId: p.unique_id,
        quoteId: validation.quote_id ?? quote.quoteId,
        originalAmount: (validation.original_amount ?? quote.originalAmount).trim(),
        convertedAmount,
        pricingCurrency: (validation.pricing_currency ?? quote.pricingCurrency).trim(),
        paymentCurrency: (validation.payment_currency ?? quote.paymentCurrency).trim(),
        exchangeRate: (validation.exchange_rate ?? quote.exchangeRate).trim(),
        expiresAt: validation.expires_at ?? quote.expiresAt,
      };
      upsertActiveQuote(refreshed);
      return refreshed;
    } catch (error) {
      setQuoteIssue({ payment: p, message: getRawErrorMessage(error) });
      return null;
    }
  }

  async function prepareConversionQuote(p: DmsPaymentItem): Promise<StoredPaymentQuote | null> {
    const chain = (p.blockchain || "ETHEREUM").toUpperCase();
    const chainConfig = chain === "CARDANO" ? cardanoConfig : ethConfig;
    const tokenSymbol = chainConfig?.token_symbol ?? "NTX";
    const validatorDid = (p.payment_validator_did ?? "").trim();
    if (!validatorDid) {
      setQuoteIssue({ payment: p, message: "Missing payment validator DID for quote request." });
      return null;
    }
    const fetchQuote = async () => {
      try {
        return await getPaymentQuote({ unique_id: p.unique_id, dest: validatorDid });
      } catch (error) {
        const message = getRawErrorMessage(error);
        const activeQuoteId = extractQuoteId(message);
        if (activeQuoteId) {
          await cancelQuoteForValidator(activeQuoteId, validatorDid);
          return getPaymentQuote({ unique_id: p.unique_id, dest: validatorDid });
        }
        throw error;
      }
    };
    try {
      const quote = await fetchQuote();
      const validation = await validatePaymentQuote({ quote_id: quote.quote_id, dest: validatorDid });
      if (!validation.valid) {
        await cancelQuoteForValidator(quote.quote_id, validatorDid);
        setQuoteIssue({ payment: p, message: validation.error || "Quote expired or is no longer valid." });
        return null;
      }
      const convertedAmount = (validation.converted_amount ?? quote.converted_amount ?? "").trim();
      if (!convertedAmount) {
        await cancelQuoteForValidator(quote.quote_id, validatorDid);
        setQuoteIssue({ payment: p, message: "Quote did not include a converted amount." });
        return null;
      }
      const preparedQuote: StoredPaymentQuote = {
        uniqueId: p.unique_id,
        quoteId: quote.quote_id,
        originalAmount: (validation.original_amount ?? quote.original_amount ?? p.original_amount ?? p.amount).trim(),
        convertedAmount,
        pricingCurrency: (validation.pricing_currency ?? quote.pricing_currency ?? p.pricing_currency ?? "USDT").trim(),
        paymentCurrency: (validation.payment_currency ?? quote.payment_currency ?? tokenSymbol).trim(),
        exchangeRate: (validation.exchange_rate ?? quote.exchange_rate ?? "").trim(),
        expiresAt: validation.expires_at ?? quote.expires_at,
      };
      upsertActiveQuote(preparedQuote);
      return preparedQuote;
    } catch (error) {
      setQuoteIssue({ payment: p, message: getRawErrorMessage(error) });
      return null;
    }
  }

  async function handlePay(p: DmsPaymentItem) {
    const chain = (p.blockchain || "ETHEREUM").toUpperCase();
    const isCardano = chain === "CARDANO";
    const chainConfig = isCardano ? cardanoConfig : ethConfig;
    if (!chainConfig) {
      toast.error("Missing token config", errorToastStyles);
      return;
    }
    if (p.status === "paid") {
      toast.info("This item is already marked paid");
      return;
    }
    const requiredWallet = walletTypeForPayment(p);
    if (requiredWallet) {
      const connection = walletConnections[requiredWallet];
      if (!connection) {
        toast.error(`Connect ${walletDisplayName(requiredWallet)} to continue`, errorToastStyles);
        return;
      }
      if (activeWalletType !== requiredWallet) {
        toast.error(`Activate ${walletDisplayName(requiredWallet)} before paying`, errorToastStyles);
        return;
      }
    }
    if (!isConversionPayment(p)) {
      await executePayment(p, p.amount);
      return;
    }
    const existingQuote = activeQuotes[p.unique_id];
    if (existingQuote) {
      const validatedQuote = await validateStoredQuoteForPayment(p, existingQuote);
      if (validatedQuote) setQuoteConfirmation({ payment: p, quote: validatedQuote });
      return;
    }
    const preparedQuote = await prepareConversionQuote(p);
    if (preparedQuote) setQuoteConfirmation({ payment: p, quote: preparedQuote });
  }

  async function handleConfirmQuotePayment() {
    if (!quoteConfirmation) return;
    const { payment, quote } = quoteConfirmation;
    setQuoteConfirming(true);
    try {
      const validatedQuote = await validateStoredQuoteForPayment(payment, quote);
      if (!validatedQuote) {
        setQuoteConfirmation(null);
        return;
      }
      const success = await executePayment(payment, validatedQuote.convertedAmount, validatedQuote.quoteId);
      if (success) {
        removeActiveQuote(payment.unique_id);
        setQuoteConfirmation(null);
      }
    } finally {
      setQuoteConfirming(false);
    }
  }

  async function handleCancelQuoteConfirmation() {
    if (!quoteConfirmation) return;
    const { payment, quote } = quoteConfirmation;
    const validatorDid = (payment.payment_validator_did ?? "").trim();
    setQuoteConfirming(true);
    try {
      await cancelQuoteForValidator(quote.quoteId, validatorDid);
      removeActiveQuote(payment.unique_id);
      setQuoteConfirmation(null);
      toast.info("Payment quote cancelled.");
    } finally {
      setQuoteConfirming(false);
    }
  }

  const isLoading = cfgQ.isLoading || pageQ.isLoading;
  const totalCount = pageQ.data?.total_count ?? summary?.total_count ?? 0;
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
  const hasNextPage = page < totalPages;

  const hasActiveTextFilters = (
    filters.deploymentId || filters.uniqueId || filters.contractDid ||
    filters.toAddress || filters.fromAddress || filters.txHash
  );

  return (
    <div className="flex flex-1 flex-col">
      <div className="container/main flex flex-1 flex-col gap-2">
        <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6 px-4 md:px-6">

          {/* HEADER ROW */}
          <div className="flex flex-col md:flex-row md:items-center gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <Wallet className="h-5 w-5" />
              <h2 className="text-lg font-semibold mr-2">Payments</h2>

              {!!summary && (
                <div className="flex flex-wrap items-center gap-2">
                  <Badge className="select-none" variant="secondary" title="Total transactions">
                    {summary.total_count} Total
                  </Badge>
                  <Badge className="select-none bg-green-100 text-green-800 border border-green-200" title="Paid transactions">
                    {summary.paid_count} Paid
                  </Badge>
                  <Badge className="select-none bg-yellow-100 text-yellow-800 border border-yellow-200" title="Unpaid transactions">
                    {summary.unpaid_count} Unpaid
                  </Badge>
                </div>
              )}
            </div>
          </div>

          {/* CONTROLS ROW (Top Level Filters & Refresh) */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-3">
              <div className="w-32">
                <Select
                  value={filters.blockchain}
                  onValueChange={(val: "all" | "ETHEREUM" | "CARDANO") => {
                    setFilters(prev => ({ ...prev, blockchain: val }));
                    setDraftFilters(prev => ({ ...prev, blockchain: val }));
                    setPage(1);
                  }}
                >
                  <SelectTrigger className="h-9 w-full font-medium text-sm">
                    <SelectValue placeholder="Blockchain" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Chains</SelectItem>
                    <SelectItem value="CARDANO">Cardano</SelectItem>
                    <SelectItem value="ETHEREUM">Ethereum</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="w-32">
                <Select
                  value={filters.status}
                  onValueChange={(val: "all" | "paid" | "unpaid") => {
                    setFilters(prev => ({ ...prev, status: val }));
                    setDraftFilters(prev => ({ ...prev, status: val }));
                    setPage(1);
                  }}
                >
                  <SelectTrigger className="h-9 w-full font-medium text-sm">
                    <SelectValue placeholder="Status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Status</SelectItem>
                    <SelectItem value="unpaid">Unpaid</SelectItem>
                    <SelectItem value="paid">Paid</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <Button
                variant="outline"
                size="sm"
                className="h-9 font-medium text-sm"
                onClick={() => setIsFiltersOpen((prev) => !prev)}
                aria-expanded={isFiltersOpen}
              >
                <Filter className="mr-2 h-4 w-4" />
                Filters
                {isFiltersOpen ? <ChevronUp className="ml-2 h-4 w-4" /> : <ChevronDown className="ml-2 h-4 w-4" />}
              </Button>
            </div>

            <div className="flex items-center gap-3 md:ml-auto">
              <Button
                variant="outline"
                size="sm"
                className="h-9 font-medium text-sm"
                onClick={handlePaymentsRefresh}
                disabled={pageQ.isFetching || summaryQ.isFetching}
              >
                {pageQ.isFetching || summaryQ.isFetching ? (
                  <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Refreshing</>
                ) : (
                  <><RefreshCw className="mr-2 h-4 w-4" /> Refresh</>
                )}
              </Button>
              <Separator orientation="vertical" className="h-6" />
              <div className="flex items-center gap-2">
                <Switch id="auto-refresh" checked={autoRefresh} onCheckedChange={setAutoRefresh} />
                <Label htmlFor="auto-refresh" className="font-medium text-sm cursor-pointer">Auto refresh</Label>
              </div>
            </div>
          </div>

          {/* ACTIVE TEXT FILTERS ROW */}
          {hasActiveTextFilters && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[12xp] text-muted-foreground mr-1">Active filters:</span>

              {filters.deploymentId && (
                <Badge variant="secondary" className="gap-1 pr-1 cursor-pointer hover:bg-secondary/80" onClick={() => removeFilter("deploymentId")}>
                  Deployment: {middleEllipsis(filters.deploymentId, 6, 4)} <X className="h-3 w-3" />
                </Badge>
              )}
              {filters.uniqueId && (
                <Badge variant="secondary" className="gap-1 pr-1 cursor-pointer hover:bg-secondary/80" onClick={() => removeFilter("uniqueId")}>
                  ID: {middleEllipsis(filters.uniqueId, 6, 4)} <X className="h-3 w-3" />
                </Badge>
              )}
              {filters.contractDid && (
                <Badge variant="secondary" className="gap-1 pr-1 cursor-pointer hover:bg-secondary/80" onClick={() => removeFilter("contractDid")}>
                  Contract: {middleEllipsis(filters.contractDid, 6, 4)} <X className="h-3 w-3" />
                </Badge>
              )}
              {filters.fromAddress && (
                <Badge variant="secondary" className="gap-1 pr-1 cursor-pointer hover:bg-secondary/80" onClick={() => removeFilter("fromAddress")}>
                  From: {middleEllipsis(filters.fromAddress, 6, 4)} <X className="h-3 w-3" />
                </Badge>
              )}
              {filters.toAddress && (
                <Badge variant="secondary" className="gap-1 pr-1 cursor-pointer hover:bg-secondary/80" onClick={() => removeFilter("toAddress")}>
                  To: {middleEllipsis(filters.toAddress, 6, 4)} <X className="h-3 w-3" />
                </Badge>
              )}
              {filters.txHash && (
                <Badge variant="secondary" className="gap-1 pr-1 cursor-pointer hover:bg-secondary/80" onClick={() => removeFilter("txHash")}>
                  Tx: {middleEllipsis(filters.txHash, 6, 4)} <X className="h-3 w-3" />
                </Badge>
              )}
            </div>
          )}

          {/* COLLAPSIBLE FILTERS PANEL */}
          <Collapsible open={isFiltersOpen} onOpenChange={setIsFiltersOpen}>
            <CollapsibleContent>
              <Card className="mt-1 mb-4 p-3 md:p-4 border-border shadow-sm">
                <div className="flex flex-col md:flex-row gap-4">
                  {/* Inputs Grid */}
                  <div className="flex-1 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-3 gap-3">
                    <div className="space-y-1">
                      <Label className="text-[11px] text-muted-foreground uppercase tracking-wide">Deployment ID</Label>
                      <Input
                        placeholder="Filter by deployment ID"
                        value={draftFilters.deploymentId}
                        onKeyDown={handleFilterTextKeyDown}
                        onChange={(e) => setDraftFilters(p => ({ ...p, deploymentId: e.target.value }))}
                        className="font-mono text-[12px] h-8 placeholder:text-[12px]"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-[11px] text-muted-foreground uppercase tracking-wide">Unique ID</Label>
                      <Input
                        placeholder="Filter by unique ID"
                        value={draftFilters.uniqueId}
                        onKeyDown={handleFilterTextKeyDown}
                        onChange={(e) => setDraftFilters(p => ({ ...p, uniqueId: e.target.value }))}
                        className="font-mono text-[12px] h-8 placeholder:text-[12px]"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-[11px] text-muted-foreground uppercase tracking-wide">Contract DID</Label>
                      <Input
                        placeholder="Filter by contract DID"
                        value={draftFilters.contractDid}
                        onKeyDown={handleFilterTextKeyDown}
                        onChange={(e) => setDraftFilters(p => ({ ...p, contractDid: e.target.value }))}
                        className="font-mono text-[12px] h-8 placeholder:text-[12px]"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-[11px] text-muted-foreground uppercase tracking-wide">From address</Label>
                      <Input
                        placeholder="Source address"
                        value={draftFilters.fromAddress}
                        onKeyDown={handleFilterTextKeyDown}
                        onChange={(e) => setDraftFilters(p => ({ ...p, fromAddress: e.target.value }))}
                        className="font-mono text-[12px] h-8 placeholder:text-[12px]"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-[11px] text-muted-foreground uppercase tracking-wide">To address</Label>
                      <Input
                        placeholder="Destination address"
                        value={draftFilters.toAddress}
                        onKeyDown={handleFilterTextKeyDown}
                        onChange={(e) => setDraftFilters(p => ({ ...p, toAddress: e.target.value }))}
                        className="font-mono text-[12px] h-8 placeholder:text-[12px]"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-[11px] text-muted-foreground uppercase tracking-wide">Transaction hash</Label>
                      <Input
                        placeholder="On-chain hash"
                        value={draftFilters.txHash}
                        onKeyDown={handleFilterTextKeyDown}
                        onChange={(e) => setDraftFilters(p => ({ ...p, txHash: e.target.value }))}
                        className="font-mono text-[12px] h-8 placeholder:text-[12px]"
                      />
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div className="flex flex-col items-end justify-start gap-2 shrink-0 md:w-32 md:border-l md:border-border/50 md:pl-4 pt-4 md:pt-0 border-t md:border-t-0 border-border/50">
                    <Button size="sm" className="w-full h-8" onClick={handleApplyFilters}>
                      Apply Filters
                    </Button>
                    <Button variant="ghost" size="sm" className="w-full h-8 text-muted-foreground" onClick={handleClearFilters}>
                      Clear Fields
                    </Button>
                  </div>
                </div>
              </Card>
            </CollapsibleContent>
          </Collapsible>

          {/* LIST / CONTENT */}
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
          ) : pageItems.length === 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>Nothing to show</CardTitle>
              </CardHeader>
              <CardContent className="text-muted-foreground">
                Try adjusting the filters
              </CardContent>
            </Card>
          ) : (
            <>
            <div className="grid grid-cols-1 gap-3 lg:gap-3">
              {pageItems.map((p) => {
                const isSending = !!sending[p.unique_id];
                const txHash = sent[p.unique_id];
                const chain = (p.blockchain || "ETHEREUM").toUpperCase();
                const chainConfig = chain === "CARDANO" ? cardanoConfig : ethConfig;
                const explorer = chainConfig?.explorer_base_url && (txHash || p.tx_hash)
                    ? `${chainConfig.explorer_base_url!.replace(/\/$/, "")}/tx/${txHash || p.tx_hash}`
                    : null;
                const requiredWallet = walletTypeForPayment(p);
                const walletProviderMissing = requiredWallet === "ethereum" ? !hasEthereumProvider : requiredWallet === "cardano" ? !hasCardanoProvider : false;
                const recoverableQuote = activeQuotes[p.unique_id];
                const recoverableQuoteExpiry = recoverableQuote ? formatTime(recoverableQuote.expiresAt) : null;
                const walletRestriction = !chainConfig ? "Payment config missing" : requiredWallet && walletProviderMissing ? `${walletDisplayName(requiredWallet)} extension not detected` : null;
                const buttonDisabled = isSending || p.status === "paid" || !chainConfig || Boolean(walletRestriction);

                let buttonLabelOverride: string | null = null;
                if (p.status === "unpaid" && walletRestriction) {
                  if (walletProviderMissing) buttonLabelOverride = requiredWallet === "cardano" ? "Install Eternl" : "Install MetaMask";
                } else if (recoverableQuote && p.status === "unpaid") {
                  buttonLabelOverride = "Resume payment";
                } else if (!chainConfig) {
                  buttonLabelOverride = "Config missing";
                }

                const tokenSymbol = chain === "CARDANO" ? cardanoConfig?.token_symbol ?? "NTX" : ethConfig?.token_symbol ?? "NTX";
                const conversionRequired = isConversionPayment(p);
                const pricingCurrency = (p.pricing_currency ?? "").trim();
                const originalAmount = (p.original_amount ?? p.amount).trim();

                const amountCurrencyLabel = conversionRequired ? (pricingCurrency || "QUOTE") : tokenSymbol;
                const amountValueLabel = conversionRequired ? originalAmount : p.amount;
                const amountSecondaryLabel = conversionRequired ? `Converted to ${tokenSymbol} at pay time` : null;

                const createdAtLabel = formatTime(p.created_at);
                const isExpanded = Boolean(expandedRows[p.unique_id]);

                const detailFields: PaymentDetailField[] = [];
                addDetailField(detailFields, "Unique ID", p.unique_id, "Globally unique transaction identifier.");
                addDetailField(detailFields, "Contract DID", p.contract_did, "Contract decentralized identifier tied to this payment.");
                addDetailField(detailFields, "Validator DID", p.payment_validator_did, "DID of the validator that created/validates this payment.");
                addDetailField(detailFields, "Blockchain", chain, "Target blockchain network for settlement.");
                addDetailField(detailFields, "Status", p.status, "Current settlement status from DMS.");
                addDetailField(detailFields, "Amount", `${amountCurrencyLabel} ${amountValueLabel}`, conversionRequired ? "Original invoice amount in pricing currency. Final payment amount is quoted in payment currency right before payment." : "Invoice amount to be paid.");

                if (conversionRequired) {
                  addDetailField(detailFields, "Requires conversion", "Yes", "Price conversion is required at payment time.");
                  addDetailField(detailFields, "Pricing currency", pricingCurrency || "Unknown", "Stable currency used for invoice pricing.");
                  addDetailField(detailFields, "Original amount", originalAmount, "Amount denominated in pricing currency before conversion.");
                  addDetailField(detailFields, "Payment currency", tokenSymbol, "Token used for blockchain settlement.");
                }

                addDetailField(detailFields, "To Address", p.to_address, "Provider destination address that receives payment.");
                addDetailField(detailFields, "From Address", p.from_address, "Requester/source address associated with this payment.");
                addDetailField(detailFields, "CREATED AT", createdAtLabel, "Transaction creation date.");
                addDetailField(detailFields, "Transaction Hash", txHash || p.tx_hash, "On-chain transaction hash after submission.");

                const metadataFieldDetails = buildMetadataDetailFields(p.metadata);
                const rawMetadata = metadataPrettyJson(p.metadata);

                return (
                  <Collapsible
                    key={p.unique_id}
                    open={isExpanded}
                    onOpenChange={(open) => setExpandedRows((prev) => ({ ...prev, [p.unique_id]: open }))}
                  >
                  <Card
                    data-testid={`payment-card-${p.unique_id}`}
                    data-payment-unique-id={p.unique_id}
                    className="rounded-lg border border-border/60 shadow-sm hover:shadow-md transition p-4 sm:p-5"
                  >
                    <div className="grid grid-cols-1 md:grid-cols-[1.5fr_1.5fr_auto] gap-4 items-start">

                      {/* COLUMN 1: Keys & Addresses */}
                      <div className="flex flex-col space-y-1.5 text-xs min-w-0">
                        <div className="flex items-center gap-1.5 min-w-0">
                          <span className="font-medium text-muted-foreground w-10 shrink-0">ID:</span>
                          <code className="bg-muted px-1.5 py-0.5 rounded font-mono truncate" title={p.unique_id}>
                            {shorten(p.unique_id)}
                          </code>
                          <CopyButton text={p.unique_id} className="shrink-0 h-5 w-5" />
                        </div>

                        {p.from_address && (
                          <div className="flex items-center gap-1.5 min-w-0">
                            <span className="font-medium text-muted-foreground w-10 shrink-0">From:</span>
                            <code className="bg-muted px-1.5 py-0.5 rounded font-mono truncate" title={p.from_address}>
                              {shorten(p.from_address)}
                            </code>
                            <CopyButton text={p.from_address} className="shrink-0 h-5 w-5" />
                          </div>
                        )}

                        <div className="flex items-center gap-1.5 min-w-0">
                          <span className="font-medium text-muted-foreground w-10 shrink-0">To:</span>
                          <code className="bg-muted px-1.5 py-0.5 rounded font-mono truncate" title={p.to_address}>
                            {shorten(p.to_address)}
                          </code>
                          <CopyButton text={p.to_address} className="shrink-0 h-5 w-5" />
                        </div>
                      </div>

                      {/* COLUMN 2: Operations & Data */}
                      <div className="flex flex-col space-y-1.5 text-xs min-w-0">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="font-medium text-muted-foreground w-14 shrink-0 truncate">{amountCurrencyLabel}:</span>
                          <code className="text-green-600 bg-green-500/10 px-1.5 py-0.5 rounded text-xs font-semibold truncate">
                            {amountValueLabel}
                          </code>
                          {amountSecondaryLabel && (
                            <span className="text-[10px] text-muted-foreground w-full sm:w-auto mt-1 sm:mt-0">{amountSecondaryLabel}</span>
                          )}
                        </div>

                        {requiredWallet && (
                          <div className="flex items-center gap-1.5">
                            <span className="font-medium text-muted-foreground w-14 shrink-0">Wallet:</span>
                            <Badge variant="outline" className="font-normal text-[12px] px-1 py-0 h-4">{walletDisplayName(requiredWallet)}</Badge>
                          </div>
                        )}

                        {createdAtLabel && (
                          <div className="flex items-center gap-1.5">
                            <span className="font-medium text-muted-foreground w-14 shrink-0">Created:</span>
                            <span className="text-foreground text-[12px]">{createdAtLabel}</span>
                          </div>
                        )}

                        {(txHash || p.tx_hash) && (
                           <div className="flex items-center gap-1.5 min-w-0">
                             <span className="font-medium text-muted-foreground w-14 shrink-0">TxHash:</span>
                             <code className="bg-muted px-1.5 py-0.5 rounded font-mono truncate" title={txHash || p.tx_hash}>
                               {shorten(txHash || p.tx_hash)}
                             </code>
                             {explorer && (
                                <a href={explorer} target="_blank" rel="noreferrer" className="text-primary hover:underline text-[10px] ml-1" title="View on explorer">
                                  View
                                </a>
                             )}
                           </div>
                        )}

                        {recoverableQuote && (
                          <div className="flex items-center gap-1.5">
                            <span className="font-medium text-muted-foreground w-14 shrink-0">Quote:</span>
                            <span className="text-[10px] text-muted-foreground">
                              Ready {recoverableQuoteExpiry ? `(expires ${recoverableQuoteExpiry})` : ""}
                            </span>
                          </div>
                        )}
                      </div>

                      {/* COLUMN 3: Actions */}
                      <div className="flex flex-col items-start md:items-end justify-between h-full gap-3 mt-2 md:mt-0">
                        <Button
                          size="sm"
                          className="w-full md:w-auto h-8 px-4 text-xs"
                          onClick={() => handlePay(p)}
                          disabled={buttonDisabled}
                          title={walletRestriction ?? undefined}
                        >
                          {isSending ? (
                            <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Sending...</>
                          ) : p.status === "unpaid" ? (
                            buttonLabelOverride ? buttonLabelOverride : <><Send className="mr-2 h-3.5 w-3.5" /> Pay Now</>
                          ) : (
                            <><CheckCheckIcon className="mr-2 h-4 w-4" /> Paid</>
                          )}
                        </Button>

                        <CollapsibleTrigger asChild>
                          <Button variant="ghost" size="sm" className="h-8 px-2 text-xs w-full md:w-auto md:ml-auto">
                            Details
                            <ChevronDown className={cn("ml-1 h-3.5 w-3.5 transition-transform", isExpanded && "rotate-180")} />
                          </Button>
                        </CollapsibleTrigger>
                      </div>

                    </div>

                    <CollapsibleContent>
                      <Separator className="my-4" />
                      <div className="pt-2">
                        <div className="mb-3 flex items-center gap-2">
                          <h3 className="text-sm font-medium">Payment Details</h3>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <button type="button" className="inline-flex items-center text-muted-foreground">
                                <CircleHelp className="h-4 w-4" />
                              </button>
                            </TooltipTrigger>
                            <TooltipContent side="top" className="max-w-xs text-xs">
                              Expanded fields include transaction metadata and allocation-level breakdown used for invoicing.
                            </TooltipContent>
                          </Tooltip>
                        </div>
                        {detailFields.length > 0 && (
                          <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
                            {detailFields.map((field) => <DetailFieldRow key={`${p.unique_id}-${field.label}`} field={field} />)}
                          </div>
                        )}
                        {metadataFieldDetails.length > 0 && (
                          <>
                            <div className="mt-4 mb-3 flex items-center gap-2">
                              <h4 className="text-sm font-medium">Metadata Fields</h4>
                            </div>
                            <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
                              {metadataFieldDetails.map((field, idx) => <DetailFieldRow key={`${p.unique_id}-meta-${idx}-${field.label}`} field={field} />)}
                            </div>
                          </>
                        )}
                        {rawMetadata && (
                          <div className="mt-4 rounded border border-border/60 bg-muted/10 p-3">
                            <div className="mb-2 flex items-center gap-1 text-[11px] uppercase tracking-wide text-muted-foreground">
                              <span>Raw Metadata JSON</span>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <button type="button" className="inline-flex items-center"><CircleHelp className="h-3.5 w-3.5" /></button>
                                </TooltipTrigger>
                                <TooltipContent side="top" className="max-w-xs text-xs">Full metadata payload returned by DMS for this payment.</TooltipContent>
                              </Tooltip>
                            </div>
                            <pre className="max-h-72 overflow-auto rounded bg-background p-2 text-xs">{rawMetadata}</pre>
                          </div>
                        )}
                      </div>
                    </CollapsibleContent>
                  </Card>
                  </Collapsible>
                );
              })}
            </div>

            <div className="flex justify-between items-center mt-6">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((old) => Math.max(old - 1, 1))}
                disabled={page === 1}
              >
                Previous
              </Button>
              <span className="text-sm text-muted-foreground">
                Page {page} of {totalPages}
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
        </div>
      </div>

      <Dialog open={Boolean(quoteConfirmation)} onOpenChange={(open) => { if (!open && quoteConfirmation && !quoteConfirming) void handleCancelQuoteConfirmation(); }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Confirm conversion quote</DialogTitle>
            <DialogDescription>Review conversion details before opening your wallet.</DialogDescription>
          </DialogHeader>
          {quoteConfirmation && (
            <div className="space-y-2 text-sm">
              <div className="rounded border border-border/60 bg-muted/20 p-3">
                <div className="text-xs uppercase tracking-wide text-muted-foreground">Transaction</div>
                <div className="font-mono text-xs break-all">{quoteConfirmation.payment.unique_id}</div>
              </div>
              <div className="rounded border border-border/60 bg-muted/20 p-3">
                <div className="text-xs uppercase tracking-wide text-muted-foreground">Original amount</div>
                <div className="font-semibold">{quoteConfirmation.quote.pricingCurrency || "USDT"} {quoteConfirmation.quote.originalAmount}</div>
              </div>
              <div className="rounded border border-border/60 bg-muted/20 p-3">
                <div className="text-xs uppercase tracking-wide text-muted-foreground">Payment amount</div>
                <div className="font-semibold">{quoteConfirmation.quote.paymentCurrency || "NTX"} {quoteConfirmation.quote.convertedAmount}</div>
                {quoteConfirmation.quote.exchangeRate && <div className="text-xs text-muted-foreground mt-1">Exchange rate: {quoteConfirmation.quote.exchangeRate}</div>}
                {quoteConfirmation.quote.expiresAt && <div className="text-xs text-muted-foreground mt-1">Expires: {formatTime(quoteConfirmation.quote.expiresAt) ?? quoteConfirmation.quote.expiresAt}</div>}
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => void handleCancelQuoteConfirmation()} disabled={quoteConfirming}>Cancel</Button>
            <Button onClick={() => void handleConfirmQuotePayment()} disabled={quoteConfirming}>
              {quoteConfirming ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Processing</> : "Continue to wallet"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(quoteIssue)} onOpenChange={(open) => !open && setQuoteIssue(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Quote validation failed</DialogTitle>
            <DialogDescription>{quoteIssue?.message ?? "Unable to continue with this quote."}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setQuoteIssue(null)}>Cancel</Button>
            <Button onClick={() => { const pending = quoteIssue; setQuoteIssue(null); if (pending) void handlePay(pending.payment); }}>Try again</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
