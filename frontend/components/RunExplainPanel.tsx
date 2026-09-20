"use client";

import { useCallback, useState } from "react";

import { Card, CardHeader } from "@/components/ui/Card";
import { Pill } from "@/components/ui/Pill";
import { api } from "@/lib/api";
import type { ExplainResponse } from "@/lib/types";

/**
 * Optional narrative over a bounded simulator payload.
 * Failures degrade silently; the deterministic advisor panel stays authoritative.
 */
export function RunExplainPanel({ runId }: { runId: string }) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ExplainResponse | null>(null);

  const fetchExplain = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.explain(runId);
      setResult(response);
    } catch {
      /* silent degrade */
    } finally {
      setLoading(false);
    }
  }, [runId]);

  return (
    <Card>
      <CardHeader
        eyebrow="Optional narrative"
        title="Explain results"
        description="Summarizes causes, trade-offs and limitations already present in the simulator report. Does not change recommendations."
        actions={
          result ? (
            <Pill tone={result.source === "llm" ? "accent" : "neutral"}>
              {result.source === "llm" ? "LLM summary" : "Deterministic template"}
            </Pill>
          ) : null
        }
      />

      {!result ? (
        <button
          type="button"
          onClick={() => void fetchExplain()}
          disabled={loading}
          className="mt-2 w-full rounded-[12px] border border-hairline bg-surface-2 px-4 py-2.5 text-[13px] font-semibold text-ink transition-colors hover:bg-surface-3 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Generating…" : "Explain results"}
        </button>
      ) : (
        <div className="mt-4 space-y-3">
          <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-ink-2">
            {result.text}
          </p>
          {result.unavailable_reason ? (
            <p className="text-[11px] leading-relaxed text-ink-3">
              LLM unavailable ({result.unavailable_reason}); showing deterministic
              template instead.
            </p>
          ) : null}
          <p className="text-[11px] leading-relaxed text-ink-3">
            Heuristic prototype metrics — not medical or engineering advice. The
            threshold advisor above remains the source of recommendations.
          </p>
        </div>
      )}
    </Card>
  );
}
