# Demo presentation layer

Everything here is **visual only** and sits as an `over` on top of the frozen
Phase 1/2/8 scene. No frozen layer is modified, and nothing here contributes a
simulation value.

## Open this for the demo

```powershell
# in UrbanTwin (Kit): File > Open
C:\Users\arnav\Argus\presentation\demo.usda
```

Layer order is `results → presentation → phase8/scene/main.usda`.
For the plain city with no data painted on it, open `presentation/main.usda`.

## What the layer adds

| | |
|---|---|
| **Sun with soft shadows** | `DistantLight` at ~38° elevation from the south-west, 0.53° angular diameter (the sun's real size, so the penumbra looks right). This is what makes shade legible before any data is overlaid. |
| **Lighting presets** | Variant set `lighting` on `/World/Presentation`: `baseline` and `extreme_heat` (hotter, dimmer sky, warmer key). Switch it with the before/after toggle — half the perceived difference is the light, not the colours. |
| **Dark matte ground** | Extends well past the tile so the city stops floating on the viewport grid. |
| **Building material** | Warm off-white, roughness 0.72, non-metallic. Flat pure white destroys massing readability and blows out next to a bright sun. Bound on `/World/Buildings`, which is inheritable, so all 623 meshes pick it up without editing the frozen layer. |
| **Three demo cameras** | `Demo_01_Overview` (~28° elevation — the old default was near top-down, which reads as a map not a city), `Demo_02_Corridor` (street level), `Demo_03_ProblemZone`. |

## Three viewport settings that are NOT in USD

These live in the app, not the scene. Set them before recording:

1. **Turn the grid off** — the grid is on in the current screenshot and is the single noisiest thing in frame. *Viewport ⋮ menu → Show → Grid*.
2. **Hide the HUD** — the "Process Memory: 1.1 GiB used" readout is visible in the current capture. *Viewport ⋮ → Show → Heads Up Display*.
3. **Deselect everything** before capturing, so the translate gizmo is not in shot.

## Painting simulator results onto the city

```powershell
python presentation\colorize_from_snapshot.py --state before --metric crowding
python presentation\colorize_from_snapshot.py --state after  --metric crowding
python presentation\colorize_from_snapshot.py --state before --metric heat
```

Writes `results_<state>_<metric>.usda`. Swap which one `demo.usda` sublayers to
flip between before and after.

**Colour ramp is deliberately not red/green.** It runs dark blue → teal →
yellow → orange → dark red, which is ordered by lightness as well as hue, so it
survives the most common form of colour blindness, greyscale, and a washed-out
projector. A legend strip is authored at the south-west corner of the tile.

Citizens are drawn as one `PointInstancer`, not one prim each — 500 separate
prims cost real frame time on 8 GB of VRAM, one instancer costs almost nothing.
Agent colour is per-citizen simulated comfort (blue comfortable → red poor).

## Route mapping — read this before demoing

```powershell
python integration\build_route_mapping.py --report   # inspect, write nothing
python integration\build_route_mapping.py            # write route_mapping.json
```

This is what connects the simulator's abstract `R1`–`R18` to real `edge_*` IDs.
It builds a walking graph from the Phase 2 edge registry (2,130 nodes / 2,291
edges), places one anchor node per simulator building, and computes genuinely
distinct walking paths between them with a penalty-based k-shortest-paths
search.

**The current output is marked `PROVISIONAL`, and that matters.** The anchors
were auto-placed by farthest-point sampling. The graph, the paths and the
distances are all real — but *which* OSM location stands for "the hospital" has
not been agreed by anyone. Until a human fills in `integration/route_anchors.json`
with chosen OSM node IDs and reruns:

- the mapping is fine for **rendering and for proving the pipeline works**;
- it is **not** something to describe to judges as the real geography of a
  specific place.

`--apply-distances` (which rewrites `Simulation/city.json` route lengths with
the measured OSM distances) deliberately **refuses to run** while the status is
`PROVISIONAL`, so a guessed geography cannot leak into the simulation silently.

### To make it real

Put chosen node IDs in `integration/route_anchors.json`:

```json
{
  "anchors": {
    "H1": "12393855010", "H2": "...", "H3": "...", "T1": "...",
    "W1": "...", "S1": "...", "HOS1": "...", "M1": "..."
  }
}
```

Rerun; status becomes `HUMAN_ANCHORED` and `--apply-distances` unlocks.
