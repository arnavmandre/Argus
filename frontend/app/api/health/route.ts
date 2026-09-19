import { fixtures } from "@/lib/server/fixtures";
import { isMockMode, json, proxy } from "@/lib/server/upstream";

export const dynamic = "force-dynamic";

export async function GET() {
  if (!isMockMode()) return proxy("/api/health");
  return json(await fixtures.health());
}
