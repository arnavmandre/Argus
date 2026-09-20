import { isMockMode, json, proxy } from "@/lib/server/upstream";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ runId: string }> };

/** Grounded recommendations are live-only; recorded fixtures never pose as RAG. */
export async function POST(_request: Request, ctx: Ctx) {
  const { runId } = await ctx.params;
  if (!isMockMode()) {
    return proxy(`/api/runs/${encodeURIComponent(runId)}/advise`, {
      method: "POST",
      body: "{}",
    });
  }
  return json(
    {
      error: {
        code: "not_found",
        message: "Grounded advice is available only with the live Python API.",
      },
    },
    404,
  );
}
