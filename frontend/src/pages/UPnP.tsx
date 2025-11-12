import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../components/ui/card";
import { Button } from "../components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "../components/ui/dialog";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { Badge } from "../components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "../components/ui/alert";
import { Checkbox } from "../components/ui/checkbox";
import { toast } from "sonner";
import {
  Wifi,
  RefreshCw,
  Plus,
  Trash2,
  ExternalLink,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Network,
  Globe,
  Shield,
  Zap,
  Lock,
  Server,
} from "lucide-react";
import {
  discoverGateway,
  listPortMappings,
  createPortMapping,
  deletePortMapping,
  configureApplianceForwarding,
  disableApplianceForwarding,
  getApplianceStatus,
  CreatePortMappingRequest,
  PortMapping,
} from "../api/upnp";

export default function UPnPPage() {
  const queryClient = useQueryClient();
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [newMapping, setNewMapping] = useState<CreatePortMappingRequest>({
    external_port: 443,
    internal_port: 8443,
    protocol: "TCP",
    description: "Custom Port",
  });

  // Queries
  const [forceRefresh, setForceRefresh] = useState(false);
  
  const {
    data: gatewayData,
    isLoading: gatewayLoading,
    refetch: refetchGateway,
  } = useQuery({
    queryKey: ["upnp-gateway", forceRefresh],
    queryFn: () => discoverGateway(forceRefresh),
    retry: 1,
    staleTime: 0, // Always fetch fresh data - critical for detecting router state changes
    refetchOnMount: 'always', // Always refetch when component mounts
    refetchOnWindowFocus: true, // Refetch when user returns to tab
  });

  const {
    data: statusData,
    isLoading: statusLoading,
    refetch: refetchStatus,
  } = useQuery({
    queryKey: ["upnp-status"],
    queryFn: getApplianceStatus,
    retry: 1,
    staleTime: 10000, // Cache for 10 seconds (short TTL for real-time accuracy)
    enabled: gatewayData?.status === "success", // Only query if gateway is available
  });

  const {
    data: mappingsData,
    isLoading: mappingsLoading,
    refetch: refetchMappings,
  } = useQuery({
    queryKey: ["upnp-mappings", gatewayData?.gateway_info?.local_ip],
    queryFn: () => listPortMappings(gatewayData?.gateway_info?.local_ip),
    retry: 1,
    staleTime: 10000, // Cache for 10 seconds (short TTL for real-time accuracy)
    enabled: !!gatewayData?.gateway_info?.local_ip,
  });

  // Mutations
  const configureApplianceMutation = useMutation({
    mutationFn: configureApplianceForwarding,
    onSuccess: (data) => {
      if (data.status === "success" || data.status === "partial") {
        toast.success("Success", {
          description: data.message,
        });
        queryClient.invalidateQueries({ queryKey: ["upnp-status"] });
        queryClient.invalidateQueries({ queryKey: ["upnp-mappings"] });
      } else {
        toast.error("Error", {
          description: data.message,
        });
      }
    },
    onError: (error: any) => {
      toast.error("Error", {
        description: error.response?.data?.detail || error.message,
      });
    },
  });

  const disableApplianceMutation = useMutation({
    mutationFn: disableApplianceForwarding,
    onSuccess: (data) => {
      if (data.status === "success" || data.status === "partial") {
        toast.success("Success", {
          description: data.message,
        });
        queryClient.invalidateQueries({ queryKey: ["upnp-status"] });
        queryClient.invalidateQueries({ queryKey: ["upnp-mappings"] });
      } else {
        toast.error("Error", {
          description: data.message,
        });
      }
    },
    onError: (error: any) => {
      toast.error("Error", {
        description: error.response?.data?.detail || error.message,
      });
    },
  });

  const addMappingMutation = useMutation({
    mutationFn: createPortMapping,
    onSuccess: (data) => {
      if (data.status === "success") {
        toast.success("Success", {
          description: data.message,
        });
        setAddDialogOpen(false);
        setNewMapping({
          external_port: 443,
          internal_port: 8443,
          protocol: "TCP",
          description: "Custom Port",
        });
        queryClient.invalidateQueries({ queryKey: ["upnp-mappings"] });
        queryClient.invalidateQueries({ queryKey: ["upnp-status"] });
      } else {
        toast.error("Error", {
          description: data.message,
        });
      }
    },
    onError: (error: any) => {
      toast.error("Error", {
        description: error.response?.data?.detail || error.message,
      });
    },
  });

  const deleteMappingMutation = useMutation({
    mutationFn: ({ port, protocol }: { port: number; protocol: string }) =>
      deletePortMapping(port, protocol),
    onSuccess: (data) => {
      if (data.status === "success") {
        toast.success("Success", {
          description: data.message,
        });
        queryClient.invalidateQueries({ queryKey: ["upnp-mappings"] });
        queryClient.invalidateQueries({ queryKey: ["upnp-status"] });
      } else {
        toast.error("Error", {
          description: data.message,
        });
      }
    },
    onError: (error: any) => {
      toast.error("Error", {
        description: error.response?.data?.detail || error.message,
      });
    },
  });

  const handleRefreshAll = () => {
    // Force a fresh discovery (bypasses cache)
    setForceRefresh(true);
    setTimeout(() => {
      refetchGateway();
      refetchStatus();
      refetchMappings();
      // Reset to false after refetch
      setTimeout(() => setForceRefresh(false), 100);
    }, 10);
  };

  const handleAddMapping = () => {
    addMappingMutation.mutate(newMapping);
  };

  const handleDeleteMapping = (mapping: PortMapping) => {
    if (
      window.confirm(
        `Delete port mapping ${mapping.external_port}/${mapping.protocol}?`
      )
    ) {
      deleteMappingMutation.mutate({
        port: mapping.external_port,
        protocol: mapping.protocol,
      });
    }
  };

  const gatewayAvailable = gatewayData?.gateway_found && gatewayData?.status === "success";

  return (
    <div className="container mx-auto p-4 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Network className="h-8 w-8" />
            UPnP Port Forwarding
          </h1>
          <p className="text-muted-foreground mt-1">
            Manage router port forwarding for external access
          </p>
        </div>
        <Button
          onClick={handleRefreshAll}
          variant="outline"
          disabled={gatewayLoading || statusLoading || mappingsLoading}
        >
          <RefreshCw
            className={`h-4 w-4 mr-2 ${
              gatewayLoading || statusLoading || mappingsLoading
                ? "animate-spin"
                : ""
            }`}
          />
          Refresh All
        </Button>
      </div>

      {/* Error Alert - Show when UPnP is not available */}
      {!gatewayLoading && !gatewayAvailable && (
        <Alert variant={gatewayData?.router_info?.detected ? "default" : "destructive"}>
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>
            {gatewayData?.router_info?.detected 
              ? "UPnP Not Available" 
              : "UPnP Not Available"}
          </AlertTitle>
          <AlertDescription>
            {gatewayData?.message ||
              (gatewayData?.router_info?.detected
                ? `Router detected (${gatewayData.router_info.brand} at ${gatewayData.router_info.gateway_ip}) but UPnP is not enabled. Enable UPnP on your router to configure port forwarding automatically, or configure port forwarding manually.`
                : "No UPnP gateway found. Ensure UPnP is enabled on your router or configure port forwarding manually.")}
          </AlertDescription>
        </Alert>
      )}

      {/* Gateway Info Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Wifi className="h-5 w-5" />
            Gateway Information
          </CardTitle>
          <CardDescription>
            UPnP router discovery and connection details
          </CardDescription>
        </CardHeader>
        <CardContent>
          {gatewayLoading ? (
            <div className="text-center py-8 text-muted-foreground">
              <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-2" />
              Discovering gateway...
            </div>
          ) : (
            <div className="space-y-4">
              {/* Router Information - Show if router_info exists (even when UPnP is disabled) */}
              {gatewayData?.router_info?.detected && (
                <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                  <div className="flex items-center gap-2 mb-2">
                    <Wifi className="h-4 w-4 text-blue-600" />
                    <span className="font-semibold text-blue-900">
                      {gatewayData.router_info.brand || "Router"} Detected
                    </span>
                  </div>
                  <div className="text-sm text-blue-800">
                    <span className="font-mono">
                      {gatewayData.router_info.gateway_ip || "Unknown"}
                    </span>
                    {gatewayData.router_info.mac_address && (
                      <span className="text-blue-600 ml-2">
                        ({gatewayData.router_info.mac_address})
                      </span>
                    )}
                  </div>
                </div>
              )}
              
              {/* UPnP Connection Details - Only show if UPnP is available */}
              {gatewayAvailable && gatewayData.gateway_info ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <Globe className="h-4 w-4 text-muted-foreground" />
                      <span className="font-semibold">External IP:</span>
                      <span className="font-mono">
                        {gatewayData.gateway_info.external_ip}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Wifi className="h-4 w-4 text-muted-foreground" />
                      <span className="font-semibold">Router IP:</span>
                      <span className="font-mono">
                        {gatewayData.gateway_info.gateway_ip || gatewayData.router_info?.gateway_ip || "Unknown"}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Network className="h-4 w-4 text-muted-foreground" />
                      <span className="font-semibold">Appliance IP:</span>
                      <span className="font-mono">
                        {gatewayData.gateway_info.local_ip}
                      </span>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <Shield className="h-4 w-4 text-muted-foreground" />
                      <span className="font-semibold">Connection Type:</span>
                      <span>{gatewayData.gateway_info.connection_type}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-green-500" />
                      <span className="font-semibold">UPnP Status:</span>
                      <Badge variant="outline" className="bg-green-50 text-green-700">
                        {gatewayData.gateway_info.connection_status}
                      </Badge>
                    </div>
                  </div>
                </div>
              ) : gatewayData?.router_info?.detected ? (
                /* Show router info only (UPnP disabled) */
                <div className="text-center py-4 text-muted-foreground">
                  <AlertCircle className="h-6 w-6 mx-auto mb-2 text-yellow-600" />
                  <p>Router detected but UPnP is not available</p>
                  <p className="text-sm mt-1">
                    {gatewayData?.message || "Enable UPnP on your router to configure port forwarding automatically."}
                  </p>
                </div>
              ) : (
                /* No router detected at all */
                <div className="text-center py-8 text-muted-foreground">
                  <XCircle className="h-8 w-8 mx-auto mb-2" />
                  No router detected
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Appliance Status Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Zap className="h-5 w-5" />
            Appliance Port Forwarding
          </CardTitle>
          <CardDescription>
            Configure external access to your appliance
          </CardDescription>
        </CardHeader>
        <CardContent>
          {statusLoading ? (
            <div className="text-center py-8 text-muted-foreground">
              <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-2" />
              Checking status...
            </div>
          ) : statusData?.status === "success" ? (
            <div className="space-y-6">
              {/* Port 443 - Web Apps */}
              <div className="p-4 border rounded-lg space-y-3">
                <div className="flex items-start justify-between">
                  <div className="flex items-start gap-3 flex-1">
                    <Server className="h-5 w-5 text-blue-500 mt-1" />
                    <div className="flex-1">
                      <div className="font-semibold text-base flex items-center gap-2">
                        Web Applications (Port 443)
                        {statusData.appliance_forwarding?.port_443.mapping_exists ? (
                          <Badge variant="outline" className="bg-green-50 text-green-700">
                            <CheckCircle2 className="h-3 w-3 mr-1" />
                            Active
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="bg-gray-50 text-gray-700">
                            <XCircle className="h-3 w-3 mr-1" />
                            Inactive
                          </Badge>
                        )}
                      </div>
                      <p className="text-sm text-muted-foreground mt-1">
                        Forward port 443 → 443 for Caddy proxy to serve multiple web applications.
                        This allows external HTTPS access to your web services.
                      </p>
                      {statusData.gateway_info?.external_ip && statusData.appliance_forwarding?.port_443.mapping_exists && (
                        <div className="mt-2">
                          <a
                            href={`https://${statusData.gateway_info.external_ip}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sm text-blue-600 hover:underline flex items-center gap-1"
                          >
                            <ExternalLink className="h-3 w-3" />
                            https://{statusData.gateway_info.external_ip}
                          </a>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant={statusData.appliance_forwarding?.port_443.mapping_exists ? "outline" : "default"}
                    onClick={() => configureApplianceMutation.mutate({ enable_web_apps: true, enable_remote_management: false })}
                    disabled={!gatewayAvailable || configureApplianceMutation.isPending || statusData.appliance_forwarding?.port_443.mapping_exists}
                  >
                    {configureApplianceMutation.isPending ? (
                      <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <CheckCircle2 className="h-4 w-4 mr-2" />
                    )}
                    Enable
                  </Button>
                  {statusData.appliance_forwarding?.port_443.mapping_exists && (
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() => disableApplianceMutation.mutate({ disable_web_apps: true, disable_remote_management: false })}
                      disabled={!gatewayAvailable || disableApplianceMutation.isPending}
                    >
                      {disableApplianceMutation.isPending ? (
                        <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                      ) : (
                        <XCircle className="h-4 w-4 mr-2" />
                      )}
                      Disable
                    </Button>
                  )}
                </div>
              </div>

              {/* Port 8443 - Remote Management */}
              <div className="p-4 border rounded-lg space-y-3 bg-yellow-50/50 border-yellow-200">
                <div className="flex items-start justify-between">
                  <div className="flex items-start gap-3 flex-1">
                    <Lock className="h-5 w-5 text-yellow-600 mt-1" />
                    <div className="flex-1">
                      <div className="font-semibold text-base flex items-center gap-2">
                        Remote Management (Port 8443)
                        {statusData.appliance_forwarding?.port_8443.mapping_exists ? (
                          <Badge variant="outline" className="bg-green-50 text-green-700">
                            <CheckCircle2 className="h-3 w-3 mr-1" />
                            Active
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="bg-gray-50 text-gray-700">
                            <XCircle className="h-3 w-3 mr-1" />
                            Inactive
                          </Badge>
                        )}
                      </div>
                      <p className="text-sm text-muted-foreground mt-1">
                        <strong className="text-yellow-800">Optional:</strong> Forward port 8443 → 8443 to allow remote management 
                        of this appliance from the internet. <strong>Use with caution.</strong>
                      </p>
                      {statusData.gateway_info?.external_ip && statusData.appliance_forwarding?.port_8443.mapping_exists && (
                        <div className="mt-2">
                          <a
                            href={`https://${statusData.gateway_info.external_ip}:8443`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sm text-yellow-700 hover:underline flex items-center gap-1 font-medium"
                          >
                            <ExternalLink className="h-3 w-3" />
                            https://{statusData.gateway_info.external_ip}:8443
                          </a>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant={statusData.appliance_forwarding?.port_8443.mapping_exists ? "outline" : "default"}
                    onClick={() => configureApplianceMutation.mutate({ enable_web_apps: false, enable_remote_management: true })}
                    disabled={!gatewayAvailable || configureApplianceMutation.isPending || statusData.appliance_forwarding?.port_8443.mapping_exists}
                  >
                    {configureApplianceMutation.isPending ? (
                      <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <CheckCircle2 className="h-4 w-4 mr-2" />
                    )}
                    Enable
                  </Button>
                  {statusData.appliance_forwarding?.port_8443.mapping_exists && (
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() => disableApplianceMutation.mutate({ disable_web_apps: false, disable_remote_management: true })}
                      disabled={!gatewayAvailable || disableApplianceMutation.isPending}
                    >
                      {disableApplianceMutation.isPending ? (
                        <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                      ) : (
                        <XCircle className="h-4 w-4 mr-2" />
                      )}
                      Disable
                    </Button>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <AlertCircle className="h-8 w-8 mx-auto mb-2" />
              Status unavailable
            </div>
          )}
        </CardContent>
      </Card>

      {/* Port Mappings Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                Port Mappings for This Appliance
                {mappingsData && (
                  <Badge variant="outline" className="font-normal">
                    {mappingsData.filtered_count} / {mappingsData.total_count} total
                  </Badge>
                )}
              </CardTitle>
              <CardDescription>
                Port forwarding rules pointing to this appliance
                {gatewayData?.gateway_info?.local_ip && (
                  <span className="font-mono ml-1">({gatewayData.gateway_info.local_ip})</span>
                )}
              </CardDescription>
            </div>
            <Dialog open={addDialogOpen} onOpenChange={setAddDialogOpen}>
              <DialogTrigger asChild>
                <Button
                  size="sm"
                  disabled={!gatewayAvailable}
                >
                  <Plus className="h-4 w-4 mr-2" />
                  Add Mapping
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Add Port Mapping</DialogTitle>
                  <DialogDescription>
                    Create a new port forwarding rule on your router
                  </DialogDescription>
                </DialogHeader>
                <div className="space-y-4 py-4">
                  <div className="space-y-2">
                    <Label htmlFor="external-port">External Port</Label>
                    <Input
                      id="external-port"
                      type="number"
                      value={newMapping.external_port}
                      onChange={(e) =>
                        setNewMapping({
                          ...newMapping,
                          external_port: parseInt(e.target.value),
                        })
                      }
                      placeholder="443"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="internal-port">Internal Port</Label>
                    <Input
                      id="internal-port"
                      type="number"
                      value={newMapping.internal_port}
                      onChange={(e) =>
                        setNewMapping({
                          ...newMapping,
                          internal_port: parseInt(e.target.value),
                        })
                      }
                      placeholder="8443"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="protocol">Protocol</Label>
                    <Select
                      value={newMapping.protocol}
                      onValueChange={(value) =>
                        setNewMapping({ ...newMapping, protocol: value })
                      }
                    >
                      <SelectTrigger id="protocol">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="TCP">TCP</SelectItem>
                        <SelectItem value="UDP">UDP</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="description">Description</Label>
                    <Input
                      id="description"
                      value={newMapping.description}
                      onChange={(e) =>
                        setNewMapping({
                          ...newMapping,
                          description: e.target.value,
                        })
                      }
                      placeholder="My Service"
                    />
                  </div>
                </div>
                <DialogFooter>
                  <Button
                    variant="outline"
                    onClick={() => setAddDialogOpen(false)}
                  >
                    Cancel
                  </Button>
                  <Button
                    onClick={handleAddMapping}
                    disabled={addMappingMutation.isPending}
                  >
                    {addMappingMutation.isPending && (
                      <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                    )}
                    Add Mapping
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </CardHeader>
        <CardContent>
          {mappingsLoading ? (
            <div className="text-center py-8 text-muted-foreground">
              <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-2" />
              Loading mappings...
            </div>
          ) : mappingsData?.mappings && mappingsData.mappings.length > 0 ? (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>External Port</TableHead>
                    <TableHead>Protocol</TableHead>
                    <TableHead>Internal Address</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {mappingsData.mappings.map((mapping, idx) => (
                    <TableRow key={idx}>
                      <TableCell className="font-mono">
                        {mapping.external_port}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{mapping.protocol}</Badge>
                      </TableCell>
                      <TableCell className="font-mono">
                        {mapping.internal_ip}:{mapping.internal_port}
                      </TableCell>
                      <TableCell>{mapping.description}</TableCell>
                      <TableCell>
                        {mapping.enabled ? (
                          <Badge
                            variant="outline"
                            className="bg-green-50 text-green-700"
                          >
                            <CheckCircle2 className="h-3 w-3 mr-1" />
                            Enabled
                          </Badge>
                        ) : (
                          <Badge
                            variant="outline"
                            className="bg-gray-50 text-gray-700"
                          >
                            <XCircle className="h-3 w-3 mr-1" />
                            Disabled
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDeleteMapping(mapping)}
                          disabled={deleteMappingMutation.isPending}
                        >
                          <Trash2 className="h-4 w-4 text-red-500" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <Network className="h-8 w-8 mx-auto mb-2" />
              <p className="font-medium">No port mappings found for this appliance</p>
              {mappingsData?.total_count > 0 && (
                <p className="text-sm mt-2">
                  Router has {mappingsData.total_count} total mapping(s), but none point to this appliance
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Info Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <AlertCircle className="h-5 w-5" />
            About UPnP Port Forwarding
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground">
          <p>
            <strong>UPnP (Universal Plug and Play)</strong> allows your appliance to
            automatically configure port forwarding on your router, making it accessible
            from the internet.
          </p>
          <div>
            <p className="font-semibold text-foreground mb-1">Port Configuration:</p>
            <ul className="list-disc list-inside ml-4 space-y-1">
              <li>
                <strong>Port 443 → 443:</strong> For web applications served via Caddy proxy.
                This allows HTTPS access to your web services at <code>https://&lt;your-ip&gt;</code>
              </li>
              <li>
                <strong>Port 8443 → 8443:</strong> Optional remote management access to this appliance interface
                at <code>https://&lt;your-ip&gt;:8443</code>
              </li>
            </ul>
          </div>
          <div>
            <p className="font-semibold text-foreground mb-1">Requirements:</p>
            <ul className="list-disc list-inside ml-4 space-y-1">
              <li>UPnP must be enabled on your router</li>
              <li>Your router must support UPnP/IGD protocol</li>
              <li>The appliance must be on the same local network as the router</li>
            </ul>
          </div>
          <p>
            <strong className="text-yellow-700">Security Note:</strong> Only forward necessary ports. 
            Remote management (port 8443) should only be enabled if you need to manage this appliance 
            from outside your network.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

