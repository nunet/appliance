/**
 * Combine a local date string (YYYY-MM-DD) and a time string (HH:mm)
 * into a UTC ISO string suitable for backend queries.
 * If timeStr is empty or undefined, defaults to "23:59".
 */
export function combineLocalDateAndTimeToUtcIso(dateStr: string, timeStr?: string): string {
  if (!dateStr) {
    throw new Error("dateStr is required");
  }
  const [yearStr, monthStr, dayStr] = dateStr.split("-");
  const year = Number(yearStr);
  const month = Number(monthStr); // 1-based
  const day = Number(dayStr);

  const effectiveTime = timeStr && timeStr.trim() ? timeStr : "23:59";
  const [hhStr, mmStr] = effectiveTime.split(":");
  const hours = Number(hhStr || 0);
  const minutes = Number(mmStr || 0);

  // Construct local time Date (month is 0-based in JS Date)
  const local = new Date(year, month - 1, day, hours, minutes, 0, 0);

  // Return UTC ISO format
  return local.toISOString();
}
