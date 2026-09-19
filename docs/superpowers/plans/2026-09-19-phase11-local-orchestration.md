# Phase 11 Local Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide one repository-root command that runs a scenario through the real simulator, canonical snapshot export, before/after USD agent generation, frontend fixture export and integration validation, then publishes an atomic run manifest.

**Architecture:** Existing scripts remain the owners of simulation, snapshot translation, USD authoring and fixture shaping. A new `integration/run_pipeline.py` invokes those boundaries in an isolated `data/runs/<run-id>.staging` directory, validates the outputs, atomically publishes the completed run, and only then refreshes compatibility outputs used by the current demo.

**Tech Stack:** Python 3 standard library, existing dependency-free simulator, OpenUSD `pxr` scripts, `unittest`, JSON manifests, subprocess boundaries.

**Spec:** `docs/superpowers/specs/2026-09-19-urbantwin-live-integration-phases-design.md`

## Global Constraints

- Never edit Phase 1–8 scene layers.
- Keep the canonical v1 snapshot schema unchanged.
- Never generate `integration/route_mapping.json`.
- Simulator results remain authoritative.
- The orchestrator must call existing domain scripts rather than duplicate their formulas.
- A failed run must not replace the most recent completed run or frontend fixtures.
- Commands must work from repository root on Windows PowerShell.
- Tests use `unittest`; do not introduce a Python package dependency.

---

## File Structure

- `Simulation/main.py` — accept explicit scenario and report-output arguments while preserving the current default demo.
- `Simulation/test_cli.py` — verify scenario parsing and report identity without launching an HTTP layer.
- `phase9/agents_instancer.py` — accept explicit output and demo-stage paths.
- `phase9/test_agents_instancer_cli.py` — verify a renderer invocation writes only the requested layer.
- `integration/export_api_mocks.py` — accept a run ID instead of embedding one constant in every fixture.
- `integration/validate_integration.py` — accept report, snapshots and runtime-stage paths.
- `integration/test_export_interfaces.py` — protect the new exporter and validator CLI contracts.
- `integration/run_pipeline.py` — isolated execution, stage recording, publication and manifest ownership.
- `integration/test_run_pipeline.py` — unit tests for command construction, failure behavior and atomic publication.
- `docs/PHASE11_LOCAL_PIPELINE.md` — operator-facing command, outputs and recovery behavior.
- `frontend/README.md` — point fixture refresh instructions at the one-command pipeline.

---

### Task 1: Make simulator scenarios and report paths explicit

**Files:**
- Modify: `Simulation/main.py:1203-1247`
- Modify: `Simulation/main.py:1569-1582`
- Create: `Simulation/test_cli.py`

**Interfaces:**
- Consumes: existing `simulate()`, `urban_advisor()` and `recommended_interventions()`.
- Produces: `run_demo(citizens=None, city_state=None, scenario=None) -> dict`, `parse_cli(argv=None) -> argparse.Namespace`, and a CLI `--output PATH`.

- [ ] **Step 1: Write the failing scenario test**

```python
# Simulation/test_cli.py
import tempfile
import unittest
from pathlib import Path

from Simulation import main


class SimulatorCliTests(unittest.TestCase):
    def test_run_demo_uses_explicit_scenario(self):
        scenario = {
            "temperature": 31,
            "humidity": 55,
            "rainfall": 12,
            "population": 42000,
        }
        report = main.run_demo(scenario=scenario)
        self.assertEqual(report["scenario"], scenario)
        self.assertEqual(report["before"]["inputs"], scenario)

    def test_parse_cli_preserves_existing_positional_inputs(self):
        args = main.parse_cli([
            "citizens.json",
            "city.json",
            "--temperature", "31",
            "--humidity", "55",
            "--rainfall", "12",
            "--population", "42000",
            "--output", "report.json",
        ])
        self.assertEqual(args.citizens, Path("citizens.json"))
        self.assertEqual(args.city, Path("city.json"))
        self.assertEqual(args.output, Path("report.json"))
        self.assertEqual(args.temperature, 31)
        self.assertEqual(args.population, 42000)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and confirm the interface is absent**

Run:

```powershell
python -m unittest Simulation.test_cli -v
```

Expected: failure because `run_demo()` rejects `scenario` or `parse_cli` does not exist.

- [ ] **Step 3: Add the CLI parser and scenario injection**

Add `argparse` to the standard-library imports and implement:

```python
DEFAULT_SCENARIO = {
    "temperature": 40,
    "humidity": 80,
    "rainfall": 80,
    "population": 100_000,
}


