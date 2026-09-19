import { fixtures } from "@/lib/server/fixtures";
import { isMockMode, json, proxy } from "@/lib/server/upstream";

export const dynamic = "force-dynamic";

/**
 * Public WebRTC connection settings only.
 *
 * Nothing here may come from `NEXT_PUBLIC_*`. When a session manager exists it
 * should mint a short-lived token server-side and return it through this
 * endpoint; infrastructure credentials must never reach the browser bundle.
 */
export async function GET() {
  if (!isMockMode()) return proxy("/api/stream/config");
  return json(await fixtures.streamConfig());
}
