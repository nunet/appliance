import * as React from "react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useQuery } from "@tanstack/react-query";
import { getTemplates } from "../api/deployments";

export default function HorizontalCarousel() {
  // Fetch templates using TanStack Query
  const { data, isLoading, isError } = useQuery({
    queryKey: ["templates-ensembles"],
    queryFn: getTemplates,
  });

  // If still loading → show skeletons
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 px-4 my-4">
        <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border rounded-lg">
          <CardHeader>
            <CardTitle className="text-lg font-semibold">Ensembles</CardTitle>
            {/* <CardDescription>
              Click on a template to view or deploy.
            </CardDescription> */}
          </CardHeader>
          <div className="w-full overflow-x-auto">
            <div className="flex gap-4 p-4">
              {[1, 2, 3].map((i) => (
                <Card
                  key={i}
                  className="min-w-[300px] max-w-[300px] flex-shrink-0 p-4"
                >
                  <Skeleton className="h-6 w-1/2 mb-2" />
                  <Skeleton className="h-4 w-3/4 mb-2" />
                  <Skeleton className="h-3 w-full" />
                </Card>
              ))}
            </div>
          </div>
        </Card>
      </div>
    );
  }

  // If error
  if (isError) {
    return <p className="text-destructive">Failed to load templates.</p>;
  }

  const templates = data?.items || [];

  // If empty
  if (templates.length === 0) {
    return <p className="text-muted-foreground">No templates found.</p>;
  }

  // Normal render
  return (
    <div className="grid grid-cols-1 gap-4 px-4 my-4">
      <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border rounded-lg">
        <CardHeader>
          <CardTitle className="text-lg font-semibold">Ensembles</CardTitle>
          <CardDescription>
            Click on a template to view or deploy.
          </CardDescription>
        </CardHeader>
        <div className="w-full overflow-x-auto">
          <div className="flex gap-4 snap-x snap-mandatory overflow-x-scroll scrollbar-hide p-4">
            {templates.map((template: any, idx: number) => (
              <Card
                key={idx}
                className="min-w-[300px] max-w-[300px] snap-center shadow-md flex-shrink-0"
              >
                <CardHeader>
                  <CardTitle>{template.name}</CardTitle>
                  <CardDescription>{template.relative_path}</CardDescription>
                  <p className="text-xs text-muted-foreground break-all mt-2">
                    {template.path}
                  </p>
                </CardHeader>
              </Card>
            ))}
          </div>
        </div>
      </Card>
    </div>
  );
}
