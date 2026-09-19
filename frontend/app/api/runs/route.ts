import { RECORDED_RUN_ID } from "@/lib/server/fixtures";
import { activeRunId, createRun, validateScenario } from "@/lib/server/run-store";
import { isMockMode, json, proxy } from "@/lib/server/upstream";

export const dynamic = "force-dynamic";

export async function GET() {
  if (!isMockMode()) return proxy("/api/runs");
  return json({
    source: "recorded_fixture",
    recorded_run_id: RECORDED_RUN_ID,
    active_run_id: activeRunId(),
  });
}

export async function POST(request: Request) {
  if (!isMockMode()) {
    return proxy("/api/runs", { method: "POST", body: await request.text() });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return json(
      { error: { code: "validation_failed", message: "Request body must be JSON." } },
      400,
    );
  }

  const validated = await validateScenario(body);
  if (!validated.ok) return json(validated.error, 422);

  // One local worker: a second concurrent run is refused rather than queued.
  const active = activeRunId();
  if (active) {
    return json(
      {
        error: {
          code: "conflict",
          message: `Run ${active} is still in progress. This prototype runs one simulation at a time.`,
        },
      },
      409,
    );
  }

  const record = createRun(validated.request);
  return json({ run_id: record.runId, status: "queued" }, 202);
}
