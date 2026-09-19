/**
 * The Omniverse viewport boundary.
 *
 * Acceptance criterion 9 of docs/FRONTEND_BACKEND_HANDOFF.md: the WebRTC
 * implementation must be isolated so the NVIDIA client can replace the mock
 * viewport without rewriting the dashboard. Everything the dashboard knows
 * about the viewport is in this file.
 *
 * An adapter owns transport only. It reports status and, if it has one, hands
 * back a MediaStream. It never renders. `components/OmniverseViewer.tsx` renders
 * whatever state the adapter reports, so swapping `mockViewerAdapter` for
 * `kitWebRtcViewerAdapter` changes no dashboard code.
 *
 * An adapter must never fabricate a picture. If there is no stream, the status
 * is "offline" or "failed" and the UI says so.
 */
import type { StreamConfig, ViewCommand, ViewCommandResult } from "../types";

export type ViewerStatus =
  | "idle"
  | "connecting"
  | "connected"
  | "offline"
  | "failed";

export interface ViewerState {
  status: ViewerStatus;
  /** One sentence a judge can read. Always present except when idle. */
  message: string;
  /** Only set when a real remote stream is attached. */
  stream: MediaStream | null;
  /** What the connected transport can actually do. */
  capabilities: {
    video: boolean;
    input: boolean;
    messaging: boolean;
  };
  /** Extra lines the viewport surface may show, e.g. how to launch on desktop. */
  detail: string[];
}

export const IDLE_VIEWER_STATE: ViewerState = {
  status: "idle",
  message: "",
  stream: null,
  capabilities: { video: false, input: false, messaging: false },
  detail: [],
};

export interface ViewerConnectContext {
  config: StreamConfig;
  /** Called on every transition, including the first. */
  onState: (state: ViewerState) => void;
  signal: AbortSignal;
}

export interface ViewerConnection {
  /** Forward an allow-listed view command. Adapters that cannot deliver say so. */
  send: (command: ViewCommand) => Promise<ViewCommandResult>;
  close: () => Promise<void>;
}

export interface ViewerAdapter {
  id: string;
  displayName: string;
  /** Shown in the viewport footer so the transport in use is never ambiguous. */
  transportLabel: string;
  connect: (ctx: ViewerConnectContext) => Promise<ViewerConnection>;
}
