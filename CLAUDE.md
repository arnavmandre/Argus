# UrbanTwin AI — working notes for Claude

Hackathon project. Human-centric urban digital twin: Python simulation +
OpenUSD/Omniverse visualisation + survey-calibrated synthetic citizens.

## Before creating ANY new script, check whether it already exists

This repo has been built across several sessions. Long sessions get summarised,
and work done earlier can drop out of context — it has already happened once
that a whole set of tools was rebuilt from scratch under new filenames, creating
silent duplicates (`build_presentation.py` vs `make_cameras.py`+`set_scenario.py`,
`colorize_from_snapshot.py` vs `recolor_paths.py`, `build_route_mapping.py` vs
`propose_route_mapping.py`).

**So: `ls` the target directory and `git log --oneline -15` before writing a new
file.** If something close already exists, extend it rather than adding a
parallel implementation. If you genuinely think a rewrite is better, say so and
delete the old one — never leave both.

Commit at each working milestone. Commits are the checkpoint that survives
context loss.

## Layout

| Path | Owner | Notes |
|---|---|---|
| `Simulation/` | simulation | `main.py` is self-contained, dependency-free, deterministic. `python main.py` runs ~80 asserts then the demo. |
| `phase1/`–`phase8/` | visualisation | OSM city → semantics → contract → bridges → packaged states. **Treat as frozen.** |
| `integration/` | boundary | Snapshot loader + route-mapping proposal tooling. |
| `phase9/` | realism + demo | Materials, heights, trees, lighting, cameras, overlays — all `over` layers — plus `build_city_from_osm.py`. **Open `phase9/scene/main.usda` for the demo.** |
| `docs/` | contracts | `INTEGRATION_CONTRACT.md` is authoritative. |

## Hard rules

1. **Never edit `phase1/`–`phase8/` scene layers.** `city_id` is the SHA-256 of
   the frozen Phase 1 manifest; the scene contract depends on it. Add `over`
   layers in `phase9/` instead.
2. **Never write `integration/route_mapping.json` automatically.** That filename
   is reserved for a mapping the *team* has agreed. Tools emit
   `route_mapping.proposal.json`. Auto-chosen anchors are geometrically real but
   semantically provisional — nobody has agreed which OSM building is "the
   hospital".
3. **The simulator's `citizens.json` schema is fixed:** `id, archetype, home,
   destination, heat_tolerance, rain_tolerance, crowd_tolerance,
   walking_speed_kmh, green_preference, transit_preference` (+ optional
   `weight`). Unknown keys are ignored silently, so a typo = a dropped field.
4. **Visualisation reads canonical v1 snapshots**, not
   `Simulation/urbantwin_demo_output.json`. The exporter owns normalisation
   (0–100 → 0–1) and route→edge mapping.
5. **Metrics are heuristic prototypes**, not medical/meteorological models. Keep
   the disclaimers in output and docs.

## Integrity — this project is judged

Only claim what the code does when executed. Verified as of this writing:

- ✅ Deterministic; data-driven city and citizens; per-citizen route choice
  responds to heat/rain/crowd/transit/green; emergent corridor congestion
  (MSA-damped iterative assignment); citizen profiles move the HEI.
- ✅ Phase 9: 623 buildings carry 12 distinct OSM-derived materials and heights
  spanning 2–39 m; 511 trees at surveyed OSM positions; `city_osm.json` runs the
  simulator on real Russell Square geometry with `osm_edges` on every route.
- ❌ **No survey pipeline exists yet.** Do not claim citizen profiles are
  calibrated from real participant responses until it does.
- ⚠️ Building heights: only **223 of 623** come from real OSM data
  (`urbantwin:heightSource` records each one). The rest are inferred from
  building class or interpolated from neighbours. Do not call the skyline
  surveyed.
- ⚠️ The default 8-building `city.json` is still abstract, and
  `integration/route_mapping.proposal.json` is still provisional. Use
  `city_osm.json` when real geography matters.
- ❌ Nothing in Omniverse yet displays output from `Simulation/main.py` — the
  overlays read Phase 3 **mock** snapshots. No exporter exists.

## Commands

```powershell
cd Simulation; python main.py                        # tests + 8-building demo
cd Simulation; python main.py citizens_osm.json city_osm.json   # real OSM city
python phase9\set_scenario.py baseline|heat|rain|dusk
python phase8\switch_state.py stressed|intervention
python phase9\validate_phase9.py
python phase3\validate_mock_data.py <snapshot.json>
```

Open `phase9/scene/main.usda` in Kit for the demo stage.
Kit app lives outside the repo: `C:\Users\arnav\omniverse\kit-app-template`,
launch with `.\repo.bat launch -n urbantwin.kit`.
