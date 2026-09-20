"use client";

import dynamic from "next/dynamic";
import { useCallback, useState } from "react";

import { AdvisorPanel } from "@/components/AdvisorPanel";
import { AdvisorImpactSummary } from "@/components/AdvisorImpactSummary";
import { RunExplainPanel } from "@/components/RunExplainPanel";
import { RagAdvisorPanel } from "@/components/RagAdvisorPanel";
import { BeforeAfterChart } from "@/components/BeforeAfterChart";
import { BehaviorLegend } from "@/components/BehaviorLegend";
import { CitizenInspector } from "@/components/CitizenInspector";
import { Disclosures } from "@/components/Disclosures";
import { MetricGrid } from "@/components/MetricGrid";
import { ProblemAreas } from "@/components/ProblemAreas";
import { RunStatus } from "@/components/RunStatus";
import { ScenarioControls } from "@/components/ScenarioControls";
import { SiteHeader } from "@/components/SiteHeader";
import { Card, CardHeader } from "@/components/ui/Card";
import { Pill } from "@/components/ui/Pill";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import type { Bootstrap } from "@/lib/server/bootstrap";
import { useRunner } from "@/lib/use-runner";
import type { RunState, RunSummary, ScenarioInput } from "@/lib/types";

/**
 * The viewport is client-only: WebRTC and media APIs do not exist during server
 * rendering, and the adapter must never run on the server.
 */
const OmniverseViewer = dynamic(
  () => import("@/components/OmniverseViewer").then((m) => m.OmniverseViewer),
  {
    ssr: false,
    loading: () => (
      <div className="min-h-[260px] sm:min-h-[300px] lg:min-h-[340px] rounded-[18px] border border-hairline bg-surface shadow-[var(--shadow-card)]">
        <div className="shimmer size-full min-h-[260px] sm:min-h-[300px] lg:min-h-[340px] rounded-[18px]" />
      </div>
    ),
  },
);

