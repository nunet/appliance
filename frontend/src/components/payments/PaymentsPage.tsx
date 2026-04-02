"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
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
import { CheckCheckIcon, ChevronDown, CircleHelp, Loader2, RefreshCw, Send, Wallet } from "lucide-react";
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

function readActiveQuotesFromStorage(): Record<string, StoredPaymentQuote> {
  try {
    const raw = localStorage.getItem(ACTIVE_QUOTES_STORAGE_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return {};
    }
    const output: Record<string, StoredPaymentQuote> = {};
    for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (!value || typeof value !== "object" || Array.isArray(value)) {
        continue;
      }
      const entry = value as Record<string, unknown>;
      const uniqueId = typeof entry.uniqueId === "string" ? entry.uniqueId.trim() : "";
      const quoteId = typeof entry.quoteId === "string" ? entry.quoteId.trim() : "";
      if (!key.trim() || !uniqueId || !quoteId) {
        continue;
      }
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
  } catch {
    // best effort only
  }
}

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

function inferWalletType(address: string): WalletType | null {
  const value = address?.trim() ?? "";
  if (/^0x[a-fA-F0-9]{40}$/.test(value)) {
    return "ethereum";
  }
  if (/^(addr|stake)[0-9a-z]+$/i.test(value)) {
    return "cardano";
  }
  return null;
}

function walletDisplayName(type: WalletType) {
  return type === "ethereum" ? "MetaMask" : "Eternl";
}

function isConversionPayment(item: DmsPaymentItem): boolean {
  if (typeof item.requires_conversion === "boolean") {
    return item.requires_conversion;
  }

  // Backward-compatibility fallback for older payloads that may omit
  // requires_conversion but still include pricing/original amount fields.
  const pricingCurrency = (item.pricing_currency ?? "").trim();
  if (!pricingCurrency) {
    return false;
  }

  const originalAmount = (item.original_amount ?? "").trim();
  if (!originalAmount) {
    return true;
  }

  const convertedAmount = (item.amount ?? "").trim();
  if (!convertedAmount) {
    return true;
  }

  const originalNum = Number(originalAmount);
  const convertedNum = Number(convertedAmount);
  if (Number.isFinite(originalNum) && Number.isFinite(convertedNum)) {
    return originalNum !== convertedNum;
  }

  return originalAmount !== convertedAmount;
}

function extractQuoteId(message: string): string | null {
  const match = message.match(/quote[_\s-]?id[:=]\s*([A-Za-z0-9._:-]+)/i);
  return match?.[1] ?? null;
}

function getRawErrorMessage(error: unknown): string {
  const errorLike = error as {
    response?: { data?: { detail?: unknown; message?: string } };
    message?: string;
  };
  const detail = errorLike?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (detail && typeof detail === "object" && "message" in detail) {
    const nestedMessage = (detail as { message?: unknown }).message;
    if (typeof nestedMessage === "string" && nestedMessage.trim()) {
      return nestedMessage;
    }
  }
  const message = errorLike?.response?.data?.message;
  if (typeof message === "string" && message.trim()) {
    return message;
  }
  return errorLike?.message || "Something went wrong";
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : null;
}

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim().length > 0) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
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
  if (!raw) {
    return null;
  }
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) {
    return raw;
  }
  return parsed.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function pluralize(count: number, singular: string, plural?: string): string {
  const noun = count === 1 ? singular : (plural ?? `${singular}s`);
  return `${count} ${noun}`;
}

