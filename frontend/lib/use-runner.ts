"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError } from "./api";
import type {
  RunRequest,
  RunStatus,
  RunSummary,
  ScenarioField,
} from "./types";

const POLL_MS = 500;

export interface RunnerState {
  status: RunStatus | "idle";
  runId: string | null;
  progress: number;
  error: string | null;
  fieldErrors: Partial<Record<ScenarioField, string>>;
}

const IDLE: RunnerState = {
  status: "idle",
  runId: null,
  progress: 0,
  error: null,
  fieldErrors: {},
};

/**
 * Drives one run through queued -> running -> complete | failed | cancelled.
 *
 * Polling is used rather than SSE because the planned API only promises polling
 * or SSE ("If runs become asynchronous, return 202 and expose progress through
 * polling or server-sent events"). Swapping in SSE later touches this hook only.
 */
export function useRunner(onComplete: (summary: RunSummary) => void) {
  const [state, setState] = useState<RunnerState>(IDLE);
  const completeRef = useRef(onComplete);
  completeRef.current = onComplete;

  const active = state.status === "queued" || state.status === "running";

  const start = useCallback(async (request: RunRequest) => {
    setState({ ...IDLE, status: "queued" });
    try {
      const created = await api.createRun(request);
      setState({
        status: created.status,
        runId: created.run_id,
        progress: 0,
        error: null,
        fieldErrors: {},
      });
    } catch (caught) {
      const apiError = caught instanceof ApiError ? caught : null;
      // A rejected scenario or a busy worker is a problem with the request, not
      // a failed simulation: nothing ran, so the run status stays idle and the
      // message belongs on the form.
      const rejectedBeforeStarting =
        apiError?.code === "validation_failed" || apiError?.code === "conflict";
      setState({
        status: rejectedBeforeStarting ? "idle" : "failed",
        runId: null,
        progress: 0,
        error:
          apiError?.message ??
          "The run could not be started. The backend did not accept the request.",
        fieldErrors: apiError?.fields ?? {},
      });
    }
  }, []);

  const cancel = useCallback(async () => {
    const runId = state.runId;
    if (!runId) return;
    try {
      await api.cancelRun(runId);
      setState((prev) => ({ ...prev, status: "cancelled", progress: 0 }));
    } catch (caught) {
      setState((prev) => ({
        ...prev,
        error: caught instanceof ApiError ? caught.message : "Cancellation failed.",
      }));
    }
  }, [state.runId]);

  const reset = useCallback(() => setState(IDLE), []);

  useEffect(() => {
    if (!active || !state.runId) return;
    const runId = state.runId;
    let stopped = false;

    const tick = async () => {
      try {
        const summary = await api.run(runId);
        if (stopped) return;
        setState((prev) => ({
          ...prev,
          status: summary.status,
          progress:
            summary.progress ??
            (summary.status === "complete"
              ? 1
              : summary.status === "running"
                ? Math.min(0.95, Math.max(prev.progress, 0.1))
                : prev.progress),
          error:
            summary.status === "failed"
              ? (summary.error?.message ?? "The simulation failed.")
              : prev.error,
        }));
        if (summary.status === "complete") {
          completeRef.current(summary);
        }
      } catch (caught) {
        if (stopped) return;
        setState((prev) => ({
          ...prev,
          status: "failed",
          error:
            caught instanceof ApiError
              ? caught.message
              : "Lost contact with the backend while the run was in progress.",
        }));
      }
    };

    const timer = setInterval(() => void tick(), POLL_MS);
    void tick();
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [active, state.runId]);

  return { state, active, start, cancel, reset };
}
