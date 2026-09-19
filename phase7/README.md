# Phase 7 — intervention proposal visualization

Phase 7 converts validated intervention commands into simple proposed geometry.
The active stage is `scene/main.usda`, currently generated from
`mock_intervention.json`. It contains one cyan `ADD_SHADE` canopy on `edge_1255`,
plus the same 300 agents and unchanged stress heat/crowding values.

All proposal roots store their original intervention ID, type, target/amount,
`status = proposed`, and `visualOnly = true`. `/World/Interventions` is labelled
`PROPOSED - EFFECT NOT SIMULATED`. This prevents proposal geometry from implying
that the intervention works or that any metric improved.

Supported contract commands:

| Type | Visualization |
|---|---|
| `ADD_SHADE` | Cyan canopy and two support posts along the target segment |
| `ADD_GREENERY` | Simple green canopies and brown trunks along the target |
| `ADD_ROUTE` | Bright cyan curve through the supplied proposal points |
| `INCREASE_PATH_CAPACITY` | Wider cyan proposal band on the existing path |
| `IMPROVE_ACCESSIBILITY` | Blue proposal band on the existing path |

The `amount` field controls only proposal visualization extent or quantity. It
does not represent verified physical dimensions, added capacity, accessibility
gain, heat reduction, or effectiveness.

## Playback

```powershell
python phase7\omniverse_bridge.py phase3\mock_data\mock_stress.json
python phase7\omniverse_bridge.py phase3\mock_data\mock_intervention.json
```

The stress command produces an empty Interventions scope. The intervention
command restores the shade proposal. Reopen the stage after each command because
an already-running Omniverse process may cache the replaced generated layer.

## Automated validation

```powershell
python phase7\validate_interventions.py
```

The test exercises all five contract types, verifies their USD geometry and
proposal metadata, confirms empty-state removal, and checks that the intervention
fixture preserves stress agents and metrics exactly.

## MANUAL STEP REQUIRED

1. In UrbanTwin choose **File > Open** and open
   `C:\Users\arnav\Argus\phase7\scene\main.usda`.
2. Expand **World > Interventions**. It should contain one proposal. Select it
   and press **F** to frame the target corridor.
3. Confirm a bright cyan shade canopy with two supports is visible over the path.
   It is a proposal marker, not construction-ready design.
4. Run the stress command above and use **File > Reopen**. Interventions should
   become empty while agents, routes and metric bands remain.
5. Run the intervention command and reopen. The canopy should return, while heat
   and crowd colors remain identical to stress.

Stop after confirming the proposal toggles and metrics remain unchanged. Phase 8
will package fast stressed/intervention switching for the demo.
