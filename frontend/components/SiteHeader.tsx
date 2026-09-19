"use client";

import { useState } from "react";

import { Dot, Pill } from "@/components/ui/Pill";
import type { Health } from "@/lib/types";

/**
 * The header carries the single most important claim on the page: whether
 * anything here is live. It reads only `/api/health`, never a build flag.
 */
export function SiteHeader({ health }: { health: Health }) {
  const [open, setOpen] = useState(false);

  const live = health.mode === "live" && health.capabilities.live_simulation;
  const tone = live ? "positive" : health.status === "offline" ? "negative" : "caution";
  const label =
    health.status === "offline"
      ? "Backend unreachable"
      : live
        ? "Live backend"
        : "Recorded data";

  return (
    <header className="sticky top-0 z-40 border-b border-hairline glass">
      <div className="mx-auto flex max-w-[1560px] flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3 sm:px-8">
        <div className="flex min-w-0 items-center gap-3">
          <Mark />
          <div className="min-w-0">
            <p className="truncate text-[15px] font-semibold tracking-[-0.02em] text-ink">
              UrbanTwin AI
            </p>
            <p className="truncate text-[12px] text-ink-3">
              Simulate the human experience before building the city
            </p>
          </div>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <Pill tone={tone}>
            <Dot
              color={
                live
                  ? "var(--positive)"
                  : health.status === "offline"
                    ? "var(--negative)"
                    : "var(--caution)"
              }
            />
            {label}
          </Pill>
          <Pill tone={health.omniverse_stream === "online" ? "positive" : "neutral"}>
            Omniverse stream {health.omniverse_stream}
          </Pill>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className="rounded-full border border-hairline px-3 py-1 text-[11px] font-semibold text-ink-2 transition-colors hover:text-ink"
          >
            {open ? "Hide status" : "What is live?"}
          </button>
        </div>
      </div>

      {open ? (
        <div className="border-t border-hairline bg-surface">
          <div className="mx-auto max-w-[1560px] px-5 py-4 sm:px-8">
            <div className="grid gap-x-8 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-3">
                  Capabilities
                </p>
                <ul className="space-y-1.5">
                  {Object.entries(health.capabilities).map(([key, value]) => (
                    <li key={key} className="flex items-center gap-2 text-[12px] text-ink-2">
                      <Dot color={value ? "var(--positive)" : "var(--ink-4)"} />
                      <span className="capitalize">{key.replaceAll("_", " ")}</span>
                      <span className="ml-auto tabular text-ink-3">
                        {value ? "available" : "not built"}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="sm:col-span-1 lg:col-span-2">
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-3">
                  Reported by /api/health
                </p>
                <ul className="space-y-1.5">
                  {health.notes.map((note) => (
                    <li key={note} className="text-[12px] leading-relaxed text-ink-2">
                      {note}
                    </li>
                  ))}
                </ul>
                <p className="mt-3 text-[11px] text-ink-3">
                  Checked {new Date(health.checked_utc).toLocaleString()}
                </p>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </header>
  );
}

function Mark() {
  return (
    <span
      aria-hidden
      className="grid size-8 shrink-0 place-items-center rounded-[9px] bg-accent text-accent-ink"
    >
      <svg viewBox="0 0 24 24" className="size-[18px]" fill="none" strokeWidth="1.8">
        <path
          d="M4 20V9.5L12 4l8 5.5V20"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path d="M9.5 20v-5.5h5V20" stroke="currentColor" strokeLinecap="round" />
      </svg>
    </span>
  );
}
