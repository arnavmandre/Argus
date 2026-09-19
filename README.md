# UrbanTwin AI — Omniverse digital twin

This repository contains the visual digital-twin side of UrbanTwin AI. It imports
a real OpenStreetMap study area into OpenUSD and visualizes external JSON snapshots
as citizens, routes, heat, crowding, and proposed urban interventions. It does not
contain the behavioral simulation engine.

## Open the current demo

Open this stage in the UrbanTwin Kit app:

```text
C:\Users\arnav\Argus\phase8\scene\main.usda
```

Switch the packaged demo state from PowerShell:

```powershell
cd C:\Users\arnav\Argus
python phase8\switch_state.py stressed
python phase8\switch_state.py intervention
```

Use **File > Reopen** in UrbanTwin after switching. The intervention state adds a
proposed shade canopy; scenario metrics deliberately remain unchanged until a real
post-intervention simulator snapshot is available.

## Main documentation

- [Setup and environment audit](docs/OMNIVERSE_SETUP.md)
- [Simulator integration contract](docs/INTEGRATION_CONTRACT.md)
- [Omniverse teammate handoff](docs/OMNIVERSE_HANDOFF.md)
- [Project brief](docs/PROJECT_BRIEF.md)
- [Current Phase 8 demo guide](phase8/README.md)
- [Repository structure](docs/REPOSITORY_STRUCTURE.md)

## Validation

Run the current end-to-end state check:

```powershell
python phase8\validate_states.py
```

Validate a teammate snapshot before integration:

```powershell
python phase3\validate_mock_data.py path\to\simulation_output.json
```

Phase 9 begins when the teammate supplies an actual simulator output file.
The workspace currently contains a simulator report with a different schema;
the required adapter work is documented in the Omniverse handoff.
