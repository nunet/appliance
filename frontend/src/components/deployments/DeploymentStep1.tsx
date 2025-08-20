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
import { useInfiniteQuery } from "@tanstack/react-query";
import { fetchTemplates, type Template } from "../../api/deployments";

export default function DeploymentStepOne({
  path,
  setter,
  category,
  setCategory,
  set_yaml_path,
}) {
  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, status } =
    useInfiniteQuery({
      queryKey: ["templates"],
      queryFn: ({ pageParam = 1 }) => fetchTemplates(pageParam),
      getNextPageParam: (lastPage) => {
        const maxPages = Math.ceil(lastPage.total / lastPage.page_size);
        return lastPage.page < maxPages ? lastPage.page + 1 : undefined;
      },
      initialPageParam: 1,
    });

  const templates: Template[] = data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <div className="flex flex-col w-full h-full overflow-x-hidden">
      <h2 className="text-2xl font-semibold mb-6">Select an Ensemble</h2>

      {status === "loading" && <p>Loading...</p>}
      {status === "error" && <p>Error fetching templates.</p>}

      <div className="w-full max-w-6xl mx-auto">
        {/* 1 col on mobile, 2 on md, 3 on lg+ */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {templates.map((tpl) => (
            <Card
              key={`${tpl.category}-${tpl.path}`}
              onClick={() => {
                setter(tpl.path);
                setCategory(tpl.category);
                set_yaml_path(tpl.yaml_path || tpl.path);
              }}
              className={cn(
                "cursor-pointer transition-all duration-500 border-2 rounded-2xl h-full",
                path === tpl.path
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

        {/* Load more button below the grid */}
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
    </div>
  );
}