def parse_cli(argv=None):
    parser = argparse.ArgumentParser(description="Run the UrbanTwin simulation.")
    parser.add_argument("citizens", type=Path, nargs="?")
    parser.add_argument("city", type=Path, nargs="?")
    parser.add_argument("--temperature", type=float, default=DEFAULT_SCENARIO["temperature"])
    parser.add_argument("--humidity", type=float, default=DEFAULT_SCENARIO["humidity"])
    parser.add_argument("--rainfall", type=float, default=DEFAULT_SCENARIO["rainfall"])
    parser.add_argument("--population", type=int, default=DEFAULT_SCENARIO["population"])
    parser.add_argument("--output", type=Path, default=Path("urbantwin_demo_output.json"))
    return parser.parse_args(argv)
```

Change `run_demo()` to copy the supplied scenario:

```python
def run_demo(citizens=None, city_state=None, scenario=None):
    scenario = dict(DEFAULT_SCENARIO if scenario is None else scenario)
    before = simulate(**scenario, city_state=city_state, citizens=citizens)
```

Replace the current `sys.argv` block with:

```python
if __name__ == "__main__":
    args = parse_cli()
    scenario = {
        "temperature": args.temperature,
        "humidity": args.humidity,
        "rainfall": args.rainfall,
        "population": args.population,
    }
    run_tests()
    demo = run_demo(citizens=args.citizens, city_state=args.city, scenario=scenario)
    print_demo_summary(demo)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(demo, indent=2) + "\n", encoding="utf-8")
    print(f"\nSaved: {args.output}")
