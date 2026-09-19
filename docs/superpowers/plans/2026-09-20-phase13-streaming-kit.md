# Phase 13 Streaming Kit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `urbantwin_streaming.kit` in the external Kit App Template and document local streaming verification against the Phase 9 stage—without touching Argus `main` or the dashboard.

**Architecture:** Streaming is a Kit application layer that depends on the existing `urbantwin` base app plus `omni.kit.livestream.app`. Stage loading is supplied at launch via `--/app/auto_load_usd`. Argus only receives design/plan/operator docs on branch `phase13-streaming-kit`.

**Tech Stack:** Omniverse Kit App Template (Kit 110.3), `omni.kit.livestream.app`, NVIDIA web-viewer-sample (verification client), PowerShell launch scripts.

**Spec:** `docs/superpowers/specs/2026-09-20-phase13-streaming-kit-design.md`

## Global Constraints

- Never edit Argus Phase 1–8 scene layers.
- Do not merge to Argus `main` in this phase unless the human explicitly asks.
- Do not flip frontend `stream/config` to available or change dashboard components.
- Do not invent a second city/stage path; use `phase9/scene/main.usda`.
- Prefer NVIDIA’s `{app}_streaming.kit` naming so `repo.bat launch` discovers the app.
- Document absolute Windows paths as examples; keep `.kit` free of machine-specific Absolute paths.

---

## File Structure

### Kit App Template (`C:\Users\arnav\omniverse\kit-app-template`, branch `phase13-streaming-kit`)

- Create: `source/apps/urbantwin_streaming.kit`
- Create: `launch_urbantwin_streaming.bat` (convenience wrapper)
- Modify if needed: `urbantwin_playback.toml` notes only

### Argus (`C:\Users\arnav\Argus\.worktrees\phase13-streaming-kit`, branch `phase13-streaming-kit`)

- Create: `docs/superpowers/specs/2026-09-20-phase13-streaming-kit-design.md`
- Create: `docs/superpowers/plans/2026-09-20-phase13-streaming-kit.md` (this file)
- Create: `docs/PHASE13_STREAMING_KIT.md`
- Modify: `CLAUDE.md` commands section (branch only) — point to streaming launch

---

### Task 1: Create the streaming Kit layer

**Files (Kit repo):**
- Create: `source/apps/urbantwin_streaming.kit`

- [ ] **Step 1: Write `urbantwin_streaming.kit` from the default streaming template**

Instantiate `templates/apps/streaming_configs/default_stream.kit` with:

- `application_name` → `urbantwin`
- `application_display_name` → `UrbanTwin AI`
- `version` → `0.1.0`

Add livestream-friendly settings used by USD Viewer streaming samples where applicable:

```toml
[settings]
app.livestream.allowResize = 1
app.livestream.skipCapture = 1
```

Keep dependency on `"urbantwin" = {}` and `"omni.kit.livestream.app" = {}`.

- [ ] **Step 2: Commit on the Kit branch**

```powershell
cd C:\Users\arnav\omniverse\kit-app-template
git add source/apps/urbantwin_streaming.kit
git commit -m "Add UrbanTwin streaming Kit application layer"
```

(If `source/` was previously untracked, add only the streaming kit plus any already-required `urbantwin.kit` the layer depends on—do not commit unrelated build artifacts.)

---

### Task 2: Launch wrapper and build/smoke

**Files (Kit repo):**
- Create: `launch_urbantwin_streaming.bat`

- [ ] **Step 1: Add a wrapper that auto-loads the Phase 9 stage**

```bat
@echo off
setlocal
set STAGE=C:\Users\arnav\Argus\phase9\scene\main.usda
cd /d "%~dp0"
call .\repo.bat launch -n urbantwin_streaming.kit -- --no-window --/app/auto_load_usd="%STAGE%"
```

- [ ] **Step 2: Build if required**

```powershell
.\repo.bat build
```

- [ ] **Step 3: Attempt launch smoke**

Launch the wrapper (or equivalent `repo.bat launch`). Record whether:

1. the process starts;
2. the livestream extension loads;
3. the stage path is accepted.

If GPU/driver/SDK blocks connection, capture the exact error in the Argus operator doc rather than claiming success.

- [ ] **Step 4: Commit wrapper + any build-required kit fixes on the Kit branch**

---

### Task 3: Argus operator documentation (branch only)

**Files (Argus worktree):**
- Create: `docs/PHASE13_STREAMING_KIT.md`
- Modify: `CLAUDE.md` (commands)
- Commit design + plan + docs on `phase13-streaming-kit` only

- [ ] **Step 1: Write the operator runbook**

Must include:

- Kit branch and file names;
- build/launch commands including `--no-window` and `auto_load_usd`;
- how to connect NVIDIA `web-viewer-sample` (stream only);
- explicit statement that Argus dashboard / `stream/config` remain offline until Phase 14;
- recovery tips (port in use, rebuild after kit change, wrong stage path).

- [ ] **Step 2: Commit on Argus branch**

```powershell
cd C:\Users\arnav\Argus\.worktrees\phase13-streaming-kit
git add docs CLAUDE.md
git commit -m "Document Phase 13 streaming Kit setup"
```

## Phase 13 Completion Gate

- Kit branch contains `urbantwin_streaming.kit` and launch wrapper.
- Argus branch (not `main`) contains design, plan, and `PHASE13_STREAMING_KIT.md`.
- Smoke evidence or a precise blocker is recorded.
- No Argus dashboard or API capability flips.
- Argus `main` unchanged.
