"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Dot, Pill } from "@/components/ui/Pill";
import { cx } from "@/lib/cx";
import { VIDEO_ELEMENT_ID } from "@/lib/viewer/kit-webrtc-adapter";
import {
  IDLE_VIEWER_STATE,
  selectViewerAdapter,
  type ViewerConnection,
  type ViewerState,
} from "@/lib/viewer";
import {
  VIEW_CAMERAS,
  VIEW_OVERLAYS,
  type RunState,
  type StreamConfig,
  type ViewCamera,
  type ViewCommandResult,
  type ViewOverlay,
  type ViewPlayback,
} from "@/lib/types";

const OVERLAY_LABELS: Record<ViewOverlay, string> = {
  behavior: "Behavior",
  congestion: "Routes only",
  shade: "Shade canopy",
  none: "City only",
};
/**
 * The Omniverse viewport.
 *
 * This component renders viewer *state*; it contains no transport code. The
 * adapter in `lib/viewer/` owns connecting, and is chosen from what
 * `/api/stream/config` reports. Replacing the placeholder adapter with the
 * NVIDIA Kit App Streaming client therefore changes nothing here or anywhere
 * else in the dashboard.
 *
 * Mounted client-only: WebRTC and media APIs do not exist during SSR.
 */
export function OmniverseViewer({
  runId,
  config,
  state,
  onStateChange,
  hasAfter,
  className,
}: {
  runId: string | null;
  config: StreamConfig;
  state: RunState;
  onStateChange: (state: RunState) => void;
  hasAfter: boolean;
  className?: string;
}) {
  const adapter = useMemo(() => selectViewerAdapter(config), [config]);
  const [viewer, setViewer] = useState<ViewerState>(IDLE_VIEWER_STATE);
  const [attempt, setAttempt] = useState(0);
  const [camera, setCamera] = useState<ViewCamera>("Overview");
  const [overlay, setOverlay] = useState<ViewOverlay>("behavior");
  const [playback, setPlayback] = useState<ViewPlayback>("play");
  const [commandResult, setCommandResult] = useState<ViewCommandResult | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const connectionRef = useRef<ViewerConnection | null>(null);
  const cleanupPromiseRef = useRef<Promise<void>>(Promise.resolve());
  const automaticRetriesRef = useRef(0);
  const runIdRef = useRef<string | null>(runId);
  const commandedRunIdRef = useRef<string | null>(runId);
  runIdRef.current = runId;

  // Do NOT depend on runId: a finished simulation must not tear down WebRTC.
  useEffect(() => {
    const controller = new AbortController();
    let closed = false;

    const previousCleanup = cleanupPromiseRef.current;
    const connectionPromise = previousCleanup.then(() => adapter.connect({
        config,
        // Stable id for allow-list before the first simulation completes.
        runId: runIdRef.current ?? "viewport",
        signal: controller.signal,
        onState: (next) => {
          if (!closed) setViewer(next);
        },
        getRunId: () => runIdRef.current ?? "viewport",
      }));

    connectionPromise
      .then((connection) => {
        if (closed) {
          void connection.close();
          return;
        }
        connectionRef.current = connection;
      })
      .catch((error: unknown) => {
        if (closed || controller.signal.aborted) return;
        setViewer({
          status: "failed",
          message:
            error instanceof Error
              ? `The viewport adapter failed: ${error.message}`
              : "The viewport adapter failed for an unknown reason.",
          stream: null,
          capabilities: { video: false, input: false, messaging: false },
          detail: [],
        });
      });

    return () => {
      closed = true;
      controller.abort();
      connectionRef.current = null;
      cleanupPromiseRef.current = connectionPromise
        .then((connection) => connection.close())
        .catch(() => undefined);
    };
  }, [adapter, config, attempt]);

  useEffect(() => {
    if (viewer.status === "connected") {
      automaticRetriesRef.current = 0;
      return;
    }
    if (viewer.status !== "failed" || config.status !== "available") return;
    if (automaticRetriesRef.current >= 3) return;

    automaticRetriesRef.current += 1;
    const timer = window.setTimeout(() => setAttempt((value) => value + 1), 1500);
    return () => window.clearTimeout(timer);
  }, [config.status, viewer.status]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    // The streaming client owns srcObject on this element now, so only ever
    // set it — never clear it back to null, or we would tear down the live
    // stream the library just attached.
    if (viewer.stream && video.srcObject !== viewer.stream) {
      video.srcObject = viewer.stream;
    }
  }, [viewer.stream]);

  const sendCommand = useCallback(
    async (next: {
      state: RunState;
      camera: ViewCamera;
      overlay: ViewOverlay;
      playback: ViewPlayback;
    }) => {
      try {
        const result = await connectionRef.current?.send(next);
        if (result) {
          setCommandResult(result);
        } else {
          setCommandResult({
            accepted: false,
            delivered: false,
            reason:
              "No WebRTC viewport connection is available yet. Wait until the stream shows Live, then retry.",
            command: next,
          });
        }
      } catch {
        setCommandResult({
          accepted: false,
          delivered: false,
          reason: "The view command could not be sent.",
          command: next,
        });
      }
    },
    [],
  );

  const connected = viewer.status === "connected" && viewer.stream !== null;

  useEffect(() => {
    if (!connected || !runId || commandedRunIdRef.current === runId) return;
    commandedRunIdRef.current = runId;
    setPlayback("play");
    void sendCommand({ state, camera, overlay, playback: "restart" });
  }, [camera, connected, overlay, runId, sendCommand, state]);

  return (
    <div
      className={cx(
        "flex flex-col overflow-hidden rounded-[18px] border border-hairline bg-surface shadow-[var(--shadow-card)]",
        className,
      )}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-hairline px-4 py-3">
        <StatusChip status={viewer.status} />
        <p className="text-[13px] font-semibold tracking-[-0.01em] text-ink">
          Omniverse RTX viewport
        </p>
        <div className="ml-auto flex items-center gap-2">
          <SegmentedControl
            ariaLabel="Simulation state shown in the viewport"
            size="sm"
            value={state}
            onChange={(next) => {
              onStateChange(next);
              void sendCommand({ state: next, camera, overlay, playback });
            }}
            segments={[
              { value: "before", label: "Before" },
              {
                value: "after",
                label: "After",
                disabled: !hasAfter,
                title: hasAfter
                  ? undefined
                  : "This run has no intervention arm to show.",
              },
            ]}
          />
        </div>
      </div>

      {/*
        Fixed 16:9 to match the 1280x720 stream. It used to stretch to whatever
        height the layout gave it and `object-cover` then cropped the picture to
        fill (the top of the frame, including overlays, was cut off).
      */}
      <div className="relative aspect-video w-full bg-black">
        <Backdrop />
        {/*
          Always mounted, and carrying the id the Kit streaming client binds to.
          AppStreamer attaches its mouse / wheel / keyboard forwarding to this
          exact element, so it must (a) exist before connect() runs and (b) be
          the element the user actually clicks. Drag to orbit, scroll to zoom.
        */}
        <video
          id={VIDEO_ELEMENT_ID}
          ref={videoRef}
          autoPlay
          playsInline
          muted
          tabIndex={0}
          aria-label="Omniverse RTX viewport. Drag to orbit, scroll to zoom."
          className={cx(
            "absolute inset-0 size-full bg-black object-contain outline-none",
            connected
              ? "cursor-grab active:cursor-grabbing"
              : "pointer-events-none opacity-0",
          )}
        />
        {!connected && (
          <div className="absolute inset-0 grid place-items-center p-6">
            <ViewerStatePanel
              viewer={viewer}
              adapterName={adapter.displayName}
              onRetry={() => {
                automaticRetriesRef.current = 0;
                setAttempt((n) => n + 1);
              }}
            />
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-3 border-t border-hairline px-4 py-3">
        <label className="flex items-center gap-2 text-[12px] text-ink-2">
          <span className="text-ink-3">Camera</span>
          <select
            value={camera}
            onChange={(event) => {
              const next = event.target.value as ViewCamera;
              setCamera(next);
              void sendCommand({ state, camera: next, overlay, playback });
            }}
            className="rounded-[8px] border border-hairline bg-surface-2 px-2 py-1 text-[12px] text-ink"
          >
            {VIEW_CAMERAS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <label className="flex items-center gap-2 text-[12px] text-ink-2">
          <span className="text-ink-3">Overlay</span>
          <select
            value={overlay}
            onChange={(event) => {
              const next = event.target.value as ViewOverlay;
              setOverlay(next);
              void sendCommand({ state, camera, overlay: next, playback });
            }}
            className="rounded-[8px] border border-hairline bg-surface-2 px-2 py-1 text-[12px] text-ink"
            title="Shade canopy shows the proposed ADD_SHADE intervention. Pick Camera separately (Street is a good angle)."
          >
            {VIEW_OVERLAYS.map((option) => (
              <option key={option} value={option}>
                {OVERLAY_LABELS[option]}
              </option>
            ))}
          </select>
        </label>

        <div className="flex items-center gap-1.5" aria-label="Animation playback">
          <span className="mr-1 text-[12px] text-ink-3">Animation</span>
          {(["play", "pause", "restart"] as const).map((action) => (
            <button
              key={action}
              type="button"
              disabled={!connected}
              onClick={() => {
                setPlayback(action === "pause" ? "pause" : "play");
                void sendCommand({
                  state,
                  camera,
                  overlay,
                  playback: action,
                });
              }}
              className={cx(
                "rounded-[8px] border px-2 py-1 text-[11px] font-semibold capitalize transition-colors disabled:cursor-not-allowed disabled:opacity-40",
                (action === "pause" ? playback === "pause" : action === "play" ? playback === "play" : false)
                  ? "border-accent-line bg-accent-soft text-accent"
                  : "border-hairline bg-surface-2 text-ink-2 hover:bg-surface-3",
              )}
            >
              {action}
            </button>
          ))}
        </div>

        <p className="ml-auto text-[11px] text-ink-3">{adapter.transportLabel}</p>
      </div>

      {commandResult ? (
        <p className="border-t border-hairline bg-surface-2 px-4 py-2 text-[11px] leading-relaxed text-ink-3">
          View command{" "}
          <span className="font-mono text-ink-2">
            {commandResult.command.state}/{commandResult.command.camera}/
            {commandResult.command.overlay}
            /{commandResult.command.playback}
          </span>{" "}
          {commandResult.accepted ? "passed the server allow-list" : "was rejected"}
          {commandResult.delivered ? " and was delivered." : "; not delivered. "}
          {commandResult.reason}
        </p>
      ) : null}
    </div>
  );
}

function StatusChip({ status }: { status: ViewerState["status"] }) {
  const map = {
    idle: { tone: "neutral", label: "Idle", color: "var(--ink-4)" },
    connecting: { tone: "caution", label: "Connecting", color: "var(--caution)" },
    connected: { tone: "positive", label: "Live", color: "var(--positive)" },
    offline: { tone: "neutral", label: "Offline", color: "var(--ink-4)" },
    failed: { tone: "negative", label: "Failed", color: "var(--negative)" },
  } as const;
  const entry = map[status];
  return (
    <Pill tone={entry.tone}>
      <Dot color={entry.color} className={status === "connecting" ? "breathe" : undefined} />
      {entry.label}
    </Pill>
  );
}

function ViewerStatePanel({
  viewer,
  adapterName,
  onRetry,
}: {
  viewer: ViewerState;
  adapterName: string;
  onRetry: () => void;
}) {
  if (viewer.status === "connecting" || viewer.status === "idle") {
    return (
      <div className="flex flex-col items-center gap-3 text-center">
        <Spinner />
        <p className="text-[13px] text-ink-2">
          {viewer.message || "Preparing the viewport\u2026"}
        </p>
      </div>
    );
  }

  const failed = viewer.status === "failed";

  return (
    <div className="max-w-md rounded-[16px] border border-hairline bg-surface/85 p-5 text-center shadow-[var(--shadow-lift)] backdrop-blur-xl">
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-3">
        {failed ? "Viewport failed" : "Viewport offline"}
      </p>
      <p className="mt-2 text-[15px] font-semibold tracking-[-0.015em] text-ink">
        No live RTX stream is connected
      </p>
      <p className="mt-2 text-[13px] leading-relaxed text-ink-2">{viewer.message}</p>
      {viewer.detail.length > 0 ? (
        <ul className="mt-3 space-y-1 text-left">
          {viewer.detail.map((line) => (
            <li key={line} className="text-[12px] leading-relaxed text-ink-3">
              {line}
            </li>
          ))}
        </ul>
      ) : null}
      <div className="mt-4 flex items-center justify-center gap-2">
        <button
          type="button"
          onClick={onRetry}
          className="rounded-full bg-accent px-4 py-1.5 text-[12px] font-semibold text-accent-ink transition-colors hover:bg-accent-hover"
        >
          Retry connection
        </button>
        <span className="text-[11px] text-ink-3">via {adapterName}</span>
      </div>
    </div>
  );
}

function Spinner() {
  return (
    <span
      aria-hidden
      className="size-6 animate-spin rounded-full border-2 border-hairline-strong border-t-accent"
    />
  );
}

/**
 * An abstract backdrop for the empty viewport. Deliberately a plain grid, not a
 * drawing of a city: nothing here should be mistaken for the rendered twin.
 */
function Backdrop() {
  return (
    <div
      aria-hidden
      className="absolute inset-0 bg-canvas-tint"
      style={{
        backgroundImage:
          "linear-gradient(var(--hairline) 1px, transparent 1px), linear-gradient(90deg, var(--hairline) 1px, transparent 1px)",
        backgroundSize: "44px 44px",
        maskImage: "radial-gradient(ellipse at center, black 35%, transparent 85%)",
        WebkitMaskImage: "radial-gradient(ellipse at center, black 35%, transparent 85%)",
      }}
    />
  );
}
