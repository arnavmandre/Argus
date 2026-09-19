# Phase 12 Python HTTP API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a local Python HTTP service that implements the contract the Next.js proxy already consumes, so `URBANTWIN_API_BASE` runs real Phase 11 pipelines and the dashboard shows live scenario-specific results with no recorded-fixture warning.

**Architecture:** A stdlib `ThreadingHTTPServer` under `api/` validates requests, keeps an in-memory single-worker run registry, and executes `integration.run_pipeline.run_pipeline` on a background thread. Response envelopes reuse the existing `integration/export_api_mocks.py` shaping helpers with `source: "live"`. The Next.js app stays the same-origin facade; streaming and Kit delivery remain offline stubs until Phases 13–15.

**Tech Stack:** Python 3 standard library (`http.server`, `threading`, `json`, `unittest`), Phase 11 `run_pipeline`, existing mock-shaping helpers, Next.js proxy via `URBANTWIN_API_BASE`.

**Spec:** `docs/superpowers/specs/2026-09-19-urbantwin-live-integration-phases-design.md` (Phase 12)

## Global Constraints

- Never edit Phase 1–8 scene layers.
- Keep the canonical v1 snapshot schema unchanged.
- Never generate `integration/route_mapping.json`.
- Simulator results remain authoritative; the API must not invent metrics, problem places, or intervention effects.
- Health/capability labels must match reality (`mode: "live"`, streaming still offline).
- Phase 11 remains the execution engine; do not reimplement simulation or export formulas.
- One local simulation worker at a time (409 conflict when busy).
- No new Python package dependencies (no FastAPI/uvicorn/pip installs).
- Tests use `unittest`; commands must work from repository root on Windows PowerShell.
- Do not present recorded fixtures as live when the Python API is configured.

---

## File Structure

- `api/__init__.py` — package marker.
- `api/validation.py` — scenario/view request validation matching frontend ranges and allow-lists.
- `api/shapes.py` — live-mode envelopes built from simulator reports (wrap/extend export helpers).
- `api/run_manager.py` — in-memory run registry, single-worker lock, background pipeline execution, cancel.
- `api/server.py` — HTTP routing for all required endpoints.
- `api/__main__.py` — `python -m api` entrypoint.
- `api/test_validation.py` — validation unit tests.
- `api/test_shapes.py` — live summary shaping tests.
- `api/test_run_manager.py` — queue/conflict/cancel/failure unit tests with mocked pipeline.
- `api/test_server.py` — HTTP contract tests against a temporary server.
- `docs/PHASE12_LOCAL_API.md` — operator runbook (start API, set `URBANTWIN_API_BASE`, verify live UI).
- Modify: `integration/export_api_mocks.py` — expose reusable summary builders that accept `source`.
- Modify: `frontend/README.md` and `CLAUDE.md` — live API commands.
- Modify: `integration/run_pipeline.py` only if cancel requires a cooperative stop hook; prefer process-level cancel in `run_manager` first.

---

### Task 1: Shared live response shaping and request validation

**Files:**
- Modify: `integration/export_api_mocks.py`
- Create: `api/__init__.py`
- Create: `api/validation.py`
- Create: `api/shapes.py`
- Create: `api/test_validation.py`
- Create: `api/test_shapes.py`

**Interfaces:**
- Consumes: simulator report dicts; model card JSON; frontend constraint ranges.
- Produces:
  - `validate_run_request(body: dict) -> tuple[dict | None, dict | None]` returning `(normalized, error)`
  - `validate_view_command(body: dict) -> tuple[dict | None, dict | None]`
  - `live_run_summary(report, created_utc, run_id, *, status="complete", warnings=None, error=None) -> dict`
  - `live_citizen_page(report, run_id, state, limit, offset) -> dict`
  - `live_health(checked_utc) -> dict` with `mode: "live"`, `source: "live"`, `capabilities.http_api/live_simulation: true`, streaming still offline
  - `live_scenarios() -> dict` with `source: "live"`
  - `live_stream_config(checked_utc) -> dict` with `status: "offline"`, `source: "live"`
  - `live_model_card(card, exported_utc) -> dict` with `source: "live"`

- [ ] **Step 1: Write failing validation and shape tests**

