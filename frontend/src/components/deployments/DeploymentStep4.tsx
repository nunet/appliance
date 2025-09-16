import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

interface DeploymentStepFourProps {
  template_path: string; // e.g., an id or path to pick the template
  category?: string;
  formData: Record<string, any>; // dynamic formData
  deployment_type: string;
  peer_id?: string;
}

// Utility to make camelCase or snake_case keys readable
const formatLabel = (key: string) => {
  return key
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2") // camelCase -> spaces
    .replace(/\b\w/g, (l) => l.toUpperCase()); // capitalize
};

export default function DeploymentStepFour({
  template_path,
  formData,
  deployment_type,
  peer_id,
  category,
}: DeploymentStepFourProps) {
  // Build summary items dynamically
  const summaryItems = [
    { label: "Ensemble", value: template_path },
    { label: "Category", value: category || "N/A" },
    { label: "Deployment Type", value: deployment_type },
    ...Object.entries(formData).map(([key, value]) => ({
      label: formatLabel(key),
      value,
    })),
  ];

  // Add peer_id if deployment_type is targeted
  if (deployment_type === "targeted" && peer_id) {
    summaryItems.push({ label: "Peer ID", value: "..." + peer_id.slice(-6) });
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
