"use client";

import { cx } from "@/lib/cx";

export interface Segment<T extends string> {
  value: T;
  label: string;
  disabled?: boolean;
  title?: string;
}

export function SegmentedControl<T extends string>({
  segments,
  value,
  onChange,
  size = "md",
  ariaLabel,
  className,
}: {
  segments: Segment<T>[];
  value: T;
  onChange: (value: T) => void;
  size?: "sm" | "md";
  ariaLabel: string;
  className?: string;
}) {
  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={cx(
        "inline-flex rounded-[10px] border border-hairline bg-surface-2 p-[3px]",
        className,
      )}
    >
      {segments.map((segment) => {
        const active = segment.value === value;
        return (
          <button
            key={segment.value}
            role="tab"
            type="button"
            aria-selected={active}
            disabled={segment.disabled}
            title={segment.title}
            onClick={() => onChange(segment.value)}
            className={cx(
              "rounded-[8px] font-medium transition-all duration-200 [transition-timing-function:var(--ease)]",
              size === "sm" ? "px-2.5 py-1 text-[12px]" : "px-3.5 py-1.5 text-[13px]",
              active
                ? "bg-surface text-ink shadow-[0_1px_2px_rgba(0,0,0,0.12)]"
                : "text-ink-2 hover:text-ink",
              segment.disabled && "cursor-not-allowed opacity-40",
            )}
          >
            {segment.label}
          </button>
        );
      })}
    </div>
  );
}