```python
# api/test_validation.py
import unittest
from api.validation import validate_run_request, validate_view_command

class ValidationTests(unittest.TestCase):
    def test_accepts_extreme_heat_rain_preset(self):
        body = {
            "temperature": 40, "humidity": 80, "rainfall": 80, "population": 100000,
            "apply_recommended_interventions": True,
            "animation_frames": 3, "animation_duration_seconds": 6,
        }
        request, error = validate_run_request(body)
        self.assertIsNone(error)
        self.assertEqual(request["population"], 100000)
        self.assertEqual(request["animation_frames"], 3)

    def test_rejects_out_of_range_temperature(self):
        body = {"temperature": 99, "humidity": 80, "rainfall": 80, "population": 100000,
                "apply_recommended_interventions": True}
        request, error = validate_run_request(body)
        self.assertIsNone(request)
        self.assertEqual(error["error"]["code"], "validation_failed")

    def test_view_command_allow_list(self):
        ok, err = validate_view_command({"state": "before", "camera": "ProblemZone", "overlay": "behavior"})
        self.assertIsNone(err)
        bad, err2 = validate_view_command({"state": "before", "camera": "/World/Hack", "overlay": "behavior"})
        self.assertIsNone(bad)
        self.assertEqual(err2["error"]["code"], "validation_failed")
```

```python
# api/test_shapes.py
import json
import unittest
from pathlib import Path
from api.shapes import live_run_summary, live_health

ROOT = Path(__file__).resolve().parents[1]

class ShapeTests(unittest.TestCase):
    def test_live_summary_marks_source_live_and_drops_fixture_warning(self):
        report = json.loads((ROOT / "Simulation" / "urbantwin_demo_output.json").read_text(encoding="utf-8"))
        summary = live_run_summary(report, "2026-09-19T12:00:00+00:00", "live-run-1")
        self.assertEqual(summary["source"], "live")
        self.assertEqual(summary["status"], "complete")
        self.assertTrue(all("Recorded fixture" not in w for w in summary["warnings"]))

    def test_live_health_capabilities(self):
        health = live_health("2026-09-19T12:00:00+00:00")
        self.assertEqual(health["mode"], "live")
        self.assertTrue(health["capabilities"]["http_api"])
        self.assertTrue(health["capabilities"]["live_simulation"])
        self.assertFalse(health["capabilities"]["omniverse_streaming"])
        self.assertEqual(health["omniverse_stream"], "offline")
```

- [ ] **Step 2: Run tests and confirm failure**

```powershell
python -m unittest api.test_validation api.test_shapes -v
```

Expected: import failures for `api.validation` / `api.shapes`.

- [ ] **Step 3: Implement validation and live shapes**

Constraint ranges (exact):

| Field | Range |
|---|---|
| temperature | -10 .. 45 |
| humidity | 20 .. 90 |
| rainfall | 0 .. 100 |
| population | 25000 .. 100000 |

View allow-lists must match `frontend/lib/types.ts` (`VIEW_CAMERAS`, `VIEW_OVERLAYS`) and states `before|after`.

Refactor `integration/export_api_mocks.py` so `run_summary`, `scenarios_fixture`, health, stream-config and model-card builders accept a `source` argument (default `"recorded_fixture"`) and a warning list override. Keep fixture CLI defaults unchanged. `api/shapes.py` calls those helpers with `source="live"` and live-mode warnings that state the numbers came from a just-executed simulator run.

Default animation when omitted: `animation_frames=60`, `animation_duration_seconds=60`. Reject `animation_frames < 1` or `duration <= 0`.

- [ ] **Step 4: Re-run shaping tests and fixture exporter smoke**

```powershell
python -m unittest api.test_validation api.test_shapes -v
python integration\export_api_mocks.py --help
```

Expected: all new tests pass; exporter help still works.

- [ ] **Step 5: Commit**

```powershell
git add api integration/export_api_mocks.py
git commit -m "Add live API validation and response shaping"
```

---

### Task 2: In-memory run manager around Phase 11

**Files:**
- Create: `api/run_manager.py`
- Create: `api/test_run_manager.py`

**Interfaces:**
- Consumes: `validate_run_request` output; `integration.run_pipeline.run_pipeline` / `PipelineConfig` / `PipelineError`.
- Produces:
  - `RunManager(root: Path, *, pipeline_fn=None)`
  - `create_run(request) -> dict` with `{run_id, status: "queued"}` or raises `ConflictError`
  - `get_run(run_id) -> dict | None` returning a `RunSummary`-shaped dict
  - `list_active() -> str | None`
  - `cancel_run(run_id) -> dict` (`cancelled` or conflict/not-found error shape)
  - `get_citizens(run_id, state, limit, offset) -> dict | None`

Behavior:

