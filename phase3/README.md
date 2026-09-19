# Phase 3 — mock simulation data contract

This phase provides a strict JSON boundary between an external simulator and the
future Omniverse visualization bridge. It does not calculate behavior, routes,
heat, crowding, accessibility, or intervention effects.

The three fixtures are explicitly labelled **DEMO / MOCK SIMULATION DATA**:

- `mock_data/mock_normal.json`: 32°C, 50K population equivalent, 120 representative agents.
- `mock_data/mock_stress.json`: 45°C, 100K population equivalent, 300 representative agents.
- `mock_data/mock_intervention.json`: the same stress metrics plus a proposed `ADD_SHADE` command.

The intervention fixture deliberately keeps stress metrics unchanged. Visual
geometry alone does not claim improvement; the teammate's simulator must provide
a later post-intervention snapshot. Values are illustrative and are not measured
conditions or real simulator results.

`mock_data/demo_selection.json` records 24 geographically distributed corridors
(156 segments), covering approximately 762 x 779 m, and mock problem edge
`edge_1255`. Each corridor follows an existing OSM way in its original order.
Area boundaries and explicitly private/no-access ways are excluded. Missing
segments break corridors; no bridges across network gaps are invented.
These separate corridors are not asserted to form a city-wide connected network.
Selection is for visual fixtures, not route choice or an urban-planning conclusion.
Citizens are assigned among corridors and spaced by distance along each corridor,
with a +/-0.38 m lateral offset. Counts and metrics are authored mock values.
The intervention snapshot preserves all stress positions and metrics.

## Validate

From the repository root:

```powershell
python phase3\validate_mock_data.py
python phase3\test_validation.py
python phase3\validate_distribution.py
```

Validate a teammate file with:

```powershell
python phase3\validate_mock_data.py path\to\simulation_output.json
```

The validator checks JSON Schema 2020-12 plus the current city ID, known path IDs,
unique IDs, finite numbers, and consistent use of aliases. It requires the Python
`jsonschema` package. It rejects the entire snapshot on error; a future bridge
must retain the last valid visual state rather than partially applying invalid data.

Regenerate only the demo fixtures with:

```powershell
python phase3\generate_mock_data.py
```

Regeneration is deterministic against the frozen Phase 2 registry. If the city
revision changes, regenerate fixtures and coordinate the new `city_id` and edge
registry with the teammate.

See the complete field semantics and handoff rules in
[`../docs/INTEGRATION_CONTRACT.md`](../docs/INTEGRATION_CONTRACT.md). Phase 4 will consume
these files and create lightweight visual agents. It is not included here.
