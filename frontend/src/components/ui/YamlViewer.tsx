"use client";

import { useMemo } from "react";
import hljs from "highlight.js/lib/core";
import yamlLanguage from "highlight.js/lib/languages/yaml";
import { parseDocument } from "yaml";

import { cn } from "@/lib/utils";

hljs.registerLanguage("yaml", yamlLanguage);

type YamlViewerProps = {
  value: string;
  className?: string;
  maxHeight?: string | number;
  wrapLongLines?: boolean;
};

export function YamlViewer({
  value,
  className,
  maxHeight = "60vh",
  wrapLongLines = true,
}: YamlViewerProps) {
  const lint = useMemo(() => {
    const trimmed = value?.trim();
    if (!trimmed) {
      return { status: "empty" as const, messages: [] as string[] };
    }

    try {
      const doc = parseDocument(value);
      const errors = doc.errors?.map((err) => err.message).filter(Boolean) ?? [];
      if (errors.length) {
        return { status: "error" as const, messages: errors };
      }

      const warnings = doc.warnings?.map((warn) => warn.message).filter(Boolean) ?? [];
      if (warnings.length) {
        return { status: "warn" as const, messages: warnings };
      }

      return { status: "ok" as const, messages: [] as string[] };
    } catch (error) {
      const message =
        error && typeof error === "object" && "message" in error
          ? String((error as Error).message)
          : "Invalid YAML";
      return { status: "error" as const, messages: [message] };
    }
  }, [value]);

  const displayValue = value?.trim() ? value : "# empty";

  const highlighted = useMemo(() => {
    try {
      return hljs.highlight(displayValue, {
        language: "yaml",
        ignoreIllegals: true,
      }).value;
    } catch (error) {
      try {
        return hljs.highlightAuto(displayValue).value;
      } catch (error2) {
        return displayValue.replaceAll("<", "&lt;").replaceAll(">", "&gt;");
      }
    }
  }, [displayValue]);

  return (
    <div
      className={cn(
        "relative flex w-full flex-col overflow-hidden rounded-md border bg-background/70",
        className
      )}
      style={{ maxHeight }}
    >
      {lint.status === "error" && lint.messages.length > 0 && (
        <div className="border-b border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          YAML issue: {lint.messages[0]}
        </div>
      )}
      {lint.status === "warn" && lint.messages.length > 0 && (
        <div className="border-b border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-500">
          YAML warning: {lint.messages[0]}
        </div>
      )}
      {lint.status === "empty" && (
        <div className="border-b border-border/60 bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          No YAML content returned.
        </div>
      )}
      <pre
        className={cn(
          "hljs m-0 overflow-auto font-mono text-xs leading-relaxed",
          wrapLongLines ? "whitespace-pre-wrap break-words" : "whitespace-pre"
        )}
        style={{
          maxHeight,
          padding: "1rem",
        }}
      >
        <code
          className="language-yaml"
          dangerouslySetInnerHTML={{ __html: highlighted }}
        />
      </pre>
    </div>
  );
}
