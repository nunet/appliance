"use client";

import { useEffect, useMemo } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ChevronDown } from "lucide-react";
import { Separator } from "../ui/separator";
import { useQuery } from "@tanstack/react-query";
import { fetchTemplates, type Template } from "../../api/deployments";

interface Props {
  template: string;
  formData: Record<string, any>;
  setFormData: React.Dispatch<React.SetStateAction<Record<string, any>>>;
  formValid: boolean;
  setFormValid: (valid: boolean) => void;
  peer_id: string;
  deployment_type: string;
}

type FieldSpec = {
  label?: string;
  type?: string;
  placeholder?: string;
  required?: boolean;
  description?: string;
  default?: any;
  min?: number;
  max?: number;
  step?: number;
  options?: Array<{ value: string; label: string }>;
};

const FIELD_MAP: Record<string, keyof Props["formData"]> = {
  domain_name: "domain",
  proxy_port: "proxyPort",
  private_key: "privateKey",
  log_level: "logLevel",
  allocations_alloc1_resources_cpu_cores: "cpu",
  allocations_alloc1_resources_ram_size: "ram",
  allocations_alloc1_resources_disk_size: "disk",
};

export default function DeploymentStepThree({
  template,
  formData,
  setFormData,
  formValid,
  setFormValid,
  peer_id,
  deployment_type,
}: Props) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["templates-forms-page-1"],
    queryFn: () => fetchTemplates(1),
  });

  const tpl: Template | undefined = useMemo(() => {
    const all: Template[] = data?.items ?? [];
    return all.find((t) => t.path === template);
  }, [data, template]);

  const fields = (tpl?.schema?.fields ?? {}) as Record<string, FieldSpec>;

  // apply defaults
  useEffect(() => {
    if (!tpl) return;
    const next: Record<string, any> = {};
    for (const [apiKey, spec] of Object.entries(fields)) {
      const localKey = FIELD_MAP[apiKey];
      if (!localKey) continue;
      const hasValue =
        formData[localKey] !== undefined && formData[localKey] !== "";
      if (!hasValue && spec.default !== undefined) {
        next[localKey] = spec.default;
      }
    }
    if (Object.keys(next).length) {
      setFormData((prev) => ({ ...prev, ...next }));
    }
  }, [tpl]); // eslint-disable-line react-hooks/exhaustive-deps

  // validation
  useEffect(() => {
    if (!tpl) return;
    let valid = true;

    const checkNumber = (val: any, min?: number, max?: number) => {
      const num = Number(val);
      if (Number.isNaN(num)) return false;
      if (min !== undefined && num < min) return false;
      if (max !== undefined && num > max) return false;
      return true;
    };

    for (const [apiKey, spec] of Object.entries(fields)) {
      const localKey = FIELD_MAP[apiKey];
      if (!localKey) continue;

      // skip peer_id unless targeted
      if (apiKey === "peer_id" && deployment_type !== "targeted") continue;

      const val = formData[localKey];

      if (spec.required) {
        if (val === undefined || val === null || `${val}`.trim() === "") {
          valid = false;
          break;
        }
      }

      if (spec.type === "number") {
        if (!checkNumber(val, spec.min, spec.max)) {
          valid = false;
          break;
        }
      }

      if (apiKey === "proxy_port" && val !== undefined && val !== "") {
        const n = Number(val);
        if (!Number.isInteger(n) || n < 1 || n > 65535) {
          valid = false;
          break;
        }
      }
    }

    setFormValid(valid);
  }, [formData, tpl, deployment_type]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleChange = (field: keyof Props["formData"], value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const resetToDefault = (field: keyof Props["formData"]) => {
    const entry = Object.entries(FIELD_MAP).find(([, v]) => v === field);
    const apiKey = entry?.[0];
    if (apiKey) {
      const spec = fields[apiKey];
      if (spec && spec.default !== undefined) {
        setFormData((prev) => ({ ...prev, [field]: spec.default }));
      }
    }
  };

  if (!template)
    return <p className="text-muted-foreground">Select a template first.</p>;
  if (isLoading) return <p>Loading schema...</p>;
  if (isError) return <p>Error loading templates.</p>;
  if (!tpl) return <p>No template found for path: {template}</p>;

  const specByLocal = (localKey: keyof Props["formData"]) => {
    const entry = Object.entries(FIELD_MAP).find(([, v]) => v === localKey);
    const apiKey = entry?.[0];
    return apiKey ? fields[apiKey] : undefined;
  };

  const renderField = (
    localKey: keyof Props["formData"],
    readonly?: boolean,
    externalValue?: string
  ) => {
    const spec = specByLocal(localKey);
    if (!spec) return null;

    const val = externalValue ?? formData[localKey] ?? "";

    return (
      <div className="grid gap-2 my-3">
        <Label htmlFor={localKey}>{spec.label ?? localKey}</Label>
        <div className="flex items-center gap-2">
          <Input
            id={localKey}
            type={spec.type === "number" ? "number" : "text"}
            value={val}
            placeholder={spec.placeholder}
            min={spec.min as number | undefined}
            max={spec.max as number | undefined}
            step={spec.step as number | undefined}
            readOnly={readonly}
            onChange={(e) =>
              !readonly && handleChange(localKey, e.target.value)
            }
          />
          {!readonly && (
            <Button
              variant="outline"
              size="sm"
              type="button"
              onClick={() => resetToDefault(localKey)}
            >
              Reset
            </Button>
          )}
        </div>
        {spec.min !== undefined && spec.max !== undefined && (
          <p className="text-xs text-muted-foreground">
            Min: {spec.min}, Max: {spec.max}
          </p>
        )}
      </div>
    );
  };

  return (
    <div className="flex flex-col items-center w-full">
      <h2 className="text-2xl font-semibold mb-6">Configure</h2>
      <Separator className="mb-6" />

      <div className="grid gap-6 w-full max-w-3xl">
        <Collapsible defaultOpen={false}>
          <CollapsibleTrigger className="flex items-center justify-between bg-muted px-4 py-2 rounded-md cursor-pointer w-full mb-4">
            <span className="font-medium">Resource Configuration</span>
            <ChevronDown className="w-4 h-4 transition-transform data-[state=open]:rotate-180" />
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-2 grid gap-2">
            {renderField("cpu")}
            {renderField("disk")}
            {renderField("ram")}
          </CollapsibleContent>
        </Collapsible>

        <Separator className="my-4" />

        {renderField("domain")}
        {renderField("logLevel")}

        {/* Peer ID only if targeted */}
        {deployment_type === "targeted" &&
          renderField("peerId" as keyof Props["formData"], true, peer_id)}

        {renderField("privateKey")}
        {renderField("proxyPort")}

        {!formValid && (
          <p className="text-sm text-red-600">
            Some fields are invalid or missing. Please review the constraints.
          </p>
        )}
      </div>
    </div>
  );
}
