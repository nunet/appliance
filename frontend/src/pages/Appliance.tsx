import { AlertTriangle, Loader2, TimerIcon } from "lucide-react";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";

import {
  getApplianceLogs,
  ApplianceLogs,
  refreshAuthToken,
  getTelemetryLocalMetrics,
  getApplianceUptime,
  getTelemetryPluginConfig,
  getTelemetryPluginStatus,
  triggerPluginSync,
  uninstallTelemetryPlugin,
  TelemetryLocalMetricsResponse,
  updateTelemetryPluginConfig,
  TelemetryPluginConfig,
  TelemetryPluginStatus,
} from "../api/api";
import { Alert, AlertDescription } from "../components/ui/alert";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "../components/ui/chart";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { RefreshButton } from "../components/ui/RefreshButton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Skeleton } from "../components/ui/skeleton";
import { Switch } from "../components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";

const LINE_OPTIONS = [50, 100, 250, 500];
const LOCAL_METRIC_RANGE_OPTIONS = [
  { value: "15m", label: "15m", minutes: 15, step: 15 },
  { value: "1h", label: "1h", minutes: 60, step: 30 },
  { value: "6h", label: "6h", minutes: 360, step: 60 },
  { value: "24h", label: "24h", minutes: 1440, step: 120 },
  { value: "7d", label: "7d", minutes: 10080, step: 900 },
  { value: "30d", label: "30d", minutes: 43200, step: 3600 },
];

