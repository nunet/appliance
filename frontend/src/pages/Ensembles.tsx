import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import TemplateUploadDialog from "@/components/ensembles/TemplateUploadDialog";
import { TemplateDeleteDialog } from "@/components/ensembles/TemplateDeleteDialog";
import { getTemplates, Template } from "@/api/deployments";
import { getTemplateDetail, TemplateDetailResponse, getEffectiveSchema } from "@/api/ensembles";

type GroupedTemplate = {
  stem: string;
  category: string;
  yamlTemplate: Template | null;
  jsonTemplate: Template | null;
  displayPath: string;
};

export default function EnsemblesPage() {
  const [editOpen, setEditOpen] = React.useState(false);
  const [createOpen, setCreateOpen] = React.useState(false);
  const [deleteOpen, setDeleteOpen] = React.useState(false);
  const [selectedGroup, setSelectedGroup] = React.useState<GroupedTemplate | null>(null);
  const [editingDetail, setEditingDetail] = React.useState<TemplateDetailResponse | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = React.useState(false);
  const [searchTerm, setSearchTerm] = React.useState("");
  const [categoryFilter, setCategoryFilter] = React.useState<string>("all");

  const {
    data,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["templates-ensembles"],
    queryFn: getTemplates,
  });

  const templates = data?.items || [];
  const folderOptions = React.useMemo(() => {
    const values = new Set<string>();
    templates.forEach((tpl: Template) => {
      const category = (tpl.category || "").trim();
      values.add(category || "root");
    });
    return Array.from(values).sort();
  }, [templates]);

  // Group templates by stem (name without extension)
  const groupedTemplates = React.useMemo(() => {
    const groups = new Map<string, GroupedTemplate>();
    
    templates.forEach((tpl: Template) => {
      const name = tpl.name || tpl.path || "";
      const isYaml = name.endsWith(".yaml") || name.endsWith(".yml");
      const isJson = name.endsWith(".json");
      
      if (!isYaml && !isJson) return;
      
      // Extract stem (name without extension)
      let stem = name;
      if (isYaml) {
        stem = name.replace(/\.(ya?ml)$/i, "");
      } else if (isJson) {
        stem = name.replace(/\.json$/i, "");
      }
      
      const category = (tpl.category || "").trim() || "root";
      const key = `${category}:${stem}`;
      
      if (!groups.has(key)) {
        groups.set(key, {
          stem,
          category,
          yamlTemplate: null,
          jsonTemplate: null,
          displayPath: (tpl as any)?.relative_path || tpl.path || "",
        });
      }
      
      const group = groups.get(key)!;
      if (isYaml) {
        group.yamlTemplate = tpl;
        // Use YAML path for display
        group.displayPath = (tpl as any)?.relative_path || tpl.path || "";
      } else if (isJson) {
        group.jsonTemplate = tpl;
        // Only use JSON path if YAML doesn't exist
        if (!group.yamlTemplate) {
          group.displayPath = (tpl as any)?.relative_path || tpl.path || "";
        }
      }
    });
    
    return Array.from(groups.values());
  }, [templates]);

  const resolveTemplatePath = React.useCallback(
    (grouped: GroupedTemplate) => {
      // Prefer YAML path, fallback to JSON
      const yamlPath = grouped.yamlTemplate?.yaml_path || 
                      (grouped.yamlTemplate as any)?.relative_path || 
                      grouped.yamlTemplate?.path;
      if (yamlPath) return yamlPath;
      
      const jsonPath = (grouped.jsonTemplate as any)?.relative_path || 
                      grouped.jsonTemplate?.path;
      if (jsonPath) {
        // Convert JSON path to YAML path
        return jsonPath.replace(/\.json$/i, ".yaml");
      }
      
      return "";
    },
    []
  );

  const resolveDeletePath = React.useCallback(
    (grouped: GroupedTemplate | null) => {
      if (!grouped) return "";

      const yamlPath =
        grouped.yamlTemplate?.yaml_path ||
        (grouped.yamlTemplate as any)?.relative_path ||
        grouped.yamlTemplate?.path;
      if (yamlPath) return yamlPath;

      const jsonPath =
        (grouped.jsonTemplate as any)?.relative_path ||
        grouped.jsonTemplate?.path ||
        "";
      return jsonPath;
    },
    []
  );

  const handleEdit = React.useCallback(
    async (grouped: GroupedTemplate) => {
      // Handle JSON-only templates differently
      if (grouped.jsonTemplate && !grouped.yamlTemplate) {
        // For JSON-only templates, we need to fetch the JSON content
        const jsonPath = (grouped.jsonTemplate as any)?.relative_path || grouped.jsonTemplate?.path || "";
        const yamlPath = jsonPath.replace(/\.json$/i, ".yaml");
        
        setIsLoadingDetail(true);
        try {
          // Try to get template detail - this will fail because YAML doesn't exist
          // but we'll catch it and construct our own response with JSON content
          try {
            const detail = await getTemplateDetail(yamlPath);
            setEditingDetail(detail);
            setEditOpen(true);
          } catch (yamlErr: any) {
            // YAML doesn't exist (expected for JSON-only templates)
            // Try to fetch JSON content via getEffectiveSchema or construct from available data
            let jsonContent = "";
            
            try {
              // Try to get JSON schema - this might work even without YAML
              // by using the JSON path converted to YAML path
              const schema = await getEffectiveSchema(yamlPath, "sidecar");
              jsonContent = JSON.stringify(schema, null, 2);
            } catch (schemaErr: any) {
              // Schema fetch failed, try to get it from template object
              const jsonSchema = (grouped.jsonTemplate as any)?.schema;
              if (jsonSchema) {
                jsonContent = JSON.stringify(jsonSchema, null, 2);
              }
              // If still no content, leave empty - user can edit it
            }
            
            // Construct detail response for JSON-only template
            const detail: TemplateDetailResponse = {
              status: "success",
              yaml_path: yamlPath, // Path where YAML should be created
              json_path: jsonPath,
              category: grouped.category,
              yaml_content: "", // Empty YAML - user can create it
              json_content: jsonContent || null,
            };
            setEditingDetail(detail);
            setEditOpen(true);
          }
        } catch (err: any) {
          const detail = err?.response?.data?.detail;
          toast.error(detail || "Failed to load template.");
        } finally {
          setIsLoadingDetail(false);
        }
        return;
      }
      
      // Normal flow for templates with YAML
      const templatePath = resolveTemplatePath(grouped);
      if (!templatePath) {
        toast.error("Template path is missing.");
        return;
      }
      setIsLoadingDetail(true);
      try {
        const detail = await getTemplateDetail(templatePath);
        setEditingDetail(detail);
        setEditOpen(true);
      } catch (err: any) {
        const detail = err?.response?.data?.detail;
        toast.error(detail || "Failed to load template.");
      } finally {
        setIsLoadingDetail(false);
      }
    },
    [resolveTemplatePath]
  );

  const handleDelete = React.useCallback((grouped: GroupedTemplate) => {
    setSelectedGroup(grouped);
    setDeleteOpen(true);
  }, []);

  const matchesFilters = React.useCallback(
    (grouped: GroupedTemplate) => {
      const stemLower = grouped.stem.toLowerCase();
      const pathLower = grouped.displayPath.toLowerCase();
      const query = searchTerm.trim().toLowerCase();
      
      if (query && !stemLower.includes(query) && !pathLower.includes(query)) {
        return false;
      }
      if (categoryFilter !== "all" && grouped.category !== categoryFilter) {
        return false;
      }
      return true;
    },
    [searchTerm, categoryFilter]
  );

  const filteredTemplates = React.useMemo(
    () => groupedTemplates.filter(matchesFilters),
    [groupedTemplates, matchesFilters]
  );
  
  const templateCount = React.useMemo(() => filteredTemplates.length, [filteredTemplates]);

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 px-4 my-4">
        <Card
          className="bg-gradient-to-t from-primary/5 to-card shadow-xs border rounded-lg"
          data-testid="ensembles-card"
        >
          <CardHeader className="flex flex-col gap-4">
            <div className="flex items-center justify-between flex-row w-full">
              <div>
                <CardTitle className="text-lg font-semibold">Ensembles</CardTitle>
                <CardDescription>Loading templates…</CardDescription>
              </div>
              <div className="flex items-center gap-2">
                <Input 
                  placeholder="Search file name…" 
                  value={searchTerm} 
                  onChange={(e) => setSearchTerm(e.target.value)} 
                  className="w-48"
                  data-testid="ensemble-search-input"
                />
                <Select value={categoryFilter} onValueChange={setCategoryFilter}>
                  <SelectTrigger className="w-48" data-testid="ensemble-category-filter">
                    <SelectValue placeholder="Filter by category" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all" data-testid="ensemble-category-option-all">All categories</SelectItem>
                    {folderOptions.map((cat) => (
                      <SelectItem key={cat} value={cat} data-testid={`ensemble-category-option-${cat}`}>{cat}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button 
                  variant="outline" 
                  onClick={() => setCreateOpen(true)}
                  data-testid="ensemble-add-button"
                >
                  Add Ensemble
                </Button>
                <Button 
                  onClick={() => window.location.assign("/#/deploy/new")}
                  data-testid="ensemble-deploy-button"
                >
                  New Deployment
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-3">
              {[1, 2, 3].map((key) => (
                <Card key={key} className="p-4">
                  <Skeleton className="h-6 w-1/2 mb-2" />
                  <Skeleton className="h-4 w-3/4 mb-2" />
                  <Skeleton className="h-3 w-full" />
                </Card>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (isError) {
    return <p className="px-4 text-destructive">Failed to load templates.</p>;
  }

  if (templates.length === 0) {
    return (
      <div className="grid grid-cols-1 gap-4 px-4 my-4">
        <Card
          className="bg-gradient-to-t from-primary/5 to-card shadow-xs border rounded-lg"
          data-testid="ensembles-card"
        >
          <CardHeader className="flex flex-col gap-4">
          <div>
            <CardTitle className="text-lg font-semibold">Ensembles</CardTitle>
            <CardDescription>No templates found.</CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Input 
              placeholder="Search file name…" 
              value={searchTerm} 
              onChange={(e) => setSearchTerm(e.target.value)} 
              className="w-48"
              data-testid="ensemble-search-input"
            />
            <Select value={categoryFilter} onValueChange={setCategoryFilter}>
              <SelectTrigger className="w-48" data-testid="ensemble-category-filter">
                <SelectValue placeholder="Filter by category" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all" data-testid="ensemble-category-option-all">All categories</SelectItem>
                {folderOptions.map((cat) => (
                  <SelectItem key={cat} value={cat} data-testid={`ensemble-category-option-${cat}`}>{cat}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button 
              variant="outline" 
              onClick={() => setCreateOpen(true)}
              data-testid="ensemble-add-button"
            >
              Add Ensemble
            </Button>
            <Button 
              onClick={() => window.location.assign("/#/deploy/new")}
              data-testid="ensemble-deploy-button"
            >
              New Deployment
            </Button>
          </div>
          </CardHeader>
        </Card>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 px-4 my-4">
      <Card
        className="bg-gradient-to-t from-primary/5 to-card shadow-xs border rounded-lg"
        data-testid="ensembles-card"
      >
        <CardHeader className="flex flex-col gap-4">
          <div className="flex items-center justify-between w-full">
            <div>
              <CardTitle className="text-lg font-semibold">Ensembles</CardTitle>
              <CardDescription>Manage, edit, or delete ensemble templates.</CardDescription>
              <p className="text-xs text-muted-foreground mt-1" data-testid="ensemble-counts">
                {templateCount} templates
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Input
                placeholder="Search file name…"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-48"
                data-testid="ensemble-search-input"
              />
              <Select value={categoryFilter} onValueChange={setCategoryFilter}>
                <SelectTrigger className="w-48" data-testid="ensemble-category-filter">
                  <SelectValue placeholder="Filter by category" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all" data-testid="ensemble-category-option-all">All categories</SelectItem>
                  {folderOptions.map((cat) => (
                    <SelectItem key={cat} value={cat} data-testid={`ensemble-category-option-${cat}`}>{cat}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button 
                variant="outline" 
                onClick={() => setCreateOpen(true)}
                data-testid="ensemble-add-button"
              >
                Add Ensemble
              </Button>
              <Button 
                onClick={() => window.location.assign("/#/deploy/new")}
                data-testid="ensemble-deploy-button"
              >
                New Deployment
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {filteredTemplates.length === 0 ? (
            <p className="text-muted-foreground py-4 text-center" data-testid="ensemble-empty-state">
              No templates found
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-4" data-testid="ensemble-list">
              {filteredTemplates.map((grouped) => (
                <Card
                  key={`${grouped.category}:${grouped.stem}`}
                  className="hover:shadow-md transition-shadow"
                  data-testid="ensemble-row"
                  data-ensemble-stem={grouped.stem}
                  data-ensemble-category={grouped.category}
                  data-ensemble-path={grouped.displayPath}
                  data-ensemble-has-yaml={Boolean(grouped.yamlTemplate)}
                  data-ensemble-has-json={Boolean(grouped.jsonTemplate)}
                >
                  <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 p-4">
                    <div className="flex-1 min-w-0">
                      <CardTitle className="text-base font-semibold mb-1">
                        {grouped.stem}
                      </CardTitle>
                      <div className="text-sm text-muted-foreground space-y-0.5">
                        <p className="break-all font-mono text-xs" data-testid="ensemble-path">
                          {grouped.displayPath}
                        </p>
                        <p data-testid="ensemble-category">
                          <b>Category:</b> <span className="font-semibold">{grouped.category}</span>
                        </p>
                      </div>
                    </div>

                    <div className="flex flex-col md:items-end gap-3 shrink-0">
                      <div className="flex gap-2 self-start md:self-end">
                        <Button
                          size="sm"
                          className="w-full md:w-auto"
                          onClick={() => {
                            const path = resolveTemplatePath(grouped);
                            window.location.assign(`/#/deploy/new?template=${encodeURIComponent(path)}`);
                          }}
                        >
                          Deploy
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="w-full md:w-auto"
                          onClick={() => handleEdit(grouped)}
                          data-testid="ensemble-edit-button"
                          data-ensemble-stem={grouped.stem}
                        >
                          Edit
                        </Button>
                        <Button
                          variant="destructive"
                          size="sm"
                          className="w-full md:w-auto"
                          onClick={() => handleDelete(grouped)}
                          data-testid="ensemble-delete-button"
                          data-ensemble-stem={grouped.stem}
                        >
                          Delete
                        </Button>
                      </div>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <TemplateUploadDialog
        open={createOpen}
        onOpenChange={(openDialog) => setCreateOpen(openDialog)}
        onUploaded={() => {
          setCreateOpen(false);
          refetch();
        }}
        existingFolders={folderOptions}
      />

      <TemplateUploadDialog
        mode="edit"
        open={editOpen}
        onOpenChange={(openDialog) => {
          setEditOpen(openDialog);
          if (!openDialog) setEditingDetail(null);
        }}
        onUploaded={() => {
          refetch();
          setEditingDetail(null);
        }}
        initialData={
          editingDetail
            ? {
                yamlPath: editingDetail.yaml_path,
                yamlContent: editingDetail.yaml_content,
                jsonContent: editingDetail.json_content,
                category: editingDetail.category,
              }
            : null
        }
        isLoadingInitialData={isLoadingDetail && !editingDetail}
      />

      <TemplateDeleteDialog
        open={deleteOpen}
        onOpenChange={(openDialog) => {
          setDeleteOpen(openDialog);
          if (!openDialog) setSelectedGroup(null);
        }}
        templatePath={resolveDeletePath(selectedGroup)}
        templateName={selectedGroup?.stem}
        onDeleted={() => {
          setSelectedGroup(null);
          refetch();
        }}
      />

    </div>
  );
}
