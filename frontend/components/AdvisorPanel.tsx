"use client";

import { Card, CardHeader } from "@/components/ui/Card";
import { Pill } from "@/components/ui/Pill";
import type {
  AdvisorResult,
  AdvisorSource,
  InterventionParameters,
} from "@/lib/types";

const RECOMMENDATION_LABEL: Record<string, string> = {
  increase_shade: "Increase shade",
  improve_drainage: "Improve drainage",
  alternative_pedestrian_routes: "Open alternative pedestrian routes",
  no_major_intervention: "No major intervention needed",
};

const PARAMETER_LABEL: Record<string, string> = {
  shade_boost: "Shade boost",
  drainage_boost: "Drainage boost",
  route_capacity_boost: "Route capacity boost",
};

/**
 * Advisor output.
 *
 * The working advisor is deterministic threshold logic, not an LLM, and the
 * panel says so in its own header rather than in a footnote. Every string here
 * comes from the simulator's `advisor` block.
 */
export function AdvisorPanel({
  advisor,
  source,
  applied,
  canApply,
  onApplyRecommended,
}: {
  advisor: AdvisorResult;
  source?: AdvisorSource;
  applied?: InterventionParameters;
  canApply: boolean;
  onApplyRecommended: () => void;
}) {
  const appliedEntries = Object.entries(applied ?? {}).filter(
    ([, value]) => typeof value === "number",
  );
  const noMajorIntervention = advisor.recommendations.includes(
    "no_major_intervention",
  );

  return (
    <Card>
      <CardHeader
        eyebrow="Decision support"
        title="Advisor recommendations"
        description={advisor.summary}
        actions={
          <Pill tone="neutral" title={source?.detail}>
            {source?.label ?? "Deterministic threshold advisor"}
          </Pill>
        }
      />

      {source ? (
        <p className="mt-3 text-[11px] leading-relaxed text-ink-3">{source.detail}</p>
      ) : null}

      {advisor.explanation.length > 0 ? (
        <ul className="mt-4 space-y-2">
          {advisor.explanation.map((line) => (
            <li key={line} className="flex gap-2 text-[13px] leading-relaxed text-ink-2">
              <span aria-hidden className="mt-[7px] size-1.5 shrink-0 rounded-full bg-accent" />
              <span>{line}</span>
            </li>
          ))}
        </ul>
      ) : null}

      <div className="mt-5 space-y-3">
        {advisor.recommendations.map((recommendation) => {
          const supported = advisor.supported_interventions[recommendation];
          const affected = advisor.affected_buildings[recommendation] ?? [];
          return (
            <div
              key={recommendation}
              className="rounded-[14px] border border-hairline bg-surface-2 p-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-[14px] font-semibold tracking-[-0.01em] text-ink">
                  {RECOMMENDATION_LABEL[recommendation] ?? recommendation}
                </p>
                {supported ? (
                  <div className="flex flex-wrap gap-1.5">
                    {Object.entries(supported.changes).map(([key, value]) => (
                      <Pill key={key} tone="accent">
                        {PARAMETER_LABEL[key] ?? key} +{Math.round(value * 100)}%
                      </Pill>
                    ))}
                  </div>
                ) : null}
              </div>

              {supported ? (
                <p className="mt-2 text-[12.5px] leading-relaxed text-ink-2">
                  {supported.effect}
                </p>
              ) : null}

              {affected.length > 0 ? (
                <p className="mt-2 text-[11px] text-ink-3">
                  Most affected:{" "}
                  <span className="font-mono text-ink-2">{affected.join(", ")}</span>
                </p>
              ) : null}
            </div>
          );
        })}
      </div>

      {appliedEntries.length > 0 ? (
        <div className="mt-4 rounded-[14px] border border-accent-line bg-accent-soft p-4">
          <p className="text-[12px] font-semibold text-accent">Applied in this run</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {appliedEntries.map(([key, value]) => (
              <Pill key={key} tone="accent">
                {PARAMETER_LABEL[key] ?? key} +{Math.round((value as number) * 100)}%
              </Pill>
            ))}
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-ink-2">
            The &ldquo;after&rdquo; arm is a full re-simulation with these parameters,
            not an adjustment applied to the before numbers.
          </p>
        </div>
      ) : noMajorIntervention ? (
        <div className="mt-4 rounded-[14px] border border-hairline bg-surface-2 p-4">
          <p className="text-[12px] font-semibold text-ink">Control scenario complete</p>
          <p className="mt-2 text-[11px] leading-relaxed text-ink-2">
            The calm scenario is the baseline. No intervention is applied, so the
            before and after values are expected to remain the same.
          </p>
        </div>
      ) : (
        <button
          type="button"
          onClick={onApplyRecommended}
          disabled={!canApply}
          className="mt-4 w-full rounded-[12px] bg-accent px-4 py-2.5 text-[13px] font-semibold text-accent-ink transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:bg-surface-3 disabled:text-ink-3"
        >
          Apply these interventions and re-simulate
        </button>
      )}

      <p className="mt-4 text-[11px] leading-relaxed text-ink-3">
        Decision-support suggestions from threshold rules over the simulator&rsquo;s own
        output. Effectiveness numbers come from re-running the simulation, not from
        the advisor.
      </p>
    </Card>
  );
}
