# Phase 4 — lightweight pedestrian agents

Update: the current mock fixtures now contain 120 normal / 300 stress agents
spread across 24 corridors. The historical counts below describe the original
Phase 4 checkpoint. Use `phase5/scene/main.usda` for the current generated demo.

Phase 4 consumes a complete, validated Phase 3 snapshot and authors lightweight
capsule pedestrians into a separate OpenUSD layer. It does not calculate agent
behavior, routes, heat, crowding, accessibility, or intervention effects.

The active scene is `scene/main.usda`. It composes `agents.usda` over the accepted
Phase 2 scene. The current generated layer contains `mock_normal.json`: 18 blue
representative agents for a population equivalent of 50K.

Agents use one `UsdGeomPointInstancer` and one capsule prototype. This is compact
and appropriate for hundreds of visual representatives. Simulator string IDs,
stress values, heat exposure and JSON-encoded routes are aligned arrays on
`/World/Simulation/Agents/AgentInstancer`. USD integer instance IDs are stable
hashes; the simulator string IDs remain authoritative.

Coordinates are metres: X east, Y north, Z up. An agent's JSON position is its
foot position. The capsule prototype is offset upward by 0.85 m and is 1.7 m tall
including caps. Point-instancer positions are stored as 32-bit floats, so readback
can differ from JSON by a tiny rounding amount (validated below 0.1 mm).

## Load a complete snapshot

From the repository root:

```powershell
python phase4\omniverse_bridge.py phase3\mock_data\mock_normal.json
python phase4\omniverse_bridge.py phase3\mock_data\mock_stress.json
```

Each command validates the full snapshot before writing. It atomically replaces
`agents.usda`; absent agents are removed, existing positions are updated, and new
agents appear. Invalid input leaves the last valid layer unchanged. `load_state`,
`spawn_agents`, `update_agents`, and `reset_agents` are available in the bridge.
Reset takes a valid template snapshot and writes the same state metadata with an
empty agent list.

This phase intentionally uses full-file playback. Do not run both commands while
Omniverse is saving edits to the same generated layer. The generated `agents.usda`
should be treated as bridge-owned output.

## Validation

```powershell
python phase4\validate_agents.py
```

The check opens the composed stage and verifies base-city composition, JSON-to-USD
coordinates and IDs, normal-to-stress replacement, removal/reset, and preservation
of the last valid layer after invalid input.

## MANUAL STEP REQUIRED

1. In UrbanTwin, save any manual work under a separate filename.
2. Choose **File > Open** and open
   `C:\Users\arnav\Argus\phase4\scene\main.usda`.
3. In Stage, expand **World > Simulation > Agents > AgentInstancer**. The normal
   fixture should show 18 small blue capsules along the selected corridor.
4. If they are hard to locate, select `AgentInstancer` in Stage and press **F** to
   frame it. Use Perspective view to orbit around them.
5. Keep UrbanTwin open, run the stress command above, then use **File > Reopen**
   (or close and reopen the same stage if Reopen is unavailable). It should show
   48 agents. Automatic live reload is not claimed or required.

Stop after confirming that capsules appear in both counts. Phase 5 will visualize
route usage and is not part of this phase.
