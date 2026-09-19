"use client";

import { Card, CardHeader } from "@/components/ui/Card";
import { Pill, type PillTone } from "@/components/ui/Pill";
import type { ModelCard, ModelEntry, TrustVerdict } from "@/lib/types";

const VERDICT: Record<TrustVerdict, { label: string; tone: PillTone }> = {
  promising: { label: "Promising", tone: "positive" },
  supported_for_prototype: { label: "Supported for prototype", tone: "caution" },
  not_validated: { label: "Not validated", tone: "negative" },
};

const TARGET_LABEL: Record<string, string> = {
  comfort: "Comfort",
  stress: "Stress",
  walking_likelihood: "Walking likelihood",
  avoidance_likelihood: "Avoidance likelihood",
  route_choice: "Route choice",
};

/**
 * Model trust.
 *
 * Deliberately per target rather than one headline accuracy: two of these five
 * models fail to beat their own baseline, and a single averaged number would
 * hide that. The models are also not wired into the simulator, which the panel
 * states up front.
 */
export function ModelTrustPanel({ card }: { card: ModelCard }) {
  return (
    <Card>
      <CardHeader
        eyebrow="Model trust"
        title="What the models can and cannot do"
        description={`Random Forests trained on the survey, held out by participant. Overall verdict: ${card.overall_verdict.replaceAll("_", " ")}.`}
        actions={
          <Pill tone={card.wired_into_simulator ? "positive" : "neutral"}>
            {card.wired_into_simulator
              ? "Wired into the simulator"
              : "Not wired into the simulator"}
          </Pill>
        }
      />

      <div className="mt-5 overflow-x-auto">
        <table className="w-full min-w-[520px] border-collapse">
          <thead>
            <tr className="border-b border-hairline text-left">
              <Th>Target</Th>
              <Th align="right">Holdout</Th>
              <Th align="right">Baseline</Th>
              <Th align="right">Rows</Th>
              <Th align="right">Verdict</Th>
            </tr>
          </thead>
          <tbody>
            {card.models.map((model) => (
              <tr key={model.target} className="border-b border-hairline last:border-0">
                <td className="py-2.5 pr-3">
                  <p className="text-[13px] font-medium text-ink">
                    {TARGET_LABEL[model.target] ?? model.target}
                  </p>
                  <p className="text-[11px] text-ink-3">{model.kind}</p>
                </td>
                <td className="tabular py-2.5 pr-3 text-right text-[12px] text-ink">
                  {scoreLabel(model.final_holdout, model.kind)}
                </td>
                <td className="tabular py-2.5 pr-3 text-right text-[12px] text-ink-3">
                  {scoreLabel(model.final_holdout_baseline, model.kind)}
                </td>
                <td className="tabular py-2.5 pr-3 text-right text-[12px] text-ink-3">
                  {model.labelled_rows}
                </td>
                <td className="py-2.5 text-right">
                  <Pill tone={VERDICT[model.trust_verdict].tone}>
                    {VERDICT[model.trust_verdict].label}
                  </Pill>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-3">
            Limitations
          </p>
          <ul className="mt-2 space-y-1.5">
            {card.limitations.map((limitation) => (
              <li key={limitation} className="text-[12px] leading-relaxed text-ink-2">
                {limitation}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-3">
            Where the citizens come from
          </p>
          <p className="mt-2 text-[12px] leading-relaxed text-ink-2">
            {card.survey.participants} survey participants &rarr;{" "}
            {card.survey.scenario_response_rows} scenario responses &rarr;{" "}
            {card.survey.synthetic_citizens.toLocaleString("en-GB")} survey-calibrated
            synthetic citizens.
          </p>
          <p className="mt-2 text-[12px] leading-relaxed text-ink-3">
            {card.survey.note}
          </p>
          <p className="mt-2 text-[11px] text-ink-3">
            Split policy: {card.split_policy}. scikit-learn {card.sklearn_version}, seed{" "}
            {card.random_seed}.
          </p>
        </div>
      </div>
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

function scoreLabel(score: ModelEntry["final_holdout"], kind: ModelEntry["kind"]): string {
  if (kind === "classification") {
    return `macro F1 ${fmt(score.macro_f1)}`;
  }
  return `MAE ${fmt(score.mae)} \u00b7 R\u00b2 ${fmt(score.r2)}`;
}

function fmt(value: number | undefined): string {
  return value === undefined ? "\u2014" : value.toFixed(2);
}
