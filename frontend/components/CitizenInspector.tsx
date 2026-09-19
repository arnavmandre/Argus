"use client";

import { useEffect, useState } from "react";

import { Card, CardHeader } from "@/components/ui/Card";
import { Dot, Pill } from "@/components/ui/Pill";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { api, ApiError } from "@/lib/api";
import { BEHAVIOR_META } from "@/lib/behaviors";
import { formatCount } from "@/lib/metric-format";
import type { CitizenPage, RunState } from "@/lib/types";

const PAGE_SIZE = 25;

/**
 * Optional citizen inspection.
 *
 * Fetched only when opened and only one page at a time: the run holds 1,000
 * citizens and the handoff forbids pulling them all into the page.
 */
export function CitizenInspector({
  runId,
  state,
  hasAfter,
}: {
  runId: string;
  state: RunState;
  hasAfter: boolean;
}) {
  const [open, setOpen] = useState(false);
  // Seeded from the dashboard's state; remounted by the parent when that
  // changes, so no effect is needed to keep the two in step.
  const [arm, setArm] = useState<RunState>(state);
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<CitizenPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Loading is derived from "which page has arrived" rather than tracked, so
  // nothing has to be set synchronously inside the fetch effect.
  const wanted = `${runId}|${arm}|${offset}`;
  const [loaded, setLoaded] = useState<string | null>(null);
  const loading = open && loaded !== wanted && error === null;

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    api
      .citizens(runId, arm, PAGE_SIZE, offset)
      .then((result) => {
        if (cancelled) return;
        setPage(result);
        setError(null);
        setLoaded(wanted);
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setError(
          caught instanceof ApiError
            ? caught.message
            : "The citizen page could not be loaded.",
        );
        setLoaded(wanted);
      });
    return () => {
      cancelled = true;
    };
  }, [open, runId, arm, offset, wanted]);

  const changeArm = (next: RunState) => {
    setArm(next);
    setOffset(0);
  };

  return (
    <Card>
      <CardHeader
        eyebrow="Population"
        title="Citizen inspection"
        description="Survey-calibrated synthetic citizens, loaded a page at a time."
        actions={
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="rounded-full border border-hairline px-3 py-1.5 text-[12px] font-semibold text-ink-2 transition-colors hover:text-ink"
          >
            {open ? "Hide" : "Inspect citizens"}
          </button>
        }
      />

      {open ? (
        <>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <SegmentedControl<RunState>
              ariaLabel="Citizen state"
              size="sm"
              value={arm}
              onChange={changeArm}
              segments={[
                { value: "before", label: "Before" },
                {
                  value: "after",
                  label: "After",
                  disabled: !hasAfter,
                  title: hasAfter ? undefined : "This run has no intervention arm.",
                },
              ]}
            />
            {page ? (
              <p className="tabular text-[11px] text-ink-3">
                Showing {formatCount(page.offset + 1)}&ndash;
                {formatCount(Math.min(page.offset + page.limit, page.total))} of{" "}
                {formatCount(page.total)} available &middot;{" "}
                {formatCount(page.total_in_run)} simulated
              </p>
            ) : null}
          </div>

          {error ? (
            <p role="alert" className="mt-4 text-[12px] text-negative">
              {error}
            </p>
          ) : null}

          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse">
              <thead>
                <tr className="border-b border-hairline">
                  <Th>Citizen</Th>
                  <Th>Archetype</Th>
                  <Th>Behaviour</Th>
                  <Th align="right">Travel</Th>
                  <Th align="right">Comfort</Th>
                  <Th align="right">Stress</Th>
                </tr>
              </thead>
              <tbody className={loading ? "opacity-50" : undefined}>
                {(page?.items ?? []).map((citizen) => {
                  const meta = BEHAVIOR_META[citizen.behavior];
                  return (
                    <tr key={citizen.id} className="border-b border-hairline last:border-0">
                      <td className="py-2 pr-3">
                        <span className="font-mono text-[12px] text-ink">{citizen.id}</span>
                        <span className="ml-2 font-mono text-[11px] text-ink-4">
                          {citizen.route}
                        </span>
                      </td>
                      <td className="py-2 pr-3 text-[12px] text-ink-2">
                        {citizen.archetype}
                      </td>
                      <td className="py-2 pr-3">
                        <span className="flex items-center gap-1.5 text-[12px] text-ink-2">
                          <Dot color={meta.hex} />
                          {meta.label}
                        </span>
                      </td>
                      <td className="tabular py-2 pr-3 text-right text-[12px] text-ink-2">
                        {citizen.travel_minutes.toFixed(2)} min
                      </td>
                      <td className="tabular py-2 pr-3 text-right text-[12px] text-ink-2">
                        {citizen.comfort.toFixed(1)}
                      </td>
                      <td className="tabular py-2 text-right text-[12px] text-ink-2">
                        {citizen.stress.toFixed(1)}
                      </td>
                    </tr>
                  );
                })}
                {!page && loading
                  ? Array.from({ length: 6 }).map((_, index) => (
                      <tr key={index}>
                        <td colSpan={6} className="py-2">
                          <div className="shimmer h-5 w-full rounded-md" />
                        </td>
                      </tr>
                    ))
                  : null}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex items-center justify-between gap-3">
            <button
              type="button"
              disabled={offset === 0 || loading}
              onClick={() => setOffset((v) => Math.max(0, v - PAGE_SIZE))}
              className="rounded-full border border-hairline px-3 py-1.5 text-[12px] font-semibold text-ink-2 transition-colors hover:text-ink disabled:opacity-40"
            >
              Previous
            </button>
            <div className="flex flex-wrap gap-2">
              {(page?.notes ?? []).map((note) => (
                <Pill key={note} tone="neutral">
                  {note}
                </Pill>
              ))}
            </div>
            <button
              type="button"
              disabled={!page || offset + PAGE_SIZE >= page.total || loading}
              onClick={() => setOffset((v) => v + PAGE_SIZE)}
              className="rounded-full border border-hairline px-3 py-1.5 text-[12px] font-semibold text-ink-2 transition-colors hover:text-ink disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </>
      ) : null}
    </Card>
  );
}

function Th({
  children,
  align = "left",
}: {
  children: React.ReactNode;
  align?: "left" | "right";
}) {
  return (
    <th
      scope="col"
      className={`pb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-3 ${
        align === "right" ? "text-right" : "text-left"
      }`}
    >
      {children}
    </th>
  );
}
