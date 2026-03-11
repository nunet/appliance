import { type ReactNode, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ChevronsDown, Loader2, Maximize2 } from "lucide-react";
import { Button } from "../ui/button";
import { CopyButton } from "../ui/CopyButton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import {
  DmsLogEntry,
  DmsLogView,
  formatDmsLogEntry,
  formatDmsLogEntryExpanded,
} from "@/lib/dmsLogs";

type DmsLogSectionProps = {
  title: string;
  entries: DmsLogEntry[];
  view: DmsLogView;
  placeholder?: string;
  isLoading?: boolean;
  autoScroll?: boolean;
  copyText?: string;
  modalControls?: ReactNode;
};

export function DmsLogSection({
  title,
  entries,
  view,
  placeholder,
  isLoading = false,
  autoScroll = false,
  copyText,
  modalControls,
}: DmsLogSectionProps) {
  const [isModalOpen, setIsModalOpen] = useState(false);

  const shouldIgnoreOutside = (target: EventTarget | null) => {
    if (!(target instanceof Element)) return false;
    return Boolean(
      target.closest('[data-slot="select-content"]') ||
        target.closest('[data-slot="select-item"]') ||
        target.closest('[data-slot="select-scroll-up-button"]') ||
        target.closest('[data-slot="select-scroll-down-button"]') ||
        target.closest('[data-slot="tooltip-content"]')
    );
  };

  const hasContent = entries.length > 0;
  const friendlyPlaceholder = placeholder || "No logs available yet.";
  const copyPayload =
    copyText ?? (hasContent ? entries.map((entry) => entry.raw).join("\n") : "");

  return (
    <>
      <div className="flex items-center justify-between mt-4">
        <div className="flex items-center gap-2">
          <p className="font-semibold">{title}</p>
          {isLoading ? (
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" />
              Loading
            </span>
          ) : null}
        </div>
        {copyPayload ? (
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => setIsModalOpen(true)}
              aria-label={`Expand ${title} logs`}
              className="size-8 rounded-full bg-muted/50 hover:bg-muted"
            >
              <Maximize2 className="h-4 w-4" />
            </Button>
            <CopyButton text={copyPayload} className="text-xs" />
          </div>
        ) : null}
      </div>
      <DmsLogBody
        entries={entries}
        view={view}
        placeholder={friendlyPlaceholder}
        autoScroll={autoScroll}
        sizeClass="h-56"
      />
      <Dialog open={isModalOpen} onOpenChange={setIsModalOpen}>
        <DialogContent
          className="!max-w-[95vw] !w-[95vw] max-h-[90vh] sm:!max-w-[95vw]"
          onInteractOutside={(event) => {
            if (shouldIgnoreOutside(event.target)) {
              event.preventDefault();
            }
          }}
        >
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
          </DialogHeader>
          {modalControls ? <div className="mt-3">{modalControls}</div> : null}
          {copyPayload ? (
            <div className="flex justify-end mb-2">
              <CopyButton text={copyPayload} className="text-xs" />
            </div>
          ) : null}
          <DmsLogBody
            entries={entries}
            view={view}
            placeholder={friendlyPlaceholder}
            autoScroll={autoScroll}
            sizeClass="max-h-[70vh] min-h-[50vh]"
            enableExpandScroll={false}
          />
        </DialogContent>
      </Dialog>
    </>
  );
}

type DmsLogBodyProps = {
  entries: DmsLogEntry[];
  view: DmsLogView;
  placeholder: string;
  autoScroll: boolean;
  sizeClass: string;
  enableExpandScroll?: boolean;
};

