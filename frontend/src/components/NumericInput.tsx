import type { KeyboardEvent } from "react";

type NumericInputProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  min?: number;
  step?: string;
};

export function NumericInput({ label, value, onChange, min = 0, step = "0.01" }: NumericInputProps) {
  function update(next: string) {
    const cleaned = next
      .replace(",", ".")
      .replace(/[^\d.]/g, "")
      .replace(/(\..*)\./g, "$1");
    onChange(cleaned);
  }

  function blockNonNumeric(event: KeyboardEvent<HTMLInputElement>) {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.key.length === 1 && !/[\d.]/.test(event.key)) {
      event.preventDefault();
    }
    if (event.key === "." && value.includes(".")) {
      event.preventDefault();
    }
  }

  return (
    <label className="grid gap-1.5 text-sm text-muted">
      {label}
      <input
        className="rounded-md border border-border bg-canvas px-3 py-2 text-ink"
        inputMode="decimal"
        min={min}
        step={step}
        type="number"
        value={value}
        onChange={(event) => update(event.target.value)}
        onKeyDown={blockNonNumeric}
      />
    </label>
  );
}
