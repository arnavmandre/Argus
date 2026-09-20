# Phase 15 — Kit Command Delivery — Design

## Goal

Allow-listed dashboard view commands (`state` / `camera` / `overlay`) visibly
change the live streamed Kit viewport. Unknown values never reach Kit.

## Location of work

| Repo | Branch | Role |
|---|---|---|
| Argus worktree | `phase13-streaming-kit` | API delivery handshake, frontend `sendMessage`, docs |
| Kit App Template | `phase13-streaming-kit` | `urbantwin.view_commands` + messaging dependency |

`main` stays untouched.

## Design decisions

1. **Authorize then deliver on the WebRTC data channel.** The browser POSTs
   `/api/runs/{id}/view`. The Python API allow-lists as today. On success the
   connected `kit-webrtc-adapter` sends
   `{event_type: "urbantwin.view_command", payload: {state, camera, overlay}}`
   via `AppStreamer.sendMessage`. The API alone cannot push into Kit’s WebRTC
   session without a session manager; “forward” means **authorize + client
   delivery over the already-authenticated stream**. `delivered: true` only when
   the adapter confirms `sendMessage` succeeded (or API reports `delivery: "webrtc"`
   and the client reports back — keep it simple: API returns
   `accepted: true, delivery: "webrtc_client"` and the adapter sets UI
   `delivered` from `sendMessage`).

   Practical contract:
   - API: `accepted: true`, `delivered: false`, `delivery: "webrtc_client"`,
     `reason` explains client must send (or omit reason when streaming online).
   - Better: API returns `accepted: true`, `channel: "webrtc"`. Adapter after
     allow-list success calls `sendMessage` and returns
     `{accepted: true, delivered: true}` to the UI from `send()`.

2. **Kit extension `urbantwin.view_commands`.** Depends on
   `omni.kit.livestream.messaging`. Observes `urbantwin.view_command`. Maps:
   - `camera` → set viewport to `/World/Cameras/{name}`
   - `overlay` → toggle known overlay prim visibility / display purposes
   - `state` → switch before/after agent (or snapshot) presentation when both
     exist; otherwise no-op with a logged warning

3. **Camera prim names match the allow-list.** Extend `phase9/make_cameras.py`
   so Street and Aerial exist as real prims (Street ≈ current Corridor street
   shot; Aerial ≈ high tile shot). Keep Corridor as an alias or leave it for
   Kit UI. Do not invent prim paths from the browser.

4. **Overlays are allow-listed tokens only.** Implementation maps:
   - `behavior` / `congestion` / `shade` / `none` to existing Phase 9 overlay
     layers or visibility groups. If a layer is missing, log and leave scene
     unchanged (still `delivered: true` for the camera part if camera applied).

5. **Reject before Kit.** API `validate_view_command` remains the only gate.
   Kit extension also ignore-lists unknown cameras/overlays as defense in depth
   (never open arbitrary USD paths).

6. **Enable messaging on streaming kit.** Add
   `omni.kit.livestream.messaging` to `urbantwin_streaming.kit` and enable
   `urbantwin.view_commands` via `--ext-folder` / `--enable` (same pattern as
   stage_autoload) until rebuilt into the app.

## Acceptance gate

1. With streaming Kit + live API + frontend, changing Camera / Overlay /
   Before-After updates the streamed view.
2. Invalid camera/overlay/state → HTTP 422, no Kit message.
3. Without an active WebRTC session, UI still shows allow-list pass but
   `delivered: false` with an honest reason.
4. Work stays on `phase13-streaming-kit`; Argus `main` unchanged.

## Out of scope

- Free-form zoom/pan UI (browser may still use WebRTC input if Kit allows it)
- LLM explanations (Phase 16)
- Demo launcher (Phase 17)
- Merging to `main`
