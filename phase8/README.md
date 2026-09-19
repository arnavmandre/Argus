# Phase 8 — fast stressed/intervention switching

Phase 8 packages two independent generated scenes into the OpenUSD variant set
`demoState` on `/World`:

- `Stressed`: 45°C, 100K population equivalent, 300 representative agents,
  routes and stress metric bands, with no intervention geometry.
- `Intervention`: the same scenario, agents, routes and metrics, plus one proposed
  cyan shade canopy on `edge_1255`.

The active stage is `scene/main.usda`; its initial selection is `Stressed`.
State assets live separately under `states/stressed` and `states/intervention`,
so switching does not regenerate or overwrite shared agent/metric/intervention
layers. Both states still reference the accepted Phase 2 base city by relative path,
so retain the repository directory structure when copying the demo.

This is a stress-versus-proposal comparison. It is not a measured before/after
improvement: metrics deliberately remain identical until the teammate supplies a
post-intervention simulation snapshot.

## Fast switching

From the repository root:

```powershell
python phase8\switch_state.py stressed
python phase8\switch_state.py intervention
```

After each command, use **File > Reopen** in UrbanTwin. The command atomically
replaces only `scene/selection.usda`. An already-open USD stage may retain the old
layer until explicitly reopened.

You can also select `/World` in Stage and change its `demoState` variant between
`Stressed` and `Intervention` in the Property panel if the UrbanTwin property UI
shows variant controls. That changes the open stage's edit state and may mark it
unsaved; the command-line switch remains the reproducible demo method.

## Rebuild and validation

```powershell
python phase8\build_states.py
python phase8\validate_states.py
```

Rebuilding regenerates both state directories from the Phase 3 mock files and
resets the active selection to `Stressed`. Validation switches both variants and
confirms scenario, agents, routes, heat and crowding are equal; only the canopy
appears in `Intervention`. It restores `Stressed` afterward.

## MANUAL STEP REQUIRED

1. In UrbanTwin open
   `C:\Users\arnav\Argus\phase8\scene\main.usda`.
2. Select the **Overview** camera, then select **World > Interventions** and press
   **F** if needed. The initial Stressed state has no canopy.
3. Run `python phase8\switch_state.py intervention`, return to UrbanTwin and use
   **File > Reopen**. The cyan canopy should appear while metric colors and agents
   remain the same.
4. Run `python phase8\switch_state.py stressed` and reopen. The canopy should
   disappear immediately.

For the presentation, keep two commands in terminal history and use the same
camera for both states. Phase 9 is teammate integration and begins only when an
actual simulator output file is available.
