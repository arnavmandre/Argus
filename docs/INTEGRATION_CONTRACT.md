# Simulator → visualization contract v1

Phase 3 freezes the v1 file contract and provides a machine-readable schema,
validator, and mock fixtures. No visualization bridge or simulator is implemented.
Phase 2 adds `phase2/scene/edge_registry.json`: frozen `edge_001` style aliases
map to the existing OSM prim paths. The future state contract will accept these
aliases or original OSM IDs; choose one convention per snapshot and reject
duplicate references to the same segment under different names. The registry's
`city_id` is the SHA-256 of the frozen Phase 1 manifest bytes. It is also authored
on `/World` as `urbantwin:cityId`. `phase2/scene_index.py` verifies this match.
The simulator owns all metric calculations. `legacy/synthetic_city/city.json` is a different,
legacy static geometry format and must not be used as this state payload.

UTF-8 JSON, one complete snapshot per file. Producer writes a temporary file,
closes it, then atomically replaces `simulation_output.json`. Consumer validates
the entire snapshot before changing the scene; invalid input keeps the last good
state. A run ID plus sequence number identifies ordering and resets.

```json
{
  "schema_version": "1.0",
  "city_id": "<frozen manifest SHA-256>",
  "run_id": "demo-001",
  "sequence": 0,
  "timestamp": 12.5,
  "data_kind": "mock",
  "label": "DEMO / MOCK SIMULATION DATA",
  "scenario": {"temperature_c": 45, "population_equivalent": 100000},
  "agents": [
    {"id": "citizen_001", "x": 10.2, "y": 4.7, "z": 0,
     "route": ["<edge id from manifest>"], "stress": 0.72, "heat_exposure": 0.81}
  ],
  "edges": {
    "<edge id from manifest>": {"crowding": 0.88, "heat_exposure": 0.76, "accessibility": 0.43}
  },
  "interventions": [
    {"id": "proposal_001", "type": "ADD_SHADE", "target": "<edge id from manifest>", "amount": 0.5}
  ]
}
```

The example is illustrative, not a loadable mock file; replace placeholder IDs
with aliases from `phase2/scene/edge_registry.json` or original keys from
`phase1/scene/manifest.json`. The machine-readable JSON Schema and
project-aware validator are `phase3/simulation_state.schema.json` and
`phase3/validate_mock_data.py`. The integration entry point is
`integration/load_snapshot.py`; it authors agents, routes, metric overlays, and
proposal geometry into `integration/runtime/scene`.

## Validation rules

- Required top-level keys are those shown. Reject unsupported schema versions.
- `city_id`: hash of the frozen manifest bytes, not the source OSM hash inside it.
  Reject a different city to prevent valid-looking IDs from controlling the wrong scene.
- `run_id`, agent IDs and intervention IDs: nonempty strings; agent/intervention
  IDs unique within the snapshot. Treat identifiers as data, never executable paths.
- `sequence`: nonnegative integer increasing within a run. `timestamp`: finite,
  nonnegative seconds since run start. Reset ordering when `run_id` changes.
- `data_kind`: `mock` or `simulation`; mock requires the explicit demo label.
- `temperature_c`: finite Celsius value supplied by the simulator;
  `population_equivalent`: nonnegative integer. It is not the rendered agent count.
- Agent coordinates: finite metres, X east, Y north, Z up; Z is foot elevation.
  Origin and projection come from the manifest. Latitude/longitude are not accepted
  directly. The legacy Y-up scene requires an explicitly agreed coordinate adapter.
- Agent `route`: ordered array of known manifest edge IDs, possibly empty.
  These paths describe supplied route geometry, not a route-choice algorithm.
- `stress`, `heat_exposure`, `crowding`, `accessibility`: finite numbers in [0,1].
  Higher crowding/heat/stress means worse; higher accessibility means better.
  Optional missing metrics mean unknown, never silently zero.
- Every `edges` key and existing-edge intervention target must exist in the manifest.
  Reject unknown IDs before applying anything. Do not assume `edge_012` exists.
- `interventions`: array of proposals. Types: `ADD_SHADE`, `ADD_GREENERY`,
  `ADD_ROUTE`, `INCREASE_PATH_CAPACITY`, `IMPROVE_ACCESSIBILITY`.
  For existing-edge types, require `target` and finite `amount` in [0,1], defined
  as a visual proposal strength, not a physical capacity gain or efficacy estimate.
  `ADD_ROUTE` instead requires a unique `new_edge_id` and `points` (at least two
  XYZ triples in the same frame). A new route is proposal geometry until a later
  city/manifest revision establishes its simulation mapping.
- Full snapshot semantics: absent agents and interventions are removed; omitted
  edge metrics become unknown; an empty agents array resets agents.
- Begin with at most 500 representative rendered agents, sampled by the producer.
  More records should produce a clear validation error until a larger budget is
  explicitly configured. Never imply these are all 100K represented people.

## Metric legend and comparison semantics

Proposed crowd/heat bins: low `[0,0.3)`, moderate `[0.3,0.7)`, high `[0.7,1]`.
These are display thresholds, not physiological or engineering limits.
Temperature lighting is an illustrative scenario cue, not a heat computation.
Before/after snapshots must identify the same city and scenario. The simulator
supplies post-intervention metrics; geometry changes alone do not imply improvement.

## Teammate handoff

Agree on this contract and freeze the study-area manifest before integrating.
Use its `edges` mapping and projected coordinates as the common spatial boundary.
OSM segments currently represent visual paths; connectivity, routing eligibility,
access restrictions and graph construction belong to the simulation owner.
The bridge exposes `load_state`, agent create/update/remove/reset,
route highlighting, separate heat/crowd overlays and proposal visualization,
without importing simulator internal classes. File playback is the supported MVP;
networking remains deferred.