function summarizePaymentMetadata(metadata: DmsPaymentMetadata | null | undefined): string[] {
  const data = asRecord(metadata);
  if (!data) {
    return [];
  }

  const details: string[] = [];
  const deploymentId = asString(data.deployment_id);
  if (deploymentId) {
    details.push(`deployment ${deploymentId}`);
  }

  const allocationCount = asNumber(data.allocation_count);
  const allocationsRaw = Array.isArray(data.allocations) ? data.allocations : [];
  const allocations = allocationsRaw.map(asRecord).filter(Boolean) as Record<string, unknown>[];
  const allocationIds = allocations
    .map((entry) => asString(entry.allocation_id))
    .filter(Boolean) as string[];
  if (allocationIds.length > 0) {
    const preview = allocationIds.slice(0, 2).map((id) => middleEllipsis(id, 12, 6)).join(", ");
    const suffix = allocationIds.length > 2 ? ` +${allocationIds.length - 2}` : "";
    details.push(`allocations ${preview}${suffix}`);
  } else if (allocationCount !== null) {
    details.push(pluralize(allocationCount, "allocation"));
  }

  const totalUtilizationSec = asNumber(data.total_utilization_sec);
  if (totalUtilizationSec !== null) {
    details.push(`runtime ${formatDuration(totalUtilizationSec)}`);
  }

  const deploymentCount = asNumber(data.deployment_count);
  if (deploymentCount !== null) {
    details.push(pluralize(deploymentCount, "deployment"));
  }

  const periodsInvoiced = asNumber(data.periods_invoiced);
  if (periodsInvoiced !== null) {
    details.push(`${pluralize(periodsInvoiced, "period")} invoiced`);
  }

  const periodStart = formatTime(data.period_start);
  const periodEnd = formatTime(data.period_end);
  if (periodStart || periodEnd) {
    details.push(`period ${periodStart ?? "?"} to ${periodEnd ?? "?"}`);
  }

  const lastInvoiceAt = formatTime(data.last_invoice_at);
  if (lastInvoiceAt) {
    details.push(`last invoice ${lastInvoiceAt}`);
  }

  return details;
}

function metadataSearchText(value: unknown): string {
  const tokens: string[] = [];

  const walk = (current: unknown): void => {
    if (current === null || current === undefined) {
      return;
    }
    if (typeof current === "string" || typeof current === "number" || typeof current === "boolean") {
      tokens.push(String(current).toLowerCase());
      return;
    }
    if (Array.isArray(current)) {
      current.forEach(walk);
      return;
    }
    const record = asRecord(current);
    if (!record) {
      return;
    }
    Object.entries(record).forEach(([key, nested]) => {
      tokens.push(key.toLowerCase());
      walk(nested);
    });
  };

  walk(value);
  return tokens.join(" ");
}

type PaymentDetailField = {
  label: string;
  value: string;
  tooltip: string;
};

function addDetailField(
  fields: PaymentDetailField[],
  label: string,
  value: unknown,
  tooltip: string,
): void {
  if (value === null || value === undefined) {
    return;
  }
  const text = typeof value === "string" ? value.trim() : String(value);
  if (!text) {
    return;
  }
  fields.push({ label, value: text, tooltip });
}

