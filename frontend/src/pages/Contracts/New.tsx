import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { AxiosError } from "axios";
import {
  ContractCreatePayload,
  ContractTemplateDetail,
  ContractTemplateSummary,
  contractsApi,
} from "@/api/contracts";
import { getDmsStatus } from "@/api/api";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { RefreshCw, ArrowLeft, ArrowRight, FilePlus2 } from "lucide-react";
import { toast } from "sonner";

type ContractWizardStep = "select" | "configure" | "review";
const DMS_STATUS_CACHE_MS = 24 * 60 * 60 * 1000; // 24 hours

interface ContractFormState {
  solutionEnablerDid: string;
  paymentValidatorDid: string;
  providerDid: string;
  requestorDid: string;
  cpuCores: string;
  cpuClockSpeed: string;
  ramSize: string;
  diskSize: string;
  terminationAllowed: boolean;
  terminationNotice: string;
  paymentRequesterAddr: string;
  paymentProviderAddr: string;
  paymentCurrency: string;
  paymentPricingCurrency: string;
  paymentBlockchain: string;
  paymentType: string;
  paymentModel: string;
  paymentFeesPerAllocation: string;
  paymentFeePerDeployment: string;
  paymentFeePerTimeUnit: string;
  paymentTimeUnit: string;
  paymentFeePerCpuCorePerTimeUnit: string;
  paymentFeePerRamGbPerTimeUnit: string;
  paymentFeePerDiskGbPerTimeUnit: string;
  paymentFeePerGpuPerTimeUnit: string;
  paymentResourceTimeUnit: string;
  paymentFixedRentalAmount: string;
  paymentPeriod: string;
  paymentPeriodCount: string;
  contractTerms: string;
  durationStart: string;
  durationEnd: string;
  extraArgs: string;
}

const PAYMENT_TYPE_OPTIONS = [
  { value: "blockchain", label: "Blockchain" },
  { value: "fiat", label: "Fiat" },
] as const;

const BLOCKCHAIN_OPTIONS = ["UNKNOWN", "ETHEREUM", "POLYGON", "BSC", "CARDANO"] as const;

const TIME_UNIT_OPTIONS = ["second", "minute", "hour"] as const;
const PAYMENT_PERIOD_OPTIONS = ["minute", "hour", "day", "week", "month"] as const;

const PAYMENT_MODEL_OPTIONS = [
  { value: "pay_per_allocation", label: "Pay per allocation" },
  { value: "pay_per_deployment", label: "Pay per deployment" },
  { value: "pay_per_time_utilization", label: "Pay per time utilization" },
  { value: "pay_per_resource_utilization", label: "Pay per resource utilization" },
  { value: "fixed_rental", label: "Fixed rental" },
  { value: "periodic", label: "Periodic" },
] as const;

const DEFAULT_PAYMENT_MODEL = PAYMENT_MODEL_OPTIONS[0].value;

type PaymentModelConfig = {
  feesPerAllocation?: boolean;
  feePerDeployment?: boolean;
  feePerTimeUnit?: boolean;
  timeUnit?: boolean;
  resourceFees?: boolean;
  resourceTimeUnit?: boolean;
  fixedRentalAmount?: boolean;
};

const PAYMENT_MODEL_CONFIG: Record<string, PaymentModelConfig> = {
  pay_per_allocation: { feesPerAllocation: true },
  pay_per_deployment: { feePerDeployment: true },
  pay_per_time_utilization: { feePerTimeUnit: true, timeUnit: true },
  pay_per_resource_utilization: { resourceFees: true, resourceTimeUnit: true },
  fixed_rental: { fixedRentalAmount: true },
  periodic: { feePerTimeUnit: true, timeUnit: true },
};

function getPaymentModelConfig(value: string): PaymentModelConfig | null {
  const trimmed = value.trim().toLowerCase();
  return PAYMENT_MODEL_CONFIG[trimmed] ?? null;
}

function getPaymentModelLabel(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  const model = String(value);
  const match = PAYMENT_MODEL_OPTIONS.find((option) => option.value === model);
  return match ? match.label : model;
}

