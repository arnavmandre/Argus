import { cancelRun, progressOf, resolveRun } from "@/lib/server/run-store";
import { isMockMode, json, proxy } from "@/lib/server/upstream";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ runId: string }> };

export async function GET(_request: Request, ctx: Ctx) {
  const { runId } = await ctx.params;
  if (!isMockMode()) return proxy(`/api/runs/${encodeURIComponent(runId)}`);

  const summary = await resolveRun(runId);
  if (!summary) {
    return json({ error: { code: "not_found", message: `Unknown run ${runId}.` } }, 404);
  }
  const progress = progressOf(runId);
  return json(progress === null ? summary : { ...summary, progress });
}

/** Cancellation. The planned API should expose the same terminal state. */
export async function DELETE(_request: Request, ctx: Ctx) {
  const { runId } = await ctx.params;
  if (!isMockMode()) {
    return proxy(`/api/runs/${encodeURIComponent(runId)}`, { method: "DELETE" });
  }

  const cancelled = cancelRun(runId);
  if (!cancelled) {
    return json(
      {
        error: {
          code: "conflict",
          message: `Run ${runId} is not cancellable; it is unknown or already finished.`,
        },
      },
      409,
    );
  }
  return json({ run_id: runId, status: "cancelled" });
}
