import { CheckCircle2, Loader2, TriangleAlert } from "lucide-react";

type StatusPillProps = {
  tone?: "ok" | "warn" | "loading";
  children: React.ReactNode;
};

export function StatusPill({ tone = "ok", children }: StatusPillProps) {
  const classes = {
    ok: "border-brand/30 bg-brand/10 text-brand",
    warn: "border-danger/30 bg-danger/10 text-danger",
    loading: "border-accent/30 bg-accent/10 text-accent",
  };
  const Icon = tone === "loading" ? Loader2 : tone === "warn" ? TriangleAlert : CheckCircle2;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold ${classes[tone]}`}>
      <Icon className={`h-3.5 w-3.5 ${tone === "loading" ? "animate-spin" : ""}`} aria-hidden="true" />
      {children}
    </span>
  );
}
