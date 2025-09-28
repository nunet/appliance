"use client";

import * as React from "react";
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from "../../components/ui/tabs";
import { Separator } from "../../components/ui/separator";
import { CopyButton } from "../ui/CopyButton";
import { LeftTruncatedText } from "../ui/LeftTruncatedText";

// Utils
const toStr = (v: unknown) =>
  typeof v === "string" ? v : v != null ? JSON.stringify(v) : "N/A";

const K = ({ label }: { label: string }) => (
  <span className="w-28 shrink-0 text-muted-foreground text-sm">{label}</span>
);

const V = ({ value }: { value?: string }) => (
  <LeftTruncatedText
    text={value || "N/A"}
    title={value || "N/A"}
    className="font-mono text-xs sm:text-sm"
  />
);

const KV = ({
  label,
  value,
  canCopy = true,
}: {
  label: string;
  value?: string;
  canCopy?: boolean;
}) => (
  <div className="flex items-center gap-2 py-1 min-w-0">
    <K label={label} />
    <V value={value} />
    {canCopy && value ? <CopyButton className="ml-auto" text={value} /> : null}
  </div>
);

const Pill = ({
  text,
  tone = "default",
}: {
  text: string;
  tone?: "ok" | "warn" | "err" | "info" | "default";
}) => {
  const tones: Record<string, string> = {
    ok: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
    warn: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
    err: "bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300",
    info: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
    default: "bg-muted text-foreground/70",
  };
  return (
    <span
      className={`px-2 py-0.5 rounded-full text-xs font-medium ${tones[tone]}`}
    >
      {text}
    </span>
  );
};

export function AllocationTabs({
  allocationEntries,
  selectedAlloc,
  setSelectedAlloc,
}: {
  allocationEntries: [string, any][];
  selectedAlloc: string;
  setSelectedAlloc: (alloc: string) => void;
}) {
  if (!allocationEntries.length) {
    return (
      <div className="rounded-lg border bg-muted/30 p-6 text-center">
        <h3 className="text-sm font-semibold mb-2">Allocations</h3>
        <p className="text-muted-foreground text-sm">No allocations.</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border bg-card p-6 shadow-sm space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold">Allocations</h3>
        <Pill
          text={`${allocationEntries.length} item${
            allocationEntries.length === 1 ? "" : "s"
          }`}
          tone="info"
        />
      </div>

      {/* Tabs */}
      <Tabs
        value={selectedAlloc}
        onValueChange={(e) => {
          setSelectedAlloc(e);
        }}
        className="w-full"
      >
        <div className="overflow-x-auto">
          <TabsList className="flex gap-2 min-w-max rounded-lg bg-muted/40 p-1 scrollbar-thin scrollbar-thumb-muted-foreground/20">
            {allocationEntries.map(([key]) => (
              <TabsTrigger key={key} value={key}>
                {key}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>

        {allocationEntries.map(([key, alloc]) => (
          <TabsContent key={key} value={key} className="mt-4">
            <div className="rounded-lg border bg-background p-5 space-y-4 shadow-sm">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-xs uppercase text-muted-foreground">
                  Allocation
                </span>
                <span className="text-sm font-semibold">{key}</span>
                <span className="ml-auto">
                  <Pill
                    text={alloc?.status ?? "unknown"}
                    tone={
                      alloc?.status === "running"
                        ? "ok"
                        : alloc?.status === "pending"
                        ? "warn"
                        : alloc?.status === "failed"
                        ? "err"
                        : "default"
                    }
                  />
                </span>
              </div>

              <Separator />

              <div className="space-y-2">
                <KV label="ID" value={toStr(alloc?.id)} />
                <KV label="Type" value={toStr(alloc?.type)} canCopy={false} />
                <KV label="DNS" value={toStr(alloc?.dns_name)} />
                <KV label="Node ID" value={toStr(alloc?.node_id)} />
                {alloc?.private_address && (
                  <KV
                    label="Private IP"
                    value={toStr(alloc?.private_address)}
                  />
                )}

                {alloc?.ports && (
                  <div className="flex items-start gap-2">
                    <K label="Ports" />
                    <pre className="font-mono text-xs overflow-x-auto max-h-48 p-3 rounded-md bg-muted/30 border w-full">
                      {JSON.stringify(alloc.ports, null, 2)}
                    </pre>
                  </div>
                )}

                {alloc?.ddns_url && (
                  <div className="flex items-center gap-2 min-w-0">
                    <K label="DDNS URL" />
                    <a
                      className="flex-1 min-w-0 underline decoration-dotted hover:decoration-solid"
                      href={alloc.ddns_url}
                      target="_blank"
                      rel="noreferrer"
                      title={alloc.ddns_url}
                    >
                      <LeftTruncatedText
                        text={alloc.ddns_url}
                        title={alloc.ddns_url}
                        className="max-w-full"
                      />
                    </a>
                    <CopyButton className="ml-auto" text={alloc.ddns_url} />
                  </div>
                )}
              </div>
            </div>
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
