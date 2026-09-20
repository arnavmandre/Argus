# Handoff — Phase 13–17 streaming / UI interaction (2026-09-20)

**For:** Claude (or next agent) picking up UrbanTwin streaming work.  
**From:** Cursor session on branch `phase13-streaming-kit`.  
**User status (original):** Still cannot meaningfully interact with the streamed simulation. Do **not** merge to `main`. Do **not** commit unless the user asks.

> **UPDATE, later 2026-09-20: the user asked for this to be committed to `main`, and the
> interaction problems below were diagnosed and fixed. Read "Resolution" first; the
> sections after it describe the state BEFORE the fixes and are kept for history.**

Prior chat transcript (local):  
[Visual gap adjustment](cf4a608a-8b08-4a1f-93a3-3bf2b3b68ab7)

---

## Resolution (read this first)

**Important: half of the fix lives OUTSIDE this repo.** The Kit-side changes are in
`C:\Users\arnav\omniverse\kit-app-template` (branch `phase13-streaming-kit`), not in Argus.
Landing Argus on `main` does not by itself reproduce a working stream.

| Symptom | Actual cause | Where fixed |
| --- | --- | --- |
| Viewport "Failed", `srcObject was null`, header says stream online | **Ghost listener on :49100.** Closing Kit's window left an orphaned `hub.exe` holding the dead Kit's socket. The probe only does a TCP connect, so it still reported "online". | Ops. Stop with `Get-Process kit,hub \| Stop-Process -Force`, never by closing the window. |
| Buttons "delivered" but nothing happens | `omni.kit.livestream.messaging` was never a dependency, so it was never loaded. | Kit repo: `urbantwin_streaming.kit` and `urbantwin.view_commands/config/extension.toml` |
| Even with messaging loaded, commands dropped | The `observe` callback receives a `carb.eventdispatcher.Event`, not a dict; the handler logged `ignored non-dict payload`. | Kit repo: `urbantwin.view_commands/.../extension.py` |
| Mouse orbit/zoom did nothing | `AppStreamer` binds input to the element named by `videoElementId`; that element was `display: none`. | This repo: `OmniverseViewer.tsx`, `kit-webrtc-adapter.ts` |
| Picture cropped, editor UI in the stream | `omni.kit.livestream.app` streams the whole app framebuffer, and `object-cover` cropped a stretched box. | Kit repo `urbantwin.stage_autoload` hides the editor chrome; this repo uses a fixed 16:9 box |
| GPU pinned at 100% / 78 C, HUD showing 240 fps | Saved user config persisted `tickRate=120`, and DLSS Frame Generation doubled it. | Kit repo: `dlssg` off in the `.kit`; `tickRate=30` forced on the launch command line |

**Verified in Kit's own log**, not just in the UI: real browser clicks arrive
(`Processing custom kit message`), and a Kit-side self-test showed `viewport camera ->
/World/Cameras/Street` and `demoState -> Intervention`. Enable the self-test with
`--/exts/urbantwin.view_commands/selfTest=true`.

**Before/After** now switches the existing Phase 8 `demoState` variant (Stressed / Intervention)
on the session layer. It is a stress-versus-proposal comparison, **not** a measured improvement.

**Still open:** GPU is ~60% while streaming (RTX Real-Time 2.0 at 720p30; the classic mode is
disabled in the saved config, so it was not switched); there is a 4 px strip at the top of the
frame; mouse orbit still works though the user later asked for view-only; scenario sliders still
affect only the next pipeline run, not the live stage.

