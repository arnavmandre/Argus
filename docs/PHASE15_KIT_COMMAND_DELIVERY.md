# Phase 15 — Kit command delivery

Allow-listed dashboard view commands (`state`, `camera`, `overlay`) reach the
live streamed Kit viewport over the WebRTC data channel after the Python API
validates them.

## Flow

```text
Browser control change
  -> connection.send() in kit-webrtc-adapter
  -> POST /api/runs/{id}/view (allow-list)
  -> AppStreamer.sendMessage({ event_type: "urbantwin.view_command", payload })
  -> Kit extension urbantwin.view_commands
  -> viewport camera / overlay / state (best-effort)
```

The API returns `accepted: true`, `delivered: false`, `delivery: "webrtc_client"`.
The adapter sets `delivered: true` only when `sendMessage` succeeds.

## Kit host

Branch: `phase13-streaming-kit` in `kit-app-template`.

Extension: `source/extensions/urbantwin.view_commands` (mirror
`urbantwin.stage_autoload`). Empty `[dependencies]` in `extension.toml`.

Launch (from kit-app-template root):

```bat
launch_urbantwin_streaming.bat
```

That enables `--enable urbantwin.stage_autoload` and
`--enable urbantwin.view_commands` with `--ext-folder source\extensions`.

**Messaging:** Inbound commands use `omni.kit.livestream.messaging` when
importable; otherwise the extension subscribes on the carb event bus for
`urbantwin.view_command`. If messages never arrive, confirm the streaming stack
includes `omni.kit.livestream.messaging` (see comment in
`source/apps/urbantwin_streaming.kit` — not added to the generated lock by
default).

## Cameras

Regenerate demo cameras after changing `phase9/make_cameras.py`:

```powershell
cd C:\Users\arnav\Argus
python phase9\make_cameras.py
```

Kit loads `C:\Users\arnav\Argus\phase9\scene\main.usda`, which sublayers
`cameras.usda`. Allow-listed names: `Overview`, `Street`, `ProblemZone`,
`Aerial` (plus legacy `Corridor` in the scene).

## Dashboard

With live API and streaming Kit:

```powershell
python -m api --host 127.0.0.1 --port 8000
$env:URBANTWIN_API_BASE = "http://127.0.0.1:8000"
cd frontend; npm run dev
```

Change Camera / Overlay / Before-After in the viewport footer. Without WebRTC,
allow-list still passes but the UI reports not delivered.

## Tests

```powershell
cd C:\Users\arnav\Argus\.worktrees\phase13-streaming-kit
python -m unittest api.test_server.ServerContractTests.test_view_allow_list_and_undelivered -v
cd frontend; npx tsc --noEmit
```

## Next

**Phase 16** — implemented: `docs/PHASE16_CONSTRAINED_LLM.md`.

**Phase 17** — judge demo packaging: `docs/DEMO_RUNBOOK.md` and
`tools/demo_launch.ps1` (launcher + smoke test on branch `phase13-streaming-kit`).