function buildMetadataDetailFields(metadata: DmsPaymentMetadata | null | undefined): PaymentDetailField[] {
  const data = asRecord(metadata);
  if (!data) {
    return [];
  }

  const fields: PaymentDetailField[] = [];

  addDetailField(fields, "Deployment ID", asString(data.deployment_id), "Deployment identifier associated with this payment.");
  addDetailField(fields, "Allocation Count", asNumber(data.allocation_count), "Number of allocations included in this payment.");
  addDetailField(fields, "Deployment Count", asNumber(data.deployment_count), "Number of deployments invoiced in this payment.");

  const totalUtilization = asNumber(data.total_utilization_sec);
  if (totalUtilization !== null) {
    addDetailField(
      fields,
      "Total Runtime",
      `${formatDuration(totalUtilization)} (${totalUtilization.toFixed(6)} sec)`,
      "Total resource utilization duration used to calculate this payment.",
    );
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
      addDetailField(
        fields,
        `${prefix} Runtime`,
        `${formatDuration(duration)} (${duration.toFixed(6)} sec)`,
        "Runtime duration for this allocation.",
      );
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
  if (!data) {
    return null;
  }
  try {
    return JSON.stringify(data, null, 2);
  } catch {
    return null;
  }
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
type StatusFilter = "all" | "paid" | "unpaid";
const PAYMENTS_LIST_REFRESH_MS = 60 * 60 * 1000; // 1 hour

export default function PaymentsPage() {
  const [search, setSearch] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [sending, setSending] = useState<Record<string, boolean>>({});
  const [sent, setSent] = useState<Record<string, string>>({});
  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({});
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [activeQuotes, setActiveQuotes] = useState<Record<string, StoredPaymentQuote>>(() =>
    readActiveQuotesFromStorage()
  );
  const [quoteConfirmation, setQuoteConfirmation] = useState<QuoteConfirmationState | null>(null);
  const [quoteConfirming, setQuoteConfirming] = useState(false);
  const [quoteIssue, setQuoteIssue] = useState<QuoteIssueState | null>(null);
  const recoveryCheckedRef = useRef(false);

  const activeWalletType = useWalletStore((state) => state.active);
  const walletConnections = useWalletStore((state) => state.connections);
  const setWalletConnection = useWalletStore((state) => state.setConnection);
  const activateWallet = useWalletStore((state) => state.activate);

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
    staleTime: PAYMENTS_LIST_REFRESH_MS,
    gcTime: PAYMENTS_LIST_REFRESH_MS,
    refetchInterval: autoRefresh ? PAYMENTS_LIST_REFRESH_MS : false,
    refetchOnWindowFocus: false,
  });

  const config = cfgQ.data as PaymentsConfig | undefined;
  const list = listQ.data;
  const ethConfig = config?.ethereum;
  const cardanoConfig = config?.cardano;

  const ignoredToastRef = useRef<number | null>(null);

  useEffect(() => {
    const ignoredCount = list?.ignored_count ?? 0;
    if (ignoredCount > 0 && ignoredToastRef.current !== ignoredCount) {
      const plural = ignoredCount === 1 ? "" : "s";
      toast.warning(`${ignoredCount} transaction${plural} skipped due to incomplete DMS data.`);
      ignoredToastRef.current = ignoredCount;
      return;
    }
    if (ignoredToastRef.current !== ignoredCount) {
      ignoredToastRef.current = ignoredCount;
    }
  }, [list?.ignored_count]);

  const items = useMemo(() => list?.items ?? [], [list?.items]);

  useEffect(() => {
    writeActiveQuotesToStorage(activeQuotes);
  }, [activeQuotes]);

  useEffect(() => {
    if (!list || recoveryCheckedRef.current) {
      return;
    }
    recoveryCheckedRef.current = true;

    const runRecovery = async () => {
      const entries = Object.values(activeQuotes);
      if (entries.length === 0) {
        return;
      }
      const unpaidIds = new Set(
        items.filter((entry) => entry.status === "unpaid").map((entry) => entry.unique_id)
      );
      const paymentsById = new Map(items.map((entry) => [entry.unique_id, entry]));

      const recovered: Record<string, StoredPaymentQuote> = {};
      for (const quote of entries) {
        if (!unpaidIds.has(quote.uniqueId)) {
          continue;
        }
        const payment = paymentsById.get(quote.uniqueId);
        const validatorDid = (payment?.payment_validator_did ?? "").trim();
        if (!validatorDid) {
          toast.info(`Recovered quote ${quote.quoteId} is missing validator DID and was cancelled.`);
          continue;
        }
        try {
          const validation = await validatePaymentQuote({
            quote_id: quote.quoteId,
            dest: validatorDid,
          });
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
  }, [activeQuotes, items, list]);

  const errorToastStyles = {
    className: "text-white [&_*]:!text-white",
    descriptionClassName: "text-white/80",
    style: { color: "#fff", "--normal-text": "#fff", "--error-text": "#fff" },
  };

  const filtered = useMemo(() => {
    const term = search.toLowerCase();
    return items.filter((p) => {
      const metadataText = metadataSearchText(p.metadata);
      const matchesSearch =
        !term ||
        p.unique_id.toLowerCase().includes(term) ||
        p.to_address.toLowerCase().includes(term) ||
        (p.from_address ?? "").toLowerCase().includes(term) ||
        p.status.toLowerCase().includes(term) ||
        (p.blockchain ?? "").toLowerCase().includes(term) ||
        (p.pricing_currency ?? "").toLowerCase().includes(term) ||
        (p.original_amount ?? "").toLowerCase().includes(term) ||
        metadataText.includes(term);
      const matchesStatus =
        statusFilter === "all" ? true : p.status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  }, [items, search, statusFilter]);

  const hasEthereumProvider =
    typeof window !== "undefined" &&
    Boolean((window as unknown as { ethereum?: { request?: unknown } }).ethereum?.request);
  const hasCardanoProvider =
    typeof window !== "undefined" &&
    Boolean((window as unknown as { cardano?: { eternl?: unknown } }).cardano?.eternl);

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
      if (!Object.prototype.hasOwnProperty.call(prev, uniqueId)) {
        return prev;
      }
      const next = { ...prev };
      delete next[uniqueId];
      return next;
    });
  }

  async function cancelQuoteForValidator(quoteId: string, validatorDid: string): Promise<void> {
    const normalizedDid = (validatorDid ?? "").trim();
    if (!normalizedDid) {
      return;
    }
    await cancelPaymentQuote({ quote_id: quoteId, dest: normalizedDid }).catch(() => {});
  }

  async function executePayment(
    p: DmsPaymentItem,
    amountToPay: string,
    quoteId?: string
  ): Promise<boolean> {
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
      toast.error("MetaMask extension not detected", {
        ...errorToastStyles,
        description: "Install MetaMask to continue with Ethereum payments.",
      });
      return false;
    }
    if (requiredWallet === "cardano" && !hasCardanoProvider) {
      toast.error("Eternl extension not detected", {
        ...errorToastStyles,
        description: "Install Eternl to continue with Cardano payments.",
      });
      return false;
    }

    try {
      setSending((s) => ({ ...s, [p.unique_id]: true }));

      if (isCardano) {
        let connection = walletConnections.cardano;
        let api = connection?.cardanoApi as { signTx?: (tx: string, partialSign?: boolean) => Promise<string> } | undefined;
        if (!connection || !api?.signTx) {
          const namespace = getEternlNamespace();
          if (!namespace) {
            throw new Error("Eternl wallet not found");
          }
          const enabledApi = await namespace.enable();
          connection = await buildCardanoConnection(enabledApi);
          setWalletConnection("cardano", connection);
          activateWallet("cardano");
          api = connection.cardanoApi as { signTx?: (tx: string, partialSign?: boolean) => Promise<string> } | undefined;
        }
        if (!connection || !api?.signTx) {
          throw new Error("Cardano wallet connection missing");
        }

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

        toast.success("Transaction sent", {
          description: chainConfig.explorer_base_url ? `Tx: ${txHash}` : undefined,
        });
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

        toast.success("Transaction sent", {
          description: chainConfig.explorer_base_url ? `Tx: ${hash}` : undefined,
        });
      }

      listQ.refetch();
      return true;
    } catch (err: unknown) {
      const rawMessage = getRawErrorMessage(err);

      const toAda = (lovelace: number | string | null | undefined) => {
        const n = Number(lovelace);
        if (Number.isFinite(n) && n > 0) {
          return `${(n / 1_000_000).toFixed(3)} ADA`;
        }
        return null;
      };

      const formatError = (msg: string): string => {
        const lovelaceMatch = msg.match(/have\s+(\d+)\s+lovelace.*need\s*>=\s*(\d+).*min-utxo\s+(\d+)/i);
        if (lovelaceMatch) {
          const [, have, need, min] = lovelaceMatch;
          const haveAda = toAda(have);
          const needAda = toAda(need);
          const minAda = toAda(min);
          return `Not enough ADA to send. You have ${haveAda ?? have}, need at least ${needAda ?? need} (min-utxo ${minAda ?? min}).`;
        }
        const tokenMatch = msg.match(/Insufficient token balance.*have\s+([0-9]+(?:\.[0-9]+)?),\s*need\s+([0-9]+(?:\.[0-9]+)?)/i);
        if (tokenMatch) {
          const [, haveT, needT] = tokenMatch;
          return `Not enough NTX to cover the payment (have ${haveT}, need ${needT}).`;
        }
        if (msg.includes("0xe450d38c")) {
          return "Not enough NTX to cover this payment in the currently connected MetaMask account.";
        }
        return msg;
      };

      const friendlyMessage = formatError(String(rawMessage));
      console.error(err);
      toast.error("Payment failed", {
        ...errorToastStyles,
        description: friendlyMessage,
      });
      return false;
    } finally {
      setSending((s) => ({ ...s, [p.unique_id]: false }));
    }
  }

  async function validateStoredQuoteForPayment(
    p: DmsPaymentItem,
    quote: StoredPaymentQuote
  ): Promise<StoredPaymentQuote | null> {
    const validatorDid = (p.payment_validator_did ?? "").trim();
    if (!validatorDid) {
      removeActiveQuote(p.unique_id);
      setQuoteIssue({
        payment: p,
        message: "Missing payment validator DID for quote validation.",
      });
      return null;
    }
    try {
      const validation = await validatePaymentQuote({
        quote_id: quote.quoteId,
        dest: validatorDid,
      });
      if (!validation.valid) {
        await cancelQuoteForValidator(quote.quoteId, validatorDid);
        removeActiveQuote(p.unique_id);
        setQuoteIssue({
          payment: p,
          message: validation.error || "Quote expired or is no longer valid.",
        });
        return null;
      }

      const convertedAmount = (validation.converted_amount ?? quote.convertedAmount).trim();
      if (!convertedAmount) {
        await cancelQuoteForValidator(quote.quoteId, validatorDid);
        removeActiveQuote(p.unique_id);
        setQuoteIssue({
          payment: p,
          message: "Quote did not include a converted amount.",
        });
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
      setQuoteIssue({
        payment: p,
        message: getRawErrorMessage(error),
      });
      return null;
    }
  }

  async function prepareConversionQuote(p: DmsPaymentItem): Promise<StoredPaymentQuote | null> {
    const chain = (p.blockchain || "ETHEREUM").toUpperCase();
    const chainConfig = chain === "CARDANO" ? cardanoConfig : ethConfig;
    const tokenSymbol = chainConfig?.token_symbol ?? "NTX";
    const validatorDid = (p.payment_validator_did ?? "").trim();
    if (!validatorDid) {
      setQuoteIssue({
        payment: p,
        message: "Missing payment validator DID for quote request.",
      });
      return null;
    }

    const fetchQuote = async () => {
      try {
        return await getPaymentQuote({
          unique_id: p.unique_id,
          dest: validatorDid,
        });
      } catch (error) {
        const message = getRawErrorMessage(error);
        const activeQuoteId = extractQuoteId(message);
        if (activeQuoteId) {
          await cancelQuoteForValidator(activeQuoteId, validatorDid);
          return getPaymentQuote({
            unique_id: p.unique_id,
            dest: validatorDid,
          });
        }
        throw error;
      }
    };

    try {
      const quote = await fetchQuote();
      const validation = await validatePaymentQuote({
        quote_id: quote.quote_id,
        dest: validatorDid,
      });
      if (!validation.valid) {
        await cancelQuoteForValidator(quote.quote_id, validatorDid);
        setQuoteIssue({
          payment: p,
          message: validation.error || "Quote expired or is no longer valid.",
        });
        return null;
      }

      const convertedAmount = (validation.converted_amount ?? quote.converted_amount ?? "").trim();
      if (!convertedAmount) {
        await cancelQuoteForValidator(quote.quote_id, validatorDid);
        setQuoteIssue({
          payment: p,
          message: "Quote did not include a converted amount.",
        });
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
      setQuoteIssue({
        payment: p,
        message: getRawErrorMessage(error),
      });
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
      if (validatedQuote) {
        setQuoteConfirmation({ payment: p, quote: validatedQuote });
      }
      return;
    }

    const preparedQuote = await prepareConversionQuote(p);
    if (preparedQuote) {
      setQuoteConfirmation({ payment: p, quote: preparedQuote });
    }
  }

  async function handleConfirmQuotePayment() {
    if (!quoteConfirmation) {
      return;
    }
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
    if (!quoteConfirmation) {
      return;
    }
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
              {activeWalletType && (
                <Badge variant="outline" className="text-xs font-normal">
                  {walletConnections[activeWalletType]?.provider ?? walletDisplayName(activeWalletType)}
                </Badge>
              )}

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
                const chain = (p.blockchain || "ETHEREUM").toUpperCase();
                const chainConfig = chain === "CARDANO" ? cardanoConfig : ethConfig;
                const explorer =
                  chainConfig?.explorer_base_url && (txHash || p.tx_hash)
                    ? `${chainConfig.explorer_base_url!.replace(/\/$/, "")}/tx/${txHash || p.tx_hash}`
                    : null;
                const requiredWallet = walletTypeForPayment(p);
                const walletProviderMissing =
                  requiredWallet === "ethereum"
                    ? !hasEthereumProvider
                    : requiredWallet === "cardano"
                    ? !hasCardanoProvider
                    : false;
                const recoverableQuote = activeQuotes[p.unique_id];
                const recoverableQuoteExpiry = recoverableQuote ? formatTime(recoverableQuote.expiresAt) : null;
                const walletRestriction =
                  !chainConfig
                    ? "Payment config missing"
                    : requiredWallet && walletProviderMissing
                    ? `${walletDisplayName(requiredWallet)} extension not detected`
                    : null;
                const buttonDisabled =
                  isSending || p.status === "paid" || !chainConfig || Boolean(walletRestriction);
                let buttonLabelOverride: string | null = null;
                if (p.status === "unpaid" && walletRestriction) {
                  if (walletProviderMissing) {
                    buttonLabelOverride = requiredWallet === "cardano" ? "Install Eternl" : "Install MetaMask";
                  }
                } else if (recoverableQuote && p.status === "unpaid") {
                  buttonLabelOverride = "Resume payment";
                } else if (!chainConfig) {
                  buttonLabelOverride = "Config missing";
                }
                const tokenSymbol =
                  chain === "CARDANO"
                    ? cardanoConfig?.token_symbol ?? "NTX"
                    : ethConfig?.token_symbol ?? "NTX";
                const conversionRequired = isConversionPayment(p);
                const pricingCurrency = (p.pricing_currency ?? "").trim();
                const originalAmount = (p.original_amount ?? p.amount).trim();
                const amountPrimaryLabel = conversionRequired
                  ? `${pricingCurrency || "QUOTE"} ${originalAmount}`
                  : `${tokenSymbol} ${p.amount}`;
                const amountSecondaryLabel = conversionRequired
                  ? `Converted to ${tokenSymbol} at pay time`
                  : null;
                const metadataDetails = summarizePaymentMetadata(p.metadata);
                const metadataSummary = metadataDetails.join(" | ");
                const detailFields: PaymentDetailField[] = [];
                addDetailField(detailFields, "Unique ID", p.unique_id, "Globally unique transaction identifier.");
                addDetailField(detailFields, "Contract DID", p.contract_did, "Contract decentralized identifier tied to this payment.");
                addDetailField(detailFields, "Validator DID", p.payment_validator_did, "DID of the validator that created/validates this payment.");
                addDetailField(detailFields, "Blockchain", chain, "Target blockchain network for settlement.");
                addDetailField(detailFields, "Status", p.status, "Current settlement status from DMS.");
                addDetailField(
                  detailFields,
                  "Amount",
                  amountPrimaryLabel,
                  conversionRequired
                    ? "Original invoice amount in pricing currency. Final payment amount is quoted in payment currency right before payment."
                    : "Invoice amount to be paid."
                );
                if (conversionRequired) {
                  addDetailField(detailFields, "Requires conversion", "Yes", "Price conversion is required at payment time.");
                  addDetailField(detailFields, "Pricing currency", pricingCurrency || "Unknown", "Stable currency used for invoice pricing.");
                  addDetailField(detailFields, "Original amount", originalAmount, "Amount denominated in pricing currency before conversion.");
                  addDetailField(detailFields, "Payment currency", tokenSymbol, "Token used for blockchain settlement.");
                }
                addDetailField(detailFields, "To Address", p.to_address, "Provider destination address that receives payment.");
                addDetailField(detailFields, "From Address", p.from_address, "Requester/source address associated with this payment.");
                addDetailField(detailFields, "Transaction Hash", txHash || p.tx_hash, "On-chain transaction hash after submission.");

                const metadataFieldDetails = buildMetadataDetailFields(p.metadata);
                const rawMetadata = metadataPrettyJson(p.metadata);
                const isExpanded = Boolean(expandedRows[p.unique_id]);

                return (
                  <Collapsible
                    key={p.unique_id}
                    open={isExpanded}
                    onOpenChange={(open) =>
                      setExpandedRows((prev) => ({ ...prev, [p.unique_id]: open }))
                    }
                  >
                  <Card
                    data-testid={`payment-card-${p.unique_id}`}
                    data-payment-unique-id={p.unique_id}
                    className="rounded-lg border border-border/60 shadow-sm hover:shadow-md transition"
                  >
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
                              {p.from_address && (
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="font-medium text-foreground">From:</span>
                                  <code
                                    className="bg-muted px-2 py-1 rounded truncate max-w-[260px] md:max-w-none"
                                    title={p.from_address}
                                  >
                                    {middleEllipsis(p.from_address, 12, 6)}
                                  </code>
                                  <CopyButton text={p.from_address} />
                                </div>
                              )}
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="font-medium text-foreground">Amount:</span>
                                <code className="bg-muted px-2 py-1 rounded text-green-500">
                                  {amountPrimaryLabel}
                                </code>
                                {amountSecondaryLabel && (
                                  <span className="text-xs text-muted-foreground">{amountSecondaryLabel}</span>
                                )}
                              </div>
                              {recoverableQuote && (
                                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                                  <span>Recovered quote ready</span>
                                  {recoverableQuoteExpiry && <span>expires {recoverableQuoteExpiry}</span>}
                                </div>
                              )}
                              {requiredWallet && (
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="font-medium text-foreground">Wallet:</span>
                                  <Badge variant="outline">
                                    {walletDisplayName(requiredWallet)}
                                  </Badge>
                                </div>
                              )}
                              {metadataDetails.length > 0 && (
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="font-medium text-foreground">Details:</span>
                                  <span
                                    data-testid="payment-metadata-summary"
                                    className="text-xs text-muted-foreground break-all"
                                    title={metadataSummary}
                                  >
                                    {metadataSummary}
                                  </span>
                                </div>
                              )}
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
                              disabled={buttonDisabled}
                              title={walletRestriction ?? undefined}
                            >
                              {isSending ? (
                                <>
                                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                  Sending...
                                </>
                              ) : p.status === "unpaid" ? (
                                buttonLabelOverride ? (
                                  buttonLabelOverride
                                ) : (
                                  <>
                                    <Send className="mr-2 h-4 w-4" />
                                    Pay Now
                                  </>
                                )
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
                            {p.from_address && (
                              <>
                                <span className="ml-3 text-[10px] uppercase tracking-wide text-muted-foreground">
                                  From
                                </span>
                                <code
                                  className="bg-muted px-1 py-0.5 rounded text-xs font-mono"
                                  title={p.from_address}
                                >
                                  {middleEllipsis(p.from_address, 10, 6)}
                                </code>
                                <CopyButton text={p.from_address} className="shrink-0" />
                              </>
                            )}
                            <span className="ml-3 text-[10px] uppercase tracking-wide text-muted-foreground">
                              Amount
                            </span>
                            <code className="bg-muted px-1 py-0.5 rounded text-green-600 text-xs">
                              {amountPrimaryLabel}
                            </code>
                            {amountSecondaryLabel && (
                              <span className="text-[10px] text-muted-foreground">{amountSecondaryLabel}</span>
                            )}
                            {recoverableQuote && (
                              <span className="text-[10px] text-muted-foreground">
                                recovered quote{recoverableQuoteExpiry ? ` (expires ${recoverableQuoteExpiry})` : ""}
                              </span>
                            )}
                            {requiredWallet && (
                              <>
                                <span className="ml-3 text-[10px] uppercase tracking-wide text-muted-foreground">
                                  Wallet
                                </span>
                                <Badge variant="outline" className="text-[10px]">
                                  {walletDisplayName(requiredWallet)}
                                </Badge>
                              </>
                            )}
                            {metadataDetails.length > 0 && (
                              <>
                                <span className="ml-3 text-[10px] uppercase tracking-wide text-muted-foreground">
                                  Details
                                </span>
                                <span
                                  data-testid="payment-metadata-summary"
                                  className="max-w-[280px] truncate text-xs text-muted-foreground"
                                  title={metadataSummary}
                                >
                                  {metadataSummary}
                                </span>
                              </>
                            )}
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
                            disabled={buttonDisabled}
                            title={walletRestriction ?? undefined}
                          >
                            {isSending ? (
                              <>
                                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                                Sending...
                              </>
                            ) : p.status === "unpaid" ? (
                              buttonLabelOverride ? (
                                buttonLabelOverride
                              ) : (
                                <>
                                  <Send className="mr-1.5 h-4 w-4" />
                                  Pay Now
                                </>
                              )
                            ) : (
                              <>
                                <CheckCheckIcon className="mr-1.5 h-4 w-4" />
                                Paid
                              </>
                            )}
                          </Button>
                        </div>
                      </div>

                      <div className="mt-2 flex justify-end">
                        <CollapsibleTrigger asChild>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 px-2 text-xs"
                            data-testid="payment-toggle-details"
                            title="Show detailed transaction and metadata fields"
                          >
                            Details
                            <ChevronDown className={cn("ml-1 h-3.5 w-3.5 transition-transform", isExpanded && "rotate-180")} />
                          </Button>
                        </CollapsibleTrigger>
                      </div>
                    </CardHeader>

                    <CollapsibleContent>
                      <CardContent className="px-3 pb-3 pt-0 sm:px-4 lg:px-5">
                        <div className="mb-2 flex items-center gap-2">
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
                            {detailFields.map((field) => (
                              <DetailFieldRow key={`${p.unique_id}-${field.label}`} field={field} />
                            ))}
                          </div>
                        )}

                        {metadataFieldDetails.length > 0 && (
                          <>
                            <div className="mt-3 mb-2 flex items-center gap-2">
                              <h4 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                                Metadata Fields
                              </h4>
                            </div>
                            <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
                              {metadataFieldDetails.map((field, idx) => (
                                <DetailFieldRow key={`${p.unique_id}-meta-${idx}-${field.label}`} field={field} />
                              ))}
                            </div>
                          </>
                        )}

                        {rawMetadata && (
                          <div className="mt-3 rounded border border-border/60 bg-muted/10 p-2">
                            <div className="mb-2 flex items-center gap-1 text-[11px] uppercase tracking-wide text-muted-foreground">
                              <span>Raw Metadata JSON</span>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <button type="button" className="inline-flex items-center">
                                    <CircleHelp className="h-3.5 w-3.5" />
                                  </button>
                                </TooltipTrigger>
                                <TooltipContent side="top" className="max-w-xs text-xs">
                                  Full metadata payload returned by DMS for this payment.
                                </TooltipContent>
                              </Tooltip>
                            </div>
                            <pre className="max-h-72 overflow-auto rounded bg-background p-2 text-xs">
                              {rawMetadata}
                            </pre>
                          </div>
                        )}
                      </CardContent>
                    </CollapsibleContent>
                  </Card>
                  </Collapsible>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <Dialog
        open={Boolean(quoteConfirmation)}
        onOpenChange={(open) => {
          if (!open && quoteConfirmation && !quoteConfirming) {
            void handleCancelQuoteConfirmation();
          }
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Confirm conversion quote</DialogTitle>
            <DialogDescription>
              Review conversion details before opening your wallet.
            </DialogDescription>
          </DialogHeader>
          {quoteConfirmation && (
            <div className="space-y-2 text-sm">
              <div className="rounded border border-border/60 bg-muted/20 p-3">
                <div className="text-xs uppercase tracking-wide text-muted-foreground">Transaction</div>
                <div className="font-mono text-xs break-all">{quoteConfirmation.payment.unique_id}</div>
              </div>
              <div className="rounded border border-border/60 bg-muted/20 p-3">
                <div className="text-xs uppercase tracking-wide text-muted-foreground">Original amount</div>
                <div className="font-semibold">
                  {quoteConfirmation.quote.pricingCurrency || "USDT"} {quoteConfirmation.quote.originalAmount}
                </div>
              </div>
              <div className="rounded border border-border/60 bg-muted/20 p-3">
                <div className="text-xs uppercase tracking-wide text-muted-foreground">Payment amount</div>
                <div className="font-semibold">
                  {quoteConfirmation.quote.paymentCurrency || "NTX"} {quoteConfirmation.quote.convertedAmount}
                </div>
                {quoteConfirmation.quote.exchangeRate && (
                  <div className="text-xs text-muted-foreground mt-1">
                    Exchange rate: {quoteConfirmation.quote.exchangeRate}
                  </div>
                )}
                {quoteConfirmation.quote.expiresAt && (
                  <div className="text-xs text-muted-foreground mt-1">
                    Expires: {formatTime(quoteConfirmation.quote.expiresAt) ?? quoteConfirmation.quote.expiresAt}
                  </div>
                )}
              </div>
            </div>
          )}
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                void handleCancelQuoteConfirmation();
              }}
              disabled={quoteConfirming}
            >
              Cancel
            </Button>
            <Button
              onClick={() => {
                void handleConfirmQuotePayment();
              }}
              disabled={quoteConfirming}
            >
              {quoteConfirming ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Processing
                </>
              ) : (
                "Continue to wallet"
              )}
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
            <Button variant="outline" onClick={() => setQuoteIssue(null)}>
              Cancel
            </Button>
            <Button
              onClick={() => {
                const pending = quoteIssue;
                setQuoteIssue(null);
                if (pending) {
                  void handlePay(pending.payment);
                }
              }}
            >
              Try again
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