function extractErrorMessage(error: unknown): string {
  if (error && typeof error === "object") {
    if ((error as AxiosError).isAxiosError) {
      const axiosError = error as AxiosError<{ detail?: unknown; message?: string }>;
      const payload = axiosError.response?.data;
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

function toDateInput(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const offset = date.getTimezoneOffset();
  const local = new Date(date.getTime() - offset * 60000);
  return local.toISOString().slice(0, 16);
}

function toIsoString(value: string): string | undefined {
  if (!value) return undefined;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return undefined;
  }
  return date.toISOString();
}

function parseNumber(value: string): number | undefined {
  const trimmed = value.trim();
  if (!trimmed.length) return undefined;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function parseExtraArgs(value: string): string[] | undefined {
  const trimmed = value.trim();
  if (!trimmed.length) return undefined;
  return trimmed.split(/\s+/);
}

function toFormString(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value);
}

function placeholderValue(value: unknown, fallback: string): string {
  if (value === null || value === undefined) return fallback;
  if (typeof value === "string" && value.trim().length === 0) return fallback;
  return String(value);
}

function normalizeWithDefault(value: unknown, fallback: string): string {
  const normalized = toFormString(value).trim();
  return normalized.length ? normalized : fallback;
}

const DECIMAL_PATTERN = /^(?:\d+)(?:\.\d+)?$/;

function isStrictDecimal(value: string): boolean {
  return DECIMAL_PATTERN.test(value.trim());
}

function isPositiveIntegerString(value: string): boolean {
  const trimmed = value.trim();
  return /^\d+$/.test(trimmed) && Number(trimmed) > 0;
}

function coerceIsoTimestamp(value: unknown): string | null {
  if (value === null || value === undefined) {
    return null;
  }
  const text = String(value).trim();
  if (!text) {
    return null;
  }
  const parsed = Date.parse(text);
  return Number.isNaN(parsed) ? null : text;
}

function extractFormState(detail: ContractTemplateDetail): ContractFormState {
  const contract = (detail.contract as Record<string, any>) ?? {};
  const participants =
    (contract.contract_participants as Record<string, any>) ||
    (contract.participants as Record<string, any>) ||
    {};
  const resource = (contract.resource_configuration as Record<string, any>) || {};
  const cpu = (resource.cpu as Record<string, any>) || {};
  const ram = (resource.ram as Record<string, any>) || {};
  const disk = (resource.disk as Record<string, any>) || {};
  const termination = (contract.termination_option as Record<string, any>) || {};
  const payment = (contract.payment_details as Record<string, any>) || {};
  const duration = (contract.duration as Record<string, any>) || {};
  const paymentAddressesRaw = Array.isArray(payment.addresses)
    ? (payment.addresses as Array<Record<string, any>>)
    : payment.addresses && typeof payment.addresses === "object"
      ? [payment.addresses as Record<string, any>]
      : [];
  const primaryAddress = paymentAddressesRaw[0];

  const rawPaymentModel = toFormString(payment.payment_model).trim().toLowerCase();
  const paymentTypeValue = normalizeWithDefault(payment.payment_type, "blockchain").toLowerCase();
  const paymentPeriodValue = normalizeWithDefault(payment.payment_period, "hour").toLowerCase();
  const paymentPeriodCount = normalizeWithDefault(payment.payment_period_count, "1");
  const paymentTimeUnitValue = normalizeWithDefault(payment.time_unit, "hour").toLowerCase();
  const paymentResourceTimeUnitValue = normalizeWithDefault(payment.resource_time_unit, "hour").toLowerCase();
  const paymentPeriod = PAYMENT_PERIOD_OPTIONS.includes(
    paymentPeriodValue as (typeof PAYMENT_PERIOD_OPTIONS)[number]
  )
    ? paymentPeriodValue
    : "hour";
  const paymentTimeUnit = TIME_UNIT_OPTIONS.includes(paymentTimeUnitValue as (typeof TIME_UNIT_OPTIONS)[number])
    ? paymentTimeUnitValue
    : "hour";
  const paymentResourceTimeUnit = TIME_UNIT_OPTIONS.includes(
    paymentResourceTimeUnitValue as (typeof TIME_UNIT_OPTIONS)[number]
  )
    ? paymentResourceTimeUnitValue
    : "hour";

  const normalizedPaymentModel = PAYMENT_MODEL_OPTIONS.some((option) => option.value === rawPaymentModel)
    ? rawPaymentModel
    : DEFAULT_PAYMENT_MODEL;

  return {
    solutionEnablerDid: contract.solution_enabler_did?.uri ?? "",
    paymentValidatorDid: contract.payment_validator_did?.uri ?? "",
    providerDid: participants.provider?.uri ?? "",
    requestorDid: participants.requestor?.uri ?? "",
    cpuCores: cpu.cores != null ? String(cpu.cores) : "",
    cpuClockSpeed: cpu.clock_speed != null ? String(cpu.clock_speed) : "",
    ramSize: ram.size != null ? String(ram.size) : "",
    diskSize: disk.size != null ? String(disk.size) : "",
    terminationAllowed: Boolean(termination.allowed),
    terminationNotice: termination.notice_period != null ? String(termination.notice_period) : "",
    paymentRequesterAddr: toFormString(payment.requester_addr ?? primaryAddress?.requester_addr),
    paymentProviderAddr: toFormString(payment.provider_addr ?? primaryAddress?.provider_addr),
    paymentCurrency: toFormString(payment.currency ?? primaryAddress?.currency),
    paymentPricingCurrency: toFormString(payment.pricing_currency),
    paymentBlockchain: normalizeWithDefault(payment.blockchain ?? primaryAddress?.blockchain, "ETHEREUM").toUpperCase(),
    paymentType: PAYMENT_TYPE_OPTIONS.some((option) => option.value === paymentTypeValue)
      ? paymentTypeValue
      : "blockchain",
    paymentModel: normalizedPaymentModel,
    paymentFeesPerAllocation: toFormString(payment.fees_per_allocation ?? payment.fee_per_allocation),
    paymentFeePerDeployment: toFormString(payment.fee_per_deployment),
    paymentFeePerTimeUnit: toFormString(payment.fee_per_time_unit),
    paymentTimeUnit: paymentTimeUnit,
    paymentFeePerCpuCorePerTimeUnit: toFormString(payment.fee_per_cpu_core_per_time_unit),
    paymentFeePerRamGbPerTimeUnit: toFormString(payment.fee_per_ram_gb_per_time_unit),
    paymentFeePerDiskGbPerTimeUnit: toFormString(payment.fee_per_disk_gb_per_time_unit),
    paymentFeePerGpuPerTimeUnit: toFormString(payment.fee_per_gpu_per_time_unit),
    paymentResourceTimeUnit: paymentResourceTimeUnit,
    paymentFixedRentalAmount: toFormString(payment.fixed_rental_amount),
    paymentPeriod: paymentPeriod,
    paymentPeriodCount: paymentPeriodCount,
    contractTerms: contract.contract_terms ?? "",
    durationStart: toDateInput(duration.start_date),
    durationEnd: toDateInput(duration.end_date),
    extraArgs: "",
  };
}

function applyStringField(target: Record<string, any>, key: string, value: string) {
  const normalized = value.trim();
  if (normalized) {
    target[key] = normalized;
  } else {
    delete target[key];
  }
}

function applyPositiveIntegerField(target: Record<string, any>, key: string, value: string) {
  const normalized = value.trim();
  if (!normalized) {
    delete target[key];
    return;
  }
  const parsed = Number.parseInt(normalized, 10);
  if (Number.isFinite(parsed) && parsed > 0) {
    target[key] = parsed;
  } else {
    delete target[key];
  }
}

function buildContractPayload(detail: ContractTemplateDetail, form: ContractFormState) {
  const base = JSON.parse(JSON.stringify(detail.contract ?? {}));

  if (form.solutionEnablerDid.trim()) {
    base.solution_enabler_did = { uri: form.solutionEnablerDid.trim() };
  } else {
    delete base.solution_enabler_did;
  }

  if (form.paymentValidatorDid.trim()) {
    base.payment_validator_did = { uri: form.paymentValidatorDid.trim() };
  } else {
    delete base.payment_validator_did;
  }

  const participants =
    base.contract_participants ??
    base.participants ??
    (base.contract_participants = {});

  if (form.providerDid.trim()) {
    participants.provider = { uri: form.providerDid.trim() };
  } else {
    delete participants.provider;
  }

  if (form.requestorDid.trim()) {
    participants.requestor = { uri: form.requestorDid.trim() };
  } else {
    delete participants.requestor;
  }

  const resource = base.resource_configuration ?? (base.resource_configuration = {});
  const cpu = resource.cpu ?? (resource.cpu = {});
  const ram = resource.ram ?? (resource.ram = {});
  const disk = resource.disk ?? (resource.disk = {});

  const cpuCores = parseNumber(form.cpuCores);
  const cpuClock = parseNumber(form.cpuClockSpeed);
  if (cpuCores != null) {
    cpu.cores = cpuCores;
  } else {
    delete cpu.cores;
  }
  if (cpuClock != null) {
    cpu.clock_speed = cpuClock;
  } else {
    delete cpu.clock_speed;
  }

  const ramSize = parseNumber(form.ramSize);
  if (ramSize != null) {
    ram.size = ramSize;
  } else {
    delete ram.size;
  }

  const diskSize = parseNumber(form.diskSize);
  if (diskSize != null) {
    disk.size = diskSize;
  } else {
    delete disk.size;
  }

  const termination = base.termination_option ?? (base.termination_option = {});
  termination.allowed = form.terminationAllowed;
  const notice = parseNumber(form.terminationNotice);
  if (notice != null) {
    termination.notice_period = notice;
  } else {
    delete termination.notice_period;
  }

  const payment = base.payment_details ?? (base.payment_details = {});
  const normalizedRequesterAddr = form.paymentRequesterAddr.trim();
  const normalizedProviderAddr = form.paymentProviderAddr.trim();
  const normalizedCurrency = form.paymentCurrency.trim();
  const normalizedPricingCurrency = form.paymentPricingCurrency.trim();
  const normalizedBlockchain = (form.paymentBlockchain ?? "").trim().toUpperCase();

  applyStringField(payment, "requester_addr", form.paymentRequesterAddr);
  applyStringField(payment, "provider_addr", form.paymentProviderAddr);
  applyStringField(payment, "currency", form.paymentCurrency);
  applyStringField(payment, "pricing_currency", form.paymentPricingCurrency);
  applyStringField(payment, "payment_model", form.paymentModel.toLowerCase());
  applyStringField(payment, "payment_type", form.paymentType.toLowerCase());
  applyStringField(payment, "payment_period", form.paymentPeriod.toLowerCase());
  applyPositiveIntegerField(payment, "payment_period_count", form.paymentPeriodCount);
  if (normalizedBlockchain) {
    payment.blockchain = normalizedBlockchain;
  } else {
    delete payment.blockchain;
  }

  const paymentFieldKeys = [
    "fee_per_allocation",
    "fees_per_allocation",
    "fee_per_deployment",
    "fee_per_time_unit",
    "time_unit",
    "fee_per_cpu_core_per_time_unit",
    "fee_per_ram_gb_per_time_unit",
    "fee_per_disk_gb_per_time_unit",
    "fee_per_gpu_per_time_unit",
    "resource_time_unit",
    "fixed_rental_amount",
  ];
  for (const key of paymentFieldKeys) {
    delete payment[key];
  }

  const paymentModel = form.paymentModel.trim().toLowerCase();
  switch (paymentModel) {
    case "pay_per_allocation":
      applyStringField(payment, "fee_per_allocation", form.paymentFeesPerAllocation);
      break;
    case "pay_per_deployment":
      applyStringField(payment, "fee_per_deployment", form.paymentFeePerDeployment);
      break;
    case "pay_per_time_utilization":
      applyStringField(payment, "fee_per_time_unit", form.paymentFeePerTimeUnit);
      applyStringField(payment, "time_unit", form.paymentTimeUnit.toLowerCase());
      break;
    case "pay_per_resource_utilization":
      applyStringField(payment, "fee_per_cpu_core_per_time_unit", form.paymentFeePerCpuCorePerTimeUnit);
      applyStringField(payment, "fee_per_ram_gb_per_time_unit", form.paymentFeePerRamGbPerTimeUnit);
      applyStringField(payment, "fee_per_disk_gb_per_time_unit", form.paymentFeePerDiskGbPerTimeUnit);
      applyStringField(payment, "fee_per_gpu_per_time_unit", form.paymentFeePerGpuPerTimeUnit);
      applyStringField(payment, "resource_time_unit", form.paymentResourceTimeUnit.toLowerCase());
      break;
    case "fixed_rental":
      applyStringField(payment, "fixed_rental_amount", form.paymentFixedRentalAmount);
      break;
    case "periodic":
      applyStringField(payment, "fee_per_time_unit", form.paymentFeePerTimeUnit);
      applyStringField(payment, "time_unit", form.paymentTimeUnit.toLowerCase());
      break;
    default:
      break;
  }
  const addressPayload: Record<string, string> = {};
  if (normalizedBlockchain) {
    addressPayload.blockchain = normalizedBlockchain;
  }
  if (normalizedCurrency) {
    addressPayload.currency = normalizedCurrency;
  }
  if (normalizedRequesterAddr) {
    addressPayload.requester_addr = normalizedRequesterAddr;
  }
  if (normalizedProviderAddr) {
    addressPayload.provider_addr = normalizedProviderAddr;
  }
  if (Object.keys(addressPayload).length > 0) {
    payment.addresses = [addressPayload];
  } else {
    delete payment.addresses;
  }
  if (!normalizedPricingCurrency) {
    delete payment.pricing_currency;
  }
  const timestamp = coerceIsoTimestamp(payment.timestamp);
  payment.timestamp = timestamp ?? new Date().toISOString();

  if (form.contractTerms.trim()) {
    base.contract_terms = form.contractTerms.trim();
  } else {
    delete base.contract_terms;
  }

  const duration = base.duration ?? (base.duration = {});
  const startIso = toIsoString(form.durationStart);
  const endIso = toIsoString(form.durationEnd);
  if (startIso) {
    duration.start_date = startIso;
  } else {
    delete duration.start_date;
  }
  if (endIso) {
    duration.end_date = endIso;
  } else {
    delete duration.end_date;
  }

  return base;
}

function buildCreatePayload(detail: ContractTemplateDetail, form: ContractFormState): ContractCreatePayload {
  const payload: ContractCreatePayload = {
    contract: buildContractPayload(detail, form),
    template_id: detail.template_id,
  };

  const extraArgs = parseExtraArgs(form.extraArgs);
  if (extraArgs?.length) {
    payload.extra_args = extraArgs;
  }

  return payload;
}

function validatePaymentDetails(form: ContractFormState): string[] {
  const errors: string[] = [];
  const modelConfig = getPaymentModelConfig(form.paymentModel.trim());
  const requiresFeesPerAllocation = Boolean(modelConfig?.feesPerAllocation);
  const requiresFeePerDeployment = Boolean(modelConfig?.feePerDeployment);
  const requiresFeePerTimeUnit = Boolean(modelConfig?.feePerTimeUnit);
  const requiresTimeUnit = Boolean(modelConfig?.timeUnit);
  const requiresResourceFees = Boolean(modelConfig?.resourceFees);
  const requiresResourceTimeUnit = Boolean(modelConfig?.resourceTimeUnit);
  const requiresFixedRentalAmount = Boolean(modelConfig?.fixedRentalAmount);

  if (!modelConfig) {
    errors.push("Select a payment model.");
  }

  const paymentType = form.paymentType.trim().toLowerCase();
  if (!["fiat", "blockchain"].includes(paymentType)) {
    errors.push("Select a payment type.");
  }

  if (!form.paymentRequesterAddr.trim()) {
    errors.push("Enter a requester address.");
  }
  if (!form.paymentProviderAddr.trim()) {
    errors.push("Enter a provider address.");
  }
  if (!form.paymentCurrency.trim()) {
    errors.push("Enter a currency.");
  }
  if (!form.paymentBlockchain.trim()) {
    errors.push("Select a blockchain.");
  }

  const paymentPeriod = form.paymentPeriod.trim().toLowerCase();
  if (!paymentPeriod) {
    errors.push("Select a payment period.");
  } else if (!PAYMENT_PERIOD_OPTIONS.includes(paymentPeriod as (typeof PAYMENT_PERIOD_OPTIONS)[number])) {
    errors.push("Payment period must be minute, hour, day, week, or month.");
  }

  const paymentPeriodCount = form.paymentPeriodCount.trim();
  if (!paymentPeriodCount) {
    errors.push("Enter a payment period count.");
  } else if (!isPositiveIntegerString(paymentPeriodCount)) {
    errors.push("Payment period count must be a positive integer.");
  }

  const feesPerAllocation = form.paymentFeesPerAllocation.trim();
  if (requiresFeesPerAllocation && !feesPerAllocation) {
    errors.push("Enter fees per allocation.");
  }

  const feePerDeployment = form.paymentFeePerDeployment.trim();
  if (requiresFeePerDeployment && !feePerDeployment) {
    errors.push("Enter a fee per deployment.");
  }

  const feePerTimeUnit = form.paymentFeePerTimeUnit.trim();
  if (requiresFeePerTimeUnit && !feePerTimeUnit) {
    errors.push("Enter a fee per time unit.");
  }

  const timeUnit = form.paymentTimeUnit.trim().toLowerCase();
  if (requiresTimeUnit && !timeUnit) {
    errors.push("Select a time unit.");
  } else if (
    requiresTimeUnit &&
    !TIME_UNIT_OPTIONS.includes(timeUnit as (typeof TIME_UNIT_OPTIONS)[number])
  ) {
    errors.push("Time unit must be second, minute, or hour.");
  }

  const fixedRentalAmount = form.paymentFixedRentalAmount.trim();
  if (requiresFixedRentalAmount && !fixedRentalAmount) {
    errors.push("Enter a fixed rental amount.");
  }

  if (requiresResourceFees) {
    if (!form.paymentFeePerCpuCorePerTimeUnit.trim()) {
      errors.push("Enter a CPU core fee per time unit.");
    }
    if (!form.paymentFeePerRamGbPerTimeUnit.trim()) {
      errors.push("Enter a RAM GB fee per time unit.");
    }
    if (!form.paymentFeePerDiskGbPerTimeUnit.trim()) {
      errors.push("Enter a disk GB fee per time unit.");
    }
  }

  const resourceTimeUnit = form.paymentResourceTimeUnit.trim().toLowerCase();
  if (requiresResourceTimeUnit && !resourceTimeUnit) {
    errors.push("Select a resource time unit.");
  } else if (
    requiresResourceTimeUnit &&
    !TIME_UNIT_OPTIONS.includes(resourceTimeUnit as (typeof TIME_UNIT_OPTIONS)[number])
  ) {
    errors.push("Resource time unit must be second, minute, or hour.");
  }

  const numericFields = [
    { value: feesPerAllocation, label: "Fees per allocation" },
    { value: feePerDeployment, label: "Fee per deployment" },
    { value: feePerTimeUnit, label: "Fee per time unit" },
    { value: fixedRentalAmount, label: "Fixed rental amount" },
    { value: form.paymentFeePerCpuCorePerTimeUnit.trim(), label: "CPU core fee per time unit" },
    { value: form.paymentFeePerRamGbPerTimeUnit.trim(), label: "RAM GB fee per time unit" },
    { value: form.paymentFeePerDiskGbPerTimeUnit.trim(), label: "Disk GB fee per time unit" },
    { value: form.paymentFeePerGpuPerTimeUnit.trim(), label: "GPU fee per time unit" },
  ];

  for (const field of numericFields) {
    if (field.value.length > 0 && !isStrictDecimal(field.value)) {
      errors.push(`${field.label} must be a decimal number.`);
    }
  }

  return Array.from(new Set(errors));
}
export default function NewContractPage(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [wizardStep, setWizardStep] = React.useState<ContractWizardStep>("select");
  const [selectedTemplateId, setSelectedTemplateId] = React.useState<string | null>(null);
  const [formState, setFormState] = React.useState<ContractFormState | null>(null);
  const [reviewPayload, setReviewPayload] = React.useState<ContractCreatePayload | null>(null);
  const [paymentErrors, setPaymentErrors] = React.useState<string[]>([]);
  const shouldPrefillRequestor = React.useRef(true);

  const dmsStatusQuery = useQuery({
    queryKey: ["dms", "status"],
    queryFn: getDmsStatus,
    staleTime: DMS_STATUS_CACHE_MS,
    gcTime: DMS_STATUS_CACHE_MS,
    refetchOnWindowFocus: false,
  });
  const cachedDashboardInfo = queryClient.getQueryData<{ dms_did?: string }>(["apiData"]);
  const machineDid = dmsStatusQuery.data?.dms_did ?? cachedDashboardInfo?.dms_did ?? "";

  const templatesQuery = useQuery({
    queryKey: ["contracts", "templates"],
    queryFn: ({ signal }) => contractsApi.getContractTemplates(signal),
    staleTime: 60000,
    refetchOnWindowFocus: false,
  });

  const templateDetailQuery = useQuery({
    queryKey: ["contracts", "templates", selectedTemplateId],
    queryFn: ({ signal }) => contractsApi.getContractTemplateDetail(selectedTemplateId!, signal),
    enabled: Boolean(selectedTemplateId),
  });

  const createMutation = useMutation({
    mutationFn: (payload: ContractCreatePayload) => contractsApi.createContract(payload),
    onSuccess: (data) => {
      toast.success(data.message ?? "Contract creation submitted.");
      queryClient.invalidateQueries({ queryKey: ["contracts"] });
      navigate("/contracts");
    },
    onError: (error) => {
      toast.error("Failed to create contract", {
        description: extractErrorMessage(error),
      });
    },
  });

  React.useEffect(() => {
    if (templateDetailQuery.data) {
      shouldPrefillRequestor.current = true;
      setFormState(extractFormState(templateDetailQuery.data));
      setPaymentErrors([]);
    }
  }, [templateDetailQuery.data]);

  React.useEffect(() => {
    if (!formState) {
      return;
    }
    if (!machineDid) {
      return;
    }
    if (!shouldPrefillRequestor.current) {
      return;
    }
    if (formState.requestorDid?.trim()) {
      shouldPrefillRequestor.current = false;
      return;
    }
    shouldPrefillRequestor.current = false;
    setFormState((prev) => {
      if (!prev || prev.requestorDid?.trim()) {
        return prev;
      }
      return { ...prev, requestorDid: machineDid };
    });
  }, [formState, machineDid]);

  const templates = templatesQuery.data?.templates ?? [];
  const templatesError = templatesQuery.error ? extractErrorMessage(templatesQuery.error) : null;

  const handleTemplateSelect = React.useCallback((templateId: string) => {
    setSelectedTemplateId(templateId);
    setWizardStep("configure");
  }, []);

  const handleFormChange = React.useCallback((update: Partial<ContractFormState>) => {
    if (Object.prototype.hasOwnProperty.call(update, "requestorDid")) {
      shouldPrefillRequestor.current = false;
    }
    setPaymentErrors([]);
    setFormState((prev) => (prev ? { ...prev, ...update } : prev));
  }, []);

  const handleReset = React.useCallback(() => {
    setWizardStep("select");
    setSelectedTemplateId(null);
    setFormState(null);
    setReviewPayload(null);
    setPaymentErrors([]);
    shouldPrefillRequestor.current = true;
  }, []);

  const handleGenerateReview = React.useCallback(() => {
    if (!templateDetailQuery.data || !formState) {
      toast.error("Template details are still loading. Try again in a moment.");
      return;
    }
    const validationErrors = validatePaymentDetails(formState);
    if (validationErrors.length > 0) {
      setPaymentErrors(validationErrors);
      toast.error("Payment details need attention.", {
        description: validationErrors.join(" "),
      });
      return;
    }
    setPaymentErrors([]);
    const payload = buildCreatePayload(templateDetailQuery.data, formState);
    setReviewPayload(payload);
    setWizardStep("review");
  }, [formState, templateDetailQuery.data]);

  const handleSubmit = React.useCallback(async () => {
    if (!reviewPayload) {
      toast.error("Review the contract before submitting.");
      return;
    }
    await createMutation.mutateAsync(reviewPayload);
  }, [createMutation, reviewPayload]);

  return (
    <div className="space-y-6 px-4 py-6">
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">New Contract</h1>
          <p className="text-sm text-muted-foreground">
            Choose a contract template and configure the required fields before submitting it to the DMS.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => navigate("/contracts")} className="gap-2">
            <ArrowLeft className="h-4 w-4" />
            Back to contracts
          </Button>
          <Button
            variant="outline"
            onClick={() => templatesQuery.refetch()}
            disabled={templatesQuery.isFetching}
            className="gap-2"
          >
            <RefreshCw className={cn("h-4 w-4", templatesQuery.isFetching ? "animate-spin" : undefined)} />
            Refresh templates
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Contract template workflow</CardTitle>
          <CardDescription>
            Select a template, tailor the configuration, and confirm the details before creating the contract.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {wizardStep === "select" ? (
            <TemplateSelectionStep
              templates={templates}
              isLoading={templatesQuery.isLoading}
              error={templatesError}
              selectedTemplateId={selectedTemplateId}
              onSelectTemplate={handleTemplateSelect}
            />
          ) : wizardStep === "configure" ? (
            templateDetailQuery.isLoading || !templateDetailQuery.data || !formState ? (
              <WizardFallback />
            ) : (
              <ConfigureTemplateStep
                detail={templateDetailQuery.data}
                formState={formState}
                paymentErrors={paymentErrors}
                onChange={handleFormChange}
                onBack={handleReset}
                onContinue={handleGenerateReview}
              />
            )
          ) : templateDetailQuery.data && reviewPayload && formState ? (
            <ReviewTemplateStep
              detail={templateDetailQuery.data}
              payload={reviewPayload}
              formState={formState}
              onBack={() => setWizardStep("configure")}
              onSubmit={handleSubmit}
              isSubmitting={createMutation.isPending}
            />
          ) : (
            <WizardFallback />
          )}
        </CardContent>
      </Card>
    </div>
  );
}interface TemplateSelectionStepProps {
  templates: ContractTemplateSummary[];
  isLoading: boolean;
  error: string | null;
  selectedTemplateId: string | null;
  onSelectTemplate: (templateId: string) => void;
}

function TemplateSelectionStep({
  templates,
  isLoading,
  error,
  selectedTemplateId,
  onSelectTemplate,
}: TemplateSelectionStepProps) {
  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-24 w-full rounded-md" />
        <Skeleton className="h-24 w-full rounded-md" />
        <Skeleton className="h-24 w-full rounded-md" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
        {error}
      </div>
    );
  }

  if (templates.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-muted-foreground/40 px-4 py-10 text-center text-sm text-muted-foreground">
        No contract templates are available yet. Upload templates on the appliance backend to get started.
      </div>
    );
  }

  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {templates.map((template) => {
        const isActive = template.template_id === selectedTemplateId;
        return (
          <button
            key={template.template_id}
            type="button"
            onClick={() => onSelectTemplate(template.template_id)}
            className={cn(
              "flex h-full flex-col gap-3 rounded-md border border-border/60 bg-card p-4 text-left transition",
              "hover:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
              isActive ? "border-primary" : "",
            )}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold text-foreground">{template.name}</h3>
                <p className="text-xs text-muted-foreground">{template.template_id}</p>
              </div>
              <Badge variant="outline" className="text-[10px] uppercase">
                {template.source}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground line-clamp-3">
              {template.description ?? "No description provided for this template."}
            </p>
            {template.tags.length ? (
              <div className="flex flex-wrap gap-1">
                {template.tags.map((tag) => (
                  <Badge key={tag} variant="secondary" className="text-[10px] uppercase">
                    {tag}
                  </Badge>
                ))}
              </div>
            ) : null}
            <span className="mt-auto inline-flex items-center gap-2 text-xs font-medium text-primary">
              Use template
              <ArrowRight className="h-3 w-3" />
            </span>
          </button>
        );
      })}
    </div>
  );
}
interface ConfigureTemplateStepProps {
  detail: ContractTemplateDetail;
  formState: ContractFormState;
  paymentErrors: string[];
  onChange: (update: Partial<ContractFormState>) => void;
  onBack: () => void;
  onContinue: () => void;
}

