import { api } from "../api";
import type {
  ViewerAdapter,
  ViewerConnectContext,
  ViewerConnection,
} from "./adapter";

/**
 * NVIDIA Kit App Streaming adapter — the replacement path, not yet enabled.
 *
 * This is where the Omniverse Web SDK / WebRTC client goes. It is written as a
 * real implementation sketch so that turning streaming on is an isolated change
 * in this one file: the dashboard, the viewer component and the view-command
 * allow-list all stay as they are.
 *
 * Steps to finish it:
 *   1. build `urbantwin.streaming.kit` with the streaming extensions enabled;
 *   2. stand up a session manager and return its signaling URL, ICE servers and
 *      a short-lived token from `GET /api/stream/config` (server-side only);
 *   3. install the NVIDIA web client package and replace the marked block below
 *      with its connect call, handing the resulting MediaStream to `onState`;
 *   4. register this adapter in `lib/viewer/index.ts`.
 *
 * Until step 3 exists this adapter refuses to connect rather than pretending.
 */
export const kitWebRtcViewerAdapter: ViewerAdapter = {
  id: "nvidia-kit-webrtc",
  displayName: "NVIDIA Kit App Streaming",
  transportLabel: "WebRTC \u00b7 Kit App Streaming",

  async connect(ctx: ViewerConnectContext): Promise<ViewerConnection> {
    const { config, onState } = ctx;

    onState({
      status: "connecting",
      message: "Requesting a streaming session\u2026",
      stream: null,
      capabilities: { video: false, input: false, messaging: false },
      detail: [],
    });

    if (config.status !== "available" || !config.signaling_url) {
      onState({
        status: "offline",
        message:
          config.reason ??
          "The server has no streaming session to offer, so no WebRTC connection was attempted.",
        stream: null,
        capabilities: { video: false, input: false, messaging: false },
        detail: [`Stage: ${config.stage}`],
      });
      return inertConnection(
        "No signaling URL was returned by /api/stream/config.",
      );
    }

    // ---- NVIDIA client goes here -------------------------------------------
    // const stream = await AppStreamer.connect({
    //   server: config.signaling_url,
    //   iceServers: config.ice_servers,
    //   token: config.session_token,
    // });
    // onState({ status: "connected", message: "Streaming from the RTX host.",
    //   stream, capabilities: { video: true, input: true, messaging: true },
    //   detail: [`Stage: ${config.stage}`] });
    // ------------------------------------------------------------------------

    onState({
      status: "failed",
      message:
        "A session was offered but the NVIDIA streaming client is not installed in this build.",
      stream: null,
      capabilities: { video: false, input: false, messaging: false },
      detail: [
        "See docs/FRONTEND_BACKEND_HANDOFF.md, \u201cOmniverse/OpenUSD\u201d.",
        "https://docs.omniverse.nvidia.com/ov-web-sdk/latest/index.html",
      ],
    });
    return inertConnection("The streaming client is not installed.");
  },
};

/**
 * View commands travel over HTTP to the allow-listed endpoint, never straight
 * from the browser into Kit, so the server stays the only thing that can decide
 * what the viewport is asked to do.
 */
function inertConnection(reason: string): ViewerConnection {
  return {
    async send(command) {
      return { accepted: false, delivered: false, reason, command };
    },
    async close() {
      /* nothing to tear down */
    },
  };
}

/** Used once a session exists: validate server-side, then deliver over the channel. */
export async function sendAllowListedViewCommand(
  runId: string,
  command: Parameters<ViewerConnection["send"]>[0],
) {
  return api.view(runId, command);
}
