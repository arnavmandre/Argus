# Phase 11 local pipeline

Phase 11 provides synchronous local orchestration from a simulator scenario to
validated run artifacts and recorded frontend fixtures. It is not an HTTP API,
job queue, background service, or live stream. The command returns only after
every stage has completed or failed.

## Prerequisites

- Run PowerShell from the repository root.
- Use a Python environment that can import OpenUSD's `pxr` package.
- Keep the citizen and city inputs available at
  `Simulation/citizens_survey_city_osm.json` and
  `Simulation/city_osm.json`.
- Install the frontend dependencies from the existing lockfile when needed:
  `cd frontend; npm ci`.

## Run the real OSM pipeline

Choose a unique run ID when retaining more than one result. The Phase 11 smoke
command is:

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

Success prints the manifest path. Confirm that
`data/runs/phase11-smoke/manifest.json` has `"status": "complete"`. The pipeline
runs simulation, canonical snapshot export, runtime-stage generation, before
and after agent USD generation, frontend fixture export, and integration
validation in that order.

## Run artifacts

Each completed run directory contains all generated outputs:

```text
data/runs/<run-id>/
├── manifest.json
├── simulation_report.json
├── snapshots/
│   ├── simulation_before_000.json ... simulation_before_059.json
│   └── simulation_after_000.json  ... simulation_after_059.json
├── usd/
│   ├── agents_before.usda
│   └── agents_after.usda
├── runtime/scene/
│   ├── main.usda
│   ├── agents.usda
│   ├── interventions.usda
│   ├── metrics.usda
│   └── routes.usda
└── frontend-mocks/
    ├── health.json
    ├── model-card.json
    ├── scenarios.json
    ├── stream-config.json
    └── runs/
        ├── <run-id>.json
        └── <run-id>.citizens.json
```

Keep the bundle in this repository layout when opening its runtime stage. The
generated stage references frozen assets under `phase2/scene/main.usda`, so the
run directory is not a standalone relocatable USD package.

The snapshots are fixed equilibrium samples used for display. Kit interpolates
agent positions between those authored samples to display motion; this does not
make the simulation time-evolving or the viewport a live stream.

## Publication and recovery

The pipeline builds and validates in `data/runs/<run-id>.staging` before
installing the completed run. Only after validation does it refresh the current
compatibility outputs: the simulator report, numbered and canonical before/after
snapshots, generated agent USD layers, and `frontend/mocks/` fixtures.

A handled stage failure removes its staging directory and leaves any existing
completed `<run-id>` and manifest unchanged. If an interrupted process or
cleanup failure leaves a `.staging` directory, keep it as diagnostic evidence;
it is never a completed run. The next invocation clears stale staging before
starting, so copy any needed evidence first.

After promotion and compatibility publication commit, removal of obsolete
backup files is best-effort. A cleanup failure leaves the completed run
successful and records a `warnings` entry in its manifest instead of reporting
the invocation as failed. A retained `<run-id>.backup` is removed by the next
run; a warning naming a `.pipeline-backup` file identifies obsolete
compatibility backup litter that can be inspected and removed manually.

For fixture-only maintenance, without rerunning simulation or USD generation,
use `python integration\export_api_mocks.py`.
