// Dates and times are always shown in the business's timezone, whatever the
// browser's timezone is.

export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export const LANGUAGES: Record<string, string> = {
  te: "Telugu",
  hi: "Hindi",
  en: "English",
  ta: "Tamil",
  kn: "Kannada",
};

export function languageName(code: string | null): string {
  if (!code) return "–";
  return LANGUAGES[code.split("-")[0]] ?? code;
}

/** Today's date (YYYY-MM-DD) in the given timezone. */
export function todayIn(timeZone: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(
    new Date(),
  );
}

/** YYYY-MM-DD plus n days. */
export function addDays(day: string, n: number): string {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
}

export function dayLabel(day: string): string {
  const [y, m, d] = day.split("-").map(Number);
  return new Intl.DateTimeFormat("en-IN", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" }).format(
    new Date(Date.UTC(y, m - 1, d)),
  );
}

export function time(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat("en-IN", { hour: "numeric", minute: "2-digit", timeZone }).format(new Date(iso));
}

export function dateTime(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
    timeZone,
  }).format(new Date(iso));
}

/** The YYYY-MM-DD part of an ISO timestamp, in the given timezone. */
export function dayOf(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(
    new Date(iso),
  );
}

export function ago(iso: string): string {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

export function duration(seconds: number | null): string {
  if (seconds == null) return "–";
  const m = Math.floor(seconds / 60);
  return m ? `${m}m ${seconds % 60}s` : `${seconds}s`;
}

export function rupees(value: number | null, digits = 2): string {
  if (value == null) return "–";
  return `₹${value.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

// Two-digit area codes of the big cities; other landlines keep their digits together.
const METRO_CODES = new Set(["11", "20", "22", "33", "40", "44", "79", "80"]);

/** +919876543210 -> +91 98765 43210; landline +914023456789 -> +91 40 2345 6789 */
export function phone(value: string | null): string {
  if (!value) return "–";
  const m = value.match(/^\+91(\d{10})$/);
  if (!m) return value;
  const n = m[1];
  if ("6789".includes(n[0])) return `+91 ${n.slice(0, 5)} ${n.slice(5)}`;
  if (METRO_CODES.has(n.slice(0, 2))) return `+91 ${n.slice(0, 2)} ${n.slice(2, 6)} ${n.slice(6)}`;
  return `+91 ${n}`;
}

/** "18:30:00" -> "18:30" */
export function hhmm(value: string): string {
  return value.slice(0, 5);
}
