# Phase 9 — realism, materials, and the real-city simulation

Phase 9 sits on top of the Phase 8 stage and makes the imported city look like a
city rather than a data dump. It also generates a simulator city built from the
real OSM geometry, so the simulation and the visualisation finally describe the
same place.

Everything here is an `over`. No Phase 1–8 layer is modified, so the Phase 1
manifest hash — and with it `city_id` and the whole Phase 2–8 contract — stays
valid. All seven upstream validators still pass.

## Open this for the demo

```powershell
# in UrbanTwin (Kit): File > Open
C:\Users\arnav\Argus\phase9\scene\main.usda
```

Layer order, top wins:

```
generated/agents.usda       optional, from agents_instancer.py
generated/path_colors.usda  optional, from recolor_paths.py
cameras.usda
materials.usda              OSM-derived materials + cityLook variant set
streetscape.usda            511 trees, 39 street lamps
heights.usda                recovered / inferred building heights
look.usda                   ground, road and fallback building surfaces
lighting.usda               sun with shadows
../../phase8/scene/main.usda    the final city + demoState variants
```

Two variant sets on `/World`:

| set | variants | switch with |
|---|---|---|
| `demoState` | `Stressed`, `Intervention` | `python phase8\switch_state.py <name>` |
| `cityLook` | `realistic`, `analytic` | Stage panel on `/World`, or the variant dropdown |

Use `realistic` for hero shots and `analytic` when simulation colour is overlaid —
the desaturated palette stops the two colour systems fighting.

## What changed, and where it came from

### Materials — `build_materials.py` → `scene/materials.usda`

Phase 1 painted all 623 buildings one hardcoded grey `(0.63, 0.69, 0.75)`, and
every road, path and green space a single flat colour. But it also stored each
object's **complete OSM tag dictionary** on the prim as `urbantwin:osmTags`. The
data for a realistic city was already in the file; only the use of it was missing.

Resolution order for walls: explicit `building:colour` / `building:material`
→ `building` class → `amenity`/`shop` → level count. Roofs come from
`roof:colour` / `roof:material` via a `UsdGeom.Subset` on face 0 — buildings are
extruded prisms whose face 0 is the roof cap, so the split needs no new geometry.
Roads use `surface` and `highway` class; green spaces use `leisure`.

Result: **12 distinct wall materials across 623 buildings, 623 roof subsets.**
Materials are ~30 shared `UsdPreviewSurface` prims, not one per building.

### Making the citizens walk

```powershell
python integration\export_snapshot.py --state before --frames 60 --duration 60
python phase9\agents_instancer.py data\simulation_before_*.json --metric heat_exposure
```

Then press **play** on the timeline in Kit.

Each agent advances along its own route at that citizen's own pace — the
simulator's `travel_minutes` for them, which comes from their survey-calibrated
walking speed over the route they chose. Fast and slow walkers visibly differ,
and that difference is real.

Motion is a **sequence of ordinary v1 snapshots** using the contract's existing
`sequence` and `timestamp` fields. The schema is unchanged and every frame still
passes `phase3/validate_mock_data.py`.

Two honest caveats:

- Positions *between* frames are interpolated for display. The simulator decides
  the route and the trip duration, not the coordinates.
- Edge colours (crowding, heat) are one simulated equilibrium held constant
  across the window. The animation shows people moving through a fixed
  situation — **not** the city changing over time.

Animating also stamps `startTimeCode`/`endTimeCode` onto `scene/main.usda`,
because USD reads the timeline range from the root layer and ignores sublayers.
Regenerating from a single snapshot clears it again.

### Heights — `recover_heights.py` → `scene/heights.usda`

Phase 1 only imports ways tagged `building=*` (`build_city.py:80`). In this
extract the real 3D massing lives on **425 `building:part` ways**, which carry no
`building` tag and were therefore never imported. That is why only 3 of 623
buildings had a surveyed height and 490 sat at the flat 12 m fallback.

Only the top ring's z is rewritten, so footprint XY is provably unchanged —
`validate_phase9.py` asserts this against the Phase 1 stage.

**Be precise about what is real here.** Every prim records its source in
`urbantwin:heightSource`:

| source | count | meaning |
|---|---|---|
| `osm_height` | 3 | surveyed height tag |
| `osm_building_part_levels` | 17 | recovered from a `building:part` way |
| `assumed_3m_per_osm_level` | 203 | real `building:levels`, 3 m assumed per level |
| `inferred_from_building_type` | 107 | **inferred** from the `building` class |
| `inferred_from_neighbours` | 174 | **inferred** — median of nearest known-height buildings |
| `assumed_12m` | 119 | untouched Phase 1 fallback |

So **223 of 623 heights derive from real OSM data**; the rest are documented
inference. Do not describe the skyline as surveyed.

Only 23 buildings matched a `building:part`: 284 of the 306 unmatched parts sit
more than 15 m from any footprint, because they belong to buildings Phase 1 never
imported — the boundary-clipped polygons and unassembled multipolygon relations
already listed in the manifest's `limitations`.

### Streetscape — `place_trees.py` → `scene/streetscape.usda`

**511 trees and 39 street lamps at their surveyed OSM positions** (498
`natural=tree` nodes, 3 `natural=tree_row` ways sampled at 8 m, 39
`highway=street_lamp`). Not a decorative scatter — for a project about shade,
the trees stand where the trees actually stand.

Two `PointInstancer` prims total, three tree prototypes, with per-tree scale and
rotation derived deterministically from the OSM node id so the row is not visibly
cloned but the scene is byte-identical between runs.

### Lighting — `set_scenario.py`

```powershell
python phase9\set_scenario.py baseline|heat|rain|dusk
```

`dusk` is new: a low warm sun raking across the streets. It is the most
photogenic frame available and costs nothing — use it for stills, not for the
heat scenario, since a 42 °C claim under dusk light reads wrong.

## The real-city simulation — `build_city_from_osm.py`

```powershell
python phase9\build_city_from_osm.py
cd Simulation; python main.py citizens_osm.json city_osm.json
```

Writes `Simulation/city_osm.json` and `Simulation/citizens_osm.json` in the
simulator's own schema, where the buildings **are** OSM buildings and the routes
**are** real walking paths over the Phase 2 pedestrian graph with measured
lengths. Reuses the graph and pathfinding in
`integration/propose_route_mapping.py` rather than duplicating them.

Current output: 9 zones, 28 buildings, 92 routes, 240 citizens, runs in ~0.6 s.
Real named places appear in the output — UCL School of Pharmacy, UCL Institute of
Education, SOAS Gallery, Imperial Hotel, Waitrose.

**Every route carries `osm_edges`**, the ordered Phase 2 edge ids it traverses.
That is the point: there is no separate route mapping to agree, because the
simulator's city *is* the OSM city.

The simulator needs no changes — it already accepts
`python main.py <citizens.json> <city.json>`. The 8-building demo is untouched
and still passes all its asserts; this is an additional city, not a replacement.

## Regenerate everything

```powershell
python phase9\recover_heights.py
python phase9\build_materials.py
python phase9\place_trees.py
python phase9\build_city_from_osm.py
python phase9\validate_phase9.py
```

## Viewport settings that are not in USD

Set these in Kit before recording — none of them live in the scene file:

1. **Grid off** — Viewport ⋮ → Show → Grid
2. **HUD off** — Viewport ⋮ → Show → Heads Up Display
3. **Deselect**, so the move gizmo is out of shot
4. **RTX – Real-Time** at minimum; shadows are what make the shade readable

## Limitations

- Heights: 223 of 623 from real OSM data, the rest inferred or left at the Phase 1
  fallback. `urbantwin:heightSource` records which is which.
- Materials: roughly a third of buildings carry explicit colour/material tags; the
  rest are resolved from building class, which is a convention, not a survey.
- The tree canopy is geometry only — the simulator's `shade` values are not
  derived from it.
- Trees, lamps and the 430 discarded `building:part` ways are visual/height
  corrections only; the Phase 1 manifest is unchanged and still states its own
  original limitations.
- The OSM-derived city does not change the audit status of the behavioural model.
  The survey pipeline still does not exist, so citizen parameters remain archetype
  means with a deterministic spread, **not** survey-calibrated.
