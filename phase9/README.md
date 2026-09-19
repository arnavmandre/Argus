# Demo presentation layer

Visual only. Everything here is an `over` on top of the frozen Phase 1/2 scene —
no geometry, no semantics, no `city_id` is touched, and nothing here contributes
a simulation value.

## Open this for the demo

```powershell
# in UrbanTwin (Kit): File > Open
C:\Users\arnav\Argus\phase9\scene\main.usda
```

Layer order (top wins):

```
generated/agents.usda      <- optional, from agents_instancer.py
generated/path_colors.usda <- optional, from recolor_paths.py
cameras.usda
look.usda
lighting.usda
../../phase8/scene/main.usda   <- the final city + demoState variants
```

The stage opens fine without the two generated layers.

Phase 8 is the final city. It carries the `Stressed` / `Intervention`
variants and chains down through Phase 2 semantics to Phase 1 geometry, so
the presentation stage sits on top of everything:

```powershell
python phase8\switch_state.py stressed
python phase8\switch_state.py intervention
```

Then **File > Reopen** in Kit. Verified: the variant selection propagates
through to this stage.

## What it adds

| | |
|---|---|
| **Sun with real shadows** | `ShadowAPI` with `shadow:enable`, 0.53° angular diameter (the sun's true size, so the penumbra looks right), ~40–50° elevation. This is what makes shade legible before any data is overlaid — the whole project is about heat and shade. |
| **Scenario lighting** | `set_scenario.py baseline\|heat\|rain`. Use it with the before/after toggle: half the perceived difference in a heat demo comes from the light, not the path colours. |
| **Matte materials** | Warm off-white buildings (roughness 0.78), dark roads, dark ground. Flat pure white destroyed form readability at overview zoom and blows out next to a bright sun. Bound on the `Buildings`/`Roads` scopes, which inherits to all 623 meshes without per-prim edits. |
| **Extended ground** | The existing Phase 1 ground is *overridden* and scaled to 2600 m so the tile fades out instead of ending at a hard edge over the viewport grid. |
| **Saved cameras** | `Overview`, `Corridor`, `ProblemZone`. Flying a camera live on stage is the easiest thing to get wrong. |

## Three settings that are NOT in USD

These live in the app. Set them before recording:

1. **Grid off** — it's on in the current screenshot and is the noisiest thing in frame. *Viewport ⋮ → Show → Grid*.
2. **HUD off** — the "Process Memory: 1.1 GiB used" readout is visible in the current capture. *Viewport ⋮ → Show → Heads Up Display*.
3. **Deselect everything**, so the translate gizmo is out of shot.

RTX Real-Time is enough; Path Traced looks better if the frame rate holds.

## Painting results onto the city

```powershell
python phase9\recolor_paths.py     <canonical_snapshot.json>
python phase9\agents_instancer.py  <canonical_snapshot.json>
```

Both take a **canonical v1 snapshot** (`docs/INTEGRATION_CONTRACT.md`), not the
simulator's raw `urbantwin_demo_output.json`. That boundary is deliberate: the
exporter owns normalisation and route→edge mapping, so the visualisation never
has to guess. Output goes to `scene/generated/`, which the demo stage sublayers
automatically.

Agents are one `PointInstancer` binned into a few coloured prototypes, not one
prim per citizen — 300+ separate spheres cost real frame time on 8 GB of VRAM,
and prototype indices render consistently where per-instance colour primvars do
not.

## Route mapping — read before demoing

```powershell
python integration\propose_route_mapping.py
```

This is what connects the simulator's abstract `R1`–`R18` to real `edge_*` IDs.
It builds a walking graph from the Phase 2 edge registry (2,130 nodes / 2,291
edges) and computes genuinely distinct walking paths between anchor nodes.

It writes **`integration/route_mapping.proposal.json`**, never
`route_mapping.json`. That is intentional — `integration/README.md` reserves the
real filename for a mapping the team has agreed. The graph, paths and distances
are real, but *which* OSM location stands for "the hospital" has not been agreed
by anyone, so the anchors are geometrically valid and semantically provisional.

Use the proposal for **rendering and for proving the pipeline works**. Do not
describe it to judges as the real geography of a specific place until someone
has reviewed the anchors and promoted it to `route_mapping.json`.

`Simulation/city_osm.proposal.json` holds the same routes with their real
measured OSM lengths, for whenever you do promote it.
