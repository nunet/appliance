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
import { Button } from "@/components/ui/button";
import TemplateUploadDialog from "@/components/ensembles/TemplateUploadDialog";

export default function HorizontalCarousel() {
  const [uploadOpen, setUploadOpen] = React.useState(false);

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
          {/* ✅ Put the button in the header even during loading */}
          <CardHeader className="flex items-center justify-between flex-row">
            <div>
              <CardTitle className="text-lg font-semibold">Ensembles</CardTitle>
            </div>
            <Button onClick={() => setUploadOpen(true)}>Upload Template</Button>
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

        {/* ✅ Mount the dialog */}
        <TemplateUploadDialog
          open={uploadOpen}
          onOpenChange={setUploadOpen}
        />
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
    return (
      <div className="grid grid-cols-1 gap-4 px-4 my-4">
        <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border rounded-lg">
          <CardHeader className="flex items-center justify-between flex-row">
            <div>
              <CardTitle className="text-lg font-semibold">Ensembles</CardTitle>
              <CardDescription>Upload a template to get started.</CardDescription>
            </div>
            <Button onClick={() => setUploadOpen(true)}>Upload Template</Button>
          </CardHeader>
        </Card>

        <TemplateUploadDialog
          open={uploadOpen}
          onOpenChange={setUploadOpen}
        />
      </div>
    );
  }

  // Normal render
  return (
    <div className="grid grid-cols-1 gap-4 px-4 my-4">
      <Card className="@container/card bg-gradient-to-t from-primary/5 to-card dark:bg-card shadow-xs border rounded-lg">
        {/* ✅ Button in the main header */}
        <CardHeader className="flex items-center justify-between flex-row">
          <div>
            <CardTitle className="text-lg font-semibold">Ensembles</CardTitle>
            <CardDescription>
              Click on a template to view or deploy.
            </CardDescription>
          </div>
          <Button onClick={() => setUploadOpen(true)}>Upload Template</Button>
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

      <TemplateUploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
      />
    </div>
  );
}