import { isMockMode, json, proxy } from "@/lib/server/upstream";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ runId: string }> };

/** Optional constrained explanation; live backend only (mock mode returns 404). */
export async function POST(_request: Request, ctx: Ctx) {
  const { runId } = await ctx.params;
  if (!isMockMode()) {
    return proxy(`/api/runs/${encodeURIComponent(runId)}/explain`, {
      method: "POST",
      body: "{}",
    });
  }
  return json(
    {
      error: {
        code: "not_found",
        message: "Explain is available only when URBANTWIN_API_BASE is configured.",
      },
    },
    404,
  );
}
