"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Dot, Pill } from "@/components/ui/Pill";
import { api } from "@/lib/api";
import { cx } from "@/lib/cx";
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
} from "@/lib/types";

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
  const [commandResult, setCommandResult] = useState<ViewCommandResult | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const connectionRef = useRef<ViewerConnection | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let closed = false;

    adapter
      .connect({
        config,
        signal: controller.signal,
        onState: (next) => {
          if (!closed) setViewer(next);
        },
      })
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
      void connectionRef.current?.close();
      connectionRef.current = null;
    };
  }, [adapter, config, attempt]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.srcObject = viewer.stream;
  }, [viewer.stream]);

  const sendCommand = useCallback(
    async (next: { state: RunState; camera: ViewCamera; overlay: ViewOverlay }) => {
      if (!runId) return;
      try {
        // Always validated server-side against the allow-list, even when a
        // session exists, so the browser can never name a prim or a file path.
        const result = await api.view(runId, next);
        setCommandResult(result);
      } catch {
        setCommandResult({
          accepted: false,
          delivered: false,
          reason: "The view command could not be sent to the server.",
          command: next,
        });
      }
    },
    [runId],
  );

  const connected = viewer.status === "connected" && viewer.stream !== null;

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
              void sendCommand({ state: next, camera, overlay });
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

      <div className="relative min-h-[380px] flex-1 lg:min-h-[460px]">
        <Backdrop />
        {connected ? (
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className="absolute inset-0 size-full bg-black object-cover"
          />
        ) : (
          <div className="absolute inset-0 grid place-items-center p-6">
            <ViewerStatePanel
              viewer={viewer}
              adapterName={adapter.displayName}
              onRetry={() => setAttempt((n) => n + 1)}
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
              void sendCommand({ state, camera: next, overlay });
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
              void sendCommand({ state, camera, overlay: next });
            }}
            className="rounded-[8px] border border-hairline bg-surface-2 px-2 py-1 text-[12px] text-ink"
          >
            {VIEW_OVERLAYS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <p className="ml-auto text-[11px] text-ink-3">{adapter.transportLabel}</p>
      </div>

      {commandResult ? (
        <p className="border-t border-hairline bg-surface-2 px-4 py-2 text-[11px] leading-relaxed text-ink-3">
          View command{" "}
          <span className="font-mono text-ink-2">
            {commandResult.command.state}/{commandResult.command.camera}/
            {commandResult.command.overlay}
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
