# Phase 14 Browser WebRTC Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the UrbanTwin dashboard show a live Kit WebRTC stream when the Phase 13 streaming host is up, via the existing ViewerAdapter seam.

**Architecture:** Python `live_stream_config` / `live_health` probe the local Kit signaling port and return public DIRECT connection fields only when reachable. The frontend installs NVIDIA’s WebRTC client and completes `kit-webrtc-adapter.ts` so `OmniverseViewer` receives a real MediaStream without layout rewrites.

**Tech Stack:** Python 3 stdlib (`api/`), Next.js 16, TypeScript, `@nvidia/ov-web-rtc` (or `@nvidia/omniverse-webrtc-streaming-library` fallback), NVIDIA scoped npm registry.

**Spec:** `docs/superpowers/specs/2026-09-20-phase14-browser-webrtc-design.md`

## Global Constraints

- Work only in worktree `C:\Users\arnav\Argus\.worktrees\phase13-streaming-kit` on branch `phase13-streaming-kit`.
- Never edit Argus `main` or `phase1/`–`phase8/` scene layers.
- Never present streaming as live unless health/stream config say so.
- No `NEXT_PUBLIC_*` infrastructure credentials.
- Do **not** create git commits unless the user explicitly asks (user rule overrides plan commit steps).
- View-command Kit delivery remains Phase 15.

## File map

| File | Responsibility |
|---|---|
| `api/stream_probe.py` | TCP probe + env defaults for local Kit ports |
| `api/shapes.py` | `live_stream_config` / `live_health` use probe results |
| `api/test_stream_probe.py` | Unit tests for probe + available/offline envelopes |
| `api/test_shapes.py` / `api/test_server.py` | Update expectations for conditional streaming |
| `integration/export_api_mocks.py` | Keep fixture offline; optional helper for available envelope used only by live path |
| `frontend/lib/types.ts` | Optional host/port fields on `StreamConfig` |
| `frontend/.npmrc` | `@nvidia` registry scope |
| `frontend/package.json` | NVIDIA WebRTC dependency |
| `frontend/lib/viewer/kit-webrtc-adapter.ts` | Real AppStreamer connect + MediaStream |
| `frontend/tests/kit-webrtc-adapter.test.mjs` | Adapter selection + offline/available behavior (mock SDK if needed) |
| `docs/PHASE14_BROWSER_WEBRTC.md` | Operator steps |
| `docs/PHASE13_STREAMING_KIT.md` | Point Next → Phase 14 |
| `CLAUDE.md` | Honest Phase 14 note |

---

### Task 1: Stream probe + live stream/health shapes

**Files:**
- Create: `api/stream_probe.py`
- Create: `api/test_stream_probe.py`
- Modify: `api/shapes.py`
- Modify: `api/test_shapes.py`
- Modify: `api/test_server.py` (only if health assertions become conditional)

**Interfaces:**
- Produces:
  - `DEFAULT_STREAM_HOST = "127.0.0.1"`
  - `DEFAULT_SIGNAL_PORT = 49100`
  - `DEFAULT_MEDIA_PORT = 47998`
  - `probe_stream_endpoint(host=None, signal_port=None, timeout_s=0.35) -> dict` with keys:
    `available: bool`, `host: str`, `signal_port: int`, `media_port: int`, `reason: str | None`
  - `available_stream_config(checked_utc, probe: dict, *, source="live") -> dict`
  - `live_stream_config` and `live_health` call the probe

- [ ] **Step 1: Write failing tests in `api/test_stream_probe.py`**

