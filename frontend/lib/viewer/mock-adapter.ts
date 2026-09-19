import type {
  ViewerAdapter,
  ViewerConnectContext,
  ViewerConnection,
} from "./adapter";

/**
 * The placeholder viewport adapter.
 *
 * No streaming-enabled Kit application exists, so this adapter deliberately
 * produces no picture. It contacts `/api/stream/config`, reads back
 * `status: "offline"`, and reports offline with the reason the server gave.
 *
 * It exists so the viewport has a working, honest implementation of the same
 * interface the NVIDIA client will implement — not to simulate a stream.
 */
export const mockViewerAdapter: ViewerAdapter = {
  id: "placeholder-offline",
  displayName: "Placeholder viewport",
  transportLabel: "No transport \u00b7 stream not configured",

  async connect(ctx: ViewerConnectContext): Promise<ViewerConnection> {
    const { config, onState, signal } = ctx;

    onState({
      status: "connecting",
      message: "Checking for a streaming session\u2026",
      stream: null,
      capabilities: { video: false, input: false, messaging: false },
      detail: [],
    });

    // A short, visible probe so the connecting state is real rather than a
    // decorative spinner.
    await wait(450, signal);
    if (signal.aborted) throw new DOMException("aborted", "AbortError");

    if (config.status === "offline") {
      onState({
        status: "offline",
        message:
          config.reason ??
          "No streaming session is available for this deployment.",
        stream: null,
        capabilities: { video: false, input: false, messaging: false },
        detail: [
          `Stage: ${config.stage}`,
          config.desktop_fallback
            ? `Runs today on the desktop RTX machine: ${config.desktop_fallback}`
            : "",
          "Swap in the NVIDIA Kit App Streaming client behind this same adapter to go live.",
        ].filter(Boolean),
      });
    } else {
      // The server said a session exists but this adapter cannot open one.
      onState({
        status: "failed",
        message:
          "A streaming session was advertised, but the placeholder adapter cannot open WebRTC. Enable the NVIDIA client adapter.",
        stream: null,
        capabilities: { video: false, input: false, messaging: false },
        detail: [`Signaling: ${config.signaling_url ?? "unknown"}`],
      });
    }

    return {
      async send(command) {
        return {
          accepted: false,
          delivered: false,
          reason:
            "The placeholder viewport has no Kit session, so view commands are not delivered.",
          command,
        };
      },
      async close() {
        /* nothing to tear down */
      },
    };
  },
};

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(new DOMException("aborted", "AbortError"));
      },
      { once: true },
    );
  });
}
