import { motion } from "framer-motion";
import type { ReactNode } from "react";

type PanelProps = {
  title?: string;
  meta?: ReactNode;
  children: ReactNode;
  className?: string;
};

export function Panel({ title, meta, children, className = "" }: PanelProps) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22 }}
      className={`rounded-md border border-border bg-panel/95 p-3 shadow-soft sm:p-4 ${className}`}
    >
      {(title || meta) && (
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3 border-b border-border/60 pb-3">
          {title ? <h2 className="min-w-0 break-words text-sm font-bold uppercase tracking-normal text-ink">{title}</h2> : <span />}
          {meta ? <div className="min-w-0 text-sm text-muted">{meta}</div> : null}
        </div>
      )}
      {children}
    </motion.section>
  );
}
