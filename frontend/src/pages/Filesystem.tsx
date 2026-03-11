import React, { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUp,
  ArrowUpDown,
  Check,
  ClipboardCopy,
  ClipboardPaste,
  ChevronDown,
  ChevronUp,
  Download,
  FileText,
  Folder,
  FolderPlus,
  LayoutGrid,
  List,
  Pencil,
  Scissors,
  Trash2,
  Upload,
  X,
} from "lucide-react";

import {
  listFilesystem,
  uploadFiles,
  copyFiles,
  moveFiles,
  deleteFiles,
  downloadFile,
  createFolder,
} from "@/api/filesystem";
import type { FilesystemEntry } from "@/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { RefreshButton } from "@/components/ui/RefreshButton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { toast } from "sonner";

const DEFAULT_ROOT = "/home/ubuntu";

type ClipboardState = {
  mode: "copy" | "cut";
  paths: string[];
};

function formatBytes(size?: number | null) {
  if (size === undefined || size === null) return "—";
  if (size < 1024) return `${size} B`;
  const kb = size / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  const gb = mb / 1024;
  return `${gb.toFixed(1)} GB`;
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function extractErrorMessage(error: any, fallback: string) {
  return (
    error?.response?.data?.detail ||
    error?.response?.data?.message ||
    error?.message ||
    fallback
  );
}

function getFilenameFromDisposition(header: string | undefined) {
  if (!header) return null;
  const match = /filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(header);
  if (!match) return null;
  return decodeURIComponent(match[1].replace(/"/g, ""));
}

function buildBreadcrumbs(path: string) {
  const normalized = path.replace(/\/+$/, "");
  if (!normalized.startsWith(DEFAULT_ROOT)) {
    return [{ label: DEFAULT_ROOT, path: DEFAULT_ROOT }];
  }
  const rel = normalized.slice(DEFAULT_ROOT.length).replace(/^\//, "");
  if (!rel) {
    return [{ label: DEFAULT_ROOT, path: DEFAULT_ROOT }];
  }
  const parts = rel.split("/").filter(Boolean);
  const crumbs = [{ label: DEFAULT_ROOT, path: DEFAULT_ROOT }];
  let acc = DEFAULT_ROOT;
  parts.forEach((part) => {
    acc = `${acc}/${part}`;
    crumbs.push({ label: part, path: acc });
  });
  return crumbs;
}

const metaShortcut = (key: string) => `Ctrl/Cmd+${key}`;
const sortOrderLabel = (direction: "asc" | "desc") =>
  direction === "asc" ? "ascending" : "descending";

export default function FilesystemPage() {
  const [currentPath, setCurrentPath] = useState(DEFAULT_ROOT);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [clipboard, setClipboard] = useState<ClipboardState | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [newFolderOpen, setNewFolderOpen] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [renameValue, setRenameValue] = useState("");
  const [renameTarget, setRenameTarget] = useState<FilesystemEntry | null>(null);
  const [inlineRenamePath, setInlineRenamePath] = useState<string | null>(null);
  const [overwriteEnabled, setOverwriteEnabled] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [lastSelectedIndex, setLastSelectedIndex] = useState<number | null>(null);
  const [sortState, setSortState] = useState<{
    key: "name" | "size" | "modified";
    direction: "asc" | "desc";
  }>({
    key: "name",
    direction: "asc",
  });
  const [viewMode, setViewMode] = useState<"list" | "grid">(() => {
    if (typeof window === "undefined") return "list";
    return window.localStorage.getItem("filesystemView") === "grid" ? "grid" : "list";
  });
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const inlineRenameRef = useRef<HTMLInputElement | null>(null);

  const queryClient = useQueryClient();

  const {
    data,
    isFetching,
    refetch,
    error,
  } = useQuery({
    queryKey: ["filesystem", currentPath],
    queryFn: () => listFilesystem(currentPath),
    refetchOnMount: true,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (error) {
      toast.error(extractErrorMessage(error, "Failed to load files"));
    }
  }, [error]);

  useEffect(() => {
    setSelected(new Set());
    setLastSelectedIndex(null);
    setInlineRenamePath(null);
    setRenameTarget(null);
    setRenameValue("");
  }, [currentPath]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem("filesystemView", viewMode);
  }, [viewMode]);

  useEffect(() => {
    setLastSelectedIndex(null);
  }, [searchTerm, sortState.key, sortState.direction]);

  const items = data?.items ?? [];
  const filteredItems = useMemo(() => {
    if (!searchTerm.trim()) return items;
    const needle = searchTerm.toLowerCase();
    return items.filter((item) => item.name.toLowerCase().includes(needle));
  }, [items, searchTerm]);

  const visibleItems = useMemo(() => {
    const sorted = [...filteredItems];
    const direction = sortState.direction === "asc" ? 1 : -1;
    sorted.sort((a, b) => {
      if (a.is_dir !== b.is_dir) {
        return a.is_dir ? -1 : 1;
      }
      let cmp = 0;
      if (sortState.key === "name") {
        cmp = a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
      } else if (sortState.key === "size") {
        const sizeA = a.size ?? -1;
        const sizeB = b.size ?? -1;
        cmp = sizeA - sizeB;
      } else {
        const modA = a.modified_at ? Date.parse(a.modified_at) : 0;
        const modB = b.modified_at ? Date.parse(b.modified_at) : 0;
        cmp = modA - modB;
      }
      return cmp * direction;
    });
    return sorted;
  }, [filteredItems, sortState.direction, sortState.key]);

  const selectedEntries = filteredItems.filter((item) => selected.has(item.path));
  const hasSelection = selectedEntries.length > 0;
  const hasDirectorySelection = selectedEntries.some((item) => item.is_dir);
  const canDownload = selectedEntries.length === 1 && selectedEntries[0].is_file;
  const canPaste = clipboard && clipboard.paths.length > 0;
  const allSelected = selectedEntries.length > 0 && selectedEntries.length === visibleItems.length;
  const partiallySelected = selectedEntries.length > 0 && selectedEntries.length < visibleItems.length;
  const canRename = selectedEntries.length === 1;

  const uploadMutation = useMutation({
    mutationFn: uploadFiles,
    onSuccess: (res) => {
      if (res.status === "success") {
        toast.success(res.message || "Upload completed");
      } else if (res.status === "partial") {
        toast.warning(res.message || "Upload completed with errors");
      } else {
        toast.error(res.message || "Upload failed");
      }
      if (res.errors && res.errors.length > 0) {
        toast.error(res.errors.slice(0, 3).join("; "));
      }
      queryClient.invalidateQueries({ queryKey: ["filesystem"] });
      setSelected(new Set());
    },
    onError: (error) => {
      toast.error(extractErrorMessage(error, "Upload failed"));
    },
  });

  const createFolderMutation = useMutation({
    mutationFn: createFolder,
    onSuccess: (res) => {
      if (res.status === "success") {
        toast.success(res.message || "Folder created");
      } else {
        toast.error(res.message || "Folder creation failed");
      }
      queryClient.invalidateQueries({ queryKey: ["filesystem"] });
      setNewFolderOpen(false);
      setNewFolderName("");
    },
    onError: (error) => {
      toast.error(extractErrorMessage(error, "Folder creation failed"));
    },
  });

  const copyMutation = useMutation({
    mutationFn: copyFiles,
    onSuccess: (res) => {
      if (res.status === "success") {
        toast.success(res.message || "Copy complete");
      } else {
        toast.error(res.message || "Copy failed");
      }
      queryClient.invalidateQueries({ queryKey: ["filesystem"] });
    },
    onError: (error) => {
      toast.error(extractErrorMessage(error, "Copy failed"));
    },
  });

  const moveMutation = useMutation({
    mutationFn: moveFiles,
    onSuccess: (res) => {
      if (res.status === "success") {
        toast.success(res.message || "Move complete");
      } else {
        toast.error(res.message || "Move failed");
      }
      queryClient.invalidateQueries({ queryKey: ["filesystem"] });
      setClipboard(null);
      setSelected(new Set());
    },
    onError: (error) => {
      toast.error(extractErrorMessage(error, "Move failed"));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteFiles,
    onSuccess: (res) => {
      if (res.status === "success") {
        toast.success(res.message || "Deleted");
      } else {
        toast.error(res.message || "Delete failed");
      }
      queryClient.invalidateQueries({ queryKey: ["filesystem"] });
      setSelected(new Set());
      setConfirmDeleteOpen(false);
    },
    onError: (error) => {
      toast.error(extractErrorMessage(error, "Delete failed"));
    },
  });

  const renameMutation = useMutation({
    mutationFn: moveFiles,
    onSuccess: (res) => {
      if (res.status === "success") {
        toast.success(res.message || "Rename complete");
      } else {
        toast.error(res.message || "Rename failed");
      }
      queryClient.invalidateQueries({ queryKey: ["filesystem"] });
      setInlineRenamePath(null);
      setRenameTarget(null);
      setRenameValue("");
      setSelected(new Set());
    },
    onError: (error) => {
      toast.error(extractErrorMessage(error, "Rename failed"));
    },
  });

  const handleToggle = (
    path: string,
    index?: number,
    mode: "toggle" | "range" | "single" = "toggle"
  ) => {
    setSelected((prev) => {
      if (mode === "range" && index !== undefined && lastSelectedIndex !== null) {
        const next = new Set(prev);
        const start = Math.min(lastSelectedIndex, index);
        const end = Math.max(lastSelectedIndex, index);
        for (let i = start; i <= end; i += 1) {
          next.add(visibleItems[i].path);
        }
        return next;
      }
      if (mode === "single") {
        return new Set([path]);
      }
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
    if (index !== undefined) {
      setLastSelectedIndex(index);
    }
  };

  const handleToggleAll = () => {
    if (selectedEntries.length === visibleItems.length && visibleItems.length > 0) {
      setSelected(new Set());
      setLastSelectedIndex(null);
      return;
    }
    setSelected(new Set(visibleItems.map((item) => item.path)));
    setLastSelectedIndex(visibleItems.length ? 0 : null);
  };

  const toggleSort = (key: "name" | "size" | "modified") => {
    setSortState((prev) => {
      if (prev.key === key) {
        return { key, direction: prev.direction === "asc" ? "desc" : "asc" };
      }
      return { key, direction: "asc" };
    });
  };

  const renderSortIcon = (key: "name" | "size" | "modified") => {
    if (sortState.key !== key) {
      return <ArrowUpDown className="h-3 w-3 text-muted-foreground" />;
    }
    return sortState.direction === "asc" ? (
      <ChevronUp className="h-3 w-3" />
    ) : (
      <ChevronDown className="h-3 w-3" />
    );
  };

  const handleOpenEntry = (entry: FilesystemEntry) => {
    if (!entry.is_dir) return;
    setCurrentPath(entry.path);
    setSelected(new Set());
  };

  const handleUpload = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    uploadMutation.mutate({
      files: Array.from(files),
      path: currentPath,
      overwrite: overwriteEnabled,
    });
  };

  const handleRowClick = (
    entry: FilesystemEntry,
    index: number,
    event: React.MouseEvent<HTMLTableRowElement>
  ) => {
    if (inlineRenamePath && inlineRenamePath !== entry.path) {
      cancelInlineRename();
    }
    const target = event.target as HTMLElement;
    if (target.closest("button, a, input, [role='checkbox']")) {
      return;
    }
    if (event.shiftKey) {
      handleToggle(entry.path, index, "range");
      return;
    }
    if (event.metaKey || event.ctrlKey) {
      handleToggle(entry.path, index, "toggle");
      return;
    }
    handleToggle(entry.path, index, "single");
  };

  const handleDownload = async () => {
    if (!canDownload) return;
    const entry = selectedEntries[0];
    try {
      const res = await downloadFile(entry.path);
      const header = res.headers?.["content-disposition"] as string | undefined;
      const filename = getFilenameFromDisposition(header) || entry.name || "download";
      const blob = new Blob([res.data]);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      toast.error(extractErrorMessage(error, "Download failed"));
    }
  };

  const handleCopy = () => {
    if (!hasSelection) return;
    setClipboard({ mode: "copy", paths: selectedEntries.map((item) => item.path) });
    toast.success(`Copied ${selectedEntries.length} item(s)`);
  };

  const handleCut = () => {
    if (!hasSelection) return;
    setClipboard({ mode: "cut", paths: selectedEntries.map((item) => item.path) });
    toast.success(`Ready to move ${selectedEntries.length} item(s)`);
  };

  const handlePaste = () => {
    if (!clipboard) return;
    if (clipboard.mode === "copy") {
      copyMutation.mutate({
        sources: clipboard.paths,
        destination: currentPath,
        overwrite: overwriteEnabled,
      });
    } else {
      moveMutation.mutate({
        sources: clipboard.paths,
        destination: currentPath,
        overwrite: overwriteEnabled,
      });
    }
  };

  const handleDelete = () => {
    if (!hasSelection) return;
    setConfirmDeleteOpen(true);
  };

  const confirmDelete = () => {
    if (!hasSelection) return;
    deleteMutation.mutate({
      paths: selectedEntries.map((item) => item.path),
      recursive: hasDirectorySelection,
    });
  };

  const handleCreateFolder = () => {
    const trimmed = newFolderName.trim();
    if (!trimmed) {
      toast.error("Folder name is required");
      return;
    }
    if (trimmed.includes("/") || trimmed.includes("\\")) {
      toast.error("Folder name cannot include slashes");
      return;
    }
    const base = currentPath.replace(/\/+$/, "");
    createFolderMutation.mutate({
      path: `${base}/${trimmed}`,
      parents: true,
      exist_ok: false,
    });
  };

  const handleRename = () => {
    if (!renameTarget) return;
    const trimmed = renameValue.trim();
    if (!trimmed) {
      toast.error("Name is required");
      return;
    }
    if (trimmed.includes("/") || trimmed.includes("\\")) {
      toast.error("Name cannot include slashes");
      return;
    }
    if (trimmed === renameTarget.name) {
      setInlineRenamePath(null);
      setRenameTarget(null);
      setRenameValue("");
      return;
    }
    const base = currentPath.replace(/\/+$/, "");
    const destination = `${base}/${trimmed}`;
    renameMutation.mutate({
      sources: [renameTarget.path],
      destination,
      overwrite: overwriteEnabled,
    });
  };

  const startInlineRename = (entry: FilesystemEntry) => {
    setRenameTarget(entry);
    setRenameValue(entry.name);
    setInlineRenamePath(entry.path);
    requestAnimationFrame(() => {
      inlineRenameRef.current?.focus();
      inlineRenameRef.current?.select();
    });
  };

  const cancelInlineRename = () => {
    setInlineRenamePath(null);
    setRenameTarget(null);
    setRenameValue("");
  };

  useEffect(() => {
    if (!inlineRenamePath) return;
    const stillPresent = items.some((item) => item.path === inlineRenamePath);
    if (!stillPresent) {
      cancelInlineRename();
    }
  }, [items, inlineRenamePath, cancelInlineRename]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const isEditable =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.getAttribute("contenteditable") === "true");
      if (isEditable) return;

      if (inlineRenamePath) {
        if (event.key === "Escape") {
          event.preventDefault();
          cancelInlineRename();
        }
        return;
      }

      const meta = event.metaKey || event.ctrlKey;
      const key = event.key.toLowerCase();

      if (meta && key === "a") {
        event.preventDefault();
        if (visibleItems.length === 0) return;
        setSelected(new Set(visibleItems.map((item) => item.path)));
        setLastSelectedIndex(0);
        return;
      }

      if (meta && key === "c") {
        if (hasSelection) {
          event.preventDefault();
          handleCopy();
        }
        return;
      }

      if (meta && key === "x") {
        if (hasSelection) {
          event.preventDefault();
          handleCut();
        }
        return;
      }

      if (meta && key === "v") {
        if (canPaste) {
          event.preventDefault();
          handlePaste();
        }
        return;
      }

      if (key === "escape") {
        setSelected(new Set());
        setLastSelectedIndex(null);
        return;
      }

      if ((key === "backspace" || key === "delete") && hasSelection) {
        event.preventDefault();
        handleDelete();
        return;
      }

      if (key === "f2" && canRename) {
        event.preventDefault();
        startInlineRename(selectedEntries[0]);
        return;
      }

      if (key === "enter" && selectedEntries.length === 1 && selectedEntries[0].is_dir) {
        event.preventDefault();
        handleOpenEntry(selectedEntries[0]);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [
    visibleItems,
    hasSelection,
    canPaste,
    selectedEntries,
    inlineRenamePath,
    handleCopy,
    handleCut,
    handlePaste,
    handleDelete,
    handleOpenEntry,
    cancelInlineRename,
    startInlineRename,
  ]);

  const breadcrumbs = buildBreadcrumbs(data?.path ?? currentPath);

  return (
    <div className="flex flex-1 flex-col">
      <div className="container/main flex flex-1 flex-col gap-2">
        <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
          <div className="grid grid-cols-1 gap-4 px-4 lg:px-6">
            <Card className="bg-gradient-to-t from-primary/5 to-card shadow-xs border rounded-lg">
              <CardHeader className="flex flex-col gap-4">
                <div className="flex items-center justify-between w-full">
                  <div>
                    <CardTitle className="text-lg font-semibold">File System</CardTitle>
                    <CardDescription>Browse, upload, move, or remove files under /home/ubuntu.</CardDescription>
                  </div>
                  <div className="flex items-center gap-2">
                    <RefreshButton onClick={() => refetch()} isLoading={isFetching} tooltip="Refresh" />
                    <div className="flex items-center gap-1 rounded-md border px-1 py-1">
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            type="button"
                            size="icon"
                            variant={viewMode === "list" ? "default" : "ghost"}
                            onClick={() => setViewMode("list")}
                            aria-label="List view"
                          >
                            <List className="h-4 w-4" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent side="bottom">List view</TooltipContent>
                      </Tooltip>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            type="button"
                            size="icon"
                            variant={viewMode === "grid" ? "default" : "ghost"}
                            onClick={() => setViewMode("grid")}
                            aria-label="Grid view"
                          >
                            <LayoutGrid className="h-4 w-4" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent side="bottom">Grid view</TooltipContent>
                      </Tooltip>
                    </div>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="outline"
                          onClick={() => {
                            setNewFolderName("");
                            setNewFolderOpen(true);
                          }}
                          className="flex items-center gap-2"
                        >
                          <FolderPlus className="h-4 w-4" />
                          New Folder
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="bottom">New folder</TooltipContent>
                    </Tooltip>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="outline"
                          onClick={() => fileInputRef.current?.click()}
                          className="flex items-center gap-2"
                        >
                          <Upload className="h-4 w-4" />
                          Upload
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="bottom">Upload files</TooltipContent>
                    </Tooltip>
                    <input
                      ref={fileInputRef}
                      type="file"
                      multiple
                      className="hidden"
                      onChange={(e) => {
                        handleUpload(e.target.files);
                        if (e.currentTarget) {
                          e.currentTarget.value = "";
                        }
                      }}
                    />
                  </div>
                </div>

                <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                  <div className="flex flex-wrap items-center gap-2">
                    {data?.parent && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setCurrentPath(data.parent as string)}
                        className="flex items-center gap-1"
                      >
                        <ArrowUp className="h-4 w-4" />
                        Up
                      </Button>
                    )}
                    <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                      {breadcrumbs.map((crumb, idx) => (
                        <Button
                          key={crumb.path}
                          variant="ghost"
                          size="sm"
                          className="px-2"
                          onClick={() => {
                            setCurrentPath(crumb.path);
                            setSelected(new Set());
                          }}
                        >
                          {crumb.label}
                          {idx < breadcrumbs.length - 1 ? " /" : ""}
                        </Button>
                      ))}
                    </div>
                  </div>
                  <Input
                    placeholder="Search files…"
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="md:max-w-xs"
                  />
                </div>

                <div className="flex flex-wrap items-center gap-2 justify-between">
                  <div className="flex flex-wrap items-center gap-2">
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={!canRename || !!inlineRenamePath}
                          onClick={() => {
                            if (!canRename) return;
                            startInlineRename(selectedEntries[0]);
                          }}
                          className="flex items-center gap-1"
                        >
                          <Pencil className="h-4 w-4" />
                          Rename
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="bottom">Rename (F2)</TooltipContent>
                    </Tooltip>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={!hasSelection}
                          onClick={handleCopy}
                          className="flex items-center gap-1"
                        >
                          <ClipboardCopy className="h-4 w-4" />
                          Copy
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="bottom">Copy ({metaShortcut("C")})</TooltipContent>
                    </Tooltip>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={!hasSelection}
                          onClick={handleCut}
                          className="flex items-center gap-1"
                        >
                          <Scissors className="h-4 w-4" />
                          Cut
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="bottom">Cut ({metaShortcut("X")})</TooltipContent>
                    </Tooltip>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={!canPaste}
                          onClick={handlePaste}
                          className="flex items-center gap-1"
                        >
                          <ClipboardPaste className="h-4 w-4" />
                          Paste
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="bottom">Paste ({metaShortcut("V")})</TooltipContent>
                    </Tooltip>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={!canDownload}
                          onClick={handleDownload}
                          className="flex items-center gap-1"
                        >
                          <Download className="h-4 w-4" />
                          Download
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="bottom">Download</TooltipContent>
                    </Tooltip>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="destructive"
                          size="sm"
                          disabled={!hasSelection}
                          onClick={handleDelete}
                          className="flex items-center gap-1"
                        >
                          <Trash2 className="h-4 w-4" />
                          Delete
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="bottom">Delete (Del)</TooltipContent>
                    </Tooltip>
                  </div>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <span>Overwrite</span>
                        <Switch checked={overwriteEnabled} onCheckedChange={setOverwriteEnabled} />
                      </div>
                    </TooltipTrigger>
                    <TooltipContent side="bottom">Allow overwrite on copy, move, or upload</TooltipContent>
                  </Tooltip>
                </div>
              </CardHeader>
              <CardContent
                className="relative"
                onDragEnter={(event) => {
                  event.preventDefault();
                  setDragActive(true);
                }}
                onDragOver={(event) => {
                  event.preventDefault();
                  setDragActive(true);
                }}
                onDragLeave={(event) => {
                  if (!event.currentTarget.contains(event.relatedTarget as Node)) {
                    setDragActive(false);
                  }
                }}
                onDrop={(event) => {
                  event.preventDefault();
                  setDragActive(false);
                  handleUpload(event.dataTransfer.files);
                }}
              >
                {dragActive && (
                  <div className="absolute inset-0 z-10 flex items-center justify-center rounded-lg border border-dashed border-primary/40 bg-background/70 backdrop-blur-sm">
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Upload className="h-4 w-4" />
                      Drop files to upload
                    </div>
                  </div>
                )}
                {viewMode === "list" ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-[32px]">
                          <Checkbox
                            checked={allSelected ? true : partiallySelected ? "indeterminate" : false}
                            onCheckedChange={handleToggleAll}
                            aria-label="Select all"
                          />
                        </TableHead>
                      <TableHead aria-sort={sortState.key === "name" ? sortOrderLabel(sortState.direction) : "none"}>
                        <button
                          type="button"
                          onClick={() => toggleSort("name")}
                          className="flex items-center gap-1 text-left"
                        >
                          Name
                          {renderSortIcon("name")}
                        </button>
                      </TableHead>
                      <TableHead aria-sort={sortState.key === "size" ? sortOrderLabel(sortState.direction) : "none"}>
                        <button
                          type="button"
                          onClick={() => toggleSort("size")}
                          className="flex items-center gap-1 text-left"
                        >
                          Size
                          {renderSortIcon("size")}
                        </button>
                      </TableHead>
                      <TableHead
                        aria-sort={sortState.key === "modified" ? sortOrderLabel(sortState.direction) : "none"}
                      >
                        <button
                          type="button"
                          onClick={() => toggleSort("modified")}
                          className="flex items-center gap-1 text-left"
                        >
                          Modified
                          {renderSortIcon("modified")}
                        </button>
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {visibleItems.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={4} className="text-center text-muted-foreground py-6">
                          {error ? "Failed to load files." : "No files found."}
                        </TableCell>
                      </TableRow>
                    ) : (
                      visibleItems.map((entry, index) => (
                        <TableRow
                          key={entry.path}
                          data-state={selected.has(entry.path) ? "selected" : undefined}
                            onClick={(event) => handleRowClick(entry, index, event)}
                            onDoubleClick={() => {
                              if (entry.is_dir) {
                                handleOpenEntry(entry);
                              }
                            }}
                            className="cursor-pointer"
                          >
                            <TableCell>
                              <Checkbox
                                checked={selected.has(entry.path)}
                                onCheckedChange={() => handleToggle(entry.path, index, "toggle")}
                                aria-label={`Select ${entry.name}`}
                              />
                            </TableCell>
                            <TableCell className="max-w-[320px]">
                              {inlineRenamePath === entry.path ? (
                                <div
                                  className="flex items-center gap-2"
                                  onClick={(event) => event.stopPropagation()}
                                >
                                  {entry.is_dir ? <Folder className="h-4 w-4" /> : <FileText className="h-4 w-4" />}
                                  <Input
                                    ref={inlineRenameRef}
                                    value={renameValue}
                                    onChange={(event) => setRenameValue(event.target.value)}
                                    onKeyDown={(event) => {
                                      if (event.key === "Enter") {
                                        event.preventDefault();
                                        handleRename();
                                      }
                                      if (event.key === "Escape") {
                                        event.preventDefault();
                                        cancelInlineRename();
                                      }
                                    }}
                                    disabled={renameMutation.isPending}
                                    className="h-8 flex-1 min-w-[140px]"
                                  />
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Button
                                      type="button"
                                      size="icon"
                                      variant="ghost"
                                      onClick={handleRename}
                                      disabled={renameMutation.isPending}
                                      aria-label="Confirm rename"
                                    >
                                      <Check className="h-4 w-4" />
                                    </Button>
                                  </TooltipTrigger>
                                  <TooltipContent side="bottom">Confirm rename</TooltipContent>
                                </Tooltip>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Button
                                      type="button"
                                      size="icon"
                                      variant="ghost"
                                      onClick={cancelInlineRename}
                                      disabled={renameMutation.isPending}
                                      aria-label="Cancel rename"
                                    >
                                      <X className="h-4 w-4" />
                                    </Button>
                                  </TooltipTrigger>
                                  <TooltipContent side="bottom">Cancel rename</TooltipContent>
                                </Tooltip>
                              </div>
                            ) : (
                              <button
                                type="button"
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    handleOpenEntry(entry);
                                  }}
                                  className={`flex items-center gap-2 ${entry.is_dir ? "text-primary" : ""}`}
                                >
                                  {entry.is_dir ? <Folder className="h-4 w-4" /> : <FileText className="h-4 w-4" />}
                                  <span className="truncate">{entry.name}</span>
                                </button>
                              )}
                            </TableCell>
                            <TableCell>{entry.is_dir ? "—" : formatBytes(entry.size)}</TableCell>
                            <TableCell>{formatDate(entry.modified_at)}</TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                ) : (
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
                    {visibleItems.length === 0 ? (
                      <div className="col-span-full py-8 text-center text-muted-foreground">
                        {error ? "Failed to load files." : "No files found."}
                      </div>
                    ) : (
                      visibleItems.map((entry, index) => {
                        const isSelected = selected.has(entry.path);
                        return (
                          <div
                            key={entry.path}
                            data-state={isSelected ? "selected" : undefined}
                            onClick={(event) => handleRowClick(entry, index, event)}
                            onDoubleClick={() => {
                              if (entry.is_dir) {
                                handleOpenEntry(entry);
                              }
                            }}
                            className={`relative flex flex-col gap-2 rounded-lg border p-3 transition ${
                              isSelected
                                ? "border-primary/60 bg-primary/5 ring-1 ring-primary/30"
                                : "border-border/60 hover:border-primary/40"
                            }`}
                          >
                            <div className="flex items-start justify-between gap-2">
                              {inlineRenamePath === entry.path ? (
                                <div
                                  className="flex flex-1 items-center gap-2"
                                  onClick={(event) => event.stopPropagation()}
                                >
                                  {entry.is_dir ? <Folder className="h-4 w-4" /> : <FileText className="h-4 w-4" />}
                                  <Input
                                    ref={inlineRenameRef}
                                    value={renameValue}
                                    onChange={(event) => setRenameValue(event.target.value)}
                                    onKeyDown={(event) => {
                                      if (event.key === "Enter") {
                                        event.preventDefault();
                                        handleRename();
                                      }
                                      if (event.key === "Escape") {
                                        event.preventDefault();
                                        cancelInlineRename();
                                      }
                                    }}
                                    disabled={renameMutation.isPending}
                                    className="h-8 flex-1 min-w-[120px]"
                                  />
                                </div>
                              ) : (
                                <button
                                  type="button"
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    handleOpenEntry(entry);
                                  }}
                                  className={`flex flex-1 min-w-0 items-center gap-2 text-left ${
                                    entry.is_dir ? "text-primary" : ""
                                  }`}
                                >
                                  {entry.is_dir ? <Folder className="h-5 w-5 shrink-0" /> : <FileText className="h-5 w-5 shrink-0" />}
                                  <Tooltip>
                                    <TooltipTrigger asChild>
                                      <span className="truncate text-sm font-medium">{entry.name}</span>
                                    </TooltipTrigger>
                                    <TooltipContent side="bottom">{entry.name}</TooltipContent>
                                  </Tooltip>
                                </button>
                              )}
                              <div onClick={(event) => event.stopPropagation()}>
                                <Checkbox
                                  checked={isSelected}
                                  onCheckedChange={() => handleToggle(entry.path, index, "toggle")}
                                  aria-label={`Select ${entry.name}`}
                                />
                              </div>
                            </div>
                            <div className="text-xs text-muted-foreground">
                              <div>{entry.is_dir ? "Folder" : formatBytes(entry.size)}</div>
                              <div className="mt-1 text-[10px] uppercase tracking-wide text-muted-foreground/70">
                                Last modified
                              </div>
                              <div>{formatDate(entry.modified_at)}</div>
                            </div>
                            {inlineRenamePath === entry.path && (
                              <div className="flex items-center gap-1" onClick={(event) => event.stopPropagation()}>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Button
                                      type="button"
                                      size="icon"
                                      variant="ghost"
                                      onClick={handleRename}
                                      disabled={renameMutation.isPending}
                                      aria-label="Confirm rename"
                                    >
                                      <Check className="h-4 w-4" />
                                    </Button>
                                  </TooltipTrigger>
                                  <TooltipContent side="bottom">Confirm rename</TooltipContent>
                                </Tooltip>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Button
                                      type="button"
                                      size="icon"
                                      variant="ghost"
                                      onClick={cancelInlineRename}
                                      disabled={renameMutation.isPending}
                                      aria-label="Cancel rename"
                                    >
                                      <X className="h-4 w-4" />
                                    </Button>
                                  </TooltipTrigger>
                                  <TooltipContent side="bottom">Cancel rename</TooltipContent>
                                </Tooltip>
                              </div>
                            )}
                          </div>
                        );
                      })
                    )}
                  </div>
                )}
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t pt-2 text-xs text-muted-foreground">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-foreground font-medium">Path</span>
                    <span className="truncate">{currentPath}</span>
                  </div>
                  <div className="flex flex-wrap items-center gap-3">
                    <span>
                      {filteredItems.length} item{filteredItems.length === 1 ? "" : "s"}
                    </span>
                    <span>
                      {selectedEntries.length} selected
                    </span>
                    {clipboard && (
                      <span>
                        {clipboard.mode === "copy" ? "Clipboard copy" : "Clipboard cut"}: {clipboard.paths.length}
                      </span>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>

      <Dialog
        open={newFolderOpen}
        onOpenChange={(open) => {
          setNewFolderOpen(open);
          if (!open) {
            setNewFolderName("");
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create new folder</DialogTitle>
            <DialogDescription>Folders are created inside the current path.</DialogDescription>
          </DialogHeader>
          <Input
            placeholder="Folder name"
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                handleCreateFolder();
              }
            }}
          />
          <DialogFooter className="flex gap-2">
            <Button variant="outline" onClick={() => setNewFolderOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreateFolder} disabled={createFolderMutation.isPending}>
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={confirmDeleteOpen} onOpenChange={setConfirmDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete selected items?</DialogTitle>
            <DialogDescription>
              {hasDirectorySelection
                ? "Folders will be deleted recursively. This cannot be undone."
                : "This action cannot be undone."}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="flex gap-2">
            <Button variant="outline" onClick={() => setConfirmDeleteOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={confirmDelete}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
