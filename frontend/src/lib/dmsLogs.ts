export type DmsLogView = "compact" | "folded" | "expanded" | "map" | "raw";

export type DmsLogEntry = {
  raw: string;
  parsed: Record<string, unknown> | null;
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);

const safeString = (value: unknown): string => {
  if (value === null || value === undefined) return "";
  return typeof value === "string" ? value : String(value);
};

export const parseDmsLogEntries = (raw: string): DmsLogEntry[] => {
  if (!raw) return [];
  return raw
    .replace(/\r\n/g, "\n")
    .split("\n")
    .map((line) => line.trimEnd())
    .filter((line) => line.trim().length > 0)
    .map((line) => {
      const trimmed = line.trim();
      try {
        const parsed = JSON.parse(trimmed);
        return {
          raw: line,
          parsed: isRecord(parsed) ? parsed : null,
        };
      } catch {
        return { raw: line, parsed: null };
      }
    });
};

const formatEntryCompact = (entry: Record<string, unknown>, fallback: string): string => {
  const timestamp = safeString(entry.timestamp ?? entry.time);
  const level = safeString(entry.level);
  const msg = safeString(entry.msg ?? entry.message);
  const parts = [timestamp, level, msg].filter(Boolean).join(" ").trim();
  const extras: string[] = [];
  for (const key of ["orchestratorID", "deploymentID", "allocationID", "behavior", "did"]) {
    const value = safeString(entry[key]);
    if (value) {
      extras.push(`${key}=${value}`);
    }
  }
  const errorValue = safeString(entry.error);
  if (errorValue) {
    extras.push(`error=${errorValue}`);
  }
  if (extras.length > 0) {
    return `${parts} | ${extras.join(" ")}`.trim();
  }
  return parts || fallback;
};

const formatEntryFolded = (entry: Record<string, unknown>, fallback: string): string => {
  const timestamp = safeString(entry.timestamp ?? entry.time);
  const level = safeString(entry.level);
  const msg = safeString(entry.msg ?? entry.message);
  const line = [timestamp, level, msg].filter(Boolean).join(" ").trim();
  return line || fallback;
};

const formatEntryMap = (entry: Record<string, unknown>, fallback: string): string => {
  const msg = safeString(entry.msg ?? entry.message);
  return msg || formatEntryFolded(entry, fallback);
};

const formatEntryExpanded = (entry: Record<string, unknown>): string => {
  try {
    return JSON.stringify(entry, null, 2);
  } catch {
    return JSON.stringify(entry);
  }
};

export const formatDmsLogEntry = (entry: DmsLogEntry, view: DmsLogView): string => {
  if (!entry.parsed) return entry.raw;
  switch (view) {
    case "raw":
      return entry.raw;
    case "folded":
      return formatEntryFolded(entry.parsed, entry.raw);
    case "map":
      return formatEntryMap(entry.parsed, entry.raw);
    case "expanded":
      return formatEntryExpanded(entry.parsed);
    case "compact":
    default:
      return formatEntryCompact(entry.parsed, entry.raw);
  }
};

export const formatDmsLogEntryExpanded = (entry: DmsLogEntry): string => {
  if (!entry.parsed) return entry.raw;
  return formatEntryExpanded(entry.parsed);
};