export function Dashboard({ bootstrap }: { bootstrap: Bootstrap }) {
  const { health, scenarios, streamConfig } = bootstrap;

  const [run, setRun] = useState<RunSummary | null>(bootstrap.run);
  const [state, setState] = useState<RunState>("before");
  const [scenario, setScenario] = useState<ScenarioInput>(
    bootstrap.run?.scenario ??
      scenarios.presets[scenarios.presets.length - 1] ?? {
        temperature: 26,
        humidity: 40,
        rainfall: 5,
        population: 30000,
      },
  );
  const [applyInterventions, setApplyInterventions] = useState(true);

  const onComplete = useCallback((summary: RunSummary) => setRun(summary), []);
  const runner = useRunner(onComplete);

  const hasAfter = Boolean(run?.after);
  // Derived rather than corrected in an effect: a run without an intervention
  // arm can only ever show "before".
  const shown: RunState = hasAfter ? state : "before";

  const arm = shown === "after" && run?.after ? run.after : run?.before;
  const other = shown === "after" ? run?.before : run?.after;

  const submit = useCallback(
    (options?: {
      forceApply?: boolean;
      debugFail?: boolean;
      selectedRecommendationIds?: import("@/lib/types").RecommendationId[];
    }) => {
      const apply = options?.forceApply ?? applyInterventions;
      if (options?.forceApply) setApplyInterventions(true);
      void runner.start({
        ...scenario,
        apply_recommended_interventions: apply,
        selected_recommendation_ids: options?.selectedRecommendationIds,
        animation_frames: 12,
        animation_duration_seconds: 12,
        debug_force: options?.debugFail ? "failed" : undefined,
      });
    },
    [applyInterventions, runner, scenario],
  );

  return (
    <div className="min-h-dvh">
      <SiteHeader health={health} />

      <main className="mx-auto max-w-[1560px] px-5 py-6 sm:px-8 sm:py-8">
        {bootstrap.upstreamError ? (
          <Card className="mb-6 border-[color:var(--negative)]/40 bg-negative-soft">
            <CardHeader
              eyebrow="Backend"
              title="The configured backend is unreachable"
              description={bootstrap.upstreamError}
            />
            <p className="mt-3 text-[12px] leading-relaxed text-ink-2">
              No results are shown, because showing recorded numbers here would
              misrepresent them as live output.
            </p>
          </Card>
        ) : null}

        <div className="grid gap-5 lg:grid-cols-3 xl:gap-6">
          <div className="flex flex-col gap-5 lg:col-span-2 xl:gap-6">
            <OmniverseViewer
              runId={run?.run_id ?? null}
              config={streamConfig}
              state={shown}
              onStateChange={setState}
              hasAfter={hasAfter}
              className="rise"
            />

            {run && arm ? (
              <Card>
                <CardHeader
                  eyebrow="Human impact"
                  title="Headline metrics"
                  description="Population-weighted results for the state shown in the viewport."
                  actions={
                    <SegmentedControl<RunState>
                      ariaLabel="Metric state"
                      size="sm"
                      value={shown}
                      onChange={setState}
                      segments={[
                        { value: "before", label: "Before" },
                        {
                          value: "after",
                          label: "After",
                          disabled: !hasAfter,
                          title: hasAfter
                            ? undefined
                            : "This run has no intervention arm.",
                        },
                      ]}
                    />
                  }
                />
                <MetricGrid
                  className="mt-5 lg:grid-cols-4"
                  metrics={arm.metrics}
                  comparison={other?.metrics}
                  state={shown}
                />
                {run.control_reference ? (
                  <p className="mt-4 text-[11px] leading-relaxed text-ink-3">
                    Calm-day control from the same report (
                    {run.control_reference.scenario.temperature} &deg;C,{" "}
                    {run.control_reference.scenario.rainfall} mm): Human Experience
                    Index{" "}
                    <span className="tabular font-semibold text-ink-2">
                      {run.control_reference.metrics.human_experience_index.toFixed(1)}
                    </span>
                    , advisor said{" "}
                    {run.control_reference.recommendations
                      .join(", ")
                      .replaceAll("_", " ")}
                    .
                  </p>
                ) : null}
              </Card>
            ) : null}
          </div>

          <div className="flex flex-col gap-5 xl:gap-6">
            <ScenarioControls
              catalog={scenarios}
              scenario={scenario}
              onScenarioChange={setScenario}
              applyInterventions={applyInterventions}
              onApplyInterventionsChange={setApplyInterventions}
              onRun={() => submit()}
              onCancel={() => void runner.cancel()}
              busy={runner.active}
              fieldErrors={runner.state.fieldErrors}
              formError={
                runner.state.status === "failed" ? null : runner.state.error
              }
            />
          </div>
        </div>

        <div className="mt-5 xl:mt-6">
          <RunStatus
            run={run}
            attempt={{
              status: runner.state.status,
              runId: runner.state.runId,
              progress: runner.state.progress,
              error: runner.state.status === "failed" ? runner.state.error : null,
            }}
          />
        </div>

        {run && run.before ? (
          <>
            <div className="mt-5 grid gap-5 xl:mt-6 xl:gap-6">
              <BeforeAfterChart
                before={run.before.metrics}
                after={run.after?.metrics}
                interventionLabel={interventionLabel(run)}
              />
              {run.after && Object.keys(run.intervention ?? {}).length > 0 ? (
                <AdvisorImpactSummary
                  before={run.before.metrics}
                  after={run.after.metrics}
                  intervention={run.intervention ?? {}}
                />
              ) : null}
              <BehaviorLegend
                before={run.before.behavior_counts}
                after={run.after?.behavior_counts}
              />
              {arm ? <ProblemAreas summary={arm} state={shown} /> : null}
              {health.mode === "live" && run.status === "complete" ? (
                <>
                  <RagAdvisorPanel
                    key={`rag-${run.run_id}`}
                    runId={run.run_id}
                    busy={runner.active}
                    onApplySelected={(selectedRecommendationIds) =>
                      submit({ forceApply: true, selectedRecommendationIds })
                    }
                  />
                  <RunExplainPanel runId={run.run_id} />
                </>
              ) : null}
              {run.advisor ? (
                <details className="rounded-[18px] border border-hairline bg-surface-1 p-4">
                  <summary className="cursor-pointer text-[13px] font-semibold text-ink-2">
                    Simulator calculation details
                  </summary>
                  <p className="mt-2 text-[11px] leading-relaxed text-ink-3">
                    These deterministic rules convert selected AI actions into executable simulator parameters and identify affected locations.
                  </p>
                  <div className="mt-4">
                    <AdvisorPanel
                      advisor={run.advisor}
                      source={run.advisor_source}
                      applied={run.intervention}
                      canApply={!runner.active}
                      onApplyRecommended={() => submit({ forceApply: true })}
                    />
                  </div>
                </details>
              ) : null}
            </div>

            <div className="mt-5 grid gap-5 xl:mt-6 xl:gap-6">
              <CitizenInspector
                key={`${run.run_id}-${shown}`}
                runId={run.run_id}
                state={shown}
                hasAfter={hasAfter}
              />
            </div>
          </>
        ) : null}

        {!run && !bootstrap.upstreamError ? (
          <Card className="mt-6">
            <CardHeader
              eyebrow="No results"
              title="No run is loaded"
              description="Choose a scenario and run a simulation to populate the dashboard."
            />
          </Card>
        ) : null}

        <div className="mt-5 xl:mt-6">
          <Disclosures
            health={health}
            city={run?.city}
            stage={run?.artifacts?.omniverse_stage}
          />
        </div>

        {health.mode === "mock" ? (
          <StateTester
            busy={runner.active}
            onFail={() => submit({ debugFail: true })}
            onCancelMidRun={() => {
              submit();
              setTimeout(() => void runner.cancel(), 900);
            }}
          />
        ) : null}
      </main>
    </div>
  );
}

function interventionLabel(run: RunSummary): string | null {
  const entries = Object.entries(run.intervention ?? {});
  if (entries.length === 0) return null;
  return `Intervention: ${entries
    .map(([key, value]) => `${key.replaceAll("_", " ")} +${Math.round(value * 100)}%`)
    .join(", ")}.`;
}

/**
 * Developer control for the states that cannot occur against recorded fixtures.
 * Shown only in mock mode and labelled as an injection, never as a real failure.
 */
function StateTester({
  busy,
  onFail,
  onCancelMidRun,
}: {
  busy: boolean;
  onFail: () => void;
  onCancelMidRun: () => void;
}) {
  return (
    <div className="mt-5 flex flex-wrap items-center gap-3 rounded-[14px] border border-dashed border-hairline px-4 py-3 xl:mt-6">
      <Pill tone="neutral">Mock mode only</Pill>
      <p className="text-[11px] text-ink-3">
        Inject terminal run states to check the UI handles them. Nothing is
        simulated and no failure is real.
      </p>
      <div className="ml-auto flex gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={onFail}
          className="rounded-full border border-hairline px-3 py-1 text-[11px] font-semibold text-ink-2 transition-colors hover:text-ink disabled:opacity-40"
        >
          Inject failed run
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={onCancelMidRun}
          className="rounded-full border border-hairline px-3 py-1 text-[11px] font-semibold text-ink-2 transition-colors hover:text-ink disabled:opacity-40"
        >
          Cancel mid-run
        </button>
      </div>
    </div>
  );
}