function ConfigureTemplateStep({
  detail,
  formState,
  paymentErrors,
  onChange,
  onBack,
  onContinue,
}: ConfigureTemplateStepProps) {
  const cpu = detail.contract?.resource_configuration?.cpu ?? {};
  const ram = detail.contract?.resource_configuration?.ram ?? {};
  const disk = detail.contract?.resource_configuration?.disk ?? {};
  const termination = detail.contract?.termination_option ?? {};
  const payment = detail.contract?.payment_details ?? {};
  const paymentAddressesRaw = Array.isArray(payment.addresses)
    ? (payment.addresses as Array<Record<string, any>>)
    : payment.addresses && typeof payment.addresses === "object"
      ? [payment.addresses as Record<string, any>]
      : [];
  const paymentAddress = paymentAddressesRaw[0];
  const [paymentModelSearch, setPaymentModelSearch] = React.useState("");
  const filteredPaymentModels = React.useMemo(() => {
    const term = paymentModelSearch.trim().toLowerCase();
    if (!term) return PAYMENT_MODEL_OPTIONS;
    return PAYMENT_MODEL_OPTIONS.filter(
      (option) => option.label.toLowerCase().includes(term) || option.value.toLowerCase().includes(term)
    );
  }, [paymentModelSearch]);
  const modelConfig =
    getPaymentModelConfig(formState.paymentModel) ?? {
      feesPerAllocation: true,
      feePerDeployment: true,
      feePerTimeUnit: true,
      timeUnit: true,
      resourceFees: true,
      resourceTimeUnit: true,
      fixedRentalAmount: true,
    };
  const showFeesPerAllocation = Boolean(modelConfig.feesPerAllocation);
  const showFeePerDeployment = Boolean(modelConfig.feePerDeployment);
  const showFeePerTimeUnit = Boolean(modelConfig.feePerTimeUnit);
  const showTimeUnit = Boolean(modelConfig.timeUnit);
  const showResourceFees = Boolean(modelConfig.resourceFees);
  const showResourceTimeUnit = Boolean(modelConfig.resourceTimeUnit);
  const showFixedRentalAmount = Boolean(modelConfig.fixedRentalAmount);
  const showAllocationDeploymentFees = showFeesPerAllocation || showFeePerDeployment;
  const showTimeUtilization = showFeePerTimeUnit || showTimeUnit;
  const showResourceSection = showResourceFees || showResourceTimeUnit;
  const duration = detail.contract?.duration ?? {};
  return (
    <div className="space-y-6">
      <section className="space-y-4">
        <h3 className="text-sm font-semibold">Participants</h3>
        <div className="grid gap-3 md:grid-cols-2">
          <TextField
            label="Contract host DID"
            value={formState.solutionEnablerDid}
            onChange={(value) => onChange({ solutionEnablerDid: value })}
            placeholder={detail.contract?.solution_enabler_did?.uri ?? "did:key:..."}
          />
          <TextField
            label="Payment validator DID"
            value={formState.paymentValidatorDid}
            onChange={(value) => onChange({ paymentValidatorDid: value })}
            placeholder={detail.contract?.payment_validator_did?.uri ?? "did:key:..."}
          />
          <TextField
            label="Provider DID"
            value={formState.providerDid}
            onChange={(value) => onChange({ providerDid: value })}
            placeholder="did:key:provider..."
          />
          <TextField
            label="Requestor DID"
            value={formState.requestorDid}
            onChange={(value) => onChange({ requestorDid: value })}
            placeholder="did:key:requestor..."
          />
        </div>
      </section>

      <Separator />

      <section className="space-y-4">
        <h3 className="text-sm font-semibold">Resource configuration</h3>
        <div className="grid gap-3 md:grid-cols-2">
          <TextField
            label="CPU cores"
            value={formState.cpuCores}
            onChange={(value) => onChange({ cpuCores: value })}
            placeholder={cpu.cores != null ? String(cpu.cores) : "e.g. 1"}
          />
          <TextField
            label="CPU clock speed (MHz)"
            value={formState.cpuClockSpeed}
            onChange={(value) => onChange({ cpuClockSpeed: value })}
            placeholder={cpu.clock_speed != null ? String(cpu.clock_speed) : "e.g. 2400"}
          />
          <TextField
            label="RAM size (MB)"
            value={formState.ramSize}
            onChange={(value) => onChange({ ramSize: value })}
            placeholder={ram.size != null ? String(ram.size) : "e.g. 2048"}
          />
          <TextField
            label="Disk size (MB)"
            value={formState.diskSize}
            onChange={(value) => onChange({ diskSize: value })}
            placeholder={disk.size != null ? String(disk.size) : "e.g. 10240"}
          />
        </div>
      </section>

      <Separator />

      <section className="space-y-4">
        <h3 className="text-sm font-semibold">Payment details</h3>
        {paymentErrors.length > 0 ? (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            <p className="font-medium">Payment details need attention:</p>
            <ul className="list-disc space-y-1 pl-4">
              {paymentErrors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          </div>
        ) : null}
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-2">
            <Label>Payment model</Label>
            <Select
              value={formState.paymentModel}
              onValueChange={(value) => {
                onChange({ paymentModel: value as ContractFormState["paymentModel"] });
                setPaymentModelSearch("");
              }}
              onOpenChange={(open) => {
                if (!open) {
                  setPaymentModelSearch("");
                }
              }}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select a model" />
              </SelectTrigger>
              <SelectContent>
                <div
                  className="sticky top-0 z-10 border-b border-border/60 bg-popover p-2"
                  onMouseDown={(event) => event.stopPropagation()}
                  onKeyDown={(event) => event.stopPropagation()}
                >
                  <Input
                    value={paymentModelSearch}
                    onChange={(event) => setPaymentModelSearch(event.target.value)}
                    placeholder="Search payment models..."
                    className="h-8 w-full"
                    aria-label="Search payment models"
                  />
                </div>
                {filteredPaymentModels.length ? (
                  filteredPaymentModels.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))
                ) : (
                  <SelectItem value="__no_results__" disabled>
                    No matching models
                  </SelectItem>
                )}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Payment type</Label>
            <Select
              value={formState.paymentType}
              onValueChange={(value) => onChange({ paymentType: value as ContractFormState["paymentType"] })}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select a payment type" />
              </SelectTrigger>
              <SelectContent>
                {PAYMENT_TYPE_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="space-y-3 rounded-md border border-border/60 p-4">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Addresses</div>
          <div className="grid gap-3 md:grid-cols-2">
            <TextField
              label="Requester address"
              value={formState.paymentRequesterAddr}
              onChange={(value) => onChange({ paymentRequesterAddr: value })}
              placeholder={placeholderValue(payment.requester_addr ?? paymentAddress?.requester_addr, "0x...")}
            />
            <TextField
              label="Provider address"
              value={formState.paymentProviderAddr}
              onChange={(value) => onChange({ paymentProviderAddr: value })}
              placeholder={placeholderValue(payment.provider_addr ?? paymentAddress?.provider_addr, "0x...")}
            />
            <TextField
              label="Currency"
              value={formState.paymentCurrency}
              onChange={(value) => onChange({ paymentCurrency: value })}
              placeholder={placeholderValue(payment.currency ?? paymentAddress?.currency, "NTX")}
            />
            <TextField
              label="Pricing currency (optional)"
              value={formState.paymentPricingCurrency}
              onChange={(value) => onChange({ paymentPricingCurrency: value })}
              placeholder={placeholderValue(payment.pricing_currency, "USDT")}
            />
            <div className="space-y-2">
              <Label>Blockchain</Label>
              <Select
                value={formState.paymentBlockchain}
                onValueChange={(value) =>
                  onChange({ paymentBlockchain: value as ContractFormState["paymentBlockchain"] })
                }
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select a network" />
                </SelectTrigger>
                <SelectContent>
                  {BLOCKCHAIN_OPTIONS.map((option) => (
                    <SelectItem key={option} value={option}>
                      {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>

        {showAllocationDeploymentFees ? (
          <div className="space-y-3 rounded-md border border-border/60 p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Allocation & deployment fees
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              {showFeesPerAllocation ? (
                <TextField
                  label="Fees per allocation"
                  value={formState.paymentFeesPerAllocation}
                  onChange={(value) => onChange({ paymentFeesPerAllocation: value })}
                  placeholder={placeholderValue(payment.fees_per_allocation ?? payment.fee_per_allocation, "500")}
                />
              ) : null}
              {showFeePerDeployment ? (
                <TextField
                  label="Fee per deployment"
                  value={formState.paymentFeePerDeployment}
                  onChange={(value) => onChange({ paymentFeePerDeployment: value })}
                  placeholder={placeholderValue(payment.fee_per_deployment, "e.g. 25")}
                />
              ) : null}
            </div>
          </div>
        ) : null}

        {showTimeUtilization ? (
          <div className="space-y-3 rounded-md border border-border/60 p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Time utilization
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-2">
                <Label>Time unit</Label>
                <Select
                  value={formState.paymentTimeUnit}
                  onValueChange={(value) => onChange({ paymentTimeUnit: value })}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Select a time unit" />
                  </SelectTrigger>
                  <SelectContent>
                    {TIME_UNIT_OPTIONS.map((option) => (
                      <SelectItem key={option} value={option}>
                        {option}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <TextField
                label="Fee per time unit"
                value={formState.paymentFeePerTimeUnit}
                onChange={(value) => onChange({ paymentFeePerTimeUnit: value })}
                placeholder={placeholderValue(payment.fee_per_time_unit, "e.g. 0.01")}
              />
            </div>
          </div>
        ) : null}

        {showResourceSection ? (
          <div className="space-y-3 rounded-md border border-border/60 p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Resource-based pricing
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <TextField
                label="CPU core fee per time unit"
                value={formState.paymentFeePerCpuCorePerTimeUnit}
                onChange={(value) => onChange({ paymentFeePerCpuCorePerTimeUnit: value })}
                placeholder={placeholderValue(payment.fee_per_cpu_core_per_time_unit, "e.g. 0.10")}
              />
              <TextField
                label="RAM GB fee per time unit"
                value={formState.paymentFeePerRamGbPerTimeUnit}
                onChange={(value) => onChange({ paymentFeePerRamGbPerTimeUnit: value })}
                placeholder={placeholderValue(payment.fee_per_ram_gb_per_time_unit, "e.g. 0.05")}
              />
              <TextField
                label="Disk GB fee per time unit"
                value={formState.paymentFeePerDiskGbPerTimeUnit}
                onChange={(value) => onChange({ paymentFeePerDiskGbPerTimeUnit: value })}
                placeholder={placeholderValue(payment.fee_per_disk_gb_per_time_unit, "e.g. 0.01")}
              />
              <TextField
                label="GPU fee per time unit (optional)"
                value={formState.paymentFeePerGpuPerTimeUnit}
                onChange={(value) => onChange({ paymentFeePerGpuPerTimeUnit: value })}
                placeholder={placeholderValue(payment.fee_per_gpu_per_time_unit, "e.g. 5.00")}
              />
              <div className="space-y-2">
                <Label>Resource time unit</Label>
                <Select
                  value={formState.paymentResourceTimeUnit}
                  onValueChange={(value) => onChange({ paymentResourceTimeUnit: value })}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Select a time unit" />
                  </SelectTrigger>
                  <SelectContent>
                    {TIME_UNIT_OPTIONS.map((option) => (
                      <SelectItem key={option} value={option}>
                        {option}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
        ) : null}

        {showFixedRentalAmount ? (
          <div className="space-y-3 rounded-md border border-border/60 p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Fixed rental</div>
            <div className="grid gap-3 md:grid-cols-2">
              <TextField
                label="Fixed rental amount"
                value={formState.paymentFixedRentalAmount}
                onChange={(value) => onChange({ paymentFixedRentalAmount: value })}
                placeholder={placeholderValue(payment.fixed_rental_amount, "e.g. 20.00")}
              />
            </div>
          </div>
        ) : null}

        <div className="space-y-3 rounded-md border border-border/60 p-4">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Payment period</div>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-2">
              <Label>Payment period</Label>
              <Select
                value={formState.paymentPeriod}
                onValueChange={(value) => onChange({ paymentPeriod: value })}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select a period" />
                </SelectTrigger>
                <SelectContent>
                  {PAYMENT_PERIOD_OPTIONS.map((option) => (
                    <SelectItem key={option} value={option}>
                      {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <TextField
              label="Payment period count"
              value={formState.paymentPeriodCount}
              onChange={(value) => onChange({ paymentPeriodCount: value })}
              placeholder={placeholderValue(payment.payment_period_count, "1")}
            />
          </div>
        </div>
      </section>

      <Separator />

      <section className="space-y-4">
        <h3 className="text-sm font-semibold">Duration & termination</h3>
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="duration-start">Start date</Label>
            <Input
              id="duration-start"
              type="datetime-local"
              value={formState.durationStart}
              onChange={(event) => onChange({ durationStart: event.target.value })}
              placeholder={duration.start_date ?? ""}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="duration-end">End date</Label>
            <Input
              id="duration-end"
              type="datetime-local"
              value={formState.durationEnd}
              onChange={(event) => onChange({ durationEnd: event.target.value })}
              placeholder={duration.end_date ?? ""}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="termination-allowed">Termination allowed</Label>
            <div className="flex items-center gap-2 rounded-md border border-border/60 p-2">
              <Switch
                id="termination-allowed"
                checked={formState.terminationAllowed}
                onCheckedChange={(checked) => onChange({ terminationAllowed: checked })}
              />
              <span className="text-xs text-muted-foreground">Allow contract termination</span>
            </div>
          </div>
          <TextField
            label="Notice period (ns)"
            value={formState.terminationNotice}
            onChange={(value) => onChange({ terminationNotice: value })}
            placeholder={termination.notice_period != null ? String(termination.notice_period) : "0"}
          />
        </div>
      </section>

      <Separator />

      <section className="space-y-2">
        <h3 className="text-sm font-semibold">Contract terms</h3>
        <textarea
          className="min-h-[120px] w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          value={formState.contractTerms}
          onChange={(event) => onChange({ contractTerms: event.target.value })}
        />
      </section>

      <section className="space-y-2">
        <h3 className="text-sm font-semibold">Extra CLI arguments</h3>
        <Input
          value={formState.extraArgs}
          onChange={(event) => onChange({ extraArgs: event.target.value })}
          placeholder="Optional additional arguments passed to the create command"
        />
      </section>

      <div className="flex justify-between border-t border-border/60 pt-4">
        <Button variant="outline" onClick={onBack}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Choose another template
        </Button>
        <Button onClick={onContinue} className="gap-2">
          Continue to review
          <ArrowRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}interface ReviewTemplateStepProps {
  detail: ContractTemplateDetail;
  payload: ContractCreatePayload;
  formState: ContractFormState;
  onBack: () => void;
  onSubmit: () => void;
  isSubmitting: boolean;
}

function ReviewTemplateStep({ detail, payload, formState, onBack, onSubmit, isSubmitting }: ReviewTemplateStepProps) {
  const contract = payload.contract as Record<string, unknown>;
  const resource = (contract.resource_configuration as Record<string, any>) || {};
  const cpu = (resource.cpu as Record<string, any>) || {};
  const ram = (resource.ram as Record<string, any>) || {};
  const disk = (resource.disk as Record<string, any>) || {};
  const payment = (contract.payment_details as Record<string, any>) || {};
  const paymentAddressesRaw = Array.isArray(payment.addresses)
    ? (payment.addresses as Array<Record<string, any>>)
    : payment.addresses && typeof payment.addresses === "object"
      ? [payment.addresses as Record<string, any>]
      : [];
  const paymentAddress = paymentAddressesRaw[0];
  const duration = (contract.duration as Record<string, any>) || {};
  const termination = (contract.termination_option as Record<string, any>) || {};
  const paymentRows: Array<{ label: string; value: unknown }> = [];
  const addPaymentRow = (label: string, value: unknown) => {
    if (value === null || value === undefined) {
      return;
    }
    if (typeof value === "string" && value.trim().length === 0) {
      return;
    }
    paymentRows.push({ label, value });
  };

  addPaymentRow("Payment model", getPaymentModelLabel(payment.payment_model));
  addPaymentRow("Payment type", payment.payment_type);
  addPaymentRow("Requester address", payment.requester_addr ?? paymentAddress?.requester_addr);
  addPaymentRow("Provider address", payment.provider_addr ?? paymentAddress?.provider_addr);
  addPaymentRow("Currency", payment.currency ?? paymentAddress?.currency);
  addPaymentRow("Pricing currency", payment.pricing_currency);
  addPaymentRow("Blockchain", payment.blockchain ?? paymentAddress?.blockchain);
  addPaymentRow("Fees per allocation", payment.fees_per_allocation ?? payment.fee_per_allocation);
  addPaymentRow("Fee per deployment", payment.fee_per_deployment);
  addPaymentRow("Fee per time unit", payment.fee_per_time_unit);
  addPaymentRow("Time unit", payment.time_unit);
  addPaymentRow("CPU core fee per time unit", payment.fee_per_cpu_core_per_time_unit);
  addPaymentRow("RAM GB fee per time unit", payment.fee_per_ram_gb_per_time_unit);
  addPaymentRow("Disk GB fee per time unit", payment.fee_per_disk_gb_per_time_unit);
  addPaymentRow("GPU fee per time unit", payment.fee_per_gpu_per_time_unit);
  addPaymentRow("Resource time unit", payment.resource_time_unit);
  addPaymentRow("Fixed rental amount", payment.fixed_rental_amount);
  addPaymentRow("Payment period", payment.payment_period);
  addPaymentRow("Payment period count", payment.payment_period_count);
  addPaymentRow("Timestamp", payment.timestamp);

  return (
    <div className="space-y-5">
      <section className="space-y-2">
        <h3 className="text-sm font-semibold">Contract overview</h3>
        <div className="space-y-1 text-sm">
          <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-muted-foreground">
            <FilePlus2 className="h-4 w-4" />
            Template
          </div>
          <p className="text-sm font-medium text-foreground">{detail.name}</p>
          <p className="text-xs text-muted-foreground">{detail.template_id}</p>
        </div>
      </section>

      <section className="space-y-2">
        <h4 className="text-sm font-semibold">Destination & Scope</h4>
      </section>

      <section className="space-y-2">
        <h4 className="text-sm font-semibold">Participants</h4>
        <div className="grid gap-2 text-sm md:grid-cols-2">
          <InfoRow label="Contract host DID" value={formState.solutionEnablerDid} />
          <InfoRow label="Payment validator DID" value={formState.paymentValidatorDid} />
          <InfoRow label="Provider DID" value={formState.providerDid} />
          <InfoRow label="Requestor DID" value={formState.requestorDid} />
        </div>
      </section>

      <section className="space-y-2">
        <h4 className="text-sm font-semibold">Resources</h4>
        <div className="grid gap-2 text-sm md:grid-cols-2">
          <InfoRow label="CPU cores" value={cpu.cores ?? formState.cpuCores} />
          <InfoRow label="CPU clock (MHz)" value={cpu.clock_speed ?? formState.cpuClockSpeed} />
          <InfoRow label="RAM size (MB)" value={ram.size ?? formState.ramSize} />
          <InfoRow label="Disk size (MB)" value={disk.size ?? formState.diskSize} />
        </div>
      </section>

      <section className="space-y-2">
        <h4 className="text-sm font-semibold">Payment</h4>
        {paymentRows.length ? (
          <div className="grid gap-2 text-sm md:grid-cols-2">
            {paymentRows.map((row) => (
              <InfoRow key={row.label} label={row.label} value={row.value} />
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">No payment details set.</p>
        )}
      </section>

      <section className="space-y-2">
        <h4 className="text-sm font-semibold">Duration & Termination</h4>
        <div className="grid gap-2 text-sm md:grid-cols-2">
          <InfoRow label="Start date" value={duration.start_date ?? toIsoString(formState.durationStart)} />
          <InfoRow label="End date" value={duration.end_date ?? toIsoString(formState.durationEnd)} />
          <InfoRow label="Termination allowed" value={termination.allowed ?? formState.terminationAllowed} />
          <InfoRow label="Notice period (ns)" value={termination.notice_period ?? formState.terminationNotice} />
        </div>
      </section>

      <section className="space-y-2">
        <h4 className="text-sm font-semibold">Contract terms</h4>
        <div className="rounded-md border border-border/60 bg-muted/20 p-3 text-sm">
          {formState.contractTerms || "No additional terms provided."}
        </div>
      </section>

      <section className="space-y-1">
        <h4 className="text-sm font-semibold">Extra CLI arguments</h4>
        <code className="block rounded-md border border-dashed border-border/60 bg-muted/10 px-3 py-2 text-xs">
          {payload.extra_args?.length ? payload.extra_args.join(" ") : "None"}
        </code>
      </section>

      <div className="flex justify-between border-t border-border/60 pt-4">
        <Button variant="outline" onClick={onBack}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to configure
        </Button>
        <Button onClick={onSubmit} disabled={isSubmitting} className="gap-2">
          {isSubmitting ? (
            <>
              <RefreshCw className="h-4 w-4 animate-spin" />
              Submitting...
            </>
          ) : (
            "Create contract"
          )}
        </Button>
      </div>
    </div>
  );
}

function WizardFallback() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-6 w-1/2" />
      <Skeleton className="h-4 w-3/4" />
      <Skeleton className="h-32 w-full" />
    </div>
  );
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <Input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} />
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: unknown }) {
  const display =
    value === null || value === undefined || (typeof value === "string" && value.trim().length === 0)
      ? "-"
      : String(value);

  return (
    <div className="space-y-1">
      <span className="text-xs uppercase tracking-wide text-muted-foreground">{label}</span>
      <span className="block break-words text-sm">{display}</span>
    </div>
  );
}