1. Generate run ids as `run_YYYYMMDD_HHMMSS` plus a short random suffix if needed; must pass Phase 11 `RUN_ID_PATTERN` and reserved-id rules.
2. Single worker: if any run is `queued` or `running`, `create_run` raises conflict (`409` at HTTP layer).
3. Background thread transitions `queued -> running -> complete|failed|cancelled`.
4. Invoke Phase 11 with `publish=True` for the default demo path so compatibility outputs refresh; use the validated scenario and animation values.
5. On success, load `data/runs/<id>/simulation_report.json` and build `live_run_summary`.
6. On `PipelineError`, store `status: "failed"` with `error: {code: "simulation_failed", message: ...}`.
7. Cancel: if `queued`, mark cancelled without starting; if `running`, set a cancel flag and terminate the active subprocess (Task 2 may wrap pipeline invocation in `subprocess.Popen` of `python -m integration.run_pipeline` / `python integration/run_pipeline.py` so cancel can kill the process tree on Windows via `taskkill /PID /T /F` or `CREATE_NEW_PROCESS_GROUP` + terminate). Do not leave a partial publish: rely on Phase 11 staging isolation (failed runs must not replace completed artifacts).
8. `apply_recommended_interventions: false` is accepted in validation for forward compatibility, but Phase 12 may still run the existing before/after pipeline (document that the current simulator always evaluates the advisor path). Do not invent a second simulator mode.

- [ ] **Step 1: Write failing manager tests with a fake pipeline**

```python
# api/test_run_manager.py
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from api.run_manager import ConflictError, RunManager

class RunManagerTests(unittest.TestCase):
    def test_second_create_conflicts_while_running(self):
        def slow_pipeline(config):
            time.sleep(0.2)
            report = Path(config.root) / "data" / "runs" / config.run_id / "simulation_report.json"
            report.parent.mkdir(parents=True)
            report.write_text('{"scenario":{"temperature":31,"humidity":55,"rainfall":12,"population":42000},"before":{"metrics":{},"citizens":[],"problem_zones":[],"problem_buildings":[],"problem_routes":[],"zones":[],"buildings":[],"routes":[],"interventions":{}},"after":{"metrics":{},"citizens":[],"problem_zones":[],"problem_buildings":[],"problem_routes":[],"zones":[],"buildings":[],"routes":[],"interventions":{}},"advisor":{"summary":"","problem_zones":[],"problem_buildings":[],"problem_routes":[],"recommendations":[],"affected_buildings":{},"explanation":[],"supported_interventions":{}},"intervention":{},"delta":{},"control":{"scenario":{},"metrics":{},"recommendations":[]}}\n', encoding="utf-8")
            return {"status": "complete", "run_id": config.run_id}

        with tempfile.TemporaryDirectory() as directory:
            manager = RunManager(Path(directory), pipeline_fn=slow_pipeline)
            first = manager.create_run({
                "temperature": 31, "humidity": 55, "rainfall": 12, "population": 42000,
                "apply_recommended_interventions": True, "animation_frames": 1, "animation_duration_seconds": 1,
            })
            with self.assertRaises(ConflictError):
                manager.create_run({
                    "temperature": 26, "humidity": 40, "rainfall": 5, "population": 30000,
                    "apply_recommended_interventions": True, "animation_frames": 1, "animation_duration_seconds": 1,
                })
            # wait for completion
            for _ in range(50):
                summary = manager.get_run(first["run_id"])
                if summary["status"] in {"complete", "failed"}:
                    break
                time.sleep(0.05)
            self.assertEqual(manager.get_run(first["run_id"])["status"], "complete")
            self.assertEqual(manager.get_run(first["run_id"])["source"], "live")
```

Also cover: cancel queued run; failed pipeline becomes `failed` with error; unknown run returns `None`.

- [ ] **Step 2: Run tests — expect missing module**

```powershell
python -m unittest api.test_run_manager -v
```

- [ ] **Step 3: Implement `RunManager`**

Keep the manager free of HTTP concerns. Inject `pipeline_fn` for tests; default implementation shells out to Phase 11 so cancel can kill a real child process.

- [ ] **Step 4: Re-run manager tests**

```powershell
python -m unittest api.test_run_manager -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add api/run_manager.py api/test_run_manager.py
git commit -m "Add single-worker live run manager"
```

---

### Task 3: HTTP server for the required endpoints

**Files:**
- Create: `api/server.py`
- Create: `api/__main__.py`
- Create: `api/test_server.py`

**Interfaces:**
- Consumes: `RunManager`, validators, live shape helpers.
- Produces: `create_app(root, manager=None) -> (server, manager)` and CLI `python -m api --host 127.0.0.1 --port 8000`.

Required routes (exact paths the frontend proxies):

