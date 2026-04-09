import * as React from "react";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import type {
  ContractMetadata,
  ContractResourceCPU,
  ContractResourceDisk,
  ContractResourceMemory,
  ContractStateResponse,
  ContractTerminatePayload,
} from "@/api/contracts";
import { AlertTriangle, Loader2, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { DidDisplay } from "@/components/contracts/DidDisplay";
import { CopyButton } from "@/components/ui/CopyButton";

const SIGNED_STATES = new Set(["ACCEPTED", "APPROVED", "SIGNED"]);

export interface ContractDetailsDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  baseContract?: ContractMetadata | null;
  state?: ContractStateResponse | null;
  isLoading?: boolean;
  error?: string | null;
  onRefresh?: () => void;
  onTerminate?: (payload: ContractTerminatePayload) => void;
  isTerminating?: boolean;
}

function normalizeTimestampToMs(value: unknown): number | null {
  if (value == null) {
    return null;
  }

  if (value instanceof Date) {
    const time = value.getTime();
    return Number.isNaN(time) ? null : time;
  }

  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      return null;
    }
    const abs = Math.abs(value);
    if (abs === 0) {
      return 0;
    }
    if (abs < 1e12) {
      return Math.trunc(value * 1000);
    }
    if (abs < 1e15) {
      return Math.trunc(value);
    }
    if (abs < 1e18) {
      return Math.trunc(value / 1_000);
    }
    return Math.trunc(value / 1_000_000);
  }

  if (typeof value === "bigint") {
    const abs = value < 0n ? -value : value;
    if (abs === 0n) {
      return 0;
    }
    if (abs < 1_000_000_000_000n) {
      return Number(value) * 1000;
    }
    if (abs < 1_000_000_000_000_000n) {
      return Number(value);
    }
    if (abs < 1_000_000_000_000_000_000n) {
      return Number(value / 1_000n);
    }
    return Number(value / 1_000_000n);
  }

  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) {
      return null;
    }

    const parsed = Date.parse(trimmed);
    if (!Number.isNaN(parsed)) {
      return parsed;
    }

    const numeric = Number(trimmed);
    if (Number.isFinite(numeric)) {
      return normalizeTimestampToMs(numeric);
    }

    return null;
  }

  return null;
}

function formatDate(value?: string | number | Date | bigint | null) {
  if (value == null) return null;

  const timestampMs = normalizeTimestampToMs(value);
  if (timestampMs == null) {
    if (typeof value === "string") {
      return value;
    }
    return null;
  }

  const date = new Date(timestampMs);
  if (Number.isNaN(date.getTime())) {
    if (typeof value === "string") {
      return value;
    }
    return null;
  }

  return date.toLocaleString();
}

function formatNoticePeriodNanoseconds(value?: number | null): string | null {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    return null;
  }

  const secondsTotal = value / 1e9;
  if (secondsTotal === 0) {
    return "0 seconds";
  }

  const units = [
    { label: "day", seconds: 86400 },
    { label: "hour", seconds: 3600 },
    { label: "minute", seconds: 60 },
    { label: "second", seconds: 1 },
  ];

  const parts: string[] = [];
  let remaining = secondsTotal;

  for (const unit of units) {
    if (remaining >= unit.seconds) {
      const count = Math.floor(remaining / unit.seconds);
      remaining -= count * unit.seconds;
      parts.push(`${count} ${unit.label}${count === 1 ? "" : "s"}`);
    }
    if (parts.length >= 2) {
      break;
    }
  }

  if (parts.length === 0) {
    return "< 1 second";
  }

  return parts.join(" ");
}