```python
import socket
import unittest
from unittest import mock

from api import stream_probe


class StreamProbeTests(unittest.TestCase):
    def test_probe_reports_unavailable_when_port_closed(self):
        with mock.patch("api.stream_probe.socket.create_connection", side_effect=OSError("closed")):
            result = stream_probe.probe_stream_endpoint(host="127.0.0.1", signal_port=49100)
        self.assertFalse(result["available"])
        self.assertIn("not accepting", result["reason"].lower())

    def test_probe_reports_available_when_tcp_connects(self):
        with mock.patch("api.stream_probe.socket.create_connection") as conn:
            conn.return_value.__enter__ = mock.Mock(return_value=mock.Mock())
            conn.return_value.__exit__ = mock.Mock(return_value=False)
            result = stream_probe.probe_stream_endpoint(host="127.0.0.1", signal_port=49100)
        self.assertTrue(result["available"])
        self.assertEqual(result["signal_port"], 49100)
        self.assertEqual(result["media_port"], 47998)

    def test_force_env_skips_probe(self):
        with mock.patch.dict("os.environ", {"URBANTWIN_STREAM_FORCE": "1"}):
            with mock.patch("api.stream_probe.socket.create_connection") as conn:
                result = stream_probe.probe_stream_endpoint()
        conn.assert_not_called()
        self.assertTrue(result["available"])

    def test_available_stream_config_shape(self):
        probe = {
            "available": True,
            "host": "127.0.0.1",
            "signal_port": 49100,
            "media_port": 47998,
            "reason": None,
        }
        cfg = stream_probe.available_stream_config("2026-09-20T00:00:00+00:00", probe, source="live")
        self.assertEqual(cfg["status"], "available")
        self.assertEqual(cfg["signaling_host"], "127.0.0.1")
        self.assertEqual(cfg["signaling_port"], 49100)
        self.assertEqual(cfg["media_port"], 47998)
        self.assertEqual(cfg["signaling_url"], "http://127.0.0.1:49100")
        self.assertIsInstance(cfg["session_token"], str)
        self.assertTrue(len(cfg["session_token"]) >= 16)
```

Also add/adjust in `api/test_shapes.py`:

```python
def test_live_stream_config_offline_by_default(self):
    with mock.patch("api.shapes.probe_stream_endpoint", return_value={
        "available": False, "host": "127.0.0.1", "signal_port": 49100,
        "media_port": 47998, "reason": "Kit signaling port is not accepting connections.",
    }):
        from api.shapes import live_stream_config
        cfg = live_stream_config("2026-09-20T00:00:00+00:00")
    self.assertEqual(cfg["status"], "offline")
    self.assertIsNone(cfg["signaling_url"])
```

- [ ] **Step 2: Run tests — expect FAIL (module missing)**

Run: `python -m unittest api.test_stream_probe -v`
Expected: FAIL / ImportError for `api.stream_probe`

- [ ] **Step 3: Implement `api/stream_probe.py` and wire `api/shapes.py`**

```python
# api/stream_probe.py — essential behavior
import os
import secrets
import socket

DEFAULT_STREAM_HOST = "127.0.0.1"
DEFAULT_SIGNAL_PORT = 49100
DEFAULT_MEDIA_PORT = 47998


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def probe_stream_endpoint(host=None, signal_port=None, media_port=None, timeout_s=0.35) -> dict:
    host = host or os.environ.get("URBANTWIN_STREAM_HOST", DEFAULT_STREAM_HOST).strip() or DEFAULT_STREAM_HOST
    signal_port = signal_port if signal_port is not None else _env_int("URBANTWIN_STREAM_SIGNAL_PORT", DEFAULT_SIGNAL_PORT)
    media_port = media_port if media_port is not None else _env_int("URBANTWIN_STREAM_MEDIA_PORT", DEFAULT_MEDIA_PORT)
    if _env_bool("URBANTWIN_STREAM_FORCE"):
        return {"available": True, "host": host, "signal_port": signal_port, "media_port": media_port, "reason": None}
    try:
        with socket.create_connection((host, signal_port), timeout=timeout_s):
            pass
        return {"available": True, "host": host, "signal_port": signal_port, "media_port": media_port, "reason": None}
    except OSError:
        return {
            "available": False,
            "host": host,
            "signal_port": signal_port,
            "media_port": media_port,
            "reason": "Kit signaling port is not accepting connections. Launch urbantwin_streaming.kit first.",
        }


def available_stream_config(checked_utc, probe: dict, *, source="live") -> dict:
    host = probe["host"]
    signal_port = probe["signal_port"]
    media_port = probe["media_port"]
    return {
        "status": "available",
        "source": source,
        "checked_utc": checked_utc,
        "signaling_url": f"http://{host}:{signal_port}",
        "signaling_host": host,
        "signaling_port": signal_port,
        "media_host": host,
        "media_port": media_port,
        "ice_servers": [],
        "session_token": secrets.token_urlsafe(24),
        "stage": "phase9/scene/main.usda",
        "desktop_fallback": ".\\repo.bat launch -n urbantwin.kit",
        "references": [
            "https://docs.omniverse.nvidia.com/ov-web-sdk/latest/index.html",
            "https://docs.omniverse.nvidia.com/kit/docs/kit-app-template/108.0/docs/streaming.html",
        ],
    }
```

