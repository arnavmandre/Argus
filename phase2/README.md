# Phase 2 — scene structure and stable path IDs

Phase 1 was visually accepted by the user. Phase 2 structural validation passes:
2,291 pedestrian segment aliases resolve to existing meshes; geometry, topology
and display colours match the Phase 1 base. Invalid IDs and an incompatible stage
are rejected. No simulation behavior or mock state playback has been built.

## Composition

`scene/main.usda` composes, strongest first:

1. `interventions.usda`: empty `/World/Interventions` scope.
2. `simulation.usda`: empty `/World/Simulation` with Agents, Routes, HeatZones, CrowdZones.
3. `semantics.usda`: city identity and path metadata, without geometry duplication.
4. `../../phase1/scene/main.usda`: accepted base city, environment and cameras.

All authored stages use metres and Z-up. Keep both phase directories together
when sharing; the relative sublayer references are intentional.

## IDs and teammate handoff

`scene/edge_registry.json` is the frozen mapping between readable aliases,
original OSM segment IDs, USD paths and local centreline points. For example:

```text
edge_012
  -> osm_w1006641959_n7524408719_n11699240743
  -> /World/PedestrianPaths/osm_w1006641959_n7524408719_n11699240743
```

USD prim names retain the OSM identifiers. `edge_012` is an alias, not a renamed
prim, so `/World/PedestrianPaths/edge_012` is not a valid direct path. Use the
registry or the tested resolver:

```powershell
python phase2\scene_index.py edge_012
python phase2\validate_scene.py
```

From Python with the repository root on `sys.path`:

```python
from pxr import Usd
from phase2.scene_index import SceneIndex

stage = Usd.Stage.Open("phase2/scene/main.usda")
index = SceneIndex(stage)
prim = index.get_edge("edge_012")
```

The same resolver accepts the original OSM identifier. Each path has custom
attributes `urbantwin:edgeId`, `sourceId`, `osmWayId`, `centerline`, `widthM`,
and `widthSource`. `/World` carries `urbantwin:cityId` matching the registry.

Aliases were allocated once in sorted source-ID order. Rebuilding with
`python phase2\prepare_scene.py` reuses the saved mapping. A changed city manifest
is rejected; use a new output directory and coordinate a new city revision with
the teammate instead of silently reassigning aliases. The preparation command
regenerates the Phase 2 layers, including the empty future layers; do not run it
over manually authored simulation/intervention work in later phases.

These are visual segments, not complete walkable corridors or a routing graph.
They retain the original data limitations, including missing sidewalks, private
paths and area-boundary geometry. A demo corridor should be explicitly selected
and may comprise multiple segment IDs. No segment has measured heat or crowd data.

## MANUAL STEP REQUIRED

1. In the running UrbanTwin app, save any unsaved work under its own filename.
2. Choose **File > Open**, then
   `C:\Users\arnav\Argus\phase2\scene\main.usda`.
3. Select **Overview** in the viewport camera menu if needed. The city should look
   the same as Phase 1.
4. Expand **World** in Stage. You should now see **Simulation** and
   **Interventions**. Expand Simulation to see the four empty child scopes.
5. To inspect the example edge, search Stage for
   `osm_w1006641959_n7524408719_n11699240743`, select it, and find
   `urbantwin:edgeId` in Property. Its value is `edge_012`.

The next phase is Phase 3: agree the machine-readable JSON schema and create
explicitly labelled normal, stress and intervention mock snapshots. That work
is not included in Phase 2.
