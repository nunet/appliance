import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";

export default function DeploymentStepFour() {
  const summaryItems = [
    { label: "Ensemble", value: "Floppybird" },
    { label: "Category", value: "Auki" },
    { label: "Deployment Type", value: "Local Deployment" },
    { label: "Target", value: "local appliance" },
    { label: "CPU Cores", value: "3" },
    { label: "Disk Size", value: `15 GB` },
    { label: "RAM Size", value: `13.2 GB` },
    { label: "Log Level", value: "Debug" },
    { label: "Peer ID", value: "peer:example:123456789" },
    { label: "Proxy Port", value: "8080" },
  ];

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
