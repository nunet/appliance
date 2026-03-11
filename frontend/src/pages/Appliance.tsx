import { AlertTriangle, TimerIcon } from "lucide-react";
import React, { useCallback, useEffect, useState } from "react";

import { getApplianceLogs, ApplianceLogs, getApplianceUptime } from "../api/api";
import { Alert, AlertDescription } from "../components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { RefreshButton } from "../components/ui/RefreshButton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Skeleton } from "../components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";

const LINE_OPTIONS = [50, 100, 250, 500];

export default function Appliance() {
  const [logs, setLogs] = useState<ApplianceLogs | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lines, setLines] = useState<number>(50);

  const [uptime, setUptime] = useState<string | null>(null);
  const [isUptimeLoading, setIsUptimeLoading] = useState(true);
  const [uptimeError, setUptimeError] = useState<string | null>(null);

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

  useEffect(() => {
    fetchLogs();
    fetchUptime();
  }, [fetchLogs, fetchUptime]);

  const serviceNames = logs ? Object.keys(logs) : [];
  const defaultTab = serviceNames.length > 0 ? serviceNames[0] : "";

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
