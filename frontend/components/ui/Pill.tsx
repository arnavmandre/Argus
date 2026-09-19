import type { ReactNode } from "react";

import { cx } from "@/lib/cx";

export type PillTone = "neutral" | "accent" | "positive" | "negative" | "caution";

const TONES: Record<PillTone, string> = {
  neutral: "bg-neutral-soft text-ink-2",
  accent: "bg-accent-soft text-accent",
  positive: "bg-positive-soft text-positive",
  negative: "bg-negative-soft text-negative",
  caution: "bg-caution-soft text-caution",
};

export function Pill({
  tone = "neutral",
  children,
  className,
  title,
}: {
  tone?: PillTone;
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold tracking-[-0.005em]",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Dot({ color, className }: { color: string; className?: string }) {
  return (
    <span
      aria-hidden
      className={cx("inline-block size-2 shrink-0 rounded-full", className)}
      style={{ background: color }}
    />
  );
}
