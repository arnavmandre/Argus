import { Dashboard } from "@/components/Dashboard";
import { loadBootstrap } from "@/lib/server/bootstrap";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const bootstrap = await loadBootstrap();
  return <Dashboard bootstrap={bootstrap} />;
}