```

- [ ] **Step 4: Run simulator unit and built-in checks**

Run:

```powershell
python -m unittest Simulation.test_cli -v
cd Simulation
python main.py citizens_survey_city_osm.json city_osm.json --output urbantwin_demo_output.json
cd ..
```

Expected: two unit tests pass; all built-in assertions pass; the default report is written.

- [ ] **Step 5: Commit**

```powershell
git add Simulation/main.py Simulation/test_cli.py
git commit -m "Make simulation scenarios configurable"
```

---

### Task 2: Preserve separate before and after agent layers

**Files:**
- Modify: `phase9/agents_instancer.py:42-45`
- Modify: `phase9/agents_instancer.py:61-73`
- Modify: `phase9/agents_instancer.py:190-217`
- Create: `phase9/test_agents_instancer_cli.py`

**Interfaces:**
- Consumes: canonical snapshot files and the simulator behavior report.
- Produces: CLI options `--out PATH` and `--demo-stage PATH`; defaults retain current behavior.

- [ ] **Step 1: Write the failing renderer CLI test**

```python
# phase9/test_agents_instancer_cli.py
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AgentRendererCliTests(unittest.TestCase):
    def test_explicit_output_does_not_overwrite_default_layer(self):
        snapshot = ROOT / "data" / "simulation_before.json"
        report = ROOT / "Simulation" / "urbantwin_demo_output.json"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "agents_before.usda"
            missing_stage = Path(directory) / "no-demo-stage.usda"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "phase9" / "agents_instancer.py"),
                    str(snapshot),
                    "--behavior-report", str(report),
                    "--behavior-state", "before",
                    "--out", str(output),
                    "--demo-stage", str(missing_stage),
                ],
                check=True,
                cwd=ROOT,
            )
            self.assertTrue(output.exists())
            self.assertIn("PointInstancer", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the renderer test and verify argument rejection**

Run:

```powershell
python -m unittest phase9.test_agents_instancer_cli -v
```

Expected: failure with unrecognized arguments `--out` and `--demo-stage`.

- [ ] **Step 3: Add explicit output paths**

Add parser arguments:

```python
ap.add_argument("--out", type=Path, default=OUT,
                help="generated agent USD layer")
ap.add_argument("--demo-stage", type=Path, default=DEMO_STAGE,
                help="root stage whose timeline metadata is updated")
```

Replace output and timeline references:

```python
args.out.parent.mkdir(parents=True, exist_ok=True)
layer.Export(str(args.out))

if args.demo_stage.exists():
    demo = Sdf.Layer.FindOrOpen(str(args.demo_stage))
    # retain the existing timeline assignment and Save() block

print(f"wrote {args.out}")
```

- [ ] **Step 4: Run the renderer and Phase 9 checks**

Run:

```powershell
python -m unittest phase9.test_agents_instancer_cli -v
python phase9\validate_phase9.py
```

Expected: renderer test passes; Phase 9 validator passes without changing Phase 1–8.

- [ ] **Step 5: Commit**

```powershell
git add phase9/agents_instancer.py phase9/test_agents_instancer_cli.py
git commit -m "Support separate agent USD outputs"
```

---

### Task 3: Parameterize fixture identity and integration validation

**Files:**
- Modify: `integration/export_api_mocks.py:42-43`
- Modify: `integration/export_api_mocks.py:97-158`
- Modify: `integration/export_api_mocks.py:301-327`
- Modify: `integration/validate_integration.py:20-26`
- Modify: `integration/validate_integration.py:37-49`
- Create: `integration/test_export_interfaces.py`

**Interfaces:**
- Consumes: report, model card, canonical snapshots and runtime stage.
- Produces: fixture exporter `--run-id`; validator `--report`, `--snapshot`, `--after`, `--stage`, `--registry`.

- [ ] **Step 1: Write failing CLI contract tests**

```python
# integration/test_export_interfaces.py
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ExportInterfaceTests(unittest.TestCase):
    def test_fixture_exporter_documents_run_id(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "integration" / "export_api_mocks.py"), "--help"],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertIn("--run-id", result.stdout)

    def test_validator_documents_explicit_artifact_paths(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "integration" / "validate_integration.py"), "--help"],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        for option in ("--report", "--snapshot", "--after", "--stage", "--registry"):
            self.assertIn(option, result.stdout)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify both interfaces are missing**

Run:

```powershell
python -m unittest integration.test_export_interfaces -v
```

Expected: both tests fail because the help output lacks the new options.

- [ ] **Step 3: Thread run identity through the fixture exporter**

Add:

```python
parser.add_argument("--run-id", default=RUN_ID)
```

Change helper signatures to:

```python
def run_summary(report, generated_at, run_id):
def citizen_page_fixture(report, generated_at, run_id):
def scenarios_fixture(run_id):
```

Use `run_id` in every generated `run_id` field and output filename:

```python
write(out / "scenarios.json", scenarios_fixture(args.run_id))
write(out / "runs" / f"{args.run_id}.json",
      run_summary(report, generated_at, args.run_id))
write(out / "runs" / f"{args.run_id}.citizens.json",
      citizen_page_fixture(report, generated_at, args.run_id))
```

- [ ] **Step 4: Add explicit validator paths**

At the start of `main()` parse:

```python
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--report", type=Path, default=REPORT)
parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
parser.add_argument("--after", type=Path, default=AFTER)
parser.add_argument("--stage", type=Path, default=STAGE)
parser.add_argument("--registry", type=Path, default=REGISTRY)
args = parser.parse_args()
```

Replace the five hardcoded constants inside `main()` with the matching
`args` properties. Keep defaults identical so the current command still works.

- [ ] **Step 5: Run interface and integration tests**

Run:

```powershell
python -m unittest integration.test_export_interfaces -v
python integration\validate_integration.py
```

Expected: interface tests pass and all existing end-to-end checks pass.

- [ ] **Step 6: Commit**

```powershell
git add integration/export_api_mocks.py integration/validate_integration.py integration/test_export_interfaces.py
git commit -m "Parameterize pipeline export interfaces"
```

---

### Task 4: Build the isolated pipeline runner

**Files:**
- Create: `integration/run_pipeline.py`
- Create: `integration/test_run_pipeline.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: the CLIs created in Tasks 1–3.
- Produces: `PipelineConfig`, `StageResult`, `run_pipeline(config) -> dict`, CLI exit status and `data/runs/<run-id>/manifest.json`.

- [ ] **Step 1: Write failing unit tests for command recording and failure isolation**

```python
# integration/test_run_pipeline.py
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from integration.run_pipeline import PipelineConfig, PipelineError, run_pipeline


class PipelineTests(unittest.TestCase):
    def config(self, root):
        return PipelineConfig(
            root=root,
            run_id="test-run",
            citizens=Path("Simulation/citizens_survey_city_osm.json"),
            city=Path("Simulation/city_osm.json"),
            temperature=31,
            humidity=55,
            rainfall=12,
            population=42000,
            frames=3,
            duration=6.0,
            publish=False,
        )

    @patch("integration.run_pipeline.run_stage")
    def test_manifest_records_scenario_and_required_artifacts(self, run_stage):
        def fake_stage(name, command, cwd):
            for token in command:
                if str(token).endswith(".json") or str(token).endswith(".usda"):
                    path = Path(token)
                    if path.is_absolute():
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text("{}\n", encoding="utf-8")
            return {"name": name, "command": [str(x) for x in command], "seconds": 0.01}
        run_stage.side_effect = fake_stage

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = run_pipeline(self.config(root))
            self.assertEqual(manifest["run_id"], "test-run")
            self.assertEqual(manifest["scenario"]["temperature"], 31)
            self.assertIn("simulation_report", manifest["artifacts"])
            self.assertEqual(manifest["status"], "complete")

    @patch("integration.run_pipeline.run_stage")
    def test_failed_run_keeps_previous_complete_run(self, run_stage):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            completed = root / "data" / "runs" / "test-run"
            completed.mkdir(parents=True)
            marker = completed / "manifest.json"
            marker.write_text('{"status":"complete","old":true}\n', encoding="utf-8")
            run_stage.side_effect = PipelineError("simulation failed")

            with self.assertRaises(PipelineError):
                run_pipeline(self.config(root))

            self.assertTrue(json.loads(marker.read_text(encoding="utf-8"))["old"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and confirm the module is absent**

Run:

```powershell
python -m unittest integration.test_run_pipeline -v
```

Expected: import failure for `integration.run_pipeline`.

- [ ] **Step 3: Define pipeline types and stage execution**

Create:

```python
@dataclass(frozen=True)
class PipelineConfig:
    root: Path
    run_id: str
    citizens: Path
    city: Path
    temperature: float
    humidity: float
    rainfall: float
    population: int
    frames: int = 60
    duration: float = 60.0
    publish: bool = True


class PipelineError(RuntimeError):
    pass


def run_stage(name, command, cwd):
    started = time.perf_counter()
    result = subprocess.run(
        [str(part) for part in command],
        cwd=cwd,
        text=True,
        capture_output=True,
    )
    elapsed = round(time.perf_counter() - started, 3)
    if result.returncode:
        raise PipelineError(
            f"{name} failed with exit {result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return {
        "name": name,
        "command": [str(part) for part in command],
        "seconds": elapsed,
        "stdout": result.stdout,
    }
```

- [ ] **Step 4: Build exact commands in pipeline order**

`run_pipeline()` must create `data/runs/<run-id>.staging` and invoke:

```python
python = sys.executable
report = staging / "simulation_report.json"
snapshots = staging / "snapshots"
runtime = staging / "runtime"
usd = staging / "usd"
mocks = staging / "frontend-mocks"

simulation = [
    python, root / "Simulation" / "main.py",
    root / config.citizens, root / config.city,
    "--temperature", config.temperature,
    "--humidity", config.humidity,
    "--rainfall", config.rainfall,
    "--population", config.population,
    "--output", report,
]

snapshot_export = [
    python, root / "integration" / "export_snapshot.py",
    "--report", report,
    "--city", root / config.city,
    "--state", "both",
    "--run-id", config.run_id,
    "--out-dir", snapshots,
    "--frames", config.frames,
    "--duration", config.duration,
]
```

Then invoke:

1. `integration/load_snapshot.py` on `simulation_before_000.json` with
   `--out <staging>/runtime`;
2. `phase9/agents_instancer.py` over each state's sorted frame list, with the
   matching behavior state and `--out <staging>/usd/agents_<state>.usda`;
3. `integration/export_api_mocks.py --report ... --run-id ... --out ...`;
4. `integration/validate_integration.py` with the explicit report, first before
   snapshot, first after snapshot, runtime `scene/main.usda` and registry paths.

Reject invalid identity and animation inputs before running commands:

```python
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", config.run_id):
    raise PipelineError("run ID must use 1-64 letters, digits, dot, underscore or hyphen")
if config.frames < 1:
    raise PipelineError("frames must be >= 1")
if config.duration <= 0:
    raise PipelineError("duration must be > 0")
```

- [ ] **Step 5: Write and publish the manifest atomically**

The complete manifest shape is:

```python
manifest = {
    "schema_version": 1,
    "run_id": config.run_id,
    "status": "complete",
    "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "scenario": {
        "temperature": config.temperature,
        "humidity": config.humidity,
        "rainfall": config.rainfall,
        "population": config.population,
    },
    "animation": {"frames": config.frames, "duration_seconds": config.duration},
    "artifacts": {
        "simulation_report": "simulation_report.json",
        "before_snapshots": "snapshots/simulation_before_*.json",
        "after_snapshots": "snapshots/simulation_after_*.json",
        "before_agents_usd": "usd/agents_before.usda",
        "after_agents_usd": "usd/agents_after.usda",
        "runtime_stage": "runtime/scene/main.usda",
        "frontend_fixtures": "frontend-mocks",
    },
    "stages": stage_results,
}
```

Write it as `manifest.json.tmp`, replace it with `manifest.json`, then replace
an existing final run directory only after moving it to a backup. If promotion
fails, restore that backup.

When `publish=True`, copy through temporary sibling files and `os.replace()`:

- report → `Simulation/urbantwin_demo_output.json`;
- snapshots → `data/simulation_<state>_*.json`;
- USD layers → `phase9/scene/generated/agents_before.usda` and
  `agents_after.usda`;
- before USD layer → `phase9/scene/generated/agents.usda`;
- fixture tree → `frontend/mocks/`.

Do not publish any file until validation has passed.

- [ ] **Step 6: Add the CLI**

Expose:

```text
--run-id
--citizens
--city
--temperature
--humidity
--rainfall
--population
--frames
--duration
--no-publish
```

Defaults must reproduce the current extreme-weather OSM demo. On success print
the final manifest path. On `PipelineError`, print the stage error to stderr and
exit 1.

- [ ] **Step 7: Ignore generated run directories**

Add to `.gitignore`:

```gitignore
data/runs/
```

Do not ignore committed fixtures or Phase 9 generated layers already tracked by
the project.

- [ ] **Step 8: Run pipeline unit tests**

Run:

```powershell
python -m unittest integration.test_run_pipeline -v
```

Expected: both tests pass and temporary directories are removed.

- [ ] **Step 9: Commit**

```powershell
git add integration/run_pipeline.py integration/test_run_pipeline.py .gitignore
git commit -m "Add atomic local simulation pipeline"
```

---

### Task 5: Prove the real one-command path and document operation

**Files:**
- Create: `docs/PHASE11_LOCAL_PIPELINE.md`
- Modify: `frontend/README.md:15-35`
- Modify: `CLAUDE.md` commands section

**Interfaces:**
- Consumes: `integration/run_pipeline.py`.
- Produces: one documented operator command and fresh evidence from the real OSM pipeline.

- [ ] **Step 1: Run all focused tests**

Run:

```powershell
python -m unittest Simulation.test_cli phase9.test_agents_instancer_cli integration.test_export_interfaces integration.test_run_pipeline -v
```

Expected: all Phase 11 tests pass.

- [ ] **Step 2: Execute the real pipeline**

Run from repository root:

```powershell
python integration\run_pipeline.py `
  --run-id phase11-smoke `
  --citizens Simulation\citizens_survey_city_osm.json `
  --city Simulation\city_osm.json `
  --temperature 40 `
  --humidity 80 `
  --rainfall 80 `
  --population 100000 `
  --frames 60 `
  --duration 60
```