In `api/shapes.py`, import probe helpers and:

```python
def live_stream_config(checked_utc) -> dict:
    probe = probe_stream_endpoint()
    if probe["available"]:
        return available_stream_config(checked_utc, probe, source="live")
    cfg = stream_config_fixture(checked_utc, source="live")
    cfg["reason"] = probe["reason"] or cfg.get("reason")
    cfg["signaling_host"] = None
    cfg["signaling_port"] = None
    cfg["media_host"] = None
    cfg["media_port"] = None
    return cfg


def live_health(checked_utc) -> dict:
    health = health_fixture(checked_utc, source="live")
    probe = probe_stream_endpoint()
    if probe["available"]:
        health["omniverse_stream"] = "online"
        health["capabilities"]["omniverse_streaming"] = True
        health["notes"] = list(health.get("notes") or []) + [
            "Local Kit signaling port is accepting connections; browser WebRTC still requires the Phase 14 client.",
        ]
    return health
```

Keep `stream_config_fixture` offline for mocks. Optionally append null host/port keys there for schema stability.

- [ ] **Step 4: Run tests — expect PASS**

Run:
```
python -m unittest api.test_stream_probe api.test_shapes api.test_server -v
```
Expected: PASS. If `test_server` assumed streaming always offline, patch probe to unavailable in those tests or assert conditional behavior.

- [ ] **Step 5: Skip commit** (user rule) — leave changes unstaged for operator review.

---

### Task 2: Frontend StreamConfig types + NVIDIA package scaffold

**Files:**
- Modify: `frontend/lib/types.ts` (`StreamConfig`)
- Create: `frontend/.npmrc`
- Modify: `frontend/package.json` / lockfile via npm install
- Modify: `frontend/mocks/stream-config.json` (add null host/port keys)

**Interfaces:**
- Extends `StreamConfig` with:
  - `signaling_host: string | null`
  - `signaling_port: number | null`
  - `media_host: string | null`
  - `media_port: number | null`

- [ ] **Step 1: Update types and fixture JSON**

```ts
export interface StreamConfig {
  status: "offline" | "available";
  source: PayloadSource;
  checked_utc: string;
  signaling_url: string | null;
  /** EXTENSION: DIRECT Kit host/ports for local AppStreamer. */
  signaling_host?: string | null;
  signaling_port?: number | null;
  media_host?: string | null;
  media_port?: number | null;
  ice_servers: RTCIceServerLike[];
  session_token: string | null;
  stage: string;
  reason?: string;
  desktop_fallback?: string;
  references?: string[];
}
```

Fixture: set the four new fields to `null`.

- [ ] **Step 2: Add `.npmrc` and install client**

`frontend/.npmrc`:
```
@nvidia:registry=https://edge.urm.nvidia.com/artifactory/api/npm/omniverse-client-npm/
```

Run from `frontend/`:
```
npm install @nvidia/ov-web-rtc
```
If that package 404s, fall back to:
```
npm install @nvidia/omniverse-webrtc-streaming-library
```
Record which package landed in `docs/PHASE14_BROWSER_WEBRTC.md`.

If NVIDIA registry is unreachable from this environment, add a thin `frontend/lib/viewer/nvidia-streamer.ts` facade with the expected import path and document the install as a manual operator step — adapter must still compile via dynamic `import()` guarded by try/catch reporting failed with a clear message. Prefer real install when network works.

- [ ] **Step 3: Skip commit**

---

### Task 3: Complete `kit-webrtc-adapter.ts`

**Files:**
- Modify: `frontend/lib/viewer/kit-webrtc-adapter.ts`
- Create: `frontend/tests/kit-webrtc-adapter.test.mjs` (or extend selection tests)
- Modify: `frontend/lib/viewer/index.ts` only if needed (selection logic already correct)

**Interfaces:**
- Consumes: `StreamConfig` with host/ports when `status === "available"`
- Produces: `ViewerConnection` that terminates AppStreamer on `close()`
- Must call `onState({ status: "connected", stream: MediaStream, ...})` only after media is active

- [ ] **Step 1: Write a small Node test for selection + offline branch**