function formatDurationRange(start?: string | null, end?: string | null): string | null {
  if (!start && !end) {
    return null;
  }

  const parsedStart = start ? new Date(start) : null;
  const parsedEnd = end ? new Date(end) : null;

  const startValid = parsedStart && !Number.isNaN(parsedStart.getTime());
  const endValid = parsedEnd && !Number.isNaN(parsedEnd.getTime());

  const formatter = new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  const segments: string[] = [];
  if (startValid) {
    segments.push(formatter.format(parsedStart));
  } else if (start) {
    segments.push(start);
  }
  if (endValid) {
    segments.push(formatter.format(parsedEnd));
  } else if (end) {
    segments.push(end);
  }

  const range = segments.join(" -> ");

  if (startValid && endValid) {
    const deltaMs = parsedEnd.getTime() - parsedStart.getTime();
    if (deltaMs > 0) {
      const totalSeconds = Math.floor(deltaMs / 1000);
      const days = Math.floor(totalSeconds / 86400);
      const hours = Math.floor((totalSeconds % 86400) / 3600);
      const minutes = Math.floor((totalSeconds % 3600) / 60);

      const durationParts: string[] = [];
      if (days) durationParts.push(`${days} day${days === 1 ? "" : "s"}`);
      if (hours && durationParts.length < 2) durationParts.push(`${hours} hour${hours === 1 ? "" : "s"}`);
      if (minutes && durationParts.length < 2) durationParts.push(`${minutes} minute${minutes === 1 ? "" : "s"}`);

      if (durationParts.length === 0 && totalSeconds > 0) {
        durationParts.push("< 1 minute");
      }

      if (durationParts.length > 0) {
        return `${range} (${durationParts.join(", ")})`;
      }
    }
  }

  return range || null;
}

type PaymentAddressView = {
  requester_addr?: string | null;
  provider_addr?: string | null;
  currency?: string | null;
  blockchain?: string | null;
};

type PaymentDetailsView = {
  payment_type?: string | null;
  payment_model?: string | null;
  requester_addr?: string | null;
  provider_addr?: string | null;
  currency?: string | null;
  pricing_currency?: string | null;
  fees_per_allocation?: string | null;
  fee_per_deployment?: string | null;
  fee_per_time_unit?: string | null;
  time_unit?: string | null;
  fee_per_cpu_core_per_time_unit?: string | null;
  fee_per_ram_gb_per_time_unit?: string | null;
  fee_per_disk_gb_per_time_unit?: string | null;
  fee_per_gpu_per_time_unit?: string | null;
  resource_time_unit?: string | null;
  fixed_rental_amount?: string | null;
  payment_period?: string | null;
  payment_period_count?: number | string | null;
  blockchain?: string | null;
  timestamp?: string | number | Date | bigint | null;
  addresses?: PaymentAddressView[];
};

function normalizeDisplayValue(value: unknown): string | null {
  if (value == null) {
    return null;
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : null;
  }
  return String(value);
}

function hasDisplayValue(value: unknown): boolean {
  if (value == null) {
    return false;
  }
  if (typeof value === "string") {
    return value.trim().length > 0;
  }
  if (typeof value === "number") {
    return Number.isFinite(value);
  }
  return true;
}

function toDisplayText(value: unknown): string | null {
  if (!hasDisplayValue(value)) {
    return null;
  }
  return typeof value === "string" ? value : String(value);
}

function pickFirstValue(details: Record<string, unknown>, ...keys: string[]): unknown {
  for (const key of keys) {
    if (!key) continue;
    if (Object.prototype.hasOwnProperty.call(details, key)) {
      const value = details[key];
      if (typeof value === "string") {
        if (value.trim().length === 0) {
          continue;
        }
        return value;
      }
      if (value !== undefined && value !== null) {
        return value;
      }
    }
  }
  return undefined;
}

function extractPaymentDetails(
  contract: ContractMetadata | null | undefined,
  rawState: unknown
): PaymentDetailsView | null {
  return (
    extractPaymentDetailsFromSource(contract?.payment_details) ??
    extractPaymentDetailsFromSource(contract) ??
    extractPaymentDetailsFromSource(rawState) ??
    (rawState && typeof rawState === "object"
      ? extractPaymentDetailsFromSource((rawState as Record<string, unknown>).contract)
      : null)
  );
}

function isTerminationAllowed(contract?: ContractMetadata | null): boolean {
  if (!contract) return false;
  if (contract.current_state === "TERMINATED") {
    return false;
  }
  if (contract.termination_option && contract.termination_option.allowed === false) {
    return false;
  }
  return true;
}

