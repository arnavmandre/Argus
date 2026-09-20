#!/usr/bin/env python3
"""Stdlib smoke test for the UrbanTwin local judge demo API."""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_BASE = "http://127.0.0.1:8000"
RUN_POLL_INTERVAL = 2.0
RUN_TIMEOUT = 180.0


def _request(
    base: str,
    method: str,
    path: str,
    body: dict | None = None,
    timeout: float = 30.0,
) -> tuple[int, Any]:
    url = f"{base.rstrip('/')}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.URLError as exc:
        return 0, {"error": str(exc.reason)}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            payload = raw
        return exc.code, payload


def _check(label: str, ok: bool, detail: str = "") -> bool:
    mark = "PASS" if ok else "FAIL"
    line = f"  [{mark}] {label}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def run_smoke(base: str, *, skip_explain: bool) -> int:
    print(f"UrbanTwin demo smoke - {base}\n")
    all_ok = True

    status, health = _request(base, "GET", "/api/health")
    mode = (health or {}).get("mode") if isinstance(health, dict) else None
    all_ok &= _check(
        "GET /api/health",
        status == 200 and mode in ("live", "mock"),
        f"status={status}, mode={mode!r}",
    )

    status, stream = _request(base, "GET", "/api/stream/config")
    stream_status = (stream or {}).get("status") if isinstance(stream, dict) else None
    all_ok &= _check(
        "GET /api/stream/config",
        status == 200 and stream_status in ("available", "offline"),
        f"status={stream_status!r}",
    )

    run_body = {
        "temperature": 31,
        "humidity": 55,
        "rainfall": 12,
        "population": 42000,
        "apply_recommended_interventions": True,
        "animation_frames": 3,
        "animation_duration_seconds": 3,
    }
    status, created = _request(base, "POST", "/api/runs", run_body, timeout=60.0)
    run_id = (created or {}).get("run_id") if isinstance(created, dict) else None
    all_ok &= _check(
        "POST /api/runs",
        status == 202 and bool(run_id),
        f"status={status}, run_id={run_id!r}",
    )
    if not run_id:
        print("\nSmoke aborted: no run_id.")
        return 1

    deadline = time.time() + RUN_TIMEOUT
    final_status = None
    while time.time() < deadline:
        status, summary = _request(base, "GET", f"/api/runs/{run_id}")
        if status != 200 or not isinstance(summary, dict):
            time.sleep(RUN_POLL_INTERVAL)
            continue
        final_status = summary.get("status")
        if final_status in ("complete", "failed", "cancelled"):
            break
        time.sleep(RUN_POLL_INTERVAL)

    all_ok &= _check(
        "Poll run until terminal",
        final_status == "complete",
        f"last status={final_status!r} (timeout {RUN_TIMEOUT:.0f}s)",
    )

    view_body = {
        "state": "before",
        "camera": "Overview",
        "overlay": "behavior",
    }
    status, view = _request(base, "POST", f"/api/runs/{run_id}/view", view_body)
    accepted = (view or {}).get("accepted") if isinstance(view, dict) else None
    all_ok &= _check(
        "POST /api/runs/{id}/view (allow-list)",
        status == 200 and accepted is True,
        f"accepted={accepted!r}",
    )

    if not skip_explain:
        status, explain = _request(base, "POST", f"/api/runs/{run_id}/explain")
        source = (explain or {}).get("source") if isinstance(explain, dict) else None
        text = (explain or {}).get("text") if isinstance(explain, dict) else ""
        all_ok &= _check(
            "POST /api/runs/{id}/explain",
            status == 200 and source in ("deterministic", "llm") and bool(text),
            f"source={source!r}",
        )

    print()
    if all_ok:
        print("Checklist: all checks passed.")
        return 0
    print("Checklist: one or more checks failed.")
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smoke test UrbanTwin live API for judge demo readiness.",
    )
    parser.add_argument(
        "--base",
        default=DEFAULT_BASE,
        help=f"API base URL (default: {DEFAULT_BASE})",
    )
    parser.add_argument(
        "--skip-explain",
        action="store_true",
        help="Skip POST /api/runs/{id}/explain",
    )
    args = parser.parse_args()
    sys.exit(run_smoke(args.base, skip_explain=args.skip_explain))


if __name__ == "__main__":
    main()
