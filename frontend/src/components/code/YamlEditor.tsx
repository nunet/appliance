import * as React from "react";
import { parseDocument } from "yaml";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import CodeMirror from "@uiw/react-codemirror";
import { EditorView } from "@codemirror/view";
import { yaml as yamlMode } from "@codemirror/lang-yaml";

type YamlEditorProps = {
  label?: string;
  value: string;
  onChange: (value: string) => void;
  className?: string;
  error?: string | null;
  disabled?: boolean;
  helperText?: string;
};

export type YamlLintResult =
  | { status: "empty"; message: string }
  | { status: "ok"; message: string }
  | { status: "warn"; message: string }
  | { status: "error"; message: string };

export function lintYaml(value: string): YamlLintResult {
  const trimmed = value?.trim?.() ?? "";
  if (!trimmed) {
    return { status: "empty", message: "No YAML content provided yet." };
  }
  try {
    const doc = parseDocument(value);
    const firstError = doc.errors?.find((err) => Boolean(err?.message));
    if (firstError?.message) {
      return { status: "error", message: firstError.message };
    }
    const firstWarning = doc.warnings?.find((warn) => Boolean(warn?.message));
    if (firstWarning?.message) {
      return { status: "warn", message: firstWarning.message };
    }
    return { status: "ok", message: "YAML looks valid." };
  } catch (error) {
    const message =
      error && typeof error === "object" && "message" in error
        ? String((error as Error).message)
        : "Invalid YAML content.";
    return { status: "error", message };
  }
}

export function YamlEditor({
  label = "YAML",
  value,
  onChange,
  className,
  error,
  disabled,
  helperText,
}: YamlEditorProps) {
  const [formatError, setFormatError] = React.useState<string | null>(null);
  const lint = React.useMemo(() => lintYaml(value), [value]);
  const extensions = React.useMemo(
    () => [
      yamlMode(),
      EditorView.lineWrapping,
    ],
    []
  );

  const handleFormat = React.useCallback(() => {
    try {
      if (!value.trim()) {
        onChange("");
        setFormatError(null);
        return;
      }
      // Preserve handlebars-style placeholders by temporarily masking them
      const placeholderMap = new Map<string, string>();
      let temp = value;
      const regex = /{{\s*[^}]+?\s*}}/g;
      let idx = 0;
      temp = temp.replace(regex, (match) => {
        const key = `__PLACEHOLDER_${idx++}__`;
        placeholderMap.set(key, match);
        return key;
      });
      const doc = parseDocument(temp);
      let formatted = doc.toString({ lineWidth: 120 }).trimEnd();
      placeholderMap.forEach((original, token) => {
        formatted = formatted.replace(token, original);
      });
      onChange(formatted);
      setFormatError(null);
    } catch (fmtError: any) {
      setFormatError(fmtError?.message || "Unable to format YAML.");
    }
  }, [value, onChange]);

  const lintBadgeClass = React.useMemo(() => {
    switch (lint.status) {
      case "error":
        return "bg-destructive/15 text-destructive border-destructive/20";
      case "warn":
        return "bg-amber-500/10 text-amber-600 border-amber-500/30";
      case "ok":
        return "bg-emerald-500/10 text-emerald-600 border-emerald-500/20";
      default:
        return "bg-muted text-muted-foreground border-transparent";
    }
  }, [lint.status]);

  const lintBadgeLabel = React.useMemo(() => {
    switch (lint.status) {
      case "error":
        return "Syntax error";
      case "warn":
        return "Warning";
      case "ok":
        return "Valid YAML";
      default:
        return "Awaiting input";
    }
  }, [lint.status]);

  const lintMessageClass = React.useMemo(() => {
    switch (lint.status) {
      case "error":
        return "text-xs text-destructive";
      case "warn":
        return "text-xs text-amber-600";
      case "ok":
        return "text-xs text-emerald-600";
      default:
        return "text-xs text-muted-foreground";
    }
  }, [lint.status]);

  return (
    <div className={cn("space-y-3", className)}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Label className="text-sm font-medium">{label}</Label>
          <Badge variant="outline" className={lintBadgeClass}>
            {lintBadgeLabel}
          </Badge>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={handleFormat}
          disabled={disabled}
        >
          Format
        </Button>
      </div>
      <div className="overflow-hidden rounded-md border bg-[#0f172a]">
        <CodeMirror
          value={value}
          height="360px"
          theme="dark"
          className={cn("font-mono text-sm", disabled && "opacity-50")}
          editable={!disabled}
          extensions={extensions}
          basicSetup={{
            lineNumbers: true,
            foldGutter: true,
            highlightActiveLineGutter: true,
            highlightActiveLine: true,
            bracketMatching: true,
            autocompletion: false,
          }}
          onChange={(next) => {
            setFormatError(null);
            onChange(next);
          }}
        />
      </div>
      {helperText && !error && !formatError && (
        <p className="text-xs text-muted-foreground">{helperText}</p>
      )}
      {error && <p className="text-xs text-destructive">{error}</p>}
      {formatError && <p className="text-xs text-destructive">{formatError}</p>}
      {lint.message && (
        <p className={lintMessageClass}>
          {lint.status === "error"
            ? "Syntax issue: "
            : lint.status === "warn"
            ? "Warning: "
            : lint.status === "ok"
            ? "Syntax check: "
            : ""}
          {lint.message}
        </p>
      )}
    </div>
  );
}