export default function Appliance() {
  const [logs, setLogs] = useState<ApplianceLogs | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lines, setLines] = useState<number>(50);

  const [uptime, setUptime] = useState<string | null>(null);
  const [isUptimeLoading, setIsUptimeLoading] = useState(true);
  const [uptimeError, setUptimeError] = useState<string | null>(null);
  const [telemetryConfig, setTelemetryConfig] = useState<TelemetryPluginConfig | null>(null);
  const [telemetryStatus, setTelemetryStatus] = useState<TelemetryPluginStatus | null>(null);
  const [telemetryTokenInput, setTelemetryTokenInput] = useState("");
  const [telemetryLoading, setTelemetryLoading] = useState(true);
  const [telemetrySaving, setTelemetrySaving] = useState(false);
  const [telemetryApplying, setTelemetryApplying] = useState(false);
  const [telemetryError, setTelemetryError] = useState<string | null>(null);
  const [telemetryMessage, setTelemetryMessage] = useState<string | null>(null);
  const [telemetryStatusPending, setTelemetryStatusPending] = useState(false);
  const [telemetryUninstalling, setTelemetryUninstalling] = useState(false);
  const [telemetryGrafanaOpening, setTelemetryGrafanaOpening] = useState(false);
  const [telemetryMetricsRange, setTelemetryMetricsRange] = useState("1h");
  const [telemetryMetrics, setTelemetryMetrics] = useState<TelemetryLocalMetricsResponse | null>(null);
  const [telemetryMetricsLoading, setTelemetryMetricsLoading] = useState(false);
  const [telemetryMetricsError, setTelemetryMetricsError] = useState<string | null>(null);
  const telemetryStatusTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const selectedMetricsRange = LOCAL_METRIC_RANGE_OPTIONS.find((item) => item.value === telemetryMetricsRange) ?? LOCAL_METRIC_RANGE_OPTIONS[1];

  const formatTimestamp = (ts: number) => {
    const d = new Date(ts * 1000);
    if (selectedMetricsRange.minutes >= 7 * 24 * 60) {
      return d.toLocaleDateString([], { month: "short", day: "numeric" });
    }
    if (selectedMetricsRange.minutes > 24 * 60) {
      return d.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
    }
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  };

  const formatPercent = (value: number | null | undefined) => (value == null ? "n/a" : `${value.toFixed(1)}%`);
  const formatBps = (value: number | null | undefined) => {
    if (value == null) return "n/a";
    const units = ["B/s", "KB/s", "MB/s", "GB/s"];
    let v = value;
    let i = 0;
    while (v >= 1024 && i < units.length - 1) {
      v /= 1024;
      i += 1;
    }
    return `${v.toFixed(1)} ${units[i]}`;
  };
  const formatMib = (value: number | null | undefined) => (value == null ? "n/a" : `${value.toFixed(1)} MiB`);

  const fetchUptime = useCallback(async () => {
    setIsUptimeLoading(true);
    setUptimeError(null);
    try {
      const data = await getApplianceUptime();
      setUptime(data.uptime);
    } catch (err: any) {
      setUptimeError(err.message || "Failed to fetch uptime.");
    } finally {
      setIsUptimeLoading(false);
    }
  }, []);

  const fetchLogs = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await getApplianceLogs(lines);
      setLogs(data);
    } catch (err: any) {
      setError(err.message || "Failed to fetch logs.");
      setLogs(null);
    } finally {
      setIsLoading(false);
    }
  }, [lines]);

  const fetchTelemetry = useCallback(async () => {
    setTelemetryLoading(true);
    setTelemetryError(null);
    try {
      const [config, status] = await Promise.all([
        getTelemetryPluginConfig(),
        getTelemetryPluginStatus().catch(() => null),
      ]);
      setTelemetryConfig(config);
      setTelemetryStatus(status);
    } catch (err: any) {
      setTelemetryError(err.message || "Failed to fetch telemetry settings.");
      setTelemetryConfig(null);
      setTelemetryStatus(null);
    } finally {
      setTelemetryLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLogs();
    fetchUptime();
    fetchTelemetry();
  }, [fetchLogs, fetchUptime, fetchTelemetry]);

  useEffect(() => {
    return () => {
      if (telemetryStatusTimerRef.current) {
        clearTimeout(telemetryStatusTimerRef.current);
      }
    };
  }, []);

  const saveTelemetryConfig = useCallback(async () => {
    if (!telemetryConfig) return;
    if (telemetryStatusTimerRef.current) {
      clearTimeout(telemetryStatusTimerRef.current);
    }
    setTelemetryStatusPending(true);
    telemetryStatusTimerRef.current = setTimeout(() => {
      setTelemetryStatusPending(false);
    }, 5000);
    setTelemetrySaving(true);
    setTelemetryApplying(true);
    setTelemetryError(null);
    setTelemetryMessage(null);
    try {
      const hasSavedOrNewToken = telemetryConfig.token_set || telemetryTokenInput.trim().length > 0;
      const hasGateway = telemetryConfig.gateway_url.trim().length > 0;
      const updated = await updateTelemetryPluginConfig({
        enabled: telemetryConfig.enabled,
        remote_enabled: hasSavedOrNewToken && hasGateway ? true : false,
        local_enabled: telemetryConfig.local_enabled,
        dcgm_exporter_enabled: telemetryConfig.dcgm_exporter_enabled,
        grafana_enabled: telemetryConfig.grafana_enabled,
        gateway_url: telemetryConfig.gateway_url,
        generated_config_path: telemetryConfig.generated_config_path,
        telemetry_token: telemetryTokenInput.length > 0 ? telemetryTokenInput : undefined,
      });
      setTelemetryConfig(updated);
      setTelemetryTokenInput("");
      const result = await triggerPluginSync();
      setTelemetryMessage(result.message || "Telemetry settings saved and applied.");
      await fetchTelemetry();
    } catch (err: any) {
      setTelemetryError(err.message || "Failed to save telemetry settings.");
    } finally {
      setTelemetrySaving(false);
      setTelemetryApplying(false);
    }
  }, [fetchTelemetry, telemetryConfig, telemetryTokenInput]);

  const patchTelemetryAndApply = useCallback(
    async (patch: Partial<TelemetryPluginConfig>) => {
      if (!telemetryConfig) return;
      if (telemetryStatusTimerRef.current) {
        clearTimeout(telemetryStatusTimerRef.current);
      }
      setTelemetryStatusPending(true);
      telemetryStatusTimerRef.current = setTimeout(() => {
        setTelemetryStatusPending(false);
      }, 5000);
      setTelemetrySaving(true);
      setTelemetryApplying(true);
      setTelemetryError(null);
      setTelemetryMessage(null);
      try {
        const updated = await updateTelemetryPluginConfig({
          enabled: patch.enabled,
          remote_enabled: patch.remote_enabled,
          local_enabled: patch.local_enabled,
          dcgm_exporter_enabled: patch.dcgm_exporter_enabled,
          grafana_enabled: patch.grafana_enabled,
          gateway_url: patch.gateway_url,
          generated_config_path: patch.generated_config_path,
        });
        setTelemetryConfig(updated);
        const result = await triggerPluginSync();
        setTelemetryMessage(result.message || "Telemetry setting applied.");
        await fetchTelemetry();
      } catch (err: any) {
        setTelemetryError(err.message || "Failed to apply telemetry setting.");
        await fetchTelemetry();
      } finally {
        setTelemetrySaving(false);
        setTelemetryApplying(false);
      }
    },
    [fetchTelemetry, telemetryConfig]
  );

  const uninstallTelemetryAndData = useCallback(async () => {
    const confirmed = window.confirm(
      "Uninstall telemetry exporter and remove local telemetry data? This will stop services and delete stored telemetry data."
    );
    if (!confirmed) return;
    if (telemetryStatusTimerRef.current) {
      clearTimeout(telemetryStatusTimerRef.current);
    }
    setTelemetryStatusPending(true);
    telemetryStatusTimerRef.current = setTimeout(() => {
      setTelemetryStatusPending(false);
    }, 5000);
    setTelemetryUninstalling(true);
    setTelemetryError(null);
    setTelemetryMessage(null);
    try {
      const result = await uninstallTelemetryPlugin();
      setTelemetryMessage(result.message || "Telemetry plugin uninstall started.");
      await fetchTelemetry();
    } catch (err: any) {
      setTelemetryError(err.message || "Failed to trigger telemetry uninstall.");
    } finally {
      setTelemetryUninstalling(false);
    }
  }, [fetchTelemetry]);

  const serviceNames = logs ? Object.keys(logs) : [];
  const defaultTab = serviceNames.length > 0 ? serviceNames[0] : "";
  const remotePrereqsMet =
    telemetryConfig?.gateway_url.trim().length && telemetryConfig?.token_set ? true : false;
  const localMetricsVisible = Boolean(
    (telemetryConfig?.local_enabled || telemetryConfig?.grafana_enabled) && telemetryStatus?.local_mimir_running
  );
  const grafanaProxyBase = telemetryStatus?.grafana_url || telemetryConfig?.grafana_url || "/sys/plugins/telemetry-exporter/grafana/";
  const openGrafanaMonitoring = useCallback(async () => {
    if (!telemetryConfig?.grafana_enabled) return;
    setTelemetryGrafanaOpening(true);
    setTelemetryError(null);
    try {
      const auth = await refreshAuthToken();
      const grafanaHref = `${grafanaProxyBase}${grafanaProxyBase.includes("?") ? "&" : "?"}access_token=${encodeURIComponent(auth.access_token)}`;
      window.open(grafanaHref, "_blank", "noopener,noreferrer");
    } catch (err: any) {
      setTelemetryError(err?.message || "Failed to refresh session before opening Grafana.");
    } finally {
      setTelemetryGrafanaOpening(false);
    }
  }, [grafanaProxyBase, telemetryConfig?.grafana_enabled]);

  const fetchTelemetryMetrics = useCallback(async () => {
    if (!localMetricsVisible) {
      setTelemetryMetrics(null);
      setTelemetryMetricsError(null);
      setTelemetryMetricsLoading(false);
      return;
    }
    setTelemetryMetricsLoading(true);
    setTelemetryMetricsError(null);
    try {
      const data = await getTelemetryLocalMetrics(selectedMetricsRange.minutes, selectedMetricsRange.step);
      setTelemetryMetrics(data);
    } catch (err: any) {
      setTelemetryMetricsError(err.message || "Failed to load local telemetry metrics.");
      setTelemetryMetrics(null);
    } finally {
      setTelemetryMetricsLoading(false);
    }
  }, [localMetricsVisible, selectedMetricsRange.minutes, selectedMetricsRange.step]);

  useEffect(() => {
    fetchTelemetryMetrics();
  }, [fetchTelemetryMetrics]);

  useEffect(() => {
    if (!localMetricsVisible) return;
    const timer = setInterval(() => {
      fetchTelemetryMetrics();
    }, 15000);
    return () => clearInterval(timer);
  }, [fetchTelemetryMetrics, localMetricsVisible]);

  const chartData = (telemetryMetrics?.points || []).map((point) => ({
    ...point,
    timeLabel: formatTimestamp(point.ts),
  }));
  const hasGpuSeriesData = chartData.some(
    (point) =>
      point.gpu_utilization_percent != null ||
      point.gpu_temp_celsius != null ||
      point.gpu_vram_used_mib != null
  );

  return (
    <div className="flex flex-1 flex-col">
      <div className="container/main flex flex-1 flex-col gap-2">
        <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
          <div className="grid grid-cols-1 gap-4 px-4 lg:grid-cols-1 lg:px-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <TimerIcon className="h-5 w-5" />
                  System Status
                </CardTitle>
              </CardHeader>
              <CardContent>
                {isUptimeLoading ? (
                  <Skeleton className="h-6 w-48" />
                ) : uptimeError ? (
                  <Alert variant="destructive" className="w-auto max-w-md">
                    <AlertTriangle className="h-4 w-4" />
                    <AlertDescription>{uptimeError}</AlertDescription>
                  </Alert>
                ) : (
                  <div className="flex items-center gap-2 text-sm">
                    <p className="font-medium">Uptime:</p>
                    <p>{uptime}</p>
                  </div>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Advanced telemetry</CardTitle>
                <CardDescription>
                  Configure telemetry-exporter plugin settings. Toggles apply immediately; saving token/gateway also triggers plugin sync.
                  Local collection runs a local Mimir container and adds a local Alloy remote_write target.
                  Pro monitoring adds local Grafana dashboards and cAdvisor allocation metrics.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {telemetryLoading ? (
                  <div className="space-y-3">
                    <Skeleton className="h-6 w-48" />
                    <Skeleton className="h-6 w-full" />
                    <Skeleton className="h-10 w-40" />
                  </div>
                ) : telemetryConfig ? (
                  <>
                    <div className="flex flex-col gap-2 rounded-md border p-3 text-sm">
                      <div className="flex items-center gap-3">
                        <Switch
                          checked={telemetryConfig.enabled}
                          onCheckedChange={(checked) => patchTelemetryAndApply({ enabled: checked })}
                          disabled={telemetrySaving || telemetryApplying || telemetryUninstalling}
                        />
                        <span className="font-medium">Enable telemetry exporter</span>
                      </div>
                      <div className="flex items-center gap-3">
                        <Switch
                          checked={telemetryConfig.remote_enabled}
                          onCheckedChange={(checked) => patchTelemetryAndApply({ remote_enabled: checked })}
                          disabled={!remotePrereqsMet || telemetrySaving || telemetryApplying || telemetryUninstalling}
                        />
                        <span className="font-medium">Remote push</span>
                      </div>
                      <div className="flex items-center gap-3">
                        <Switch
                          checked={telemetryConfig.local_enabled}
                          onCheckedChange={(checked) =>
                            patchTelemetryAndApply({
                              local_enabled: checked,
                              ...(checked ? {} : { grafana_enabled: false }),
                            })
                          }
                          disabled={telemetrySaving || telemetryApplying || telemetryUninstalling}
                        />
                        <span className="font-medium">Local collection</span>
                      </div>
                      <div className="flex items-center gap-3">
                        <Switch
                          checked={telemetryConfig.dcgm_exporter_enabled}
                          onCheckedChange={(checked) => patchTelemetryAndApply({ dcgm_exporter_enabled: checked })}
                          disabled={
                            !telemetryConfig.nvidia_gpu_available ||
                            telemetrySaving ||
                            telemetryApplying ||
                            telemetryUninstalling
                          }
                        />
                        <span className="font-medium">DCGM exporter</span>
                      </div>
                      <div className="flex items-center gap-3">
                        <Switch
                          checked={telemetryConfig.grafana_enabled}
                          onCheckedChange={(checked) =>
                            patchTelemetryAndApply({
                              grafana_enabled: checked,
                              ...(checked ? { local_enabled: true, enabled: true } : {}),
                            })
                          }
                          disabled={telemetrySaving || telemetryApplying || telemetryUninstalling}
                        />
                        <span className="font-medium">Pro monitoring (Grafana + cAdvisor)</span>
                      </div>
                      {!remotePrereqsMet && (
                        <p className="text-xs text-muted-foreground">
                          Remote push stays disabled until a gateway URL and telemetry token are saved.
                        </p>
                      )}
                      {!telemetryConfig.nvidia_gpu_available && (
                        <p className="text-xs text-muted-foreground">
                          DCGM exporter is unavailable because no NVIDIA GPU was detected.
                        </p>
                      )}
                      {telemetryConfig.grafana_enabled && (
                        <p className="text-xs text-muted-foreground">
                          Pro monitoring auto-enables local collection and deploys Grafana + cAdvisor.
                        </p>
                      )}
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="telemetry-gateway">Gateway URL</Label>
                      <Input
                        id="telemetry-gateway"
                        value={telemetryConfig.gateway_url}
                        onChange={(e) =>
                          setTelemetryConfig((prev) => (prev ? { ...prev, gateway_url: e.target.value } : prev))
                        }
                        placeholder="https://telemetry.orgs.nunet.network"
                        disabled={telemetrySaving || telemetryApplying || telemetryUninstalling}
                      />
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="telemetry-token">
                        Telemetry token {telemetryConfig.token_set ? `(stored ••••${telemetryConfig.token_last8 || ""})` : "(not set)"}
                      </Label>
                      <Input
                        id="telemetry-token"
                        value={telemetryTokenInput}
                        onChange={(e) => setTelemetryTokenInput(e.target.value)}
                        placeholder={telemetryConfig.token_set ? "Enter new token to replace" : "Enter telemetry token"}
                        disabled={telemetrySaving || telemetryApplying || telemetryUninstalling}
                      />
                    </div>

                    <div className="flex flex-wrap gap-2">
                      <Button onClick={saveTelemetryConfig} disabled={telemetrySaving || telemetryApplying || telemetryUninstalling}>
                        {telemetrySaving ? "Saving..." : "Save remote telemetry settings"}
                      </Button>
                      <Button
                        variant="secondary"
                        onClick={openGrafanaMonitoring}
                        disabled={
                          !telemetryConfig.grafana_enabled ||
                          telemetryGrafanaOpening ||
                          telemetrySaving ||
                          telemetryApplying ||
                          telemetryUninstalling
                        }
                      >
                        {telemetryGrafanaOpening ? "Opening..." : "Open Pro monitoring"}
                      </Button>
                      <Button
                        variant="destructive"
                        onClick={uninstallTelemetryAndData}
                        disabled={telemetrySaving || telemetryApplying || telemetryUninstalling}
                      >
                        {telemetryUninstalling ? "Uninstalling..." : "Uninstall telemetry plugins"}
                      </Button>
                    </div>

                    <div className="text-xs text-muted-foreground">
                      <p>Toggles auto-save and auto-apply immediately.</p>
                      <p>Saving remote settings automatically enables remote push when token and gateway are present.</p>
                      <p>Plugin status: {telemetryStatus?.installed_version ? `installed ${telemetryStatus.installed_version}` : "not installed yet"}</p>
                      <p className="flex items-center gap-2">
                        Alloy:
                        {telemetryStatusPending ? (
                          <>
                            <Loader2 className="h-3 w-3 animate-spin" />
                            updating...
                          </>
                        ) : telemetryStatus?.alloy_running ? (
                          "running"
                        ) : (
                          "stopped"
                        )}
                      </p>
                      <p className="flex items-center gap-2">
                        Local Mimir:
                        {telemetryStatusPending ? (
                          <>
                            <Loader2 className="h-3 w-3 animate-spin" />
                            updating...
                          </>
                        ) : telemetryStatus?.local_mimir_running ? (
                          "running"
                        ) : (
                          "stopped"
                        )}
                      </p>
                      <p className="flex items-center gap-2">
                        DCGM exporter:
                        {telemetryStatusPending ? (
                          <>
                            <Loader2 className="h-3 w-3 animate-spin" />
                            updating...
                          </>
                        ) : telemetryStatus?.dcgm_exporter_running ? (
                          "running"
                        ) : (
                          "stopped"
                        )}
                      </p>
                      <p className="flex items-center gap-2">
                        cAdvisor:
                        {telemetryStatusPending ? (
                          <>
                            <Loader2 className="h-3 w-3 animate-spin" />
                            updating...
                          </>
                        ) : telemetryStatus?.cadvisor_running ? (
                          "running"
                        ) : (
                          "stopped"
                        )}
                      </p>
                      <p className="flex items-center gap-2">
                        Grafana:
                        {telemetryStatusPending ? (
                          <>
                            <Loader2 className="h-3 w-3 animate-spin" />
                            updating...
                          </>
                        ) : telemetryStatus?.local_grafana_running ? (
                          "running"
                        ) : (
                          "stopped"
                        )}
                      </p>
                      <p>NVIDIA GPU detected: {telemetryStatus?.nvidia_gpu_available ? "yes" : "no"}</p>
                      <p>Last sync: {telemetryStatus?.updated_at || "unknown"}</p>
                    </div>

                    <div className="space-y-3 rounded-md border p-3">
                      <div className="flex items-center justify-between gap-2">
                        <div>
                          <p className="text-sm font-medium">Local monitoring charts</p>
                          <p className="text-xs text-muted-foreground">
                            CPU, RAM, disk utilization, disk I/O, and network I/O from local Mimir.
                          </p>
                        </div>
                        <Select value={telemetryMetricsRange} onValueChange={setTelemetryMetricsRange}>
                          <SelectTrigger className="w-24">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {LOCAL_METRIC_RANGE_OPTIONS.map((opt) => (
                              <SelectItem key={opt.value} value={opt.value}>
                                {opt.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>

                      {!localMetricsVisible ? (
                        <p className="text-xs text-muted-foreground">
                          Enable Local collection and wait for Local Mimir to run to view charts.
                        </p>
                      ) : telemetryMetricsLoading ? (
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <Loader2 className="h-3 w-3 animate-spin" />
                          Loading local telemetry charts...
                        </div>
                      ) : telemetryMetricsError ? (
                        <p className="text-xs text-red-600">{telemetryMetricsError}</p>
                      ) : !telemetryMetrics?.available ? (
                        <p className="text-xs text-muted-foreground">{telemetryMetrics?.reason || "No metrics available yet."}</p>
                      ) : chartData.length === 0 ? (
                        <p className="text-xs text-muted-foreground">No local metrics data yet. Try again in a few moments.</p>
                      ) : (
                        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                          <Card className="p-2">
                            <CardHeader className="pb-1">
                              <CardTitle className="text-sm">CPU Utilization</CardTitle>
                            </CardHeader>
                            <CardContent className="p-2 pt-0">
                              <ChartContainer config={{ cpu_percent: { label: "CPU", color: "#22d3ee" } }} className="h-44 w-full">
                                <LineChart data={chartData}>
                                  <CartesianGrid vertical={false} />
                                  <XAxis dataKey="timeLabel" tickLine={false} axisLine={false} minTickGap={24} />
                                  <YAxis domain={[0, 100]} tickLine={false} axisLine={false} />
                                  <ChartTooltip content={<ChartTooltipContent formatter={(v) => formatPercent(Number(v))} />} />
                                  <Line
                                    type="monotone"
                                    dataKey="cpu_percent"
                                    stroke="var(--color-cpu_percent)"
                                    connectNulls
                                    dot={{ r: 2, fill: "var(--color-cpu_percent)" }}
                                    activeDot={{ r: 4 }}
                                    strokeWidth={2.5}
                                  />
                                </LineChart>
                              </ChartContainer>
                            </CardContent>
                          </Card>

                          <Card className="p-2">
                            <CardHeader className="pb-1">
                              <CardTitle className="text-sm">RAM Utilization</CardTitle>
                            </CardHeader>
                            <CardContent className="p-2 pt-0">
                              <ChartContainer config={{ memory_percent: { label: "RAM", color: "#a78bfa" } }} className="h-44 w-full">
                                <LineChart data={chartData}>
                                  <CartesianGrid vertical={false} />
                                  <XAxis dataKey="timeLabel" tickLine={false} axisLine={false} minTickGap={24} />
                                  <YAxis domain={[0, 100]} tickLine={false} axisLine={false} />
                                  <ChartTooltip content={<ChartTooltipContent formatter={(v) => formatPercent(Number(v))} />} />
                                  <Line
                                    type="monotone"
                                    dataKey="memory_percent"
                                    stroke="var(--color-memory_percent)"
                                    connectNulls
                                    dot={{ r: 2, fill: "var(--color-memory_percent)" }}
                                    activeDot={{ r: 4 }}
                                    strokeWidth={2.5}
                                  />
                                </LineChart>
                              </ChartContainer>
                            </CardContent>
                          </Card>

                          <Card className="p-2">
                            <CardHeader className="pb-1">
                              <CardTitle className="text-sm">Disk Utilization</CardTitle>
                            </CardHeader>
                            <CardContent className="p-2 pt-0">
                              <ChartContainer config={{ disk_utilization_percent: { label: "Disk", color: "#34d399" } }} className="h-44 w-full">
                                <LineChart data={chartData}>
                                  <CartesianGrid vertical={false} />
                                  <XAxis dataKey="timeLabel" tickLine={false} axisLine={false} minTickGap={24} />
                                  <YAxis domain={[0, 100]} tickLine={false} axisLine={false} />
                                  <ChartTooltip content={<ChartTooltipContent formatter={(v) => formatPercent(Number(v))} />} />
                                  <Line
                                    type="monotone"
                                    dataKey="disk_utilization_percent"
                                    stroke="var(--color-disk_utilization_percent)"
                                    connectNulls
                                    dot={{ r: 2, fill: "var(--color-disk_utilization_percent)" }}
                                    activeDot={{ r: 4 }}
                                    strokeWidth={2.5}
                                  />
                                </LineChart>
                              </ChartContainer>
                            </CardContent>
                          </Card>

                          <Card className="p-2">
                            <CardHeader className="pb-1">
                              <CardTitle className="text-sm">Disk I/O (read/write)</CardTitle>
                            </CardHeader>
                            <CardContent className="p-2 pt-0">
                              <ChartContainer
                                config={{
                                  disk_read_bytes_per_sec: { label: "Read", color: "#60a5fa" },
                                  disk_write_bytes_per_sec: { label: "Write", color: "#f97316" },
                                }}
                                className="h-44 w-full"
                              >
                                <LineChart data={chartData}>
                                  <CartesianGrid vertical={false} />
                                  <XAxis dataKey="timeLabel" tickLine={false} axisLine={false} minTickGap={24} />
                                  <YAxis tickLine={false} axisLine={false} />
                                  <ChartTooltip content={<ChartTooltipContent formatter={(v) => formatBps(Number(v))} />} />
                                  <Line
                                    type="monotone"
                                    dataKey="disk_read_bytes_per_sec"
                                    stroke="var(--color-disk_read_bytes_per_sec)"
                                    connectNulls
                                    dot={{ r: 2, fill: "var(--color-disk_read_bytes_per_sec)" }}
                                    activeDot={{ r: 4 }}
                                    strokeWidth={2.5}
                                  />
                                  <Line
                                    type="monotone"
                                    dataKey="disk_write_bytes_per_sec"
                                    stroke="var(--color-disk_write_bytes_per_sec)"
                                    connectNulls
                                    dot={{ r: 2, fill: "var(--color-disk_write_bytes_per_sec)" }}
                                    activeDot={{ r: 4 }}
                                    strokeWidth={2.5}
                                  />
                                </LineChart>
                              </ChartContainer>
                            </CardContent>
                          </Card>

                          <Card className="p-2 lg:col-span-2">
                            <CardHeader className="pb-1">
                              <CardTitle className="text-sm">Network I/O (rx/tx)</CardTitle>
                            </CardHeader>
                            <CardContent className="p-2 pt-0">
                              <ChartContainer
                                config={{
                                  network_rx_bytes_per_sec: { label: "RX", color: "#22d3ee" },
                                  network_tx_bytes_per_sec: { label: "TX", color: "#f472b6" },
                                }}
                                className="h-48 w-full"
                              >
                                <LineChart data={chartData}>
                                  <CartesianGrid vertical={false} />
                                  <XAxis dataKey="timeLabel" tickLine={false} axisLine={false} minTickGap={24} />
                                  <YAxis tickLine={false} axisLine={false} />
                                  <ChartTooltip content={<ChartTooltipContent formatter={(v) => formatBps(Number(v))} />} />
                                  <Line
                                    type="monotone"
                                    dataKey="network_rx_bytes_per_sec"
                                    stroke="var(--color-network_rx_bytes_per_sec)"
                                    connectNulls
                                    dot={{ r: 2, fill: "var(--color-network_rx_bytes_per_sec)" }}
                                    activeDot={{ r: 4 }}
                                    strokeWidth={2.5}
                                  />
                                  <Line
                                    type="monotone"
                                    dataKey="network_tx_bytes_per_sec"
                                    stroke="var(--color-network_tx_bytes_per_sec)"
                                    connectNulls
                                    dot={{ r: 2, fill: "var(--color-network_tx_bytes_per_sec)" }}
                                    activeDot={{ r: 4 }}
                                    strokeWidth={2.5}
                                  />
                                </LineChart>
                              </ChartContainer>
                            </CardContent>
                          </Card>

                          {telemetryConfig.nvidia_gpu_available ? (
                            <>
                              <Card className="p-2">
                                <CardHeader className="pb-1">
                                  <CardTitle className="text-sm">GPU Utilization</CardTitle>
                                </CardHeader>
                                <CardContent className="p-2 pt-0">
                                  <ChartContainer
                                    config={{ gpu_utilization_percent: { label: "GPU Util", color: "#eab308" } }}
                                    className="h-44 w-full"
                                  >
                                    <LineChart data={chartData}>
                                      <CartesianGrid vertical={false} />
                                      <XAxis dataKey="timeLabel" tickLine={false} axisLine={false} minTickGap={24} />
                                      <YAxis domain={[0, 100]} tickLine={false} axisLine={false} />
                                      <ChartTooltip content={<ChartTooltipContent formatter={(v) => formatPercent(Number(v))} />} />
                                      <Line
                                        type="monotone"
                                        dataKey="gpu_utilization_percent"
                                        stroke="var(--color-gpu_utilization_percent)"
                                        connectNulls
                                        dot={{ r: 2, fill: "var(--color-gpu_utilization_percent)" }}
                                        activeDot={{ r: 4 }}
                                        strokeWidth={2.5}
                                      />
                                    </LineChart>
                                  </ChartContainer>
                                </CardContent>
                              </Card>

                              <Card className="p-2">
                                <CardHeader className="pb-1">
                                  <CardTitle className="text-sm">GPU Temperature</CardTitle>
                                </CardHeader>
                                <CardContent className="p-2 pt-0">
                                  <ChartContainer config={{ gpu_temp_celsius: { label: "GPU Temp", color: "#ef4444" } }} className="h-44 w-full">
                                    <LineChart data={chartData}>
                                      <CartesianGrid vertical={false} />
                                      <XAxis dataKey="timeLabel" tickLine={false} axisLine={false} minTickGap={24} />
                                      <YAxis tickLine={false} axisLine={false} />
                                      <ChartTooltip content={<ChartTooltipContent formatter={(v) => `${Number(v).toFixed(1)} °C`} />} />
                                      <Line
                                        type="monotone"
                                        dataKey="gpu_temp_celsius"
                                        stroke="var(--color-gpu_temp_celsius)"
                                        connectNulls
                                        dot={{ r: 2, fill: "var(--color-gpu_temp_celsius)" }}
                                        activeDot={{ r: 4 }}
                                        strokeWidth={2.5}
                                      />
                                    </LineChart>
                                  </ChartContainer>
                                </CardContent>
                              </Card>

                              <Card className="p-2 lg:col-span-2">
                                <CardHeader className="pb-1">
                                  <CardTitle className="text-sm">GPU VRAM Used</CardTitle>
                                </CardHeader>
                                <CardContent className="p-2 pt-0">
                                  <ChartContainer config={{ gpu_vram_used_mib: { label: "VRAM", color: "#06b6d4" } }} className="h-48 w-full">
                                    <LineChart data={chartData}>
                                      <CartesianGrid vertical={false} />
                                      <XAxis dataKey="timeLabel" tickLine={false} axisLine={false} minTickGap={24} />
                                      <YAxis tickLine={false} axisLine={false} />
                                      <ChartTooltip content={<ChartTooltipContent formatter={(v) => formatMib(Number(v))} />} />
                                      <Line
                                        type="monotone"
                                        dataKey="gpu_vram_used_mib"
                                        stroke="var(--color-gpu_vram_used_mib)"
                                        connectNulls
                                        dot={{ r: 2, fill: "var(--color-gpu_vram_used_mib)" }}
                                        activeDot={{ r: 4 }}
                                        strokeWidth={2.5}
                                      />
                                    </LineChart>
                                  </ChartContainer>
                                </CardContent>
                              </Card>
                            </>
                          ) : (
                            <Card className="p-2 lg:col-span-2">
                              <CardContent className="p-3 text-xs text-muted-foreground">
                                GPU charts are hidden because no NVIDIA GPU was detected.
                              </CardContent>
                            </Card>
                          )}

                          {telemetryConfig.nvidia_gpu_available && !hasGpuSeriesData && (
                            <Card className="p-2 lg:col-span-2">
                              <CardContent className="p-3 text-xs text-muted-foreground">
                                NVIDIA GPU detected but no GPU metrics yet. Enable DCGM exporter and wait 1-2 minutes for data points.
                              </CardContent>
                            </Card>
                          )}
                        </div>
                      )}
                    </div>
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground">Telemetry plugin config is unavailable.</p>
                )}

                {telemetryError && (
                  <Alert variant="destructive">
                    <AlertTriangle className="h-4 w-4" />
                    <AlertDescription>{telemetryError}</AlertDescription>
                  </Alert>
                )}
                {telemetryMessage && (
                  <Alert>
                    <AlertDescription>{telemetryMessage}</AlertDescription>
                  </Alert>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex-row items-center justify-between">
                <div>
                  <CardTitle>System Logs</CardTitle>
                  <CardDescription>View logs from systemd services.</CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <Select value={String(lines)} onValueChange={(v) => setLines(Number(v))}>
                    <SelectTrigger className="w-32">
                      <SelectValue placeholder="Lines" />
                    </SelectTrigger>
                    <SelectContent>
                      {LINE_OPTIONS.map((option) => (
                        <SelectItem key={option} value={String(option)}>
                          {option} lines
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <RefreshButton onClick={fetchLogs} isLoading={isLoading} tooltip="Refresh logs" />
                </div>
              </CardHeader>
              <CardContent>
                {isLoading ? (
                  <div className="space-y-4">
                    <Skeleton className="h-8 w-full max-w-lg" />
                    <Skeleton className="h-40 w-full" />
                  </div>
                ) : error ? (
                  <Alert variant="destructive">
                    <AlertTriangle className="h-4 w-4" />
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                ) : logs && serviceNames.length > 0 ? (
                  <Tabs defaultValue={defaultTab} className="w-full">
                    <TabsList className="grid w-full grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5">
                      {serviceNames.map((service) => (
                        <TabsTrigger key={service} value={service}>
                          {service.replace(".service", "")}
                        </TabsTrigger>
                      ))}
                    </TabsList>
                    {serviceNames.map((service) => (
                      <TabsContent key={service} value={service}>
                        <div className="mt-4 h-96 overflow-y-auto rounded-md bg-muted p-4 font-mono text-sm">
                          <pre>{logs[service]}</pre>
                        </div>
                      </TabsContent>
                    ))}
                  </Tabs>
                ) : (
                  <p>No logs available.</p>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
