"use client";

import { useEffect, useMemo, useState } from "react";
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
  category?: string;
};

export default function DeploymentStepThree({
  template,
  formData,
  setFormData,
  formValid,
  setFormValid,
  deployment_type,
}: Props) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["templates-forms"],
    queryFn: () => fetchTemplates(1),
  });

  const tpl: Template | undefined = useMemo(() => {
    const all: Template[] = data?.items ?? [];
    return all.find((t) => t.path === template);
  }, [data, template]);

  const fields = (tpl?.schema?.fields ?? {}) as Record<string, FieldSpec>;
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  // Defaults
  useEffect(() => {
    if (!tpl) return;
    const next: Record<string, any> = {};
    for (const [key, spec] of Object.entries(fields)) {
      if (key === "peer_id") continue;
      if (formData[key] === undefined || formData[key] === "") {
        next[key] = spec.default ?? "";
      }
    }
    if (Object.keys(next).length) {
      setFormData((prev) => ({ ...prev, ...next }));
    }
  }, [tpl]);

  // Validation
  useEffect(() => {
    if (!tpl) return;

    const nextErrors: Record<string, string> = {};
    let valid = true;

    const checkNumber = (val: any, min?: number, max?: number) => {
      const n = Number(val);
      if (Number.isNaN(n)) return false;
      if (min !== undefined && n < min) return false;
      if (max !== undefined && n > max) return false;
      return true;
    };

    for (const [key, spec] of Object.entries(fields)) {
      if (key === "peer_id") continue;
      const val = formData[key];

      if (spec.required && (!val || `${val}`.trim() === "")) {
        nextErrors[key] = "This field is required.";
        valid = false;
        continue;
      }

      if (spec.type === "number" && !checkNumber(val, spec.min, spec.max)) {
        nextErrors[key] = `Value must be between ${spec.min ?? "-"} and ${
          spec.max ?? "-"
        }`;
        valid = false;
        continue;
      }

      if (key === "proxy_port" && val) {
        const n = Number(val);
        if (!Number.isInteger(n) || n < 1 || n > 65535) {
          nextErrors[key] = "Port must be an integer between 1-65535";
          valid = false;
          continue;
        }
      }

      if (!nextErrors[key]) nextErrors[key] = "";
    }

    setFieldErrors(nextErrors);
    setFormValid(valid);
  }, [formData, tpl, deployment_type]);

  const handleChange = (key: string, value: any) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
  };

  const resetToDefault = (key: string) => {
    const spec = fields[key];
    if (spec?.default !== undefined) {
      setFormData((prev) => ({ ...prev, [key]: spec.default }));
    }
  };

  const renderField = (key: string) => {
    if (key === "peer_id") return null;
    const spec = fields[key];
    if (!spec) return null;
    const val = formData[key] ?? "";
    const error = fieldErrors[key];

    if (spec.type === "select" && spec.options) {
      return (
        <div className="grid gap-1 my-2" key={key}>
          <Label>
            {spec.label || key}{" "}
            <span className="text-muted-foreground text-xs">
              {spec.default !== undefined && `(default: ${spec.default})`}
            </span>
          </Label>
          <select
            className={`px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 ${
              error ? "border-red-500" : "border-gray-600"
            } bg-gray-800 text-white`}
            value={val}
            onChange={(e) => handleChange(key, e.target.value)}
          >
            {spec.options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          {error && <p className="text-xs text-red-500">{error}</p>}
        </div>
      );
    }

    return (
      <div className="grid gap-1 my-2" key={key}>
        <Label>
          {spec.label || key}{" "}
          <span className="text-muted-foreground text-xs">
            {spec.default !== undefined && `(default: ${spec.default})`}{" "}
            {spec.min !== undefined && `(min: ${spec.min})`}{" "}
            {spec.max !== undefined && `(max: ${spec.max})`}
          </span>
        </Label>
        <div className="flex items-center gap-2">
          <Input
            type={spec.type === "number" ? "number" : "text"}
            value={val}
            placeholder={spec.placeholder}
            min={spec.min}
            max={spec.max}
            step={spec.step}
            onChange={(e) => handleChange(key, e.target.value)}
            className={error ? "border-red-500" : ""}
          />
          <Button
            size="sm"
            variant="outline"
            onClick={() => resetToDefault(key)}
          >
            Reset
          </Button>
        </div>
        {error && <p className="text-xs text-red-500">{error}</p>}
      </div>
    );
  };

  if (!template)
    return <p className="text-muted-foreground">Select a template first.</p>;
  if (isLoading) return <p>Loading template schema...</p>;
  if (isError) return <p>Error loading templates</p>;
  if (!tpl) return <p>No template found for path: {template}</p>;

  // Group allocations
  const allocations: Record<string, string[]> = {};
  const general: string[] = [];

  Object.keys(fields).forEach((k) => {
    if (k.startsWith("allocations_")) {
      const match = k.match(/^allocations_(alloc\d+)_/);
      if (match) {
        const allocId = match[1];
        allocations[allocId] = allocations[allocId] || [];
        allocations[allocId].push(k);
      }
    } else {
      if (k !== "peer_id") general.push(k);
    }
  });

  const isMultiAlloc = Object.keys(allocations).length > 1;

  return (
    <div className="flex flex-col w-full max-w-3xl mx-auto">
      <h2 className="text-xl font-semibold mb-4">{tpl.schema.name}</h2>
      <Separator className="mb-4" />

      {isMultiAlloc ? (
        <>
          {Object.entries(allocations).map(([allocId, keys]) => {
            const resourceKeys = keys.filter(
              (k) => fields[k].category === "resources"
            );

            return (
              <div key={allocId} className="mb-6 border rounded-md">
                <Collapsible>
                  <CollapsibleTrigger className="flex justify-between bg-muted/40 px-4 py-2 rounded-t-md cursor-pointer w-full">
                    <span className="font-medium">Resources ({allocId})</span>
                    <ChevronDown className="w-4 h-4 transition-transform data-[state=open]:rotate-180" />
                  </CollapsibleTrigger>
                  <CollapsibleContent className="grid gap-2 bg-muted/20 p-3">
                    {resourceKeys.map(renderField)}
                  </CollapsibleContent>
                </Collapsible>
              </div>
            );
          })}

          {/* General/settings flat */}
          {general.length > 0 && (
            <div className="grid gap-3">{general.map(renderField)}</div>
          )}
        </>
      ) : (
        <>
          {/* Single alloc → collapsible only for resources */}
          {Object.entries(allocations).map(([allocId, keys]) => {
            const resourceKeys = keys.filter(
              (k) => fields[k].category === "resources"
            );
            const settingsKeys = keys.filter(
              (k) => fields[k].category !== "resources"
            );

            return (
              <div key={allocId} className="mb-6">
                <Collapsible defaultOpen>
                  <CollapsibleTrigger className="flex justify-between bg-muted/40 px-4 py-2 rounded-t-md cursor-pointer w-full">
                    <span className="font-medium">Resources</span>
                    <ChevronDown className="w-4 h-4 transition-transform data-[state=open]:rotate-180" />
                  </CollapsibleTrigger>
                  <CollapsibleContent className="grid gap-2 bg-muted/20 p-3 border rounded-b-md">
                    {resourceKeys.map(renderField)}
                  </CollapsibleContent>
                </Collapsible>

                {/* Flat settings */}
                <div className="grid gap-3 mt-4">
                  {settingsKeys.map(renderField)}
                  {general.map(renderField)}
                </div>
              </div>
            );
          })}
        </>
      )}
    </div>
  );
}
