import { CopyButton } from "@/components/ui/CopyButton";
import { cn } from "@/lib/utils";

export function formatDidTail(value: string, tailLength = 10): string {
  const trimmed = value.trim();
  if (trimmed.length <= tailLength) {
    return trimmed;
  }
  return `...${trimmed.slice(-tailLength)}`;
}

interface DidDisplayProps {
  value?: string | null;
  muted?: boolean;
  className?: string;
  textClassName?: string;
  tailLength?: number;
}

export function DidDisplay({
  value,
  muted,
  className,
  textClassName,
  tailLength = 10,
}: DidDisplayProps) {
  if (!value) {
    return <span className="text-xs text-muted-foreground">--</span>;
  }

  const display = formatDidTail(value, tailLength);

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <span
        className={cn(
          "font-mono text-xs whitespace-nowrap",
          muted ? "text-muted-foreground/90" : "text-foreground",
          textClassName
        )}
        title={value}
      >
        {display}
      </span>
      <CopyButton text={value} />
    </div>
  );
}
