# Phase 17 — Demo hardening (design)

**Branch:** `phase13-streaming-kit` (worktree). **Not merged to `main`.**

## Goal

One launcher and one judge-facing runbook so a local demo starts the live stack
(Python API, streaming Kit, Next.js), verifies health, and documents recovery
without ad-hoc shell steps.

## Components

| Artifact | Purpose |
| --- | --- |
| `tools/demo_launch.ps1` | Start API (8000), Kit (49100 signaling), frontend (3000/3001); poll health + stream config; tee logs under `tools/demo_logs/`. |
| `tools/demo_smoke.py` | Stdlib contract smoke: health, stream config, short live run, view allow-list, optional explain. |
| `docs/DEMO_RUNBOOK.md` | Judge-facing prerequisites, ports, expected UI, honesty, recovery table. |

## Non-goals

- No process supervisor or cloud deploy.
- No change to frozen phase1–8 scene layers.
- Launcher does not kill existing listeners unless `-Force`.

## Success criteria

- Operator runs `.\tools\demo_launch.ps1` from the worktree root (or main repo with worktree present).
- Within ~90s, API health returns `mode: "live"`; stream config reflects Kit probe (available or honest offline).
- `python tools/demo_smoke.py` exits 0 against a running API.
- Runbook states mock vs live, heuristic metrics, and Kit relaunch for view delivery.

## Related phases

Phases 11–16 on this branch: pipeline API, WebRTC client, view commands, constrained explain. Phase 17 packages them for demo day.
