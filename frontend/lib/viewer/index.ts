import type { StreamConfig } from "../types";
import type { ViewerAdapter } from "./adapter";
import { kitWebRtcViewerAdapter } from "./kit-webrtc-adapter";
import { mockViewerAdapter } from "./mock-adapter";

export * from "./adapter";
export { kitWebRtcViewerAdapter } from "./kit-webrtc-adapter";
export { mockViewerAdapter } from "./mock-adapter";

/**
 * Chooses the viewport transport from what the *server* reports.
 *
 * The NVIDIA client is selected only when `/api/stream/config` says a session
 * is available. A client-side flag can never promote the viewport to "live".
 */
export function selectViewerAdapter(config: StreamConfig): ViewerAdapter {
  return config.status === "available" && config.signaling_url
    ? kitWebRtcViewerAdapter
    : mockViewerAdapter;
}
