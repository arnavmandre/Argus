# Phase 6 — heat exposure and crowding overlays

Phase 6 visualizes the `heat_exposure` and `crowding` values supplied in a valid
snapshot. It does not calculate either metric. The active stage is
`scene/main.usda`, currently generated from `mock_stress.json` with 300 agents,
156 route segments, 156 heat bands and 156 crowd bands.

Each mapped segment has two parallel bands 0.55 m above the surface:

| Metric | Low `[0,0.3)` | Moderate `[0.3,0.7)` | High `[0.7,1]` |
|---|---|---|---|
| Crowding | green | amber | magenta |
| Heat exposure | blue | orange | red |

Crowding is offset 0.65 m to one side of the centreline; heat is offset 0.65 m
to the other. Orange route curves remain centered below them. Segment direction
comes from OSM, so the visual left/right side can reverse between independently
mapped ways; metric identity is carried by color and Stage scope.

These thresholds are presentation bins and are explicitly marked in USD as not
scientific thresholds. Each curve stores `urbantwin:edgeId`, `metric`, `value`,
and `class`. The metrics in current files are labelled demo/mock values.

## Playback

From the repository root:

```powershell
python phase6\omniverse_bridge.py phase3\mock_data\mock_normal.json
python phase6\omniverse_bridge.py phase3\mock_data\mock_stress.json
```

The command validates the complete snapshot, writes `metrics.usda`, then updates
the agents and route layers. Full-snapshot semantics remove metric curves absent
from the next valid state. Invalid input is rejected before generated layers change.

## Automated validation

```powershell
python phase6\validate_metrics.py
```

This opens the composed stage, checks every authored value/class/color against
both normal and stress JSON, verifies the color transition, and confirms the
mock problem segment `edge_1255` is high crowd under stress.

## MANUAL STEP REQUIRED

1. In UrbanTwin, choose **File > Open** and open
   `C:\Users\arnav\Argus\phase6\scene\main.usda`.
2. Select the **Overview** camera. The currently generated stress scene should
   show colored bands across the study area.
3. Expand **World > Simulation > HeatZones** and **CrowdZones**. Each should have
   156 edge children.
4. Search for `edge_1255`. Under CrowdZones it should be magenta (high crowd),
   while under HeatZones it should be red (high heat).
5. To compare normal, run the normal command above and use **File > Reopen**.
   Normal crowd bands should become green and normal heat bands orange because
   the mock heat value is 0.34 (moderate).
6. Run the stress command again and reopen to restore the demo stress state.

Stop after confirming the bands are visible and their normal/stress colors are
easy to distinguish. Phase 7 will visualize intervention commands; it is not
included here.
