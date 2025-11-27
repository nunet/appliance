import * as React from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { fetchTemplates, getTemplates, type Template } from "../../api/deployments";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "../ui/card";
import { Badge } from "../ui/badge";
import { RefreshButton } from "../ui/RefreshButton";
import { useAuth } from "../../hooks/useAuth";
import { useNavigate } from "react-router-dom";
import TemplateUploadDialog from "../ensembles/TemplateUploadDialog";

export default function DeploymentStepOne({ ...props }) {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [uploadOpen, setUploadOpen] = React.useState(false);
  
  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    status,
    refetch,
    isRefetching,
  } = useInfiniteQuery({
    queryKey: ["templates"],
    queryFn: ({ pageParam = 1 }) => fetchTemplates(pageParam),
    getNextPageParam: (lastPage) => {
      const maxPages = Math.ceil(lastPage.total / lastPage.page_size);
      return lastPage.page < maxPages ? lastPage.page + 1 : undefined;
    },
    initialPageParam: 1,
    enabled: !!token, // Only run the query when we have a token
  });

  const templates: Template[] = data?.pages.flatMap((p) => p.items) ?? [];
  const { data: rawTemplates } = useQuery({
    queryKey: ["templates-raw"],
    queryFn: getTemplates,
    enabled: !!token,
  });
  const folderOptions = React.useMemo(() => {
    const set = new Set<string>(["root"]);
    templates.forEach((tpl) => {
      if (tpl.category) set.add(tpl.category);
    });
    const raw = rawTemplates?.items ?? [];
    raw.forEach((tpl: any) => {
      if (tpl.category) set.add(tpl.category);
    });
    return Array.from(set).sort();
  }, [templates, rawTemplates]);

  const resolveJsonPath = React.useCallback((yamlPath: string, jsonPath?: string | null) => {
    if (jsonPath) return jsonPath;
    if (yamlPath.endsWith(".yaml")) return `${yamlPath.slice(0, -5)}.json`;
    if (yamlPath.endsWith(".yml")) return `${yamlPath.slice(0, -4)}.json`;
    return yamlPath;
  }, []);

  const handleUploaded = React.useCallback(
    (payload: { yamlPath: string; jsonPath?: string | null; category: string }) => {
      const jsonPath = resolveJsonPath(payload.yamlPath, payload.jsonPath);
      props.setter(jsonPath);
      props.setCategory(payload.category);
      props.set_yaml_path(payload.yamlPath);
      setUploadOpen(false);
      refetch();
    },
    [props, refetch, resolveJsonPath]
  );

  return (
    <div className="flex flex-col w-full h-full overflow-x-hidden">
      {/* Header row with title + refresh */}
      <div className="flex items-center justify-between mb-6 gap-4 flex-wrap">
        <h2 className="text-2xl font-semibold">Select an Ensemble</h2>

        <div className="flex items-center gap-3">
          <Button variant="outline" onClick={() => navigate("/ensembles")}>
            Manage Ensembles
          </Button>
          <Button variant="outline" onClick={() => setUploadOpen(true)}>
            Add Ensemble
          </Button>
          <RefreshButton
            onClick={() => refetch()}
            isLoading={isRefetching}
            tooltip="Refresh Templates"
          />
        </div>
      </div>

      {status === "pending" && <p>Loading...</p>}
      {status === "error" && <p>Error fetching templates.</p>}

      <div className="w-full max-w-6xl mx-auto">
        {/* 1 col on mobile, 2 on md, 3 on lg+ */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {templates.map((tpl) => (
            <Card
              key={`${tpl.category}-${tpl.path}`}
              onClick={() => {
                props.setter(tpl.path);
                props.setCategory(tpl.category);
                props.set_yaml_path(tpl.yaml_path || tpl.path);
              }}
              className={cn(
                "cursor-pointer transition-all duration-500 border-2 rounded-2xl h-full",
                props.path === tpl.path
                  ? "bg-gradient-to-br from-blue-500/40 to-transparent border-blue-500 shadow-md"
                  : "hover:border-blue-400"
              )}
            >
              <CardHeader>
                <CardTitle className="truncate">{tpl.stem}</CardTitle>
                <CardDescription className="truncate">
                  {tpl.path}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Badge className="bg-blue-950 text-white">{tpl.category}</Badge>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Load more button */}
        {hasNextPage && (
          <div className="flex justify-center mt-6">
            <Button
              onClick={() => fetchNextPage()}
              disabled={isFetchingNextPage}
              variant="outline"
              className="px-6"
            >
              {isFetchingNextPage ? "Loading..." : "Load More"}
            </Button>
          </div>
        )}
      </div>
      <TemplateUploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        onUploaded={handleUploaded}
        existingFolders={folderOptions}
        defaultCategory={props.category}
      />
    </div>
  );
}