function getDefaultHostDid(contract?: ContractMetadata | null): string {
  if (!contract) return "";
  return (
    contract.solution_enabler_did?.uri ??
    contract.payment_validator_did?.uri ??
    contract.participants?.provider?.uri ??
    ""
  );
}

function extractTransitions(source: unknown): unknown[] {
  if (!source) {
    return [];
  }
  if (Array.isArray(source)) {
    return source;
  }
  if (typeof source === "object" && source !== null) {
    const withTransitions = source as { transitions?: unknown };
    if (Array.isArray(withTransitions.transitions)) {
      return withTransitions.transitions;
    }
  }
  return [];
}

function getTransitionInitiator(transition: Record<string, unknown>): string | null {
  const raw = transition?.initiated_by;
  if (raw && typeof raw === "object" && "uri" in raw && typeof (raw as { uri?: unknown }).uri === "string") {
    const uri = (raw as { uri: string }).uri.trim();
    if (uri.length > 0) {
      return uri;
    }
  }
  return null;
}

function normalizePaymentAddress(entry: unknown): PaymentAddressView | null {
  if (!entry || typeof entry !== "object") {
    return null;
  }
  const record = entry as Record<string, unknown>;
  const requester = pickFirstValue(record, "requester_addr", "requesterAddress", "requestor_addr", "requestorAddress");
  const provider = pickFirstValue(record, "provider_addr", "providerAddress");
  const currency = pickFirstValue(record, "currency", "token");
  const blockchain = pickFirstValue(record, "blockchain", "chain");
  if (requester == null && provider == null && currency == null && blockchain == null) {
    return null;
  }
  return {
    requester_addr: normalizeDisplayValue(requester),
    provider_addr: normalizeDisplayValue(provider),
    currency: normalizeDisplayValue(currency),
    blockchain: normalizeDisplayValue(blockchain),
  };
}

function extractPaymentAddresses(details: Record<string, unknown>): PaymentAddressView[] {
  const candidate = pickFirstValue(details, "addresses", "payment_addresses", "paymentAddresses");
  const addresses: PaymentAddressView[] = [];
  if (Array.isArray(candidate)) {
    for (const entry of candidate) {
      const normalized = normalizePaymentAddress(entry);
      if (normalized) {
        addresses.push(normalized);
      }
    }
  } else {
    const normalized = normalizePaymentAddress(candidate);
    if (normalized) {
      addresses.push(normalized);
    }
  }
  return addresses;
}

