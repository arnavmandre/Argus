"use client";

import { Pill } from "@/components/ui/Pill";
import { cx } from "@/lib/cx";
import {
  HEADLINE_METRICS,
  METRIC_META,
  deltaPolarity,
  directionLabel,
  formatDelta,
  formatMetric,
  metricFraction,
} from "@/lib/metric-format";
import type { MetricKey, RunState, SimulationMetrics } from "@/lib/types";

/**
 * Headline metric tiles.
 *
 * A tile always states its direction, because the sign of a change means
 * nothing on its own: +22.8 safety is an improvement, +22.8 heat stress is not.
 */
export function MetricGrid({
  metrics,
  comparison,
  state,
  keys = HEADLINE_METRICS,
  className,
}: {
  metrics: SimulationMetrics;
  /** The other arm, when a before/after pair exists. */
  comparison?: SimulationMetrics;
  state: RunState;
  keys?: MetricKey[];
  className?: string;
}) {
  return (
    <div className={cx("grid gap-3 sm:grid-cols-2", className)}>
      {keys.map((key) => (
        <MetricTile
          key={key}
          metricKey={key}
          value={metrics[key]}
          compareValue={comparison?.[key]}
          state={state}
        />
      ))}
    </div>
  );
}

function MetricTile({
  metricKey,
  value,
  compareValue,
  state,
}: {
  metricKey: MetricKey;
  value: number;
  compareValue?: number;
  state: RunState;
}) {
  const meta = METRIC_META[metricKey];
  // "after" is always measured against "before", whichever arm is on screen.
  const delta =
    compareValue === undefined
      ? null
      : state === "after"
        ? value - compareValue
        : compareValue - value;
  const polarity = delta === null ? null : deltaPolarity(metricKey, delta);

  return (
    <div className="rounded-[14px] border border-hairline bg-surface-2 p-4">
      <div className="flex items-start justify-between gap-2">
        <p className="text-[12px] font-medium text-ink-2">{meta.label}</p>
        {delta !== null && polarity ? (
          <Pill
            tone={
              polarity === "improvement"
                ? "positive"
                : polarity === "regression"
                  ? "negative"
                  : "neutral"
            }
            title={
              state === "after"
                ? "Change from before to after the intervention"
                : "Change the intervention would make"
            }
          >
            {formatDelta(metricKey, delta)}
          </Pill>
        ) : null}
      </div>

      <p className="tabular mt-2 text-[30px] font-semibold leading-none tracking-[-0.03em] text-ink">
        {formatMetric(metricKey, value)}
        <span className="ml-1 text-[13px] font-medium text-ink-3">{meta.unit}</span>
      </p>

      <div className="mt-3 h-1 w-full overflow-hidden rounded-full bg-surface-3">
        <div
          className={cx(
            "h-full rounded-full transition-[width] duration-500 [transition-timing-function:var(--ease)]",
            meta.direction === "higher_is_better" ? "bg-accent" : "bg-caution",
          )}
          style={{ width: `${metricFraction(metricKey, value) * 100}%` }}
        />
      </div>

      <p className="mt-2 text-[11px] text-ink-3">{directionLabel(metricKey)}</p>
    </div>
  );
}
