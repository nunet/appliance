import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "../ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { JsonEditor } from "@/components/code/JsonEditor";
import { YamlEditor, lintYaml } from "@/components/code/YamlEditor";
import { uploadTemplate, updateTemplateContent, deleteTemplate, getTemplateCategories } from "@/api/ensembles";
import { parseDocument } from "yaml";
import { cn } from "@/lib/utils";
import { CheckCircle2, ChevronDown, ChevronUp, FileJson, FileText, Info, Loader2, X } from "lucide-react";

const MAX_FILE_SIZE = 50 * 1024; // 50 KB

const formatBytes = (bytes: number, decimals = 2) => {
  if (!+bytes) return "0 Bytes";
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
};

type FileListItemProps = {
  file: File;
  icon: React.ReactNode;
  onRemove?: () => void;
};

function FileListItem({ file, icon, onRemove }: FileListItemProps) {
  return (
    <div className="flex items-center gap-3 rounded-md border bg-muted/40 p-2 text-sm">
      <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md bg-background">
        {icon}
      </div>
      <div className="flex-1 overflow-hidden">
        <p className="truncate font-medium">{file.name}</p>
        <p className="text-xs text-muted-foreground">{formatBytes(file.size)}</p>
      </div>
      {onRemove && (
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="h-8 w-8 flex-shrink-0"
          onClick={onRemove}
          aria-label="Remove file"
        >
          <X className="h-4 w-4" />
        </Button>
      )}
    </div>
  );
}

type UploadCallbackPayload = {
  yamlPath: string;
  jsonPath?: string | null;
  category: string;
  contractRequired: boolean;
};

type JsonMode = "default" | "file" | "manual";

type PlaceholderInfo = {
  key: string;
  label: string;
};

type TemplateInitialData = {
  yamlPath: string;
  yamlContent: string;
  jsonContent?: string | null;
  category?: string;
};

const PLACEHOLDER_REGEX = /{{\s*([A-Za-z0-9_]+)\s*}}/g;

function extractPlaceholders(text: string): string[] {
  if (!text) return [];
  const matches = text.matchAll(PLACEHOLDER_REGEX);
  const values = new Set<string>();
  for (const match of matches) {
    if (match[1]) values.add(match[1]);
  }
  return Array.from(values);
}

function validateJsonAgainstYaml(yamlContent: string, jsonContent: string): string | null {
  if (!yamlContent || !jsonContent) {
    return "YAML and JSON content are required.";
  }
  const placeholders = extractPlaceholders(yamlContent);
  if (!placeholders.length) {
    return null;
  }
  let parsed: any;
  try {
    parsed = JSON.parse(jsonContent);
  } catch (err: any) {
    return err?.message || "JSON content is not valid.";
  }
  const fields = parsed?.fields;
  if (!fields || typeof fields !== "object" || Array.isArray(fields)) {
    return "JSON schema must contain a 'fields' object.";
  }
  const missing = placeholders.filter((key) => !Object.prototype.hasOwnProperty.call(fields, key));
  if (missing.length) {
    return `Missing form fields for: ${missing.join(", ")}`;
  }
  return null;
}

const FORM_STEPS = [
  { id: "details", label: "YAML" },
  { id: "json", label: "JSON" },
] as const;

const EDIT_STEPS = [
  { id: "yaml", label: "YAML template" },
  { id: "json", label: "JSON schema" },
] as const;

const formatJsonContent = (content: string) => {
  if (!content?.trim()) return content || "";
  try {
    const parsed = JSON.parse(content);
    return JSON.stringify(parsed, null, 2);
  } catch {
    return content;
  }
};

const formatYamlContentSafely = (content: string) => {
  // Temporarily escape handlebars-style placeholders to avoid YAML rewriter mangling them
  const placeholderMap = new Map<string, string>();
  let temp = content || "";
  const regex = /{{\s*([^}]+?)\s*}}/g;
  let idx = 0;
  temp = temp.replace(regex, (match) => {
    const key = `__PLACEHOLDER_${idx++}__`;
    placeholderMap.set(key, match);
    return key;
  });
  try {
    const doc = parseDocument(temp);
    let formatted = doc.toString({ lineWidth: 120 }).trimEnd();
    // Restore placeholders
    placeholderMap.forEach((original, token) => {
      formatted = formatted.replace(token, original);
    });
    return formatted;
  } catch {
    return content;
  }
};

const REQUIRED_RESOURCE_PLACEHOLDERS: PlaceholderInfo[] = [
  {
    key: "allocations_alloc1_resources_cpu_cores",
    label: "CPU cores placeholder",
  },
  {
    key: "allocations_alloc1_resources_ram_size",
    label: "RAM size placeholder",
  },
  {
    key: "allocations_alloc1_resources_disk_size",
    label: "Disk size placeholder",
  },
];

const REQUIRED_CONTRACT_PLACEHOLDERS: PlaceholderInfo[] = [
  { key: "contract_did", label: "Contract DID placeholder" },
  { key: "contract_host_did", label: "Contract Host DID placeholder" },
];

const JSON_MODE_OPTIONS: Array<{
  value: JsonMode;
  title: string;
  description: string;
  tooltip: string;
}> = [
  {
    value: "default",
    title: "Use bundled JSON form",
    description: "We will copy one of the default JSON forms for you.",
    tooltip:
      "Automatically copies the bundled JSON form and maps its fields to placeholders detected in your YAML.",
  },
  {
    value: "file",
    title: "Attach my own JSON file",
    description: "Upload a JSON schema to store next to the YAML file.",
    tooltip: "Upload a JSON schema sidecar; we will store it next to the YAML file.",
  },
  {
    value: "manual",
    title: "Paste JSON manually",
    description: "Paste or edit JSON text directly in the dialog.",
    tooltip: "Paste JSON content directly if you want to tweak it before saving.",
  },
];

const formatPlaceholder = (key: string) => `{{ ${key} }}`;

const escapeRegExp = (value: string) =>
  value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const findMissingPlaceholders = (content: string, keys: string[]) => {
  if (!content) return keys;
  return keys.filter((key) => {
    const pattern = new RegExp(`{{\\s*${escapeRegExp(key)}\\s*}}`, "i");
    return !pattern.test(content);
  });
};

type Props = {
  open: boolean;
  onOpenChange: (value: boolean) => void;
  onUploaded?: (payload: UploadCallbackPayload) => void;
  existingFolders?: string[];
  defaultCategory?: string;
  mode?: "create" | "edit";
  initialData?: TemplateInitialData | null;
  isLoadingInitialData?: boolean;
};

