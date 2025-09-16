"use client";

import { memo, useEffect, useMemo, useState } from "react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import { CopyButton } from "@/components/ui/CopyButton";
import { RefreshButton } from "@/components/ui/RefreshButton"; // 👈 import your reusable refresh
import { Server, Network, Container, Globe, Box, ListTree } from "lucide-react";
import { AllocationTabs } from "./AllocationsTab";
import { useSelectedAllocation } from "./allocation.hook";

type ManifestPanelProps = {
  manifest: any | null | undefined;
  isLoading?: boolean;
  onRefresh?: () => void; // 👈 add a callback for refreshing
  isRefreshing?: boolean; // 👈 track if refreshing
  _setAlloc: (alloc: string | null) => void;
};

// ...utils (toStr, short, K, V, KV, Pill) remain unchanged...

/**
 * Small utilities
 */
const toStr = (v: unknown) =>
  typeof v === "string" ? v : v != null ? JSON.stringify(v) : "N/A";

const short = (id?: string, left = 10, right = 6) =>
  id
    ? id.length > left + right
      ? `${id.slice(0, left)}…${id.slice(-right)}`
      : id
    : "—";

const K = ({ label }: { label: string }) => (
  <span className="w-28 shrink-0 text-muted-foreground">{label}</span>
);

const V = ({ value }: { value?: string }) => (
  <span
    className="
      font-mono text-xs sm:text-sm truncate
      max-w-[160px] xs:max-w-[200px] sm:max-w-[280px] md:max-w-[420px] lg:max-w-[560px] xl:max-w-none
    "
    title={value || "N/A"}
  >
    {value || "N/A"}
  </span>
);

/**
 * Reusable KV row with a Copy button that always stays visible.
 */
const KV = ({
  label,
  value,
  canCopy = true,
}: {
  label: string;
  value?: string;
  canCopy?: boolean;
}) => (
  <div className="flex items-center gap-2 py-1">
    <K label={label} />
    <V value={value} />
    {canCopy && value ? <CopyButton className="ml-auto" text={value} /> : null}
  </div>
);

/**
 * Pills for statuses
 */
const Pill = ({
  text,
  tone = "default",
}: {
  text: string;
  tone?: "ok" | "warn" | "err" | "info" | "default";
}) => {
  const tones: Record<string, string> = {
    ok: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 ring-1 ring-emerald-500/20",
    warn: "bg-amber-500/10 text-amber-700 dark:text-amber-400 ring-1 ring-amber-500/20",
    err: "bg-rose-500/10 text-rose-600 dark:text-rose-400 ring-1 ring-rose-500/20",
    info: "bg-sky-500/10 text-sky-600 dark:text-sky-400 ring-1 ring-sky-500/20",
    default: "bg-muted text-foreground/70 ring-1 ring-border",
  };
  return (
    <span
      className={`px-2 py-0.5 rounded-full text-xs font-medium ${
        tones[tone] ?? tones.default
      }`}
    >
      {text}
    </span>
  );
};

