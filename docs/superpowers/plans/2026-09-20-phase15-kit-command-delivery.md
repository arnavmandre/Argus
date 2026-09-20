# Phase 15 Kit Command Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or execute inline. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Allow-listed Camera / Overlay / Before-After controls change the live Kit stream.

**Architecture:** API allow-lists POST `/view`. Connected `kit-webrtc-adapter` then `AppStreamer.sendMessage({event_type:"urbantwin.view_command", payload})`. Kit extension `urbantwin.view_commands` + `omni.kit.livestream.messaging` applies camera/overlay/state. Never open arbitrary paths from the browser.

**Tech Stack:** Kit Python extension, `omni.kit.livestream.messaging`, `@nvidia/ov-web-rtc` sendMessage, Python `api/`, Next.js adapter.

**Spec:** `docs/superpowers/specs/2026-09-20-phase15-kit-command-delivery-design.md`

## Global Constraints

- Work only in Argus worktree `C:\Users\arnav\Argus\.worktrees\phase13-streaming-kit` and Kit repo branch `phase13-streaming-kit`.
- Do not edit `phase1/`–`phase8/`. Phase9 camera regen OK.
- Do not git commit unless user asked (they did not — skip commits).
- Do not merge to `main`.
- Unknown values rejected at API before any Kit message.

---

### Task 1: Cameras Street + Aerial prims

**Files:** Modify `phase9/make_cameras.py`, regenerate `phase9/scene/cameras.usda` (in worktree and/or Argus main path used by Kit: `C:\Users\arnav\Argus\phase9` — Kit loads from Argus main checkout path in launch bat).

- [ ] Add Street (street-level, same as Corridor eye/target) and Aerial (high overview) shots to SHOTS
- [ ] Run `python phase9/make_cameras.py` from Argus root that Kit uses (`C:\Users\arnav\Argus`) so streaming Kit sees new prims
- [ ] Keep Overview, Corridor, ProblemZone

### Task 2: Kit extension `urbantwin.view_commands`

**Files:** Create under `C:\Users\arnav\omniverse\kit-app-template\source\extensions\urbantwin.view_commands\` (mirror `urbantwin.stage_autoload` layout).

- [ ] `config/extension.toml` — no hard deps that break resolve (empty `[dependencies]`)
- [ ] Extension observes inbound `urbantwin.view_command` via `omni.kit.livestream.messaging` if importable; else subscribe to carb event bus receive path
- [ ] Handler allow-list again: cameras `{Overview,Street,ProblemZone,Aerial}`, overlays `{behavior,congestion,shade,none}`, states `{before,after}`
- [ ] Camera: set active viewport camera to `/World/Cameras/{name}` using viewport utility
- [ ] Overlay: best-effort toggle — if `/World` children or known overlay prims missing, log and skip
- [ ] State: best-effort set custom metadata or visibility; if only one agent layer, log
- [ ] Update `launch_urbantwin_streaming.bat` to also `--enable urbantwin.view_commands`
- [ ] Add `omni.kit.livestream.messaging` to `urbantwin_streaming.kit` dependencies (may need rebuild — if resolve fails, enable via CLI only like stage_autoload)

### Task 3: API view response for Phase 15

**Files:** `api/server.py`, `api/test_server.py`

- [ ] Change undelivered reason: when stream probe available, return `accepted: true`, `delivered: false`, `delivery: "webrtc_client"`, reason that client must send on WebRTC after allow-list (adapter marks delivered)
- [ ] Or simpler: keep API as allow-list only; adapter does allow-list via api.view then sendMessage and returns delivered true/false to UI
- [ ] Update tests: accepted true; delivered still false from API alone; new field `delivery: "webrtc_client"` optional

### Task 4: Frontend delivery path

**Files:** `kit-webrtc-adapter.ts`, `OmniverseViewer.tsx`

- [ ] Hold `streamer` ref on connection; `send()`: call `api.view` first; if accepted and streamer live, `await streamer.sendMessage({event_type, payload})` (ApplicationMessage shape per ov-web-rtc); return `delivered: true` on success
- [ ] OmniverseViewer `sendCommand` must use `connectionRef.current?.send(next)` not raw `api.view` only
- [ ] capabilities.messaging true when connected

### Task 5: Docs

- [ ] `docs/PHASE15_KIT_COMMAND_DELIVERY.md`
- [ ] Update PHASE14 next pointer, CLAUDE.md, FRONTEND_BACKEND_HANDOFF view bullets

---

## Phase 16 plan (execute after 15)

**Goal:** Optional LLM explanation over bounded structured payload; degrade if unavailable.

**Files:** `api/explain.py`, `POST /api/runs/{id}/explain` or include in run summary; frontend AdvisorPanel optional section.

**Rules:** Prompt may only receive metrics, advisor recommendations, problem lists already in report. Strip/refuse new locations/metrics. Env `URBANTWIN_LLM_BASE` / off by default.

## Phase 17 plan (execute after 16)

**Goal:** One launcher + runbook for judge demo.

**Files:** `tools/demo_launch.ps1` (or `demo/launch_demo.ps1`), `docs/DEMO_RUNBOOK.md`, smoke script checking health/stream/config/view allow-list.