**Launch (headless, the cool configuration):** `launch_urbantwin_streaming.bat` in the Kit repo.
Logs are in `~\.nvidia-omniverse\logs\Kit\UrbanTwin AI Streaming\0.1\`, not under `_build\`.

---

## Where the code lives

| Tree | Path | Branch |
| --- | --- | --- |
| Argus worktree (all API/frontend/docs for 13–17) | `C:\Users\arnav\Argus\.worktrees\phase13-streaming-kit` | `phase13-streaming-kit` |
| Argus main checkout | `C:\Users\arnav\Argus` | `main` — **leave alone** |
| Kit App Template | `C:\Users\arnav\omniverse\kit-app-template` | `phase13-streaming-kit` |

Worktree HEAD commit: `4e1a12c` (*Document Phase 13 streaming Kit setup*). **Everything Phase 14–17 + the reconnect fix is uncommitted** (large dirty tree + untracked files). Treat the working tree as the source of truth, not the last commit.

Kit launch bat loads the **main** Argus stage, not the worktree:

```bat
STAGE=C:/Users/arnav/Argus/phase9/scene/main.usda
```

Cameras `Street` / `Aerial` currently exist on **both** main and worktree `phase9/scene/cameras.usda`, but any future scene edits in the worktree will **not** appear in Kit until `STAGE` is pointed at the worktree (or changes are copied to main’s `phase9/`).

---

## What the user is seeing

1. Header can show **Live backend** + **Omniverse stream online** while the viewport stays on **Connecting to local Kit App Streaming…** (probe ≠ WebRTC connected).
2. After **Run simulation**, the 3D view vanished / stuck reconnecting.
3. Camera / Overlay / Before–After (and expectation of “interacting with the simulation”) do not visibly drive Kit.

Clarify product semantics when debugging:

- **Scenario sliders** (temp/humidity/rain/population) only affect the **next** Phase 11 pipeline run. They do **not** live-update the USD stage.
- **Viewport controls** (Before/After, Camera, Overlay) are Phase 15: allow-list via API, then `AppStreamer.sendMessage` → Kit `urbantwin.view_commands`.
- Metrics cards update from the run summary JSON; they are independent of whether Kit applied a view command.

---

## What was already implemented (phases)

Documented under `docs/`:

| Doc | Status |
| --- | --- |
| `PHASE13_STREAMING_KIT.md` | Kit host `urbantwin_streaming.kit`, `--no-window`, ports 49100 / media |
| `PHASE14_BROWSER_WEBRTC.md` | `@nvidia/ov-web-rtc`, `stream_probe`, adapter select — **note:** older text still says view commands are discarded; Phase 15 superseded that |
| `PHASE15_KIT_COMMAND_DELIVERY.md` | Allow-list + WebRTC `sendMessage` + Kit extension |
| `PHASE16_CONSTRAINED_LLM.md` | `/explain` deterministic by default |
| `DEMO_RUNBOOK.md` + `tools/demo_launch.ps1` | Phase 17 launcher / smoke |

Design specs: `docs/superpowers/specs/2026-09-20-phase1{4,5,6,7}-*.md`.

### Argus (worktree) — key files

- `api/stream_probe.py` — TCP probe → `/api/stream/config`
- `api/server.py` — live runs; view endpoint; **recent:** allows `run_id == "viewport"` without a stored run
- `api/run_manager.py` — single-worker Phase 11 runs + progress
- `api/explain.py` — Phase 16
- `frontend/lib/viewer/kit-webrtc-adapter.ts` — DIRECT WebRTC; `sendAllowListedViewCommand` → `streamer.sendMessage({ event_type: "urbantwin.view_command", payload })`
- `frontend/lib/viewer/select.ts` — Kit adapter only when config `available`
- `frontend/components/OmniverseViewer.tsx` — **recent fix:** connect effect must **not** depend on `runId` (reconnect-on-run bug); uses `runIdRef` + `getRunId()`
- `frontend/lib/viewer/adapter.ts` — `getRunId?: () => string` on connect context
- `tools/demo_launch.ps1`, `tools/demo_smoke.py`

### Kit — key files (untracked / dirty under kit-app-template)

- `launch_urbantwin_streaming.bat` — `--enable urbantwin.stage_autoload` + `--enable urbantwin.view_commands`
- `source/extensions/urbantwin.stage_autoload/` — opens stage after startup (editor ignores `auto_load_usd` alone)
- `source/extensions/urbantwin.view_commands/urbantwin/view_commands/extension.py` — maps camera/overlay/state
- `source/apps/urbantwin_streaming.kit` — **does not** declare `omni.kit.livestream.messaging` in `[dependencies]` (comment only)

---

## Bug already patched (uncommitted) — stream vanishes on Run

**Cause:** `OmniverseViewer` `useEffect(..., [adapter, config, runId, attempt])` aborted WebRTC whenever a simulation finished and `runId` changed. Video unmounted (`connected && stream`), UI stuck Connecting; commands gated on `runId` / missing connection.

**Fix in tree:**

1. Drop `runId` from connect deps; keep `[adapter, config, attempt]`.
2. Pass `getRunId: () => runIdRef.current ?? "viewport"`.
3. Always `connection.send(...)` (no early return when `runId` is null).
4. API `_handle_view`: allow `run_id == "viewport"`; still 404 unknown real run ids.
5. Adapter `inertConnection` / live `send` resolve run id via `resolveRunId()`.

**Verified:**  
`python -m unittest api.test_server.ServerContractTests.test_view_allow_list_and_undelivered -v` (includes viewport + missing-run cases)  
`npx tsc --noEmit` in `frontend/` — OK.

User said after that fix they **still** cannot interact — so reconnect was necessary but **not sufficient**.

---

## Open problem — interaction still broken (start here)

Highest-likelihood gaps, in order:

### 1. WebRTC never reaches `connected` (or flaps)

Probe can report stream **online** while `AppStreamer.connect` never fires `EventStatus.SUCCESS` / media never attaches. UI then never has a live `streamer` for `sendMessage`.

**Check:**

- Chromium (Chrome/Edge), not Firefox.
- Viewport chip is **Live**, not Connecting/Failed.
- Footer line under viewport after a control change: `delivered: true` vs `not delivered` + reason.
- DevTools Network: `POST /api/runs/.../view` → 200 `accepted: true`.
- Kit log: livestream ready; no terminate storm.

Known earlier hang: do **not** pass a fabricated `sessionId` to local DIRECT streaming (adapter already omits it).

### 2. Messages never reach `urbantwin.view_commands`

Extension prefers `omni.kit.livestream.messaging.observe("urbantwin.view_command")`. If that import fails, it falls back to **carb event bus**, which **does not** receive NVIDIA WebRTC data-channel messages.

`urbantwin_streaming.kit` only **comments** that messaging should be enabled; it is **not** in `[dependencies]`. Empty `[dependencies]` in `view_commands/config/extension.toml`.

**Likely next work:** get `omni.kit.livestream.messaging` onto the running streaming app (`.kit` dependency + lock resolve, or confirmed enable via livestream stack), confirm Kit log line:

`urbantwin.view_commands: listening via messaging.observe(...)`

Then change Camera in UI and look for:

`urbantwin.view_commands: viewport camera -> /World/Cameras/...`

If UI says `delivered: true` but Kit never logs apply → message format / observe API mismatch (inspect `@nvidia/ov-web-rtc` `sendMessage` shape vs Kit observe payload).

### 3. Even when messages arrive, some commands are weak / no-ops

In `extension.py`:

- **Camera** — real: sets `viewport.camera_path` if prim exists.
- **Overlay** — toggles `/World/Agents` / `/World/Routes` visibility; `shade` tries `cityLook` variant.
- **State before/after** — mostly **no-op**: reads `urbantwin:behaviorState` on `/World/Agents` and **warns** if requested state ≠ baked; does **not** swap `agents_before` / `agents_after` layers. User expectation of Before/After driving the twin is **unmet** by design of current Kit code.

So “can’t interact” may partly mean Before/After / scenario feel dead even when camera works.

### 4. Stage / agents freshness

Kit opens **main** `phase9/scene/main.usda`. Live API runs write under the **worktree** `data/runs/...`. Unless something republishes agents into the stage Kit has open, a finished Run updates **dashboard metrics** but **not** the streamed USD. That is a product gap separate from WebRTC messaging.

### 5. Process / port chaos (ops)

Earlier: port 3000 held by stray `python`+`node` (Access denied); user must `taskkill` or use `demo_launch.ps1 -Force`. Frontend without `URBANTWIN_API_BASE` is **mock** (fixtures) even if Kit is up.

---

## Suggested debug loop (do this before more features)

```powershell
cd C:\Users\arnav\Argus\.worktrees\phase13-streaming-kit
.\tools\demo_launch.ps1 -Force   # or manual: api :8000, Kit bat, frontend with URBANTWIN_API_BASE

Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/stream/config
# expect status available when Kit signaling listens

