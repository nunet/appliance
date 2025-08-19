import { useState } from "react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default function DeploymentStepOne() {
  const [selected, setSelected] = useState<string | null>(null);

  const options = [
    {
      id: "Auki-hagali-node",
      name: "Auki-hagali-node",
      description: "No Description available for this option.",
      tag: "auki",
    },
    {
      id: "floppy-bird",
      name: "floppy-bird",
      description: "No Description available for this option.",
      tag: "rare-evo",
    },
  ];

  return (
    <div className="flex flex-col items-center w-full">
      <h2 className="text-2xl font-semibold mb-6">Choose Deployment Type</h2>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 w-full max-w-4xl">
        {options.map((opt) => (
          <Card
            key={opt.id}
            onClick={() => setSelected(opt.id)}
            className={cn(
              "cursor-pointer transition-all duration-500 border-2",
              selected === opt.id
                ? "bg-gradient-to-r from-green-500/60 to-transparent border-green-500 shadow-md"
                : "hover:border-blue-400"
            )}
          >
            <CardHeader>
              <CardTitle>{opt.name}</CardTitle>
              <CardDescription>{opt.description}</CardDescription>
            </CardHeader>
            <CardContent>
              <Badge className="bg-blue-500 text-white">{opt.tag}</Badge>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
