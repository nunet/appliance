import * as React from "react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import CodeMirror from "@uiw/react-codemirror";
import { EditorView } from "@codemirror/view";
import { json as jsonMode } from "@codemirror/lang-json";

type JsonEditorProps = {
  label?: string;
  value: string;
  onChange: (value: string) => void;
  className?: string;
  error?: string | null;
  disabled?: boolean;
  helperText?: string;
};

export function JsonEditor({
  label = "JSON",
  value,
  onChange,
  className,
  error,
  disabled,
  helperText,
}: JsonEditorProps) {
  const [formatError, setFormatError] = React.useState<string | null>(null);
  const extensions = React.useMemo(
    () => [
      jsonMode(),
      EditorView.lineWrapping,
    ],
    []
  );

  const handleFormat = React.useCallback(() => {
    try {
      const parsed = JSON.parse(value || "{}");
      const formatted = JSON.stringify(parsed, null, 2);
      onChange(formatted);
      setFormatError(null);
    } catch (fmtError: any) {
      setFormatError(fmtError?.message || "Unable to format JSON.");
    }
  }, [value, onChange]);

  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-center justify-between">
        <Label className="text-sm font-medium">{label}</Label>
        <Button type="button" size="sm" variant="outline" onClick={handleFormat} disabled={disabled}>
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
            highlightActiveLine: true,
            highlightActiveLineGutter: true,
            bracketMatching: true,
            autocompletion: true,
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
    </div>
  );
}
