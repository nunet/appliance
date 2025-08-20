import { useQuery } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { fetchTemplates } from "../../api/deployments";

interface DeploymentStepFourProps {
  template_path: string; // e.g. an id or path to pick the template
  category?: string; // optional category for the template
  formData: {
    cpu: number;
    disk: number;
    ram: number;
    proxyPort: number;
  };
  deployment_type: string;
  peer_id?: string;
}

export default function DeploymentStepFour({
  template_path,
  formData,
  deployment_type,
  peer_id,
  category,
}: DeploymentStepFourProps) {
  const summaryItems = [
    { label: "Ensemble", value: template_path },
    { label: "Category", value: category || "N/A" },
    { label: "Deployment Type", value: deployment_type },
    { label: "CPU Cores", value: formData.cpu },
    { label: "Disk Size", value: `${formData.disk} GB` },
    { label: "RAM Size", value: `${formData.ram} GB` },
    { label: "Proxy Port", value: formData.proxyPort },
  ];

  if (deployment_type === "targeted" && peer_id) {
    summaryItems.push({ label: "Peer ID", value: peer_id });
  }

  return (
    <div className="flex flex-col items-center w-full">
      <h2 className="text-2xl font-semibold mb-6">Deployment Summary</h2>

      <Card className="w-full max-w-3xl bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs">
        <CardContent>
          <div className="space-y-4">
            {summaryItems.map((item, idx) => (
              <div key={idx}>
                <div className="flex justify-between text-sm">
                  <span className="font-medium text-muted-foreground">
                    {item.label}
                  </span>
                  <span className="font-semibold">{item.value}</span>
                </div>
                {idx < summaryItems.length - 1 && (
                  <Separator className="my-2" />
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
