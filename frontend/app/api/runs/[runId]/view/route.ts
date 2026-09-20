import { fixtures } from "@/lib/server/fixtures";
import { isMockMode, json, proxy } from "@/lib/server/upstream";
import { VIEW_CAMERAS, VIEW_OVERLAYS, VIEW_PLAYBACK } from "@/lib/types";
import type { ViewCommand, ViewCommandResult } from "@/lib/types";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ runId: string }> };

const STATES = ["before", "after"] as const;

/**
 * High-level view command for the Kit viewport.
 *
 * Every field is checked against a fixed allow-list here, on the server. Prim
 * paths, file paths and anything else the browser could use to reach into the
 * stage are never forwarded — the browser can only name a state, one of four
 * cameras and one of four overlays.
 *
 * No Kit messaging extension exists yet, so an accepted command is reported as
 * accepted but not delivered.
 */
export async function POST(request: Request, ctx: Ctx) {
  const { runId } = await ctx.params;
  const raw = (await request.json().catch(() => null)) as Record<string, unknown> | null;

  const state = raw?.state;
  const camera = raw?.camera;
  const overlay = raw?.overlay;
  const playback = raw?.playback ?? "play";

  const invalid =
    !STATES.includes(state as (typeof STATES)[number]) ||
    !VIEW_CAMERAS.includes(camera as (typeof VIEW_CAMERAS)[number]) ||
    !VIEW_OVERLAYS.includes(overlay as (typeof VIEW_OVERLAYS)[number]) ||
    !VIEW_PLAYBACK.includes(playback as (typeof VIEW_PLAYBACK)[number]);

  if (invalid) {
    return json(
      {
        error: {
          code: "validation_failed",
          message: `Command rejected. state must be one of ${STATES.join("|")}, camera one of ${VIEW_CAMERAS.join(
            "|",
          )}, overlay one of ${VIEW_OVERLAYS.join("|")}, playback one of ${VIEW_PLAYBACK.join("|")}.`,
        },
      },
      422,
    );
  }

  const command = { state, camera, overlay, playback } as ViewCommand;

  if (!isMockMode()) {
    return proxy(`/api/runs/${encodeURIComponent(runId)}/view`, {
      method: "POST",
      body: JSON.stringify(command),
    });
  }

  const stream = await fixtures.streamConfig();
  const result: ViewCommandResult = {
    accepted: true,
    delivered: false,
    reason:
      stream.status === "offline"
        ? "No streaming Kit session to deliver to. The command was validated against the allow-list and discarded."
        : undefined,
    command,
  };
  return json(result);
}