function toPaymentDetailsView(detailsSource: unknown): PaymentDetailsView | null {
  if (!detailsSource || typeof detailsSource !== "object") {
    return null;
  }
  const details = detailsSource as Record<string, unknown>;
  const addresses = extractPaymentAddresses(details);
  const primary = addresses[0];
  const paymentType = pickFirstValue(details, "payment_type", "paymentType");
  const paymentModel = pickFirstValue(details, "payment_model", "paymentModel");
  const requester = pickFirstValue(details, "requester_addr", "requesterAddress", "requestor_addr", "requestorAddress");
  const provider = pickFirstValue(details, "provider_addr", "providerAddress");
  const currency = pickFirstValue(details, "currency", "token");
  const pricingCurrency = pickFirstValue(details, "pricing_currency", "pricingCurrency");
  const blockchain = pickFirstValue(details, "blockchain", "chain");
  const feesPerAllocation = pickFirstValue(details, "fees_per_allocation", "fee_per_allocation", "feesPerAllocation");
  const feePerDeployment = pickFirstValue(details, "fee_per_deployment", "feePerDeployment");
  const feePerTimeUnit = pickFirstValue(details, "fee_per_time_unit", "feePerTimeUnit");
  const timeUnit = pickFirstValue(details, "time_unit", "timeUnit");
  const feePerCpuCore = pickFirstValue(details, "fee_per_cpu_core_per_time_unit", "feePerCpuCorePerTimeUnit");
  const feePerRamGb = pickFirstValue(details, "fee_per_ram_gb_per_time_unit", "feePerRamGbPerTimeUnit");
  const feePerDiskGb = pickFirstValue(details, "fee_per_disk_gb_per_time_unit", "feePerDiskGbPerTimeUnit");
  const feePerGpu = pickFirstValue(details, "fee_per_gpu_per_time_unit", "feePerGpuPerTimeUnit");
  const resourceTimeUnit = pickFirstValue(details, "resource_time_unit", "resourceTimeUnit");
  const fixedRentalAmount = pickFirstValue(details, "fixed_rental_amount", "fixedRentalAmount");
  const paymentPeriod = pickFirstValue(details, "payment_period", "paymentPeriod");
  const paymentPeriodCount = pickFirstValue(details, "payment_period_count", "paymentPeriodCount");
  const timestamp = pickFirstValue(details, "timestamp", "payment_timestamp", "time");
  const hasDetails = [
    paymentType,
    paymentModel,
    requester,
    provider,
    currency,
    pricingCurrency,
    blockchain,
    feesPerAllocation,
    feePerDeployment,
    feePerTimeUnit,
    timeUnit,
    feePerCpuCore,
    feePerRamGb,
    feePerDiskGb,
    feePerGpu,
    resourceTimeUnit,
    fixedRentalAmount,
    paymentPeriod,
    paymentPeriodCount,
    timestamp,
  ].some((value) => value !== undefined && value !== null);
  if (!hasDetails && addresses.length === 0) {
    return null;
  }
  return {
    payment_type: normalizeDisplayValue(paymentType),
    payment_model: normalizeDisplayValue(paymentModel),
    requester_addr: normalizeDisplayValue(requester) ?? primary?.requester_addr ?? null,
    provider_addr: normalizeDisplayValue(provider) ?? primary?.provider_addr ?? null,
    currency: normalizeDisplayValue(currency) ?? primary?.currency ?? null,
    pricing_currency: normalizeDisplayValue(pricingCurrency),
    fees_per_allocation: normalizeDisplayValue(feesPerAllocation),
    fee_per_deployment: normalizeDisplayValue(feePerDeployment),
    fee_per_time_unit: normalizeDisplayValue(feePerTimeUnit),
    time_unit: normalizeDisplayValue(timeUnit),
    fee_per_cpu_core_per_time_unit: normalizeDisplayValue(feePerCpuCore),
    fee_per_ram_gb_per_time_unit: normalizeDisplayValue(feePerRamGb),
    fee_per_disk_gb_per_time_unit: normalizeDisplayValue(feePerDiskGb),
    fee_per_gpu_per_time_unit: normalizeDisplayValue(feePerGpu),
    resource_time_unit: normalizeDisplayValue(resourceTimeUnit),
    fixed_rental_amount: normalizeDisplayValue(fixedRentalAmount),
    payment_period: normalizeDisplayValue(paymentPeriod),
    payment_period_count: normalizeDisplayValue(paymentPeriodCount),
    blockchain: normalizeDisplayValue(blockchain) ?? primary?.blockchain ?? null,
    timestamp,
    addresses,
  };
}

function extractPaymentDetailsFromSource(source: unknown): PaymentDetailsView | null {
  if (!source || typeof source !== "object") {
    return null;
  }
  const record = source as Record<string, unknown>;
  const fromSelf = toPaymentDetailsView(record);
  if (fromSelf) {
    return fromSelf;
  }
  const rawDetails = pickFirstValue(record, "payment_details", "paymentDetails");
  const fromDetails = toPaymentDetailsView(rawDetails);
  if (fromDetails) {
    return fromDetails;
  }
  const contractRequest = pickFirstValue(record, "contract_request", "contractRequest");
  if (contractRequest) {
    return extractPaymentDetailsFromSource(contractRequest);
  }
  return null;
}

function InfoRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1">
      <span className="text-xs uppercase tracking-wide text-muted-foreground">{label}</span>
      <div className="text-sm">{children}</div>
    </div>
  );
}

function Section({
  title,
  children,
  className,
  actions,
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
  actions?: React.ReactNode;
}) {
  return (
    <section className={cn("space-y-3 rounded-md border border-border/40 p-4", className)}>
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold">{title}</h3>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </div>
      <div className="grid gap-3 text-sm">{children}</div>
    </section>
  );
}

