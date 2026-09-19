import { fixtures } from "@/lib/server/fixtures";
import { isMockMode, json, proxy } from "@/lib/server/upstream";
import type { CitizenPage, RunState } from "@/lib/types";

export const dynamic = "force-dynamic";

const MAX_LIMIT = 100;

type Ctx = { params: Promise<{ runId: string }> };

/**
 * Paginated citizen inspection.
 *
 * The recorded fixture holds 200 of the 1,000 simulated citizens and is read on
 * the server; only the requested page crosses the wire. `total_in_run` keeps the
 * real population visible so the UI cannot imply it is showing everybody.
 */
export async function GET(request: Request, ctx: Ctx) {
  const { runId } = await ctx.params;
  const url = new URL(request.url);

  if (!isMockMode()) {
    return proxy(`/api/runs/${encodeURIComponent(runId)}/citizens${url.search}`);
  }

  const state: RunState = url.searchParams.get("state") === "after" ? "after" : "before";
  const limit = clamp(Number(url.searchParams.get("limit") ?? 25), 1, MAX_LIMIT);
  const offset = Math.max(0, Number(url.searchParams.get("offset") ?? 0) || 0);

  const fixture = await fixtures.citizens();
  const arm = fixture.states[state];

  const page: CitizenPage = {
    run_id: runId,
    state,
    source: "recorded_fixture",
    limit,
    offset,
    total: arm.included_in_fixture,
    total_in_run: arm.total_in_run,
    items: arm.items.slice(offset, offset + limit),
    notes: [
      `Recorded fixture carries ${arm.included_in_fixture} of ${arm.total_in_run} simulated citizens.`,
      "Citizens are survey-calibrated synthetic people, not real individuals.",
    ],
  };
  return json(page);
}

function clamp(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, Math.trunc(value)));
}