Expected: exit 0 and
`data/runs/phase11-smoke/manifest.json` reports every stage complete.

- [ ] **Step 3: Verify published artifacts**

Run:

```powershell
python integration\validate_integration.py
python phase9\validate_phase9.py
cd frontend
npm run lint
npm run build
```

Expected: integration checks pass, Phase 9 validates, frontend lint exits zero
and the production build succeeds.

- [ ] **Step 4: Write the operator runbook**

`docs/PHASE11_LOCAL_PIPELINE.md` must include:

- prerequisites: Python environment with `pxr`, repository root and input files;
- the exact command from Step 2;
- artifact tree under `data/runs/<run-id>/`;
- compatibility outputs refreshed after validation;
- statement that snapshots are fixed equilibrium samples used for display;
- recovery behavior: failed staging directories are diagnostic and completed
  manifests are not replaced;
- confirmation that this is local orchestration, not an HTTP API or queue.

- [ ] **Step 5: Update existing command references**

In `frontend/README.md`, replace the standalone fixture-refresh command with the
Phase 11 pipeline command and retain `integration/export_api_mocks.py` as the
fixture-only maintenance command.

In `CLAUDE.md`, add the pipeline command under Commands and state that Phase 11
is the source for a complete local regeneration.

- [ ] **Step 6: Check documentation and working tree**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; only the Phase 11 documentation changes remain.

- [ ] **Step 7: Commit the verified milestone**

```powershell
git add docs/PHASE11_LOCAL_PIPELINE.md frontend/README.md CLAUDE.md
git commit -m "Document the Phase 11 local pipeline"
```

## Phase 11 Completion Gate

Phase 11 is complete only when:

- the focused Python tests pass;
- the real 60-frame OSM command exits zero;
- integration and Phase 9 validators pass;
- frontend lint and production build pass;
- the completed manifest lists report, snapshots, both USD layers, runtime
  stage and frontend fixtures;
- a deliberately failed test run leaves the previous completed run unchanged;
- all five task commits exist.
