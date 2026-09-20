import type { StreamConfig } from "../types";
import type { ViewerAdapter } from "./adapter";
import { kitWebRtcViewerAdapter } from "./kit-webrtc-adapter";
import { mockViewerAdapter } from "./mock-adapter";

/**
 * Pure predicate: server offered a session with a signaling endpoint.
 * Used by {@link selectViewerAdapter} and Node tests.
 */
export function shouldUseKitWebRtcAdapter(config: StreamConfig): boolean {
  return config.status === "available" && Boolean(config.signaling_url);
}

/**
 * Chooses the viewport transport from what the *server* reports.
 *
 * The NVIDIA client is selected only when `/api/stream/config` says a session
 * is available. A client-side flag can never promote the viewport to "live".
 */
export function selectViewerAdapter(config: StreamConfig): ViewerAdapter {
  return shouldUseKitWebRtcAdapter(config)
    ? kitWebRtcViewerAdapter
    : mockViewerAdapter;
}
