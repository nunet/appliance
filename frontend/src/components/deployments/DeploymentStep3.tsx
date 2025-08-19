import { useState } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Separator } from "../ui/separator";

export default function DeploymentStepThree() {
  const [formData, setFormData] = useState({
    cpu: "",
    disk: "",
    ram: "",
    domain: "",
    logLevel: "",
    peerId: "",
    privateKey: "",
    proxyPort: "",
  });

  const handleChange = (field: string, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  return (
    <div className="flex flex-col items-center w-full">
      <h2 className="text-2xl font-semibold mb-6">Configure</h2>
      <Separator className="mb-6" />
      <div className="grid gap-6 w-full max-w-3xl">
        <h2 className="text-center">Resource Configuration</h2>

        <div className="grid gap-2">
          <Label htmlFor="cpu">CPU Cores</Label>
          <Input
            id="cpu"
            type="number"
            placeholder="e.g. 4"
            value={formData.cpu}
            onChange={(e) => handleChange("cpu", e.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="disk">Disk Size (GB)</Label>
          <Input
            id="disk"
            type="number"
            placeholder="e.g. 100"
            value={formData.disk}
            onChange={(e) => handleChange("disk", e.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="ram">RAM Size (GB)</Label>
          <Input
            id="ram"
            type="number"
            placeholder="e.g. 16"
            value={formData.ram}
            onChange={(e) => handleChange("ram", e.target.value)}
          />
        </div>

        <Separator />

        <h2 className="text-center">General</h2>

        <div className="grid gap-2">
          <Label htmlFor="domain">Domain Name</Label>
          <Input
            id="domain"
            placeholder="example.com"
            value={formData.domain}
            onChange={(e) => handleChange("domain", e.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="logLevel">Log Level</Label>
          <Select
            value={formData.logLevel}
            onValueChange={(value) => handleChange("logLevel", value)}
          >
            <SelectTrigger id="logLevel">
              <SelectValue placeholder="Select log level" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="debug">Debug</SelectItem>
              <SelectItem value="info">Info</SelectItem>
              <SelectItem value="warn">Warn</SelectItem>
              <SelectItem value="error">Error</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="grid gap-2">
          <Label htmlFor="peerId">Peer ID</Label>
          <Input
            id="peerId"
            placeholder="Enter Peer ID"
            value={formData.peerId}
            onChange={(e) => handleChange("peerId", e.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="privateKey">Private Key</Label>
          <Input
            id="privateKey"
            type="password"
            placeholder="Enter private key"
            value={formData.privateKey}
            onChange={(e) => handleChange("privateKey", e.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="proxyPort">Proxy Port</Label>
          <Input
            id="proxyPort"
            type="number"
            placeholder="8080"
            value={formData.proxyPort}
            onChange={(e) => handleChange("proxyPort", e.target.value)}
          />
        </div>
      </div>
    </div>
  );
}
