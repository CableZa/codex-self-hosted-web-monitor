import { useEffect, useId, useRef, useState } from "react";
import { HelpCircle } from "lucide-react";

export function GlossaryNote({
  label,
  note,
}: {
  label: string;
  note: string;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const wrapperRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent && event.key !== "Escape") return;
      if (event instanceof MouseEvent && wrapperRef.current?.contains(event.target as Node)) return;
      setOpen(false);
    };
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", close);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", close);
    };
  }, [open]);

  return (
    <span ref={wrapperRef} className="relative inline-flex shrink-0">
      <button
        type="button"
        className="inline-flex h-6 w-6 items-center justify-center rounded-md border border-border bg-panel text-muted hover:border-brand hover:text-brand"
        aria-controls={id}
        aria-expanded={open}
        aria-label={`Explain ${label}`}
        onClick={() => setOpen((value) => !value)}
      >
        <HelpCircle className="h-3.5 w-3.5" />
      </button>
      {open ? (
        <span
          id={id}
          role="tooltip"
          className="fixed left-3 right-3 top-auto z-30 mt-2 max-w-[calc(100vw-1.5rem)] rounded-md border border-border bg-panel p-3 text-left text-sm font-normal leading-5 text-muted shadow-xl sm:absolute sm:left-auto sm:right-0 sm:top-8 sm:mt-0 sm:w-72"
        >
          <span className="block font-semibold text-ink">{label}</span>
          <span className="mt-1 block">{note}</span>
        </span>
      ) : null}
    </span>
  );
}
