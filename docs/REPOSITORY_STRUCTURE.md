# Repository structure

```text
Argus/
  README.md                  current entry point
  docs/                      project, setup, and integration documentation
  exports/                   packaged handoff archives
  integration/               canonical snapshot loader and route-map template
  legacy/                    preserved superseded prototypes
  phase1/                    real OSM import and base OpenUSD city
  phase2/                    semantic hierarchy and frozen edge registry
  phase3/                    JSON Schema, validators, and labelled mock snapshots
  phase4/                    lightweight pedestrian agents
  phase5/                    route and path-usage overlays
  phase6/                    heat and crowding overlays
  phase7/                    intervention proposal geometry
  phase8/                    packaged stressed/intervention demo variants
```

The numbered phase directories remain at repository root because their Python and
USD files use tested relative references. Each phase is reproducible and retains
its own README. The phase output folders are useful checkpoints, while Phase 8 is
the current presentation entry point.

`legacy/synthetic_city` is the earlier synthetic-grid prototype. It is preserved
for reference but is not part of the real OSM pipeline. `legacy/empty_omniverse_stage.usd`
is an earlier empty Kit stage with different units and up-axis; do not compose it
with the current city.

`exports/phase8.zip` is a point-in-time archive. The live `phase8/` directory is
the source of truth and may be newer than the ZIP.

Generated Python `__pycache__` folders and bytecode are ignored. Generated scene
layers remain tracked as demo artifacts because they can be opened directly in
Omniverse without running the build scripts first.
