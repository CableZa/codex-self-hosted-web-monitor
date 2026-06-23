import type { KeyboardEvent } from "react";
import { Minus, Plus } from "lucide-react";
import { normalizeCreditInteger } from "../lib/creditInteger";

export function CreditIntegerInput({
  label,
  value,
  onChange,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const numericValue = Number(value || 0);
  const canDecrement = !disabled && numericValue > 1;

  function updateFromInput(next: string) {
    onChange(next.replace(/\D/g, ""));
  }

  function step(amount: number) {
    const current = Number(value || 0);
    onChange(String(Math.max(1, current + amount)));
  }

  function blockNonDigits(event: KeyboardEvent<HTMLInputElement>) {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.key.length === 1 && !/\d/.test(event.key)) {
      event.preventDefault();
    }
  }

  return (
    <label className="grid gap-1.5 text-sm text-muted">
      {label}
      <span className="grid grid-cols-[2.5rem_minmax(0,1fr)_2.5rem] overflow-hidden rounded-md border border-border bg-canvas text-ink focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-brand">
        <button
          type="button"
          className="flex h-10 items-center justify-center border-r border-border text-muted disabled:opacity-40"
          disabled={!canDecrement}
          aria-label={`Decrease ${label}`}
          onClick={() => step(-1)}
        >
          <Minus className="h-4 w-4" />
        </button>
        <input
          className="h-10 min-w-0 border-0 bg-transparent px-3 py-2 text-right text-ink outline-none"
          inputMode="numeric"
          min={1}
          pattern="[0-9]*"
          step={1}
          type="text"
          value={value}
          disabled={disabled}
          onChange={(event) => updateFromInput(event.target.value)}
          onKeyDown={blockNonDigits}
          onBlur={() => onChange(normalizeCreditInteger(value))}
        />
        <button
          type="button"
          className="flex h-10 items-center justify-center border-l border-border text-muted disabled:opacity-40"
          aria-label={`Increase ${label}`}
          disabled={disabled}
          onClick={() => step(1)}
        >
          <Plus className="h-4 w-4" />
        </button>
      </span>
    </label>
  );
}
