# UrbanTwin Live Integration Phases — Design

## Goal

Turn the current deterministic simulator, OpenUSD demo and recorded-fixture
Next.js dashboard into a reliable local judge-facing product on one Windows RTX
machine.

The target loop is:

```text
choose scenario -> run the real simulator -> export visual state ->
inspect the live Kit viewport -> receive deterministic suggestions ->
apply an intervention -> compare before and after
```

Production infrastructure is explicitly out of scope for this sequence.

## Current baseline

Already implemented:

- deterministic Python simulation over the OSM-backed city;
- survey-calibrated synthetic population;
- canonical snapshot exporter and validated simulator-to-USD boundary;
- Phase 9 OpenUSD city and behavior-colored agent animation;
- deterministic advisor and supported interventions;
- typed Next.js dashboard, mock API facade and truthful capability reporting;
- browser controls and server-side command allow-list.

The Next.js route handlers currently serve recorded fixtures or proxy to
`URBANTWIN_API_BASE`. They are not the Python simulation backend. The existing
NVIDIA adapter is an honest stub. The external `urbantwin.kit` is a desktop base
application, not a streaming application.

## Global constraints

1. Simulator metrics, problem locations and intervention effects remain
   authoritative. Neither the frontend nor an LLM may invent them.
2. Phase 1–8 scene layers remain frozen. Runtime visualization changes are
   Phase 9 overlays or generated layers.
3. The canonical v1 snapshot contract remains unchanged.
4. `integration/route_mapping.json` is never generated automatically.
5. Health endpoints determine capability labels; no build flag may present a
   mock capability as live.
6. The first target is one local Windows RTX machine. Authentication, durable
   storage, multi-user scheduling and TURN deployment are deferred.
7. Every phase ends with an executable acceptance check and a commit before the
   next phase begins.

## Phase 11 — One-command local orchestration

### Outcome

One command runs the existing real pipeline and produces a manifest describing
every generated artifact:

```text
simulation report
-> canonical before/after snapshot sequences
-> separate before/after agent USD layers
-> refreshed frontend API fixtures
-> validation results
-> run manifest
```

### Design

Add `integration/run_pipeline.py` as an orchestration boundary, not a second
implementation of simulation or export logic. It invokes the existing scripts,
captures duration and output paths, stops on the first failed stage and writes
the manifest atomically only after all required stages pass.

Enhance `phase9/agents_instancer.py` with an explicit `--out` argument so the
pipeline can preserve both `agents_before.usda` and `agents_after.usda` instead
of overwriting `agents.usda`.

The orchestrator accepts:

- citizen and city input paths;
- scenario values within the simulator's existing ranges;
- animation frame count and duration;
- run ID and output directory;
- a validation switch enabled by default.

The initial implementation may call scripts as subprocesses. It must not move
simulation formulas into the orchestrator.

### Acceptance gate

From repository root, one command must:

1. return exit code zero;
2. produce a real simulator report for the supplied scenario;
3. produce before and after canonical snapshots;
4. produce separate before and after agent USD layers;
5. refresh frontend fixtures from that report;
6. pass the existing integration validation;
7. write a machine-readable manifest with commands, artifacts, checks and
   timestamps;
8. leave the previously complete manifest intact if a later run fails.

## Phase 12 — Python HTTP API

### Outcome

A local Python service implements the contract already consumed by the Next.js
proxy routes.

### Boundaries

- The service owns validation, process execution, cancellation and in-memory
  run state.
- Phase 11 remains the execution engine.
- The Next.js app remains the browser-facing same-origin facade.
- Results are summaries by default; citizens remain paginated.

### Required endpoints

```text
GET    /api/health
GET    /api/scenarios
POST   /api/runs
GET    /api/runs/{run_id}
DELETE /api/runs/{run_id}
GET    /api/runs/{run_id}/citizens
GET    /api/model-card
GET    /api/stream/config
POST   /api/runs/{run_id}/view
```

### Acceptance gate

With `URBANTWIN_API_BASE` set, the existing frontend must run a scenario through
the Python service, show genuine scenario-specific results and show no recorded
fixture warning. Failure, cancellation, conflict and invalid-input paths must be
covered.

## Phase 13 — Streaming Kit application

### Outcome

Create `urbantwin.streaming.kit` in the external Kit app repository. It opens
`phase9/scene/main.usda`, enables the supported NVIDIA streaming extensions and
can be connected to by NVIDIA's reference client on the same machine.

### Acceptance gate

The streaming app launches independently, renders the correct stage and exposes
a reachable local streaming session. This phase does not modify the dashboard.

## Phase 14 — Browser WebRTC integration

### Outcome

Complete `frontend/lib/viewer/kit-webrtc-adapter.ts` behind the existing
`ViewerAdapter` interface. Add a local session/config provider that returns only
public signaling data and short-lived credentials.

### Acceptance gate

The browser receives a real MediaStream from Kit, reports connected only after
media is active, and handles offline, failed, reconnect and teardown states
without changing dashboard components.

## Phase 15 — Kit command delivery

### Outcome

Add a Kit messaging extension that maps the existing high-level command schema
to known states, cameras and overlays. The Python service forwards only commands
that pass the existing allow-list.

### Acceptance gate

Before/after, camera and overlay controls visibly change the live viewport.
Unknown values, paths and expressions are rejected before they reach Kit.

## Phase 16 — Constrained LLM explanations

### Outcome

Add an optional explanation service over a bounded structured payload containing
simulator results and deterministic advisor output.

The LLM may summarize causes, trade-offs and limitations. It may not produce new
metrics, affected locations, commands, supported interventions or effectiveness
claims. The deterministic advisor remains the source of recommendations.

### Acceptance gate

Every generated factual claim is traceable to supplied structured fields.
Unavailable LLM service degrades to the existing deterministic UI without
blocking a run.

## Phase 17 — Demo hardening

### Outcome

Provide one launcher and one runbook for the local judge demo.

It starts the Python API, streaming Kit app and Next.js frontend, performs health
checks, records logs and prints actionable recovery steps.

### Acceptance gate

A clean machine session can reach the full judge-facing loop using only the
documented launcher and runbook. A smoke test verifies simulation, result
display, stream connection and view commands.

## Deferred production and research work

The following are separate future tracks, not hidden requirements of Phases
11–17:

- authentication and authorization;
- durable database-backed run history;
- multi-user queue and GPU-worker scheduling;
- production TURN and network deployment;
- Random Forest inference in the simulator;
- uncertainty intervals;
- accessibility and emergency-access modeling;
- vehicles, cyclists and scheduled transit;
- CFD, UTCI/WBGT and hydraulic flood models.