export function ContractDetailsDrawer({
  open,
  onOpenChange,
  baseContract,
  state,
  isLoading,
  error,
  onRefresh,
  onTerminate,
  isTerminating,
}: ContractDetailsDrawerProps) {
  const mergedContract = state?.contract ?? baseContract ?? undefined;
  const rawState = state?.raw ?? null;
  const transitions = React.useMemo<unknown[]>(() => {
    const contractTransitions = extractTransitions(mergedContract);
    if (contractTransitions.length > 0) {
      return contractTransitions;
    }
    const rawLevelTransitions = extractTransitions(rawState);
    if (rawLevelTransitions.length > 0) {
      return rawLevelTransitions;
    }
    if (rawState && typeof rawState === "object") {
      const nestedContract = (rawState as { contract?: unknown }).contract;
      const nestedTransitions = extractTransitions(nestedContract);
      if (nestedTransitions.length > 0) {
        return nestedTransitions;
      }
    }
    return [];
  }, [mergedContract, rawState]);
  const paymentDetails = React.useMemo(
    () => extractPaymentDetails(mergedContract, rawState),
    [mergedContract, rawState]
  );
  const paymentRows = React.useMemo(() => {
    if (!paymentDetails) {
      return [];
    }
    const rows: Array<{ label: string; content: React.ReactNode }> = [];
    const addTextRow = (label: string, value: unknown) => {
      const text = toDisplayText(value);
      if (text) {
        rows.push({ label, content: text });
      }
    };
    const addDidRow = (label: string, value: unknown) => {
      if (hasDisplayValue(value)) {
        rows.push({ label, content: <DidDisplay value={String(value)} muted /> });
      }
    };
    const formattedTimestamp = formatDate(paymentDetails.timestamp);

    addTextRow("Payment model", paymentDetails.payment_model);
    addTextRow("Payment type", paymentDetails.payment_type);
    addTextRow("Payment period", paymentDetails.payment_period);
    addTextRow("Payment period count", paymentDetails.payment_period_count);
    addTextRow("Currency", paymentDetails.currency);
    addTextRow("Pricing currency", paymentDetails.pricing_currency);
    addDidRow("Requester address", paymentDetails.requester_addr);
    addDidRow("Provider address", paymentDetails.provider_addr);
    addTextRow("Fees per allocation", paymentDetails.fees_per_allocation);
    addTextRow("Fee per deployment", paymentDetails.fee_per_deployment);
    addTextRow("Fee per time unit", paymentDetails.fee_per_time_unit);
    addTextRow("Time unit", paymentDetails.time_unit);
    addTextRow("Fixed rental amount", paymentDetails.fixed_rental_amount);
    addTextRow("CPU fee per time unit", paymentDetails.fee_per_cpu_core_per_time_unit);
    addTextRow("RAM fee per time unit", paymentDetails.fee_per_ram_gb_per_time_unit);
    addTextRow("Disk fee per time unit", paymentDetails.fee_per_disk_gb_per_time_unit);
    addTextRow("GPU fee per time unit", paymentDetails.fee_per_gpu_per_time_unit);
    addTextRow("Resource time unit", paymentDetails.resource_time_unit);
    addTextRow("Blockchain", paymentDetails.blockchain);
    if (formattedTimestamp) {
      rows.push({ label: "Timestamp", content: formattedTimestamp });
    }

    return rows;
  }, [paymentDetails]);
  const durationStart = formatDate(mergedContract?.duration?.start_date);
  const durationEnd = formatDate(mergedContract?.duration?.end_date);
  const resourceConfiguration = mergedContract?.resource_configuration ?? null;
  const defaultHostDid = getDefaultHostDid(mergedContract);
  const [confirmingTerminate, setConfirmingTerminate] = React.useState(false);
  const [hostDid, setHostDid] = React.useState(defaultHostDid);
  const [hostDidError, setHostDidError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (open) {
      setHostDid(defaultHostDid);
      setHostDidError(null);
      setConfirmingTerminate(false);
    } else {
      setConfirmingTerminate(false);
    }
  }, [open, defaultHostDid]);

  React.useEffect(() => {
    if (!onTerminate) {
      setConfirmingTerminate(false);
    }
  }, [onTerminate]);

  const hasDetails = Boolean(mergedContract);
  const showRaw = rawState;
  const rawPayloadString = React.useMemo(() => {
    if (!showRaw) {
      return null;
    }
    try {
      return JSON.stringify(showRaw, null, 2);
    } catch {
      return String(showRaw);
    }
  }, [showRaw]);
  const canTerminate = Boolean(onTerminate) && isTerminationAllowed(mergedContract);
  const requiresConfirmation = mergedContract ? SIGNED_STATES.has(mergedContract.current_state ?? "") : false;

  React.useEffect(() => {
    if (!canTerminate) {
      setConfirmingTerminate(false);
    }
  }, [canTerminate]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl lg:max-w-4xl max-h-[calc(100vh-3rem)] overflow-hidden p-0">
        <div className="flex max-h-[inherit] flex-col gap-0">
          <DialogHeader className="gap-3 px-6 pt-6">
            <div className="flex flex-col gap-1 text-left">
              <DialogTitle>Contract details</DialogTitle>
              <DialogDescription>
                Review contract metadata, participants, and lifecycle events.
              </DialogDescription>
            </div>

            {mergedContract ? (
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline" className="uppercase">
                  {mergedContract.current_state}
                </Badge>
                <DidDisplay value={mergedContract.contract_did} />
              </div>
            ) : null}
          </DialogHeader>

          <div className="flex-1 space-y-4 overflow-y-auto px-6 pb-6 pr-7">
            {isLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-6 w-1/2" />
                <Skeleton className="h-40 w-full" />
              </div>
            ) : null}

            {!isLoading && error ? (
              <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {error}
              </div>
            ) : null}

            {!isLoading && !error && !hasDetails ? (
              <div className="text-sm text-muted-foreground">
                Select a contract to inspect its detailed state.
              </div>
            ) : null}

            {!isLoading && !error && hasDetails ? (
            <div className="space-y-4">
              <Section title="Lifecycle">
                <div className="grid gap-3 md:grid-cols-2">
                  <InfoRow label="Current state">
                    <Badge variant="outline" className="uppercase">
                      {mergedContract?.current_state ?? "UNKNOWN"}
                    </Badge>
                  </InfoRow>
                  <InfoRow label="Termination allowed">
                    {mergedContract?.termination_option?.allowed === false ? "No" : "Yes"}
                  </InfoRow>
                  <InfoRow label="Notice period">
                    {formatNoticePeriodNanoseconds(mergedContract?.termination_option?.notice_period) ?? "--"}
                  </InfoRow>
                  <InfoRow label="Duration">
                    {formatDurationRange(mergedContract?.duration?.start_date, mergedContract?.duration?.end_date) ?? "--"}
                  </InfoRow>
                  <InfoRow label="Payment status">
                    {mergedContract?.paid === true
                      ? "Paid"
                      : mergedContract?.paid === false
                      ? "Unpaid"
                      : "Unknown"}
                    {" | "}
                    {mergedContract?.settled ? "Settled" : "Unsettled"}
                  </InfoRow>
                </div>
              </Section>

              <Section title="Participants">
                <div className="grid gap-3 md:grid-cols-2">
                  <InfoRow label="Requester">
                    <DidDisplay value={mergedContract?.participants?.requestor?.uri ?? null} muted />
                  </InfoRow>
                  <InfoRow label="Provider">
                    <DidDisplay value={mergedContract?.participants?.provider?.uri ?? null} muted />
                  </InfoRow>
                  <InfoRow label="Contract host DID">
                    <DidDisplay value={mergedContract?.solution_enabler_did?.uri ?? null} muted />
                  </InfoRow>
                  <InfoRow label="Payment validator DID">
                    <DidDisplay value={mergedContract?.payment_validator_did?.uri ?? null} muted />
                  </InfoRow>
                </div>
              </Section>

              <Section title="Resource configuration">
                {resourceConfiguration ? (
                  <div className="grid gap-3 md:grid-cols-3">
                    <InfoRow label="CPU">
                      {formatCpuDetails(resourceConfiguration.cpu) ?? "--"}
                    </InfoRow>
                    <InfoRow label="Memory">
                      {formatMemoryDetails(resourceConfiguration.ram) ?? "--"}
                    </InfoRow>
                    <InfoRow label="Disk">
                      {formatDiskDetails(resourceConfiguration.disk) ?? "--"}
                    </InfoRow>
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">No resource configuration provided.</p>
                )}
              </Section>

              <Section title="Payment details">
                {paymentRows.length ? (
                  <div className="grid gap-3 md:grid-cols-2">
                    {paymentRows.map((row) => (
                      <InfoRow key={row.label} label={row.label}>
                        {row.content}
                      </InfoRow>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">No payment details available.</p>
                )}
              </Section>

                            <Section title="Transition history">
                {transitions.length === 0 ? (
                  <p className="text-xs text-muted-foreground">No recorded transitions yet.</p>
                ) : (
                  <ol className="space-y-3">
                    {transitions.map((transition, index) => {
                      const transitionRecord = (transition ?? {}) as Record<string, unknown>;
                      const event = typeof transitionRecord.event === "string" ? transitionRecord.event : "Transition";
                      const timestamp = formatDate(
                        typeof transitionRecord.timestamp === "string" ? transitionRecord.timestamp : undefined,
                      );
                      const fromState =
                        typeof transitionRecord.from_state === "string" ? transitionRecord.from_state : "--";
                      const toState =
                        typeof transitionRecord.to_state === "string" ? transitionRecord.to_state : "--";
                      const initiator = getTransitionInitiator(transitionRecord);

                      const stateBadgeVariants = {
                        DRAFT: "secondary",
                        ACCEPTED: "default",
                        APPROVED: "default",
                        SIGNED: "default",
                        COMPLETED: "default",
                        SETTLED: "default",
                        TERMINATED: "destructive",
                        EXPIRED: "destructive",
                        REJECTED: "destructive",
                        CANCELLED: "secondary",
                      } as const;

                      const fromVariant =
                        stateBadgeVariants[(fromState as keyof typeof stateBadgeVariants) ?? "DRAFT"] ?? "outline";
                      const toVariant =
                        stateBadgeVariants[(toState as keyof typeof stateBadgeVariants) ?? "DRAFT"] ?? "outline";

                      return (
                        <li
                          key={`${fromState}-${toState}-${index}`}
                          className="rounded-lg border border-border/60 bg-muted/10 p-3 shadow-sm"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex items-center gap-2 text-sm font-semibold">
                              <Badge variant="outline" className="text-xs uppercase">
                                {index + 1}
                              </Badge>
                              <span>{event}</span>
                            </div>
                            <span className="text-xs text-muted-foreground">{timestamp ?? "--"}</span>
                          </div>
                          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                            <Badge variant={fromVariant} className="uppercase">
                              {fromState}
                            </Badge>
                            <span className="text-muted-foreground">-&gt;</span>
                            <Badge variant={toVariant} className="uppercase">
                              {toState}
                            </Badge>
                          </div>
                          {initiator ? (
                            <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                              <span>Initiated by</span>
                              <DidDisplay value={initiator} muted textClassName="text-[11px]" />
                            </div>
                          ) : null}
                        </li>
                      );
                    })}
                  </ol>
                )}
              </Section>

              {canTerminate && confirmingTerminate ? (
                <div className="space-y-3 rounded-md border border-destructive/40 bg-destructive/10 p-4">
                  <div className="flex items-center gap-2 text-destructive">
                    <AlertTriangle className="h-4 w-4" />
                    <span className="text-sm font-semibold">Confirm termination</span>
                  </div>
                  <p className="text-xs text-destructive/90">
                    {requiresConfirmation
                      ? "This contract is active. Termination notifies the host and cannot be undone."
                      : "Terminating this contract cannot be undone."}
                  </p>
                  <div className="space-y-2">
                    <label
                      htmlFor="contract-host-did"
                      className="text-xs font-medium uppercase tracking-wide text-destructive"
                    >
                      Contract host DID
                    </label>
                    <Input
                      id="contract-host-did"
                      value={hostDid}
                      onChange={(event) => {
                        setHostDid(event.target.value);
                        setHostDidError(null);
                      }}
                      placeholder="did:key:..."
                      autoComplete="off"
                    />
                    {hostDidError ? <p className="text-xs text-destructive">{hostDidError}</p> : null}
                  </div>
                  <div className="flex flex-wrap justify-end gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setConfirmingTerminate(false);
                        setHostDid(defaultHostDid);
                        setHostDidError(null);
                      }}
                    >
                      Cancel
                    </Button>
                    <Button
                      type="button"
                      variant="destructive"
                      size="sm"
                      onClick={() => {
                        if (!onTerminate || !mergedContract) {
                          setConfirmingTerminate(false);
                          return;
                        }
                        const trimmed = hostDid.trim();
                        if (!trimmed) {
                          setHostDidError("Host DID is required.");
                          return;
                        }
                        setHostDidError(null);
                        onTerminate({ contract_did: mergedContract.contract_did, contract_host_did: trimmed });
                        setConfirmingTerminate(false);
                      }}
                      disabled={Boolean(isTerminating)}
                      className="gap-2"
                    >
                      {isTerminating ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                      {isTerminating ? "Terminating..." : "Confirm terminate"}
                    </Button>
                  </div>
                </div>
              ) : null}

              {showRaw ? (
                <Section
                  title="Raw payload"
                  actions={
                    rawPayloadString ? <CopyButton text={rawPayloadString} className="h-7 w-7" /> : null
                  }
                >
                  <pre className="max-h-60 overflow-auto rounded-md bg-muted/30 p-3 text-xs">
                    {rawPayloadString ?? ""}
                  </pre>
                </Section>
              ) : null}
            </div>
          ) : null}
          </div>

          <DialogFooter className="mt-0 flex flex-wrap gap-2 border-t border-border/40 px-6 py-4 sm:justify-end">
            {canTerminate ? (
              <Button
                type="button"
                variant="destructive"
                size="sm"
                onClick={() => {
                  if (confirmingTerminate) {
                    setConfirmingTerminate(false);
                    setHostDid(defaultHostDid);
                    setHostDidError(null);
                  } else {
                    setConfirmingTerminate(true);
                    setHostDid(defaultHostDid);
                    setHostDidError(null);
                  }
                }}
                disabled={Boolean(isTerminating)}
                className="gap-2"
              >
                {isTerminating ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                {confirmingTerminate ? "Hide confirmation" : "Terminate"}
              </Button>
            ) : null}
            {onRefresh ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => onRefresh()}
                disabled={isLoading}
                className="gap-2"
              >
                {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                Refresh state
              </Button>
            ) : null}
            <DialogClose asChild>
              <Button variant="secondary" size="sm">
                Close
              </Button>
            </DialogClose>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function formatCpuDetails(cpu?: ContractResourceCPU | null): string | null {
  if (!cpu) {
    return null;
  }

  const coresValue = typeof cpu.cores === "number" && cpu.cores > 0 ? cpu.cores : null;
  const clock = typeof cpu.clock_speed === "number" && cpu.clock_speed > 0 ? cpu.clock_speed : null;

  const parts: string[] = [];
  if (coresValue !== null) {
    parts.push(`${coresValue} core${coresValue === 1 ? "" : "s"}`);
  }

  if (clock !== null) {
    let formatted = `${clock} MHz`;
    if (clock >= 1000) {
      const ghz = clock / 1000;
      formatted = `${parseFloat(ghz.toFixed(2))} GHz`;
    }
    parts.push(formatted);
  }

  if (parts.length === 0) {
    return null;
  }
  return parts.join(" · ");
}

function formatCapacityMB(value?: number | null): string | null {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
    return null;
  }

  if (value >= 1024) {
    const gb = value / 1024;
    const normalized = parseFloat(gb.toFixed(gb % 1 === 0 ? 0 : 2));
    return `${normalized} GB (${value} MB)`;
  }

  return `${value} MB`;
}

function formatDiskDetails(disk?: ContractResourceDisk | null): string | null {
  if (!disk) {
    return null;
  }
  return formatCapacityMB(disk.size);
}

function formatMemoryDetails(memory?: ContractResourceMemory | null): string | null {
  if (!memory) {
    return null;
  }
  return formatCapacityMB(memory.size);
}






