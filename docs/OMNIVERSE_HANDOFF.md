# UrbanTwin AI — Omniverse handoff

## Delivered visual system

The Omniverse/OpenUSD side is complete through Phase 8. It provides a real OSM
city, stable pedestrian edge IDs, lightweight citizens, supplied route overlays,
heat/crowding bands, proposal geometry, and Stressed/Intervention USD variants.
It does not calculate behavior or intervention effectiveness.

Current demo stage:

```text
phase8/scene/main.usda
```

Current integration loader:

```powershell
python integration\load_snapshot.py path\to\canonical_snapshot.json
```

## Required simulator output

The authoritative format is `phase3/simulation_state.schema.json`, with field
semantics in `docs/INTEGRATION_CONTRACT.md`. Key requirements are:

- `schema_version = "1.0"` and the frozen `city_id` from the edge registry.
- Complete snapshots with increasing sequence/timestamp values per run.
- At most 500 representative agents, each with metre XYZ coordinates in the
  local city frame, an ordered array of mapped `edge_*` route IDs, and 0–1 stress
  and heat exposure.
- Per-edge crowding, heat exposure and accessibility values normalized to 0–1.
- Supported proposal commands using mapped edge IDs.
- Full-snapshot semantics: absent agents/proposals are removed.

Coordinate system: X east, Y north, Z up, metres. Agent Z is foot elevation.
The origin is in `phase2/scene/edge_registry.json`.

## Audit of the teammate output found in the workspace

`Simulation/urbantwin_demo_output.json` currently contains useful before/after
behavioral results, but it cannot yet drive the city directly:

| Simulator output | Omniverse requirement | Adapter action |
|---|---|---|
| Routes `R1`–`R18` | Ordered `edge_*` arrays | Agree geography in `integration/route_mapping.template.json` |
| Citizen route as one `R*` string | Ordered mapped path IDs | Expand through the agreed mapping |
| No citizen XYZ position | Local metre XYZ position | Export a position/progress value from the simulator |
| Heat/crowd mostly 0–100 | Metrics in 0–1 | Divide by 100 after validating bounds |
| Aggregate before/after report | One canonical full snapshot per state | Export `before` and `after` separately |
| `shade_boost`, `drainage_boost`, `route_capacity_boost` | Supported intervention commands | Translate only after agreeing target edge IDs and meaning |
| No frozen city ID | Required matching `city_id` | Copy from the Phase 2 registry |

The route mapping is intentionally blank. Assigning real paths to abstract R-route
labels without team agreement would fabricate spatial meaning.

## Suggested exporter boundary

Add a small exporter beside the simulator that reads its existing report and emits:

```text
simulation_before.json
simulation_after.json
```

The exporter owns route-to-edge mapping, agent position/progress, and percentage
normalization. It should not import Omniverse APIs. Validate each output with:

```powershell
python phase3\validate_mock_data.py simulation_before.json simulation_after.json
```

Then render either file with `integration/load_snapshot.py`. Schema mismatch fixes
belong in the exporter/adapter; do not rewrite the simulator or visualization core.

## Demo operation

```powershell
python phase8\switch_state.py stressed
python phase8\switch_state.py intervention
```

Use **File > Reopen** in UrbanTwin after switching. These packaged states are
explicit mock data. The intervention variant adds proposal geometry while retaining
stress metrics, so it does not claim an uncomputed improvement.

## Verification

```powershell
python phase3\validate_mock_data.py
python phase6\validate_metrics.py
python phase7\validate_interventions.py
python phase8\validate_states.py
```

The final packaged archive is `exports/UrbanTwin_Omniverse_Handoff.zip`.