`frontend/tests/kit-webrtc-adapter.test.mjs` can import compiled logic if the repo already uses plain `.mjs` tests (see `tests/layout-readability.test.mjs`). Prefer testing `selectViewerAdapter` with available vs offline configs without loading the NVIDIA SDK:

```js
import assert from "node:assert/strict";
import { selectViewerAdapter } from "../lib/viewer/index.ts"; // or duplicate the pure predicate in a tiny helper if TS import is awkward

const offline = { status: "offline", signaling_url: null };
const available = {
  status: "available",
  signaling_url: "http://127.0.0.1:49100",
  signaling_host: "127.0.0.1",
  signaling_port: 49100,
  media_host: "127.0.0.1",
  media_port: 47998,
};
```

If importing TS from Node is painful, add `frontend/lib/viewer/select.ts` with the pure function and test that. Keep `index.ts` re-exporting it.

- [ ] **Step 2: Implement the adapter**

Behavior:

1. If `config.status !== "available"` or missing host/ports → same offline path as today.
2. `onState(connecting)`.
3. Create off-DOM `<video id="urbantwin-kit-stream" autoplay playsInline muted>`.
4. Dynamic-import NVIDIA client.
5. `new AppStreamer()` (preferred) or static `AppStreamer.connect` if that is what the installed package exports.
6. Connect with `StreamType.DIRECT` and config:
   - `signalingServer` / `signalingPort` / `mediaServer` / `mediaPort` from StreamConfig
   - `videoElementId: "urbantwin-kit-stream"`
   - `authenticate: false`
   - `autoLaunch: true`
   - `sessionId: config.session_token ?? "local"`
   - `onStart`: read `video.srcObject`; if MediaStream, `onState(connected, stream)`; else `failed`
   - `onStop` / stream failure → `onState(failed|offline)`
7. Honor `signal` abort → terminate and cleanup.
8. `send()` still posts allow-listed view via `sendAllowListedViewCommand` but returned `delivered` reflects API truth (undelivered until Phase 15).
9. `close()` → `terminate()` / disconnect and remove the off-DOM video.

If the installed SDK’s API differs (field names), adapt to the package’s types; do not invent a fake MediaStream.

- [ ] **Step 3: Run frontend tests / typecheck**

```
cd frontend
node --test tests/kit-webrtc-adapter.test.mjs
npx tsc --noEmit
```
Expected: PASS (or document SDK-blocked compile error with exact message).

- [ ] **Step 4: Skip commit**

---

### Task 4: Operator docs + CLAUDE honesty

**Files:**
- Create: `docs/PHASE14_BROWSER_WEBRTC.md`
- Modify: `docs/PHASE13_STREAMING_KIT.md` (Next section → Phase 14 done pointer)
- Modify: `CLAUDE.md` integrity / commands for Phase 14
- Modify: `docs/FRONTEND_BACKEND_HANDOFF.md` only the streaming “not configured” bullets that Phase 14 changes — stay precise

- [ ] **Step 1: Write operator doc covering**

1. Launch Kit: `launch_urbantwin_streaming.bat`
2. Launch API: `python -m api --host 127.0.0.1 --port 8000`
3. Frontend: `$env:URBANTWIN_API_BASE="http://127.0.0.1:8000"; npm run dev`
4. Verify `GET http://127.0.0.1:8000/api/stream/config` shows `available` when Kit is up
5. Chromium required; mock mode still offline
6. Env table from the design
7. What is still Phase 15 (view commands)

- [ ] **Step 2: Update CLAUDE.md** — claim only what tests prove; do not claim continuous Omniverse streaming in production.

- [ ] **Step 3: Skip commit**

---

### Task 5: End-to-end smoke (best effort on this machine)

**Files:** none required

- [ ] **Step 1:** If Kit PID is listening on 49100, run:
```
python -c "from api.stream_probe import probe_stream_endpoint; print(probe_stream_endpoint())"
python -m unittest api.test_stream_probe api.test_shapes -v
```
- [ ] **Step 2:** Curl/fetch stream config against a short-lived `python -m api` if ports free.
- [ ] **Step 3:** Record results in `docs/PHASE14_BROWSER_WEBRTC.md` smoke section (pass or exact blocker).

---

## Self-review

1. Spec coverage: probe, health flip, adapter MediaStream, offline honesty, branch isolation, no view delivery — each has a task.
2. No TBD placeholders in steps.
3. Types: `signaling_host/port`, `media_host/port` consistent across Python + TS.
