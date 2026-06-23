import type { DateRange } from "./api";

export const defaultTimeZone = "UTC";

const defaultDaysBack = 30;
const datePattern = /^\d{4}-\d{2}-\d{2}$/;
const dateTimePattern = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;

export type Preset = "today" | "48h" | "7" | "30" | "60" | "90" | "mtd" | "previous-month";

function datePartsInTimeZone(date: Date, timeZone: string) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    hourCycle: "h23",
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return {
    year: values.year,
    month: values.month,
    day: values.day,
    hour: values.hour === "24" ? "00" : values.hour,
    minute: values.minute,
  };
}

export function dateTimeLocalInTimeZone(date: Date, timeZone = defaultTimeZone) {
  const parts = datePartsInTimeZone(date, timeZone);
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}

export function todayInTimeZone(timeZone = defaultTimeZone) {
  const parts = datePartsInTimeZone(new Date(), timeZone);
  return `${parts.year}-${parts.month}-${parts.day}`;
}

export function addCalendarDays(day: string, days: number) {
  const [year, month, date] = day.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, date + days)).toISOString().slice(0, 10);
}

function monthStart(day: string) {
  return `${day.slice(0, 8)}01`;
}

function startOfDay(day: string) {
  return `${day}T00:00`;
}

function normalizeDateTime(value: string | null, fallback: string, timeZone = defaultTimeZone) {
  if (!value) return fallback;
  if (dateTimePattern.test(value.slice(0, 16))) return value.slice(0, 16);
  if (datePattern.test(value)) return startOfDay(value);
  const parsed = new Date(value);
  if (!Number.isNaN(parsed.getTime())) return dateTimeLocalInTimeZone(parsed, timeZone);
  return value;
}

export function defaultRange(timeZone = defaultTimeZone): DateRange {
  const today = todayInTimeZone(timeZone);
  return {
    start_at: startOfDay(addCalendarDays(today, -defaultDaysBack)),
    end_at: startOfDay(addCalendarDays(today, 1)),
  };
}

export function presetRange(preset: Preset, timeZone = defaultTimeZone): DateRange {
  const now = new Date();
  const today = todayInTimeZone(timeZone);
  if (preset === "today") {
    return { start_at: startOfDay(today), end_at: startOfDay(addCalendarDays(today, 1)) };
  }
  if (preset === "48h") {
    return {
      start_at: dateTimeLocalInTimeZone(new Date(now.getTime() - 48 * 60 * 60 * 1000), timeZone),
      end_at: dateTimeLocalInTimeZone(now, timeZone),
    };
  }
  if (/^\d+$/.test(preset)) {
    return { start_at: startOfDay(addCalendarDays(today, -Number(preset))), end_at: startOfDay(addCalendarDays(today, 1)) };
  }
  if (preset === "mtd") {
    return { start_at: startOfDay(monthStart(today)), end_at: startOfDay(addCalendarDays(today, 1)) };
  }
  const firstThisMonth = monthStart(today);
  const lastPreviousMonth = addCalendarDays(firstThisMonth, -1);
  return { start_at: startOfDay(monthStart(lastPreviousMonth)), end_at: startOfDay(firstThisMonth) };
}

export function rangeFromUrl(timeZone = defaultTimeZone): DateRange {
  const params = new URLSearchParams(window.location.search);
  const fallback = defaultRange(timeZone);
  const startAt = params.get("start_at");
  const endAt = params.get("end_at");
  if (startAt || endAt) {
    return {
      start_at: normalizeDateTime(startAt, fallback.start_at, timeZone),
      end_at: normalizeDateTime(endAt, fallback.end_at, timeZone),
    };
  }
  const from = params.get("date_from");
  const to = params.get("date_to");
  if (from || to) {
    const startDay = from && datePattern.test(from) ? from : fallback.start_at.slice(0, 10);
    const endDay = to && datePattern.test(to) ? to : addCalendarDays(fallback.end_at.slice(0, 10), -1);
    return { start_at: startOfDay(startDay), end_at: startOfDay(addCalendarDays(endDay, 1)) };
  }
  return fallback;
}

export function rangeUrlMode() {
  const params = new URLSearchParams(window.location.search);
  if (params.get("start_at") || params.get("end_at")) return "datetime";
  if (params.get("date_from") || params.get("date_to")) return "date";
  return "default";
}

export function validateRange(range: DateRange) {
  if (!dateTimePattern.test(range.start_at) || !dateTimePattern.test(range.end_at)) {
    return "Enter valid start and end date times.";
  }
  if (range.start_at >= range.end_at) {
    return "Start date time must be before end date time.";
  }
  return "";
}

export function rangesEqual(left: DateRange, right: DateRange) {
  return left.start_at === right.start_at && left.end_at === right.end_at;
}

export function writeRangeToUrl(range: DateRange, replace = false) {
  const params = new URLSearchParams(window.location.search);
  params.set("start_at", range.start_at);
  params.set("end_at", range.end_at);
  params.delete("date_from");
  params.delete("date_to");
  const next = `${window.location.pathname}?${params.toString()}`;
  if (replace) {
    window.history.replaceState({}, "", next);
  } else {
    window.history.pushState({}, "", next);
  }
}

export function formatRangeBound(value: string) {
  return value.replace("T", " ");
}