```text
GET    /api/health
GET    /api/scenarios
POST   /api/runs
GET    /api/runs
GET    /api/runs/{run_id}
DELETE /api/runs/{run_id}
GET    /api/runs/{run_id}/citizens?state=before&limit=100&offset=0
GET    /api/model-card
GET    /api/stream/config
POST   /api/runs/{run_id}/view
```

Status mapping:

| Condition | HTTP |
|---|---|
| POST accepted | 202 `{run_id, status:"queued"}` |
| validation failure | 422 `{error:{code:"validation_failed", message}}` |
| worker busy | 409 `{error:{code:"conflict", message}}` |
| unknown run | 404 `{error:{code:"not_found", message}}` |
| cancel ok | 200 updated summary |
| view accepted (no Kit yet) | 200 `{accepted:true, delivered:false, reason, command}` |
| bad JSON | 400 |

`GET /api/runs` returns `{source:"live", active_run_id: <id|null>}`.

- [ ] **Step 1: Write failing HTTP contract tests**

Use `http.client` against a server started on an ephemeral port in `setUp`/`tearDown`. Cover health live mode, scenarios constraints, POST+poll complete with mocked manager/pipeline, 422, 409, 404, view allow-list, citizens pagination.

- [ ] **Step 2: Run and confirm failure**

```powershell
python -m unittest api.test_server -v
```

- [ ] **Step 3: Implement `ThreadingHTTPServer` router**

Parse paths carefully; never forward arbitrary filesystem paths from the client. Read model card from `phase10/models/model_card.json`. All JSON responses use `Content-Type: application/json` and `Cache-Control: no-store`.

Note: Next.js proxy timeout is 30s per request. POST must return quickly (queue only); long work stays in the background thread.

- [ ] **Step 4: Run server tests**

```powershell
python -m unittest api.test_server -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add api/server.py api/__main__.py api/test_server.py
git commit -m "Add local UrbanTwin HTTP API server"
```

---

### Task 4: End-to-end live proof against the frontend proxy

**Files:**
- Create: `docs/PHASE12_LOCAL_API.md`
- Modify: `frontend/README.md`
- Modify: `CLAUDE.md`
- Optional smoke script only if it already fits an existing pattern — prefer documented PowerShell commands over a new script.

**Interfaces:**
- Consumes: `python -m api` and Next.js with `URBANTWIN_API_BASE=http://127.0.0.1:8000`.
- Produces: verified live path evidence and operator docs.

- [ ] **Step 1: Run the full API unit suite**

```powershell
python -m unittest api.test_validation api.test_shapes api.test_run_manager api.test_server -v
```

- [ ] **Step 2: Start API and exercise curl/Invoke-RestMethod against a short real pipeline**

```powershell
python -m api --host 127.0.0.1 --port 8000
```

In a second shell, POST a tiny animation run (`animation_frames: 1` or `3`) with a non-default scenario (e.g. temperature 31), poll until `complete`, assert `source: "live"`, metrics present, and health `mode: "live"`. Also assert 409 on a second concurrent POST while running, 422 on bad input, and DELETE cancel on a queued/running run.

- [ ] **Step 3: Frontend live check**

```powershell
$env:URBANTWIN_API_BASE = "http://127.0.0.1:8000"
cd frontend
npm run lint
npm run build
```

Manual or scripted check: open the dashboard (or fetch `/api/health` through Next) and confirm no recorded-fixture warning when proxied. If a headless browser is unavailable, document the exact PowerShell fetches through `http://127.0.0.1:3000/api/health` and `/api/runs` with the env var set for `next dev` / `next start`.

- [ ] **Step 4: Write `docs/PHASE12_LOCAL_API.md`**

Must include: start command, `URBANTWIN_API_BASE`, single-worker semantics, cancel behavior, streaming still offline, Phase 11 is the engine, integrity language (`source: "live"` vs fixtures).

- [ ] **Step 5: Update `frontend/README.md` and `CLAUDE.md`**

- [ ] **Step 6: Commit**

```powershell
git add docs/PHASE12_LOCAL_API.md frontend/README.md CLAUDE.md
git commit -m "Document the Phase 12 local HTTP API"
```

## Phase 12 Completion Gate

Phase 12 is complete only when:

- all `api.test_*` tests pass;
- a real POST→poll cycle returns `source: "live"` scenario-specific results from Phase 11;
- health reports `mode: "live"` with streaming still offline;
- conflict, validation failure and cancel paths are covered by tests;
- with `URBANTWIN_API_BASE` set, the frontend proxy path no longer depends on recorded fixtures for runs;
- docs name the exact local commands;
- no Phase 1–8 edits and no new Python dependencies.