# Chromium → http://127.0.0.1:3000 (or 3001)
# Wait until viewport status = Live
# Change Camera; read footer delivered flag
# Tail Kit log for view_commands lines
```

Instrument if needed:

- Log in `sendAllowListedViewCommand` before/after `sendMessage`.
- Log raw payload in Kit `_on_view_command_payload`.
- Confirm which listener path registered (messaging vs event bus).

Acceptance for “interaction works”:

1. Viewport stays **Live** across a full Run (reconnect fix holds).
2. Camera change visibly moves streamed view; Kit logs camera apply.
3. Overlay change visibly toggles agents/routes (or honest UI message if layer missing).
4. Before/After either swaps real agent presentation **or** UI stops implying it does until Kit implements layer switch.
5. Invalid camera still HTTP 422; no arbitrary prim paths from browser.

---

## Constraints / hard rules

- Never edit `phase1/`–`phase8/` scene layers.
- Never auto-write `integration/route_mapping.json`.
- Do not claim Omniverse streaming on `main` / mock mode.
- Metrics remain heuristic prototypes; keep disclaimers.
- User asked not to commit earlier; still ask before committing this large dirty tree.
- Prefer extending existing files (`kit-webrtc-adapter`, `view_commands` extension, `demo_launch.ps1`) over parallel scripts.

---

## Quick file map for the next edit

| Symptom | First place to look |
| --- | --- |
| View vanishes on Run | `frontend/components/OmniverseViewer.tsx` connect deps (should already be fixed) |
| Controls say not delivered / no connection | `kit-webrtc-adapter.ts` connect / `publishStreamWhenReady` |
| `delivered: true` but no scene change | Kit `extension.py` + messaging dependency in `urbantwin_streaming.kit` |
| Before/After does nothing | `_apply_state` in `extension.py` (known weak) |
| Run metrics change, twin does not | STAGE path + pipeline publish into open stage |
| Header online, viewport Connecting | probe vs WebRTC; do not trust header alone |

---

## Commands cheat sheet

```powershell
# Worktree
cd C:\Users\arnav\Argus\.worktrees\phase13-streaming-kit
python -m api --host 127.0.0.1 --port 8000
$env:URBANTWIN_API_BASE = "http://127.0.0.1:8000"
cd frontend; npm run dev

# Kit
cd C:\Users\arnav\omniverse\kit-app-template
.\launch_urbantwin_streaming.bat

# Tests
cd C:\Users\arnav\Argus\.worktrees\phase13-streaming-kit
python -m unittest api.test_server.ServerContractTests.test_view_allow_list_and_undelivered -v
cd frontend; npx tsc --noEmit
python tools\demo_smoke.py   # needs API up
```

---

## Bottom line for Claude

Phases 13–17 are largely **coded but uncommitted** on the worktree + Kit branch. The reconnect-on-`runId` bug was fixed in the working tree; the user still cannot interact. Treat **inbound WebRTC → `urbantwin.view_commands`** (messaging extension actually loaded + payload applied) and **honest Before/After / stage refresh** as the remaining product blockers. Prefer proving one camera change end-to-end in Kit logs before polishing the dashboard.