function DmsLogBody({
  entries,
  view,
  placeholder,
  autoScroll,
  sizeClass,
  enableExpandScroll = true,
}: DmsLogBodyProps) {
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set());
  const [lastExpandedKey, setLastExpandedKey] = useState<string | null>(null);
  const [isFollowingTail, setIsFollowingTail] = useState(autoScroll);
  const [shouldSnapToBottom, setShouldSnapToBottom] = useState(false);
  const rowRefs = useRef<Map<string, HTMLDivElement | null>>(new Map());
  const followTailRef = useRef(autoScroll);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const didInitialSnapRef = useRef(false);

  const hasContent = entries.length > 0;

  useEffect(() => {
    setExpandedKeys(new Set());
    setLastExpandedKey(null);
  }, [view]);

  const renderEntries = useMemo(() => {
    const occurrences = new Map<string, number>();
    return entries.map((entry) => {
      const count = (occurrences.get(entry.raw) ?? 0) + 1;
      occurrences.set(entry.raw, count);
      return {
        entry,
        key: `${entry.raw}::${count}`,
      };
    });
  }, [entries]);

  const toggleExpanded = (key: string) => {
    if (autoScroll) {
      followTailRef.current = false;
      setIsFollowingTail(false);
    }
    setExpandedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
        setLastExpandedKey((current) => (current === key ? null : current));
      } else {
        next.add(key);
        setLastExpandedKey(key);
      }
      return next;
    });
  };

  useEffect(() => {
    if (!autoScroll) {
      setShouldSnapToBottom(false);
      setIsFollowingTail(false);
      followTailRef.current = false;
      return;
    }
    setShouldSnapToBottom(true);
    setIsFollowingTail(true);
    followTailRef.current = true;
  }, [autoScroll]);

  useLayoutEffect(() => {
    if (autoScroll) return;
    if (didInitialSnapRef.current) return;
    const node = scrollRef.current;
    if (!node) return;
    if (!entries.length) return;
    node.scrollTop = node.scrollHeight;
    didInitialSnapRef.current = true;
  }, [autoScroll, entries]);

  useLayoutEffect(() => {
    if (!autoScroll) return;
    const node = scrollRef.current;
    if (!node) return;
    if (shouldSnapToBottom) {
      node.scrollTop = node.scrollHeight;
      setShouldSnapToBottom(false);
      return;
    }
    if (!followTailRef.current) return;
    node.scrollTop = node.scrollHeight;
  }, [autoScroll, entries, shouldSnapToBottom]);

  const handleScroll = () => {
    didInitialSnapRef.current = true;
    if (!autoScroll) return;
    const node = scrollRef.current;
    if (!node) return;
    const distanceFromBottom = node.scrollHeight - node.scrollTop - node.clientHeight;
    const shouldFollow = distanceFromBottom <= 1;
    if (followTailRef.current !== shouldFollow) {
      followTailRef.current = shouldFollow;
      setIsFollowingTail(shouldFollow);
    }
  };

  const jumpToBottom = () => {
    const node = scrollRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
    followTailRef.current = true;
    setIsFollowingTail(true);
  };

  const showJumpToBottom = autoScroll && !isFollowingTail && hasContent;

  useLayoutEffect(() => {
    if (!enableExpandScroll) return;
    if (!lastExpandedKey) return;
    const node = scrollRef.current;
    if (!node) return;
    const target = rowRefs.current.get(lastExpandedKey);
    if (!target) return;
    const desiredTop = target.offsetTop - node.clientHeight / 2 + target.offsetHeight / 2;
    node.scrollTo({ top: Math.max(0, desiredTop), behavior: "auto" });
  }, [enableExpandScroll, lastExpandedKey]);

  return (
    <div
      ref={scrollRef}
      onScroll={handleScroll}
      className={`relative bg-black text-white font-mono text-sm rounded-md p-3 shadow-inner ${sizeClass}`}
      style={{
        overflowX: "hidden",
        overflowY: "auto",
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
        overflowWrap: "anywhere",
        width: "100%",
        maxWidth: "100%",
      }}
    >
      {showJumpToBottom ? (
        <div className="absolute top-2 right-2">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={jumpToBottom}
            aria-label="Jump to latest logs"
            className="size-8 rounded-full bg-black/40 hover:bg-black/60 focus-visible:ring-offset-0"
          >
            <ChevronsDown className="h-4 w-4" />
          </Button>
        </div>
      ) : null}
      <div>
        {hasContent ? (
          <div className="space-y-1">
            {renderEntries.map(({ entry, key }) => {
              const collapsed = formatDmsLogEntry(entry, view);
              const expanded = formatDmsLogEntryExpanded(entry);
              const canExpand = Boolean(entry.parsed) && view !== "expanded";
              const isExpanded = expandedKeys.has(key);
              const level = String(entry.parsed?.level ?? "").toUpperCase();
              const levelClass =
                level === "ERROR" || level === "ERR"
                  ? "text-red-400"
                  : level === "WARN" || level === "WARNING"
                  ? "text-amber-300"
                  : level === "INFO"
                  ? "text-emerald-300"
                  : level === "DEBUG" || level === "DBG"
                  ? "text-cyan-300"
                  : "text-white";
              return (
                <div key={key} className="space-y-1">
                  <div
                    role={canExpand ? "button" : undefined}
                    tabIndex={canExpand ? 0 : -1}
                    onClick={() => (canExpand ? toggleExpanded(key) : null)}
                    onKeyDown={(event) => {
                      if (!canExpand) return;
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        toggleExpanded(key);
                      }
                    }}
                    ref={(el) => {
                      if (el) {
                        rowRefs.current.set(key, el);
                      } else {
                        rowRefs.current.delete(key);
                      }
                    }}
                    className={`rounded-md px-2 py-1 ${levelClass} ${
                      canExpand
                        ? "cursor-pointer bg-black/40 hover:bg-black/60 focus:outline-none focus:ring-1 focus:ring-white/30"
                        : "bg-black/20"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <span className="flex-1 whitespace-pre-wrap break-words">
                        {collapsed || entry.raw}
                      </span>
                      {canExpand ? (
                        <span className="shrink-0 text-[10px] uppercase tracking-wide text-slate-400">
                          {isExpanded ? "collapse" : "expand"}
                        </span>
                      ) : null}
                    </div>
                  </div>
                  {canExpand && isExpanded ? (
                    <div className="rounded-md border border-white/10 bg-black/30 px-3 py-2 text-xs text-white/90 whitespace-pre-wrap break-words">
                      <div className="flex justify-end mb-2">
                        <CopyButton text={expanded} className="text-[10px]" />
                      </div>
                      {expanded}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="text-muted-foreground whitespace-pre-wrap break-words">
            {placeholder}
          </div>
        )}
      </div>
    </div>
  );
}