function ManifestPanelImpl({
  manifest,
  isLoading,
  onRefresh,
  isRefreshing,
  _setAlloc,
}: ManifestPanelProps) {
  const m = manifest?.manifest ?? {};
  const hasValidId =
    m?.id !== undefined && m?.id !== null && String(m?.id).trim() !== "";
  const orchestrator = m?.orchestrator ?? {};
  const allocations: Record<string, any> = m?.allocations ?? {};
  const nodes: Record<string, any> = m?.nodes ?? {};

  const allocationEntries = useMemo(
    () => Object.entries(allocations || {}),
    [allocations]
  );
  const nodeEntries = useMemo(() => Object.entries(nodes || {}), [nodes]);
  const [selected_allocation, set_selected_allocation] = useState<string>(
    allocationEntries[0]?.[0] || "alloc1"
  );

  useEffect(() => {
    _setAlloc(selected_allocation);
  }, [selected_allocation, _setAlloc]);
  if (!hasValidId) {
    return (
      <div className="px-4 my-4 w-full">
        <Card className="flex items-center justify-center min-h-[200px] text-muted-foreground text-sm">
          No manifest available
          {onRefresh && (
            <div className="mt-4">
              <RefreshButton
                onClick={onRefresh}
                isLoading={isRefreshing}
                tooltip="Refresh manifest"
              />
            </div>
          )}
        </Card>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 px-4 my-4 w-full">
      <Card className="relative bg-gradient-to-b from-primary/5 to-card dark:from-primary/10 shadow-sm border rounded-xl overflow-hidden">
        <CardHeader className="space-y-1 flex flex-row items-center justify-between">
          <div>
            <CardDescription className="flex items-center gap-2 text-sm">
              <ListTree className="h-4 w-4" />
              Manifest
            </CardDescription>
            <CardTitle className="text-2xl md:text-3xl font-semibold tracking-tight">
              Manifest for Deployment&nbsp;
              <span className="text-primary">{short(m?.id)}</span>
            </CardTitle>
          </div>
          {onRefresh && (
            <RefreshButton
              onClick={onRefresh}
              isLoading={isRefreshing}
              tooltip="Refresh manifest"
            />
          )}
        </CardHeader>

        <CardContent className="space-y-8">
          {/* === Deployment Overview =================================================== */}
          <section className="space-y-4">
            <div className="flex items-center gap-2">
              <Server className="h-4 w-4" />
              <CardDescription className="uppercase tracking-wider text-xs">
                Deployment Overview
              </CardDescription>
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Deployment Info */}
              <div className="rounded-lg border bg-muted/30 p-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold">Deployment Info</h3>
                </div>
                <Separator className="my-3" />
                <div className="space-y-1.5">
                  <KV label="ID" value={toStr(m?.id)} />
                  {/* If available in your payload, these will render; otherwise they stay hidden */}
                  {m?.subnet && (
                    <div className="flex items-start gap-2">
                      <K label="Subnet" />
                      <pre className="font-mono text-xs overflow-x-auto max-h-36 p-2 rounded bg-background/60 border w-full">
                        {JSON.stringify(m.subnet, null, 2)}
                      </pre>
                    </div>
                  )}
                  {m?.contracts && (
                    <div className="flex items-start gap-2">
                      <K label="Contracts" />
                      <pre className="font-mono text-xs overflow-x-auto max-h-36 p-2 rounded bg-background/60 border w-full">
                        {JSON.stringify(m.contracts, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              </div>

              {/* Orchestrator */}
              <div className="rounded-lg border bg-muted/30 p-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold flex items-center gap-2">
                    <Network className="h-4 w-4" />
                    Orchestrator
                  </h3>
                </div>
                <Separator className="my-3" />
                <div className="space-y-1.5">
                  <KV label="Pub" value={toStr(orchestrator?.id?.pub)} />
                  <KV label="DID" value={toStr(orchestrator?.did?.uri)} />
                  <KV label="Host" value={toStr(orchestrator?.addr?.host)} />
                  <KV label="Inbox" value={toStr(orchestrator?.addr?.inbox)} />
                </div>
              </div>
            </div>
          </section>

          {/* === Ensemble Configuration / Allocations + Nodes ========================= */}
          <section className="space-y-4">
            <div className="flex items-center gap-2">
              <Container className="h-4 w-4" />
              <CardDescription className="uppercase tracking-wider text-xs">
                Ensemble Configuration
              </CardDescription>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Allocations */}
              <AllocationTabs
                allocationEntries={allocationEntries}
                selectedAlloc={selected_allocation}
                setSelectedAlloc={set_selected_allocation}
              />

              {/* Nodes */}
              <div className="rounded-lg border bg-muted/30 p-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold flex items-center gap-2">
                    <Box className="h-4 w-4" />
                    Nodes ({selected_allocation})
                  </h3>
                  <Pill
                    text={`${
                      nodeEntries.filter(([_, node]) =>
                        node.allocations.includes(selected_allocation)
                      ).length || 0
                    } item${
                      nodeEntries.filter(([_, node]) =>
                        node.allocations.includes(selected_allocation)
                      ).length === 1
                        ? ""
                        : "s"
                    }`}
                    tone={
                      nodeEntries.filter(([_, node]) =>
                        node.allocations.includes(selected_allocation)
                      ).length
                        ? "info"
                        : "default"
                    }
                  />
                </div>

                <Separator className="my-3" />

                {nodeEntries.filter(([_, node]) =>
                  node.allocations.includes(selected_allocation)
                ).length ? (
                  <ul className="space-y-3 max-h-[22rem] overflow-y-auto pr-1">
                    {nodeEntries
                      .filter(([_, node]) =>
                        node.allocations.includes(selected_allocation)
                      )
                      .map(([key, node]) => (
                        <li
                          key={key}
                          className="rounded-md border bg-background p-3"
                        >
                          <div className="flex items-center gap-2 mb-2">
                            <span className="text-xs uppercase text-muted-foreground">
                              Node
                            </span>
                            <span className="text-sm font-semibold">{key}</span>
                          </div>
                          <div className="space-y-1.5">
                            <KV label="ID" value={toStr(node?.id)} />
                            <KV label="Peer" value={toStr(node?.peer)} />
                            <div className="flex items-start gap-2">
                              <K label="Allocations" />
                              <span className="font-mono text-xs">
                                {Array.isArray(node?.allocations) &&
                                node.allocations.length
                                  ? node.allocations.join(", ")
                                  : "N/A"}
                              </span>
                            </div>
                            {node?.location && (
                              <div className="flex items-start gap-2">
                                <K label="Location" />
                                <pre className="font-mono text-xs overflow-x-auto max-h-28 p-2 rounded bg-background/60 border w-full">
                                  {JSON.stringify(node.location, null, 2)}
                                </pre>
                              </div>
                            )}
                            {node?.port_mappings && (
                              <div className="flex items-start gap-2">
                                <K label="Port Mappings" />
                                <pre className="font-mono text-xs overflow-x-auto max-h-28 p-2 rounded bg-background/60 border w-full">
                                  {JSON.stringify(node.port_mappings, null, 2)}
                                </pre>
                              </div>
                            )}
                          </div>
                        </li>
                      ))}
                  </ul>
                ) : (
                  <p className="text-muted-foreground text-sm">
                    No nodes for this allocation.
                  </p>
                )}
              </div>
            </div>
          </section>

          {/* === Optional DDNS section (renders only when data is present) ============ */}
          {m?.ddns || allocationEntries.some(([, a]) => a?.ddns_url) ? (
            <section className="space-y-4">
              <div className="flex items-center gap-2">
                <Globe className="h-4 w-4" />
                <CardDescription className="uppercase tracking-wider text-xs">
                  DDNS URLs
                </CardDescription>
              </div>

              <div className="rounded-lg border bg-muted/30 p-4">
                <div className="space-y-3">
                  {/* From a generic ddns map if your API provides it */}
                  {m?.ddns &&
                    Object.entries(m.ddns).map(([name, url]: any) => (
                      <div key={name} className="flex items-center gap-2">
                        <span className="text-sm font-semibold">{name}</span>
                        <span className="text-xs px-1.5 py-0.5 rounded bg-background border">
                          URL
                        </span>
                        <a
                          className="truncate underline decoration-dotted hover:decoration-solid"
                          href={String(url)}
                          target="_blank"
                          rel="noreferrer"
                          title={String(url)}
                        >
                          {String(url)}
                        </a>
                        <CopyButton className="ml-auto" text={String(url)} />
                      </div>
                    ))}

                  {/* From allocations (ddns_url per allocation) */}
                  {allocationEntries.map(([key, a]: any) =>
                    a?.ddns_url ? (
                      <div
                        key={`${key}-ddns`}
                        className="flex items-center gap-2"
                      >
                        <span className="text-sm font-semibold">{key}</span>
                        <span className="text-xs px-1.5 py-0.5 rounded bg-background border">
                          URL
                        </span>
                        <a
                          className="truncate underline decoration-dotted hover:decoration-solid"
                          href={a.ddns_url}
                          target="_blank"
                          rel="noreferrer"
                          title={a.ddns_url}
                        >
                          {a.ddns_url}
                        </a>
                        <CopyButton className="ml-auto" text={a.ddns_url} />
                      </div>
                    ) : null
                  )}
                </div>
              </div>
            </section>
          ) : null}
        </CardContent>

        <CardFooter className="flex flex-col sm:flex-row gap-2 sm:items-center sm:justify-between">
          <div className="text-xs text-muted-foreground">
            Tip: values are truncated on small screens—hover or tap to see full
            text.
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              const blob = new Blob([JSON.stringify(manifest ?? {}, null, 2)], {
                type: "application/json",
              });
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a");
              a.href = url;
              a.download = `manifest-${short(m?.id).replaceAll("…", "")}.json`;
              a.click();
              URL.revokeObjectURL(url);
            }}
          >
            Download Manifest JSON
          </Button>
        </CardFooter>

        {isLoading && (
          <div className="absolute inset-0 bg-background/70 backdrop-blur-[2px] flex items-center justify-center">
            <span className="animate-pulse text-sm text-muted-foreground">
              Loading manifest…
            </span>
          </div>
        )}
      </Card>
    </div>
  );
}

export const ManifestPanel = memo(ManifestPanelImpl);