const formatFolderLabel = (value?: string) => (!value || value === "root" ? "Default" : value);

export default function TemplateUploadDialog({
  open,
  onOpenChange,
  onUploaded,
  existingFolders = [],
  defaultCategory = "",
  mode = "create",
  initialData,
  isLoadingInitialData = false,
}: Props) {
  const qc = useQueryClient();
  const isEditMode = mode === "edit";
  const dialogTestId = isEditMode ? "ensemble-edit-dialog" : "ensemble-upload-dialog";
  const templatePath = initialData?.yamlPath;
  const [yamlFile, setYamlFile] = React.useState<File | null>(null);
  const [category, setCategory] = React.useState(defaultCategory || "");
  const [folderMode, setFolderMode] = React.useState<"existing" | "custom">(
    defaultCategory ? "existing" : "custom",
  );
  const [contractRequired, setContractRequired] = React.useState(false);
  const [jsonMode, setJsonMode] = React.useState<JsonMode>("default");
  const [jsonFile, setJsonFile] = React.useState<File | null>(null);
  const [jsonText, setJsonText] = React.useState("");
  const [jsonError, setJsonError] = React.useState<string | null>(null);
  const [yamlText, setYamlText] = React.useState("");
  const [yamlReadError, setYamlReadError] = React.useState<string | null>(null);
  const [yamlMissingPlaceholders, setYamlMissingPlaceholders] = React.useState<string[]>([]);
  const [showPlaceholderList, setShowPlaceholderList] = React.useState(false);
  const [isManualEditorOpen, setIsManualEditorOpen] = React.useState(false);
  const yamlReadRequestRef = React.useRef(0);
  const [isAnalyzingYaml, setIsAnalyzingYaml] = React.useState(false);
  const [stepIndex, setStepIndex] = React.useState(0);
  const [isDragActive, setIsDragActive] = React.useState(false);
  const [isRemovingFile, setIsRemovingFile] = React.useState(false);
  const fileInputRef = React.useRef<HTMLInputElement | null>(null);
  const [overwritePrompt, setOverwritePrompt] = React.useState<{
    message?: string;
    yaml?: string | null;
    json?: string | null;
  } | null>(null);
  const [isOverwriting, setIsOverwriting] = React.useState(false);
  const [editYamlContent, setEditYamlContent] = React.useState("");
  const [editJsonContent, setEditJsonContent] = React.useState("");
  const [editYamlError, setEditYamlError] = React.useState<string | null>(null);
  const [editJsonError, setEditJsonError] = React.useState<string | null>(null);
  const [editStep, setEditStep] = React.useState<"yaml" | "json">("yaml");

  const { data: categoryData } = useQuery({
    queryKey: ["template-categories"],
    queryFn: getTemplateCategories,
    staleTime: 60_000,
  });

  const folderOptions = React.useMemo(() => {
    const set = new Set<string>(["root"]);
    existingFolders.filter(Boolean).forEach((f) => set.add(f));
    (categoryData || []).forEach((f) => set.add(f));
    return Array.from(set).sort();
  }, [existingFolders, categoryData]);
  const fallbackCategory = React.useMemo(() => {
    if (defaultCategory) return defaultCategory;
    if (folderOptions.includes("root")) return "root";
    return "";
  }, [defaultCategory, folderOptions]);

  const handleRemoveFile = React.useCallback(() => {
    if (isAnalyzingYaml || isRemovingFile) return;
    setIsRemovingFile(true);
    setTimeout(() => {
      setYamlFile(null);
      setYamlText("");
      setYamlReadError(null);
      setYamlMissingPlaceholders([]);
      setIsAnalyzingYaml(false);
      setIsRemovingFile(false);
    }, 300);
  }, [isAnalyzingYaml, isRemovingFile]);

  const handleYamlSelection = React.useCallback(
    (file: File | null) => {
      setYamlFile(file);
      setYamlText("");
      setYamlReadError(null);
      setYamlMissingPlaceholders([]);
      setIsAnalyzingYaml(false);
      if (!file) {
        return;
      }

      if (!/\.(ya?ml)$/i.test(file.name)) {
        toast.error("Invalid file type. Please upload a .yaml or .yml file.");
        setYamlFile(null);
        return;
      }

      if (file.size > MAX_FILE_SIZE) {
        toast.error(`File is too large. Max size is ${formatBytes(MAX_FILE_SIZE)}.`);
        setYamlFile(null);
        return;
      }

      if (file.size === 0) {
        toast.error("The selected file is empty. Please choose a valid YAML file.");
        setYamlFile(null);
        return;
      }

      const requestId = ++yamlReadRequestRef.current;
      setIsAnalyzingYaml(true);
      file
        .text()
        .then((text) => {
          if (yamlReadRequestRef.current !== requestId) return;

          if (!text.trim()) {
            toast.error("The selected file contains no content. Please choose a valid YAML file.");
            setYamlFile(null);
            setIsAnalyzingYaml(false);
            return;
          }

          setYamlText(text);
          setIsAnalyzingYaml(false);
        })
        .catch(() => {
          if (yamlReadRequestRef.current !== requestId) return;
          setYamlReadError("We couldn't read that file. Please try again.");
          setIsAnalyzingYaml(false);
        });
    },
    []
  );
  const handleYamlChange = React.useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0] ?? null;
      handleYamlSelection(file);
      // Allow selecting the same file consecutively
      event.target.value = "";
    },
    [handleYamlSelection]
  );
  const handleDrop = React.useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      setIsDragActive(false);
      if (isRemovingFile) return;
      const file = event.dataTransfer?.files?.[0];
      if (file) {
        handleYamlSelection(file);
      }
    },
    [handleYamlSelection, isRemovingFile]
  );
  const handleDragOver = React.useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      if (isRemovingFile) {
        event.dataTransfer.dropEffect = "none";
        return;
      }
      if (!isDragActive) {
        setIsDragActive(true);
      }
      event.dataTransfer.dropEffect = "copy";
    },
    [isDragActive, isRemovingFile]
  );
  const handleDragLeave = React.useCallback((event: React.DragEvent<HTMLDivElement>) => {
    if (event.currentTarget.contains(event.relatedTarget as Node)) {
      return;
    }
    setIsDragActive(false);
  }, []);
  const triggerFileDialog = React.useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const resetForm = React.useCallback(() => {
    setYamlFile(null);
    setYamlText("");
    setYamlReadError(null);
    setYamlMissingPlaceholders([]);
    setCategory(fallbackCategory);
    setFolderMode(fallbackCategory ? "existing" : "custom");
    setContractRequired(false);
    setJsonMode("default");
    setJsonFile(null);
    setJsonText("");
    setJsonError(null);
    setShowPlaceholderList(false);
    setIsManualEditorOpen(false);
    setIsAnalyzingYaml(false);
    setStepIndex(0);
    setEditYamlContent("");
    setEditJsonContent("");
    setEditYamlError(null);
    setEditJsonError(null);
  }, [fallbackCategory]);

  React.useEffect(() => {
    if (jsonMode !== "file") {
      setJsonFile(null);
    }
    if (jsonMode !== "manual") {
      setJsonText("");
      setJsonError(null);
      setIsManualEditorOpen(false);
    }
  }, [jsonMode]);

  React.useEffect(() => {
    if (jsonMode !== "default" && contractRequired) {
      setContractRequired(false);
    }
    if (jsonMode !== "default") {
      setShowPlaceholderList(false);
    }
  }, [jsonMode, contractRequired]);

  React.useEffect(() => {
      if (!isEditMode) return;
      if (open && initialData) {
        const prettyYaml = initialData.yamlContent || "";
        const prettyJson = formatJsonContent(initialData.jsonContent || "");
        setEditYamlContent(prettyYaml);
      setEditJsonContent(prettyJson);
      setEditYamlError(null);
      setEditJsonError(null);
      setEditStep(
        prettyYaml.trim().length ? "yaml" : "json"
      );
    } else if (open && !isLoadingInitialData && !initialData) {
      setEditYamlContent("");
      setEditJsonContent("");
      setEditStep("yaml");
    }
    if (!open) {
      setEditStep("yaml");
    }
  }, [open, initialData, isEditMode, isLoadingInitialData]);

  React.useEffect(() => {
    if (!open) {
      setCategory(fallbackCategory);
      setFolderMode(fallbackCategory ? "existing" : "custom");
    } else if (!category && fallbackCategory && folderMode !== "custom") {
      setCategory(fallbackCategory);
    } else if (!fallbackCategory && folderMode === "existing" && !category) {
      setFolderMode("custom");
    }
  }, [fallbackCategory, open, category, folderMode]);

  React.useEffect(() => {
    if (!yamlFile) {
      setIsAnalyzingYaml(false);
    }
  }, [yamlFile]);

  const isDefaultJson = jsonMode === "default";

  const placeholderConfig = React.useMemo(() => {
    if (!isDefaultJson) {
      return { all: [], base: [] as PlaceholderInfo[], contract: [] as PlaceholderInfo[] };
    }
    const base = [...REQUIRED_RESOURCE_PLACEHOLDERS];
    const contract = contractRequired ? [...REQUIRED_CONTRACT_PLACEHOLDERS] : [];
    return {
      all: [...contract, ...base],
      base,
      contract,
    };
  }, [isDefaultJson, contractRequired]);

  const yamlLint = React.useMemo(() => lintYaml(editYamlContent), [editYamlContent]);
  const isYamlStep = editStep === "yaml";
  const canAdvanceFromYaml = React.useMemo(
    () => editYamlContent.trim().length > 0 && yamlLint.status !== "error",
    [editYamlContent, yamlLint.status]
  );
  const hasJsonContent = React.useMemo(() => Boolean(editJsonContent.trim()), [editJsonContent]);
  const placeholderMismatch = React.useMemo(() => {
    if (!editYamlContent.trim() || !hasJsonContent) return null;
    return validateJsonAgainstYaml(editYamlContent, editJsonContent);
  }, [editYamlContent, editJsonContent, hasJsonContent]);
  const canSaveEdit = React.useMemo(
    () =>
      isEditMode &&
      Boolean(editYamlContent.trim()) &&
      (!hasJsonContent || !editJsonError) &&
      !editYamlError &&
      !isLoadingInitialData &&
      !placeholderMismatch,
    [isEditMode, editYamlContent, hasJsonContent, editJsonError, editYamlError, isLoadingInitialData, placeholderMismatch]
  );

  React.useEffect(() => {
    if (!placeholderConfig.all.length || !yamlText) {
      setYamlMissingPlaceholders([]);
      return;
    }
    setYamlMissingPlaceholders(
      findMissingPlaceholders(
        yamlText,
        placeholderConfig.all.map((item) => item.key)
      )
    );
  }, [yamlText, placeholderConfig]);

  const missingPlaceholderSet = React.useMemo(
    () => new Set(yamlMissingPlaceholders),
    [yamlMissingPlaceholders]
  );
  const detectedMissingPlaceholders = React.useMemo(
    () => yamlMissingPlaceholders.length > 0,
    [yamlMissingPlaceholders]
  );

  const placeholderToggleLabel = showPlaceholderList
    ? "Hide placeholders"
    : detectedMissingPlaceholders
      ? "Show required placeholders"
      : "View placeholders";

  const handleJsonModeChange = React.useCallback((value: string) => {
    if (value === "default" || value === "file" || value === "manual") {
      setJsonMode(value);
    }
  }, []);

  const handleManualJsonChange = React.useCallback(
    (event: React.ChangeEvent<HTMLTextAreaElement>) => {
      const value = event.target.value;
      setJsonText(value);
      if (!value.trim()) {
        setJsonError("JSON content is required when manual mode is selected.");
        return;
      }
      try {
        const parsed = JSON.parse(value);
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
          setJsonError("JSON must describe an object with form metadata.");
          return;
        }
        const issues: string[] = [];
        if (!parsed.name || typeof parsed.name !== "string") {
          issues.push("a 'name' string");
        }
        if (!parsed.description || typeof parsed.description !== "string") {
          issues.push("a 'description' string");
        }
        if (
          !parsed.fields ||
          typeof parsed.fields !== "object" ||
          Array.isArray(parsed.fields) ||
          Object.keys(parsed.fields).length === 0
        ) {
          issues.push("a 'fields' object with at least one entry");
        }
        if (issues.length > 0) {
          setJsonError(`JSON must include ${issues.join(" and ")}.`);
          return;
        }
        setJsonError(null);
      } catch {
        setJsonError("JSON content is not valid JSON.");
      }
    },
    []
  );

  const manualReady = jsonMode === "manual" && Boolean(jsonText.trim()) && !jsonError;
  const fileReady = jsonMode === "file" && Boolean(jsonFile);
  const defaultReady = isDefaultJson;
  const requiresPlaceholderCheck = isDefaultJson && Boolean(yamlFile);
  const hasMissingPlaceholders =
    requiresPlaceholderCheck && detectedMissingPlaceholders;
  const hasYamlIssues = Boolean(yamlReadError) || hasMissingPlaceholders || isAnalyzingYaml;
  const canSubmit =
    Boolean(yamlFile) &&
    !hasYamlIssues &&
    (defaultReady || fileReady || manualReady);
  const canProceedToJson = Boolean(yamlFile) && !yamlReadError && !isAnalyzingYaml;
  const isFirstStep = stepIndex === 0;
  const isLastStep = stepIndex === FORM_STEPS.length - 1;

  const submit = React.useCallback(
    async (confirmOverwrite: boolean) => {
      if (!yamlFile) throw new Error("Please choose a YAML file");
      if (yamlReadError) {
        throw new Error("Please fix the YAML file error before uploading.");
      }
      if (isAnalyzingYaml) {
        throw new Error("Still analyzing YAML. Please wait.");
      }
      if (jsonMode === "file" && !jsonFile) {
        throw new Error("Please choose a JSON file or switch to another option.");
      }
      if (jsonMode === "manual") {
        if (!jsonText.trim()) {
          throw new Error("Please paste JSON content or change the mode.");
        }
        if (jsonError) {
          throw new Error(jsonError);
        }
        try {
          JSON.parse(jsonText);
        } catch {
          throw new Error("JSON content is not valid.");
        }
      }
      if (isDefaultJson && yamlMissingPlaceholders.length > 0) {
        throw new Error(
          `Add the missing placeholders (${yamlMissingPlaceholders
            .map((key) => formatPlaceholder(key))
            .join(", ")}) or switch JSON modes.`
        );
      }
      const form = new FormData();
      form.append("file", yamlFile);
      if (category) form.append("category", category);
      form.append("confirm_overwrite", String(confirmOverwrite));
      form.append("contract_required", String(isDefaultJson ? contractRequired : false));
      if (jsonMode === "file" && jsonFile) {
        form.append("sidecar", jsonFile);
      } else if (jsonMode === "manual") {
        const normalized = jsonText.trim();
        const yamlStem = yamlFile.name.replace(/\.(ya?ml)$/i, "") || yamlFile.name;
        const blob = new Blob([normalized], { type: "application/json" });
        form.append("sidecar", blob, `${yamlStem || "template"}-form.json`);
      }
      return uploadTemplate(form);
    },
    [
      yamlFile,
      category,
      contractRequired,
      isDefaultJson,
      jsonMode,
      jsonFile,
      jsonText,
      jsonError,
      yamlMissingPlaceholders,
      yamlReadError,
      isAnalyzingYaml,
    ]
  );

  const handleDialogChange = React.useCallback(
    (value: boolean) => {
      if (!value) resetForm();
      onOpenChange(value);
    },
    [onOpenChange, resetForm]
  );

  const goToNextStep = React.useCallback(() => {
    setStepIndex((prev) => Math.min(prev + 1, FORM_STEPS.length - 1));
  }, []);

  const goToPrevStep = React.useCallback(() => {
    setStepIndex((prev) => Math.max(prev - 1, 0));
  }, []);

  const handleUploadComplete = React.useCallback(
    (res: any) => {
      qc.invalidateQueries({ queryKey: ["yaml-templates"] });
      qc.invalidateQueries({ queryKey: ["form-templates"] });
      qc.invalidateQueries({ queryKey: ["templates"] });
      if (res?.yaml_path && onUploaded) {
        onUploaded({
          yamlPath: res.yaml_path,
          jsonPath: res.json_path,
          category: category || "root",
          contractRequired,
        });
      }
      onOpenChange(false);
      resetForm();
    },
    [qc, onUploaded, category, contractRequired, onOpenChange, resetForm]
  );

  const { mutateAsync: doUpload, isPending: isUploading } = useMutation({
    mutationFn: async () => submit(false),
    onSuccess: (res) => {
      toast.success(res.message || "Template uploaded");
      setOverwritePrompt(null);
      handleUploadComplete(res);
    },
    onError: async (err: any) => {
      const detail = err?.response?.data?.detail;
      if (detail?.status === "confirm_overwrite") {
        const existsYaml = detail.existing_paths?.yaml;
        const existsJson = detail.existing_paths?.json;
        setOverwritePrompt({
          message:
            detail.message ||
            "A template with this name already exists in this folder.",
          yaml: existsYaml,
          json: existsJson,
        });
        toast.message("Template already exists. Confirm below to replace it.");
        return;
      }
      const fallbackMessage =
        typeof detail === "string" && detail
          ? detail
          : err?.message || "Upload failed";
      toast.error(fallbackMessage);
    },
  });

  const { mutateAsync: doEdit, isPending: isSavingEdit } = useMutation({
    mutationFn: async () => {
      if (!isEditMode) return null;
      if (!templatePath) {
        throw new Error("Template path is missing.");
      }
      const nextYaml = editYamlContent.trim();
      const nextJson = editJsonContent.trim();
      if (!nextYaml) {
        setEditYamlError("YAML content cannot be empty.");
        throw new Error("YAML content cannot be empty.");
      }
      if (nextJson) {
        const mismatch = placeholderMismatch || validateJsonAgainstYaml(nextYaml, nextJson);
        if (mismatch) {
          setEditJsonError(mismatch);
          throw new Error(mismatch);
        }
      }
      // Allow creating missing files - if content is provided, it will be created
      return updateTemplateContent({
        template_path: templatePath,
        yaml_content: nextYaml,
        json_content: nextJson || null,
      });
    },
    onSuccess: (res) => {
      if (!res) return;
      toast.success(res.message || "Template updated");
      qc.invalidateQueries({ queryKey: ["yaml-templates"] });
      qc.invalidateQueries({ queryKey: ["form-templates"] });
      qc.invalidateQueries({ queryKey: ["templates-ensembles"] });
      if (templatePath && onUploaded) {
        onUploaded({
          yamlPath: templatePath,
          jsonPath: res.json_path,
          category: initialData?.category || category || "root",
          contractRequired: false,
        });
      }
      onOpenChange(false);
      resetForm();
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail;
      toast.error(detail || err?.message || "Failed to update template");
    },
  });

  const { mutateAsync: doDelete, isPending: isDeleting } = useMutation({
    mutationFn: async () => {
      if (!isEditMode || !templatePath) {
        throw new Error("Template path is missing.");
      }
      return deleteTemplate(templatePath);
    },
    onSuccess: () => {
      toast.success("Template deleted");
      qc.invalidateQueries({ queryKey: ["yaml-templates"] });
      qc.invalidateQueries({ queryKey: ["form-templates"] });
      qc.invalidateQueries({ queryKey: ["templates-ensembles"] });
      onOpenChange(false);
      resetForm();
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail;
      toast.error(detail || err?.message || "Failed to delete template");
    },
  });

  const handleOverwriteConfirm = React.useCallback(async () => {
    if (!overwritePrompt) return;
    setIsOverwriting(true);
    try {
      const res = await submit(true);
      toast.success(res.message || "Template replaced");
      setOverwritePrompt(null);
      handleUploadComplete(res);
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || error?.message || "Overwrite failed");
    } finally {
      setIsOverwriting(false);
    }
  }, [overwritePrompt, submit, handleUploadComplete]);

  return (
    <Dialog open={open} onOpenChange={handleDialogChange}>
      <DialogContent
        className={cn(
          "max-h-[90vh] overflow-y-auto",
          isEditMode ? "sm:max-w-[720px] lg:max-w-[960px]" : "sm:max-w-[520px]"
        )}
        data-testid={dialogTestId}
        data-mode={isEditMode ? "edit" : "create"}
      >
        <DialogHeader>
          <DialogTitle>
            {isEditMode ? "Edit Ensemble Template" : "Upload Ensemble"}
          </DialogTitle>
          <DialogDescription>
            {isEditMode
              ? "Update the YAML and JSON schema for this template."
              : "Upload an ensemble file and choose how to manage its JSON form."}
          </DialogDescription>
        </DialogHeader>

        {isEditMode ? (
          isLoadingInitialData ? (
            <p className="py-2 text-sm text-muted-foreground">Loading template contents...</p>
          ) : !initialData ? (
            <p className="py-2 text-sm text-destructive">Template details are unavailable.</p>
          ) : (
            <div className="space-y-6 py-2">
              <div
                className="rounded-md border bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
                data-testid="ensemble-edit-path-summary"
              >
                <p className="font-semibold text-foreground">Path</p>
                <p className="break-all font-mono text-foreground" data-testid="ensemble-edit-path">
                  {initialData.yamlPath}
                </p>
                {initialData.category && (
                  <p className="mt-1" data-testid="ensemble-edit-category">
                    Category: <span className="font-semibold">{initialData.category}</span>
                  </p>
                )}
              </div>
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-3 text-xs font-semibold">
                  {EDIT_STEPS.map((step, index) => {
                    const isActive = editStep === step.id;
                    const isComplete = editStep === "json" && step.id === "yaml";
                    return (
                      <React.Fragment key={step.id}>
                        <button
                          type="button"
                          onClick={() => setEditStep(step.id)}
                          className="flex items-center gap-2 rounded-md px-2 py-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring transition"
                          data-testid={`ensemble-edit-step-${step.id}`}
                        >
                          <span
                            className={cn(
                              "flex h-7 w-7 items-center justify-center rounded-full border text-xs font-semibold",
                              isActive
                                ? "bg-primary text-primary-foreground border-primary"
                                : isComplete
                                  ? "bg-emerald-500/15 text-emerald-700 border-emerald-500/40"
                                  : "text-muted-foreground border-border"
                            )}
                          >
                            {index + 1}
                          </span>
                          <span
                            className={cn(
                              "text-xs font-semibold",
                              isActive
                                ? "text-foreground"
                                : isComplete
                                  ? "text-emerald-700"
                                  : "text-muted-foreground"
                            )}
                          >
                            {step.label}
                          </span>
                        </button>
                        {index < EDIT_STEPS.length - 1 && (
                          <div className="h-px w-10 bg-border sm:w-16" aria-hidden="true" />
                        )}
                      </React.Fragment>
                    );
                  })}
                </div>

                {isYamlStep ? (
                  <div data-testid="ensemble-edit-yaml-editor">
                    <YamlEditor
                      label="YAML Template"
                      value={editYamlContent}
                      onChange={(val) => {
                        setEditYamlContent(val);
                        setEditYamlError(null);
                      }}
                      helperText="Edit with syntax highlighting and lint feedback."
                      error={editYamlError}
                      className="min-h-[420px]"
                    />
                  </div>
                ) : (
                  <div data-testid="ensemble-edit-json-editor">
                    <JsonEditor
                      label="JSON Form Schema"
                      value={editJsonContent}
                      onChange={(val) => {
                        setEditJsonContent(val);
                        setEditJsonError(null);
                      }}
                      helperText="Ensure every placeholder from the YAML has a corresponding field."
                      error={editJsonError}
                      className="min-h-[420px]"
                    />
                  </div>
                )}
                {placeholderMismatch && (
                  <div
                    className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive"
                    data-testid="ensemble-edit-placeholder-warning"
                  >
                    {placeholderMismatch}
                  </div>
                )}
              </div>
            </div>
          )
        ) : (
          <div className="space-y-4 py-2">
          <div className="flex flex-wrap items-center gap-3 text-xs font-medium">
            {FORM_STEPS.map((step, index) => (
              <div key={step.id} className="flex items-center gap-2">
                <span
                  className={cn(
                    "flex h-6 w-6 items-center justify-center rounded-full border text-xs",
                    index === stepIndex
                      ? "border-primary bg-primary text-primary-foreground"
                      : index < stepIndex
                        ? "border-emerald-500 bg-emerald-500/10 text-emerald-600 dark:border-emerald-400 dark:text-emerald-200"
                        : "border-border text-muted-foreground"
                  )}
                >
                  {index + 1}
                </span>
                <span
                  className={cn(
                    "text-sm",
                    index === stepIndex
                      ? "text-foreground"
                      : index < stepIndex
                        ? "text-emerald-600 dark:text-emerald-300"
                        : "text-muted-foreground"
                  )}
                >
                  {step.label}
                </span>
              </div>
            ))}
          </div>

          {stepIndex === 0 && (
            <div className="grid gap-6">
              <section className="space-y-3" data-testid="ensemble-yaml-section">
                <div>
                  <Label className="text-sm font-semibold">Ensemble YAML</Label>
                  <p className="text-xs text-muted-foreground">
                    Upload the YAML or YML file that describes your ensemble. We will inspect it for the placeholders
                    required by the bundled JSON forms.
                  </p>
                </div>
                <div
                  role="button"
                  tabIndex={yamlFile ? -1 : 0}
                  onClick={yamlFile ? undefined : triggerFileDialog}
                  onKeyDown={
                    yamlFile
                      ? undefined
                      : (event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            triggerFileDialog();
                          }
                        }
                  }
                  onDragEnter={handleDragOver}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  className={cn(
                    "flex flex-col justify-center rounded-md border-2 border-dashed text-center transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    isDragActive
                      ? "border-primary bg-primary/5"
                      : "border-muted-foreground/40 bg-muted/20",
                    yamlFile ? "p-4" : "p-6 items-center"
                  )}
                  data-testid="ensemble-yaml-dropzone"
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".yaml,.yml,text/yaml"
                    className="hidden"
                    onChange={handleYamlChange}
                    data-testid="ensemble-yaml-input"
                  />
                  {yamlFile ? (
                    <>
                      <div
                        className={cn(
                          "flex w-full items-center gap-3 text-sm transition-opacity duration-300",
                          isRemovingFile && "opacity-0"
                        )}
                      >
                        <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-md bg-background">
                          {isAnalyzingYaml ? (
                            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                          ) : (
                            <FileText className="h-6 w-6 text-muted-foreground" />
                          )}
                        </div>
                        <div className="flex-1 overflow-hidden text-left">
                          <p className="truncate font-medium">{yamlFile.name}</p>
                          <p className="text-xs text-muted-foreground">
                            {isAnalyzingYaml ? "Analyzing..." : formatBytes(yamlFile.size)}
                          </p>
                        </div>
                        <Button
                          type="button"
                          size="icon"
                          variant="ghost"
                          className="h-8 w-8 flex-shrink-0"
                          onClick={handleRemoveFile}
                          aria-label="Remove file"
                          disabled={isAnalyzingYaml || isRemovingFile}
                        >
                          {isRemovingFile ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <X className="h-4 w-4" />
                          )}
                        </Button>
                      </div>
                      <p className="text-xs text-muted-foreground mt-4">
                        or click to browse for a file
                      </p>
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        className="mt-2"
                        onClick={(event) => {
                          event.stopPropagation();
                          triggerFileDialog();
                        }}
                        disabled={isRemovingFile}
                      >
                        Browse files
                      </Button>
                    </>
                  ) : (
                    <>
                      <p className="text-sm font-medium">Upload a file</p>
                      <p className="text-xs text-muted-foreground">
                        Drag and drop or click to upload (Max. 50KB)
                      </p>
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        className="mt-3"
                        onClick={(event) => {
                          event.stopPropagation();
                          triggerFileDialog();
                        }}
                      >
                        Browse files
                      </Button>
                    </>
                  )}
                </div>
                <p className="mt-1.5 text-xs text-muted-foreground" data-testid="ensemble-yaml-status">
                  {yamlFile
                    ? yamlReadError
                      ? yamlReadError
                      : isAnalyzingYaml
                        ? "Analyzing YAML..."
                        : `Selected: ${yamlFile.name}`
                    : "Accepted formats: .yaml, .yml"}
                </p>
              </section>

              <section className="space-y-3" data-testid="ensemble-folder-section">
                <div>
                  <div className="flex items-center gap-2">
                    <Label className="text-sm font-semibold">Folder</Label>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button
                          type="button"
                          className="text-muted-foreground transition hover:text-foreground"
                        >
                          <Info className="h-4 w-4" aria-hidden="true" />
                          <span className="sr-only">Folder placement info</span>
                        </button>
                      </TooltipTrigger>
                      <TooltipContent side="top" className="max-w-xs text-left">
                        {defaultCategory
                          ? `New uploads default to "${defaultCategory}". If you leave this empty we will place the files in the root folder.`
                          : "Location to store the uploaded ensemble. Leaving this empty stores the files at the root level."}
                      </TooltipContent>
                    </Tooltip>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Choose an existing folder or create one.
                  </p>
                </div>
                <Select
                  value={folderMode === "custom" ? "custom" : category || undefined}
                  onValueChange={(value) => {
                    if (value === "custom") {
                      setFolderMode("custom");
                      if (folderOptions.includes(category) || !category) {
                        setCategory("");
                      }
                      return;
                    }
                    setFolderMode("existing");
                    setCategory(value);
                  }}
                >
                  <SelectTrigger data-testid="ensemble-folder-select">
                    <SelectValue
                      placeholder={
                        fallbackCategory
                          ? formatFolderLabel(fallbackCategory)
                          : "Pick existing folder"
                      }
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {folderOptions.map((folder) => (
                      <SelectItem
                        key={folder}
                        value={folder}
                        data-testid={`ensemble-folder-option-${folder || "root"}`}
                      >
                        {formatFolderLabel(folder)}
                      </SelectItem>
                    ))}
                    <SelectItem value="custom" data-testid="ensemble-folder-option-custom">
                      Create new folder…
                    </SelectItem>
                  </SelectContent>
                </Select>
                {folderMode === "custom" && (
                  <>
                    <Input
                      className="mt-2"
                      placeholder="Enter new folder name"
                      value={category}
                      onChange={(event) => setCategory(event.target.value)}
                      data-testid="ensemble-folder-input"
                    />
                    <p className="text-xs text-muted-foreground">
                      We will create this folder under ~/ensembles if it does not exist.
                    </p>
                  </>
                )}
              </section>
            </div>
          )}

          {stepIndex === 1 && (
            <div className="grid gap-6">
              <section className="space-y-2">
                <Label className="text-sm font-semibold">Selected files</Label>
                <div className="space-y-2">
                  {yamlFile && (
                    <FileListItem
                      file={yamlFile}
                      icon={<FileText className="h-5 w-5 text-muted-foreground" />}
                    />
                  )}
                  {jsonFile && (
                    <FileListItem
                      file={jsonFile}
                      icon={<FileJson className="h-5 w-5 text-muted-foreground" />}
                      onRemove={() => setJsonFile(null)}
                    />
                  )}
                </div>
              </section>
              <section className="space-y-3">
                <div>
                  <Label className="text-sm font-semibold">JSON form strategy</Label>
                  <p className="text-xs text-muted-foreground">
                    Decide whether to use the bundled defaults, upload a JSON sidecar, or paste JSON manually.
                  </p>
                </div>
                <RadioGroup
                  value={jsonMode}
                  onValueChange={handleJsonModeChange}
                  className="gap-2"
                  data-testid="ensemble-json-mode"
                >
                  {JSON_MODE_OPTIONS.map((option) => (
                    <label
                      key={option.value}
                      htmlFor={`json-mode-${option.value}`}
                      className={cn(
                        "flex cursor-pointer items-start gap-3 rounded-md border p-3 transition hover:border-primary",
                        jsonMode === option.value && "border-primary bg-primary/5"
                      )}
                      data-testid={`ensemble-json-mode-${option.value}`}
                    >
                      <RadioGroupItem
                        id={`json-mode-${option.value}`}
                        value={option.value}
                        className="mt-1"
                      />
                      <div className="flex-1 space-y-1">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium">{option.title}</p>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <button
                                type="button"
                                className="text-muted-foreground transition hover:text-foreground"
                                onClick={(event) => {
                                  event.preventDefault();
                                  event.stopPropagation();
                                }}
                              >
                                <Info className="h-4 w-4" aria-hidden="true" />
                                <span className="sr-only">Learn more</span>
                              </button>
                            </TooltipTrigger>
                            <TooltipContent side="top">{option.tooltip}</TooltipContent>
                          </Tooltip>
                        </div>
                        <p className="text-xs text-muted-foreground">{option.description}</p>
                      </div>
                    </label>
                  ))}
                </RadioGroup>

                {jsonMode === "file" && !jsonFile && (
                  <div className="space-y-2 rounded-md border p-3">
                    <Label className="text-sm font-medium">Upload JSON sidecar</Label>
                    <Input
                      type="file"
                      accept=".json,application/json"
                      onChange={(event) => setJsonFile(event.target.files?.[0] ?? null)}
                      data-testid="ensemble-json-file-input"
                    />
                    <p className="text-xs text-muted-foreground">Accepted format: .json</p>
                  </div>
                )}

                {jsonMode === "manual" && (
                  <div className="space-y-2 rounded-md border p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <Label className="text-sm font-medium">Manual JSON input</Label>
                        <p className="text-xs text-muted-foreground">
                          Advanced option. Keep it collapsed unless you need to edit JSON inline.
                        </p>
                      </div>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => setIsManualEditorOpen((prev) => !prev)}
                        className="gap-1"
                        data-testid="ensemble-json-toggle"
                      >
                        {isManualEditorOpen ? "Collapse editor" : "Open editor"}
                        {isManualEditorOpen ? (
                          <ChevronUp className="h-4 w-4" aria-hidden="true" />
                        ) : (
                          <ChevronDown className="h-4 w-4" aria-hidden="true" />
                        )}
                      </Button>
                    </div>
                    {isManualEditorOpen ? (
                      <>
                        <Textarea
                          value={jsonText}
                          spellCheck={false}
                          onChange={handleManualJsonChange}
                          placeholder='Paste JSON here, e.g. { "name": "My template" }'
                          className="font-mono"
                          data-testid="ensemble-json-textarea"
                        />
                        <p
                          className={cn(
                            "text-xs",
                            jsonError ? "text-destructive" : "text-muted-foreground"
                          )}
                          data-testid="ensemble-json-helper"
                        >
                          {jsonError
                            ? jsonError
                            : "We will save this JSON as the sidecar next to your YAML."}
                        </p>
                      </>
                    ) : (
                      <p className="text-xs text-muted-foreground">
                        Manual JSON editor is collapsed. Select "Open editor" to paste content.
                      </p>
                    )}
                  </div>
                )}
              </section>

              <div className="flex flex-col gap-3 rounded-md border px-3 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <Label className="font-medium">Contract required?</Label>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button
                          type="button"
                          className="text-muted-foreground transition hover:text-foreground"
                        >
                          <Info className="h-4 w-4" aria-hidden="true" />
                          <span className="sr-only">Contract toggle help</span>
                        </button>
                      </TooltipTrigger>
                      <TooltipContent side="top" className="max-w-xs text-left">
                        Copies the contract-specific JSON form. Your YAML must include contract placeholders such as{" "}
                        <span className="font-mono">{formatPlaceholder("contract_did")}</span> so the default form can fill
                        them.
                      </TooltipContent>
                    </Tooltip>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {isDefaultJson
                      ? "Enable to copy the contract-specific JSON form instead of the base version."
                      : "Disabled because a custom JSON sidecar will be saved."}
                  </p>
                </div>
                <Switch
                  checked={contractRequired}
                  disabled={!isDefaultJson}
                  onCheckedChange={(checked) => setContractRequired(Boolean(checked))}
                  data-testid="ensemble-contract-switch"
                />
              </div>

              {isDefaultJson && (
                <div className="space-y-3">
                  {hasMissingPlaceholders ? (
                    <Alert className="space-y-3 border-dashed" data-testid="ensemble-placeholder-warning">
                      <Info className="h-4 w-4" aria-hidden="true" />
                      <AlertTitle>Default JSON form requirements</AlertTitle>
                      <AlertDescription className="space-y-2">
                        <p className="text-xs">
                          We found mismatches between your YAML placeholders and the bundled JSON form. Update the YAML or
                          provide a custom JSON sidecar.
                        </p>
                        <div className="flex flex-wrap items-center gap-3 text-xs">
                          <p className="font-medium">
                            Scope:{" "}
                            {contractRequired ? "Contracts and resources" : "Resource values only"}
                          </p>
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            className="gap-1 px-2"
                            onClick={() => setShowPlaceholderList((prev) => !prev)}
                            data-testid="ensemble-placeholder-toggle"
                          >
                            {placeholderToggleLabel}
                            {showPlaceholderList ? (
                              <ChevronUp className="h-4 w-4" aria-hidden="true" />
                            ) : (
                              <ChevronDown className="h-4 w-4" aria-hidden="true" />
                            )}
                          </Button>
                        </div>
                        <p className="text-xs text-destructive">
                          Missing placeholders:{" "}
                          {yamlMissingPlaceholders.map((key) => formatPlaceholder(key)).join(", ")}
                        </p>
                      </AlertDescription>
                    </Alert>
                  ) : (
                    <div
                      className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-emerald-500/40 bg-emerald-50 px-4 py-3 text-emerald-900 dark:border-emerald-500/50 dark:bg-emerald-950/40 dark:text-emerald-100"
                      data-testid="ensemble-placeholder-ok"
                    >
                      <div className="flex items-center gap-3">
                        <CheckCircle2 className="h-5 w-5 text-emerald-500" />
                        <div>
                          <p className="text-sm font-semibold">All placeholders detected</p>
                          <p className="text-xs">Your YAML matches the selected JSON form.</p>
                        </div>
                      </div>
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            className="gap-1 px-2 text-emerald-900 hover:text-emerald-900 dark:text-emerald-100"
                            onClick={() => setShowPlaceholderList((prev) => !prev)}
                            data-testid="ensemble-placeholder-toggle"
                          >
                        {placeholderToggleLabel}
                        {showPlaceholderList ? (
                          <ChevronUp className="h-4 w-4" aria-hidden="true" />
                        ) : (
                          <ChevronDown className="h-4 w-4" aria-hidden="true" />
                        )}
                      </Button>
                    </div>
                  )}
                  {showPlaceholderList && (
                    <div className="space-y-3 rounded-md border bg-muted/40 p-3 text-xs" data-testid="ensemble-placeholder-list">
                      <div>
                        <p className="font-medium">Always include:</p>
                        <ul className="mt-1 list-disc space-y-1 pl-5">
                          {placeholderConfig.base.map((item) => (
                            <li
                              key={item.key}
                              className={cn(
                                "flex flex-wrap gap-1",
                                missingPlaceholderSet.has(item.key) &&
                                  "text-destructive font-medium"
                              )}
                            >
                              <span>{item.label}</span>
                              <span className="font-mono text-muted-foreground">
                                {formatPlaceholder(item.key)}
                              </span>
                              {missingPlaceholderSet.has(item.key) && (
                                <span className="text-destructive">(missing)</span>
                              )}
                            </li>
                          ))}
                        </ul>
                      </div>
                      {contractRequired && (
                        <div>
                          <p className="font-medium">Required for contract defaults:</p>
                          <ul className="mt-1 list-disc space-y-1 pl-5">
                            {placeholderConfig.contract.map((item) => (
                              <li
                                key={item.key}
                                className={cn(
                                  "flex flex-wrap gap-1",
                                  missingPlaceholderSet.has(item.key) &&
                                    "text-destructive font-medium"
                                )}
                              >
                                <span>{item.label}</span>
                                <span className="font-mono text-muted-foreground">
                                  {formatPlaceholder(item.key)}
                                </span>
                                {missingPlaceholderSet.has(item.key) && (
                                  <span className="text-destructive">(missing)</span>
                                )}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
        )}

        {!isEditMode && overwritePrompt && (
          <Alert variant="destructive" className="space-y-3" data-testid="ensemble-overwrite-warning">
            <Info className="h-4 w-4" aria-hidden="true" />
            <AlertTitle>Template already exists</AlertTitle>
            <AlertDescription className="space-y-3">
              <p className="text-sm">
                {overwritePrompt.message ||
                  "We found an existing template with the same name. Replace it to continue."}
              </p>
              <div className="text-xs">
                <p className="font-medium">Existing files:</p>
                <ul className="mt-1 list-disc space-y-1 pl-5">
                  {overwritePrompt.yaml && (
                    <li>
                      YAML: <span className="font-mono break-all">{overwritePrompt.yaml}</span>
                    </li>
                  )}
                  {overwritePrompt.json && (
                    <li>
                      JSON: <span className="font-mono break-all">{overwritePrompt.json}</span>
                    </li>
                  )}
                  {!overwritePrompt.yaml && !overwritePrompt.json && (
                    <li>Matching template already exists.</li>
                  )}
                </ul>
              </div>
              <div className="flex flex-wrap gap-2 pt-1">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setOverwritePrompt(null)}
                  disabled={isOverwriting}
                  data-testid="ensemble-overwrite-cancel"
                >
                  Cancel
                </Button>
                <Button
                  type="button"
                  variant="destructive"
                  onClick={handleOverwriteConfirm}
                  disabled={isOverwriting}
                  data-testid="ensemble-overwrite-confirm"
                >
                  {isOverwriting ? "Replacing..." : "Replace template"}
                </Button>
              </div>
            </AlertDescription>
          </Alert>
        )}

        {isEditMode ? (
          <DialogFooter className="flex flex-wrap justify-between gap-2">
            <div className="flex gap-2">
              <Button
                variant="destructive"
                onClick={() => doDelete()}
                disabled={isDeleting || isSavingEdit}
                data-testid="ensemble-dialog-delete"
              >
                {isDeleting ? "Deleting..." : "Delete"}
              </Button>
              <Button
                variant="outline"
                onClick={() => handleDialogChange(false)}
                disabled={isSavingEdit || isDeleting}
                data-testid="ensemble-dialog-cancel"
              >
                Cancel
              </Button>
            </div>
            <div className="flex flex-wrap gap-2">
              {!isYamlStep && (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setEditStep("yaml")}
                  disabled={isSavingEdit || isDeleting}
                  data-testid="ensemble-dialog-back"
                >
                  Back
                </Button>
              )}
              {isYamlStep ? (
                <Button
                  type="button"
                  onClick={() => setEditStep("json")}
                  disabled={!canAdvanceFromYaml || isDeleting}
                  data-testid="ensemble-dialog-next"
                >
                  Next: JSON
                </Button>
              ) : (
                <Button
                  onClick={() => doEdit()}
                  disabled={isSavingEdit || !canSaveEdit || isDeleting}
                  data-testid="ensemble-dialog-save"
                >
                  {isSavingEdit ? "Saving..." : "Save changes"}
                </Button>
              )}
            </div>
          </DialogFooter>
        ) : (
          <DialogFooter className="flex flex-wrap justify-between gap-2">
            <Button
              variant="outline"
              onClick={() => handleDialogChange(false)}
              disabled={isUploading}
              data-testid="ensemble-dialog-cancel"
            >
              Cancel
            </Button>
            <div className="flex flex-wrap gap-2">
              {!isFirstStep && (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={goToPrevStep}
                  disabled={isUploading}
                  data-testid="ensemble-dialog-back"
                >
                  Back
                </Button>
              )}
              <Button
                type="button"
                onClick={() => (isLastStep ? doUpload() : goToNextStep())}
                disabled={
                  isUploading ||
                  isRemovingFile ||
                  (isLastStep ? !canSubmit : !canProceedToJson)
                }
                data-testid={isLastStep ? "ensemble-dialog-save" : "ensemble-dialog-next"}
              >
                {isLastStep ? (isUploading ? "Uploading..." : "Save template") : "Next"}
              </Button>
            </div>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}
