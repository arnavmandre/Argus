"use client";

import { useCallback, useState } from "react";

import { Card, CardHeader } from "@/components/ui/Card";
import { Pill } from "@/components/ui/Pill";
import { api } from "@/lib/api";
import type { RagAdvisorResponse, RecommendationId } from "@/lib/types";

const LABELS: Record<string, string> = {
  increase_shade: "Increase shade",
  improve_drainage: "Improve drainage",
  alternative_pedestrian_routes: "Open alternative pedestrian routes",
  no_major_intervention: "No major intervention",
};

/** On-demand to avoid spending Groq credits until the operator asks for advice. */
export function RagAdvisorPanel({
  runId,
  busy,
  onApplySelected,
}: {
  runId: string;
  busy: boolean;
  onApplySelected: (ids: RecommendationId[]) => void;
}) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RagAdvisorResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const retrieve = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.advise(runId);
      setResult(response);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Grounded advice failed.");
    } finally {
      setLoading(false);
    }
  }, [runId]);

  return (
    <Card>
      <CardHeader
        eyebrow="Optional decision support"
        title="Grounded urban advisor"
        description="This is the Groq LLM section. It is separate from the Random Forest model-trust table. Retrieve advice to see whether this request used Groq or the fallback."
        actions={result ? (
          <Pill tone={result.fallback_used ? "caution" : "accent"}>
            {result.fallback_used ? "Deterministic fallback" : "RAG grounded"}
          </Pill>
        ) : null}
      />

      {!result ? (
        <button
          type="button"
          onClick={() => void retrieve()}
          disabled={loading}
          className="mt-4 w-full rounded-[12px] border border-hairline bg-surface-2 px-4 py-2.5 text-[13px] font-semibold text-ink transition-colors hover:bg-surface-3 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Retrieving advice…" : "Retrieve grounded advice"}
        </button>
      ) : (
        <div className="mt-4 space-y-3">
          {result.recommendations.map((recommendation) => (
            <div key={`${recommendation.rank}-${recommendation.argus_recommendation_id}`} className="rounded-[14px] border border-hairline bg-surface-2 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-[14px] font-semibold text-ink">
                  <span>{recommendation.rank}. {recommendation.intervention ?? LABELS[recommendation.argus_recommendation_id]}</span>
                </div>
                {recommendation.knowledge_id ? <Pill tone="neutral">{recommendation.knowledge_id}</Pill> : null}
              </div>
              {recommendation.reason ? <p className="mt-2 text-[12.5px] leading-relaxed text-ink-2">{recommendation.reason}</p> : null}
              {recommendation.tradeoffs?.length ? (
                <p className="mt-2 text-[11px] leading-relaxed text-ink-3">Trade-offs: {recommendation.tradeoffs.join("; ")}</p>
              ) : null}
              {recommendation.source?.status === "VERIFIED" && recommendation.source.url ? (
                <a className="mt-2 inline-block text-[11px] font-semibold text-accent hover:underline" href={recommendation.source.url} target="_blank" rel="noreferrer">
                  {recommendation.source.title}
                </a>
              ) : recommendation.source ? (
                <p className="mt-2 text-[11px] text-caution">Source pending verification</p>
              ) : null}
              <button
                type="button"
                disabled={busy}
                onClick={() => onApplySelected([recommendation.argus_recommendation_id])}
                className="mt-3 rounded-[10px] border border-accent-line bg-accent-soft px-3 py-2 text-[12px] font-semibold text-accent transition-colors hover:bg-surface-3 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {recommendation.argus_recommendation_id === "no_major_intervention"
                  ? "Re-run with no intervention"
                  : "Test only this action"}
              </button>
            </div>
          ))}
          <p className="text-[11px] leading-relaxed text-ink-3">
            {result.fallback_used
              ? `No LLM output was used: ${result.unavailable_reason ?? "the deterministic fallback answered."}`
              : `Confirmed LLM output from ${result.model ?? "the configured Groq model"}. Retrieval: ${result.retrieval_backend ?? "unknown"}.`}
          </p>
          <p className="text-[11px] leading-relaxed text-ink-3">
            Each button starts a separate run with only that action, so its effect can be measured independently.
          </p>
        </div>
      )}
      {error ? <p className="mt-3 text-[11px] text-negative">{error}</p> : null}
    </Card>
  );
}
