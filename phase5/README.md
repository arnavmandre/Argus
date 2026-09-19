# Phase 5 — supplied route and path-usage visualization

Phase 5 adds orange route curves to the Phase 4 agent scene. It reads route IDs
from each validated agent record, resolves them through the frozen Phase 2 edge
registry, and draws the registered segment centreline 0.35 m above the path.
It does not construct paths or choose routes.

The active stage is `scene/main.usda`. The generated scene currently contains
the distributed stress fixture: 300 representative blue capsules and 156 orange
segments across 24 corridors throughout the study area. Normal uses 120 agents.
`urbantwin:agentUsageCount` counts the displayed citizens assigned to each segment.
The current mock problem edge is `edge_1255`. The original small-square test route
has been replaced; frozen city IDs and edge mappings have not changed.

Under `/World/Simulation/Routes`, each curve is named by its stable alias, such
as `edge_008`. Its custom attributes store the stable edge ID, original OSM ID,
and representative-agent usage count. Usage is a count of displayed records,
not the scenario's 100K population equivalent and not a crowding calculation.

## Load route states

From the repository root:

```powershell
python phase5\omniverse_bridge.py phase3\mock_data\mock_normal.json
python phase5\omniverse_bridge.py phase3\mock_data\mock_stress.json
```

Each command regenerates both `agents.usda` and `routes.usda`, then composes them
over the accepted Phase 2 scene. Full-snapshot semantics remove route curves that
are absent from the next snapshot. Invalid snapshots are rejected before either
generated layer changes. The route layer is bridge-owned output.

## Validation

```powershell
python phase5\validate_routes.py
```

The test verifies that supplied route IDs create matching curves, registered
coordinates are preserved, changed route arrays change the visible route set,
usage counts align with agents, and reset removes agents and routes. It explicitly
reloads the stage because OpenUSD caches layers in a running process.

## MANUAL STEP REQUIRED

1. In UrbanTwin choose **File > Open** and open
   `C:\Users\arnav\Argus\phase5\scene\main.usda`.
2. Expand **World > Simulation > Routes**. You should see 156 edge entries.
3. Select **Routes** or one of its edges and press **F** to frame it. Orange lines
   should follow the corridor containing the blue agents.
4. Run the normal or stress command above and then use **File > Reopen**. The
   current mock fixtures use the same distributed route IDs, so agent count
   changes between 120 and 300 while route shapes remain the same. Automated validation separately
   confirms that changed route IDs change the authored curves.

Stop after confirming the orange route overlay is visible and aligned with the
paths. Phase 6 will visualize heat exposure and crowding as separate metric
overlays; it is not part of this phase.
