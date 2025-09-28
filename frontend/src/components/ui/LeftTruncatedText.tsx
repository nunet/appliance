import { cn } from "@/lib/utils";

type LeftTruncatedTextProps = {
  text: string;
  className?: string;
  title?: string;
};

export function LeftTruncatedText({
  text,
  className,
  title,
}: LeftTruncatedTextProps) {
  return (
    <span
      className={cn(
        "inline-flex min-w-0 max-w-full overflow-hidden text-ellipsis whitespace-nowrap text-left [direction:rtl]",
        className
      )}
      title={title ?? text}
    >
      <span className="block w-full [direction:ltr]">{text}</span>
    </span>
  );
}
