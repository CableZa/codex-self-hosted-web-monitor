import type { Dispatch, SetStateAction } from "react";
import type { DateRange } from "../lib/apiTypes";
import { defaultRange, presetRange, type Preset } from "../lib/dateRange";

const presets: Array<{ id: Preset; label: string }> = [
  { id: "today", label: "Today" },
  { id: "48h", label: "Last 48 hours" },
  { id: "7", label: "Last 7" },
  { id: "30", label: "Last 30" },
  { id: "60", label: "Last 60" },
  { id: "90", label: "Last 90" },
  { id: "mtd", label: "Month to date" },
  { id: "previous-month", label: "Previous month" },
];

export function UsageWindowControls({
  applyRange,
  draftRange,
  rangeError,
  setDraftRange,
  timezone,
}: {
  applyRange: (range: DateRange, options?: { preset?: Preset }) => void;
  draftRange: DateRange;
  rangeError: string;
  setDraftRange: Dispatch<SetStateAction<DateRange>>;
  timezone: string;
}) {
  function setRangePart(bound: keyof DateRange, value: string) {
    setDraftRange((current) => ({ ...current, [bound]: value.slice(0, 16) }));
  }

  return (
    <>
      <div className="flex flex-wrap gap-2">
        {presets.map((preset) => (
          <button
            key={preset.id}
            type="button"
            className="rounded-md border border-border bg-canvas px-3 py-2 text-sm font-semibold hover:border-brand hover:text-brand"
            onClick={() => applyRange(presetRange(preset.id, timezone), { preset: preset.id })}
          >
            {preset.label}
          </button>
        ))}
      </div>
      <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
        <label className="grid gap-1 text-sm text-muted">
          Start
          <input
            className="min-w-0 rounded-md border border-border bg-canvas px-3 py-2 text-ink"
            type="datetime-local"
            value={draftRange.start_at.slice(0, 16)}
            onChange={(event) => setRangePart("start_at", event.target.value)}
          />
        </label>
        <label className="grid gap-1 text-sm text-muted">
          End
          <input
            className="min-w-0 rounded-md border border-border bg-canvas px-3 py-2 text-ink"
            type="datetime-local"
            value={draftRange.end_at.slice(0, 16)}
            onChange={(event) => setRangePart("end_at", event.target.value)}
          />
        </label>
        <button
          className="self-end rounded-md border border-border bg-panel px-4 py-2 font-semibold"
          onClick={() => applyRange(defaultRange(timezone))}
          type="button"
        >
          Reset
        </button>
      </div>
      {rangeError ? <div className="text-sm text-danger">{rangeError}</div> : null}
    </>
  );
}
