import { notFound } from "next/navigation";

import { Dashboard } from "@/components/Dashboard";
import { loadBootstrap } from "@/lib/server/bootstrap";

export const dynamic = "force-dynamic";

/** Permalink for a single run. Same dashboard, seeded with that run. */
export default async function RunPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;
  const bootstrap = await loadBootstrap(runId);
  if (!bootstrap.run && !bootstrap.upstreamError) notFound();
  return <Dashboard bootstrap={bootstrap} />;
}
