# Simulator integration entry point

The Omniverse side accepts the canonical v1 snapshot documented in
`../docs/INTEGRATION_CONTRACT.md`. Load a compliant file with:

```powershell
python integration\load_snapshot.py path\to\simulation_output.json
```

Then open `integration/runtime/scene/main.usda` in UrbanTwin. The loader validates
the entire snapshot before replacing generated USD layers.

The current `Simulation/urbantwin_demo_output.json` is a behavioral report, not a
canonical visualization snapshot. Do not pass it directly to this loader. Complete
`route_mapping.template.json` jointly after deciding which real OSM paths represent
simulator routes R1–R18, then add an exporter at the simulator boundary.

The runtime directory is generated and ignored by Git. Use the Phase 8 packaged
mock scene for presentations until the canonical exporter is complete.
