# Phase 14 — Browser WebRTC Integration — Design

## Goal

Wire the existing Next.js viewport to a local UrbanTwin streaming Kit host so
the dashboard can show a real RTX MediaStream when Kit is running, and stay
honestly offline when it is not.

## Location of work

| Repo | Branch | Role |
|---|---|---|
| `C:\Users\arnav\Argus\.worktrees\phase13-streaming-kit` | `phase13-streaming-kit` | Stream config probe, kit-webrtc adapter, docs |
| Kit App Template | `phase13-streaming-kit` | Unchanged (Phase 13 already ships `urbantwin_streaming.kit`) |

`main` stays untouched. Do not merge unless the operator asks.

## Design decisions

1. **Reuse the ViewerAdapter seam.** `OmniverseViewer` already selects
   `kitWebRtcViewerAdapter` when `/api/stream/config` reports
   `status: "available"` and a signaling URL. Complete that adapter; do not
   rewrite dashboard layout components.

2. **Local DIRECT stream only.** Connect to the Phase 13 host on the same
   machine (`127.0.0.1`, signal TCP `49100`, media UDP `47998` by default). No
   NVCF / OVAS session manager in this phase.

3. **Python API owns availability.** `live_stream_config` probes whether the
   signaling TCP port accepts connections (or honors an explicit env override).
   Only then return `status: "available"` plus public host/port fields and a
   short-lived opaque `session_token` (local nonce, not infrastructure creds).
   Mock fixtures stay offline.

4. **Health matches stream config.** When the probe succeeds,
   `omniverse_stream: "online"` and `capabilities.omniverse_streaming: true`.
   Otherwise remain offline / false. Never claim live streaming from fixtures.

5. **NVIDIA client behind the adapter.** Install `@nvidia/ov-web-rtc` (preferred)
   or `@nvidia/omniverse-webrtc-streaming-library` via NVIDIA’s scoped npm
   registry (`.npmrc`). The adapter must report `connected` only after media is
   active and must hand a real `MediaStream` to `onState` so the existing video
   element path works. Prefer attaching AppStreamer to an off-DOM `<video>` and
   reading `srcObject` on start if the SDK does not expose a MediaStream API.

6. **View commands stay undelivered.** Phase 15 owns Kit messaging. Adapter
   `send()` may call the allow-listed HTTP endpoint but must not claim Kit
   delivery.

## Env knobs (server-side only)

| Variable | Default | Meaning |
|---|---|---|
| `URBANTWIN_STREAM_HOST` | `127.0.0.1` | Signaling/media host advertised to the browser |
| `URBANTWIN_STREAM_SIGNAL_PORT` | `49100` | Kit primaryStream signalPort |
| `URBANTWIN_STREAM_MEDIA_PORT` | `47998` | Kit primaryStream streamPort |
| `URBANTWIN_STREAM_FORCE` | unset | If `1`/`true`, advertise available without TCP probe (dev only) |

No `NEXT_PUBLIC_*` streaming secrets.

## StreamConfig extensions

Keep existing fields. Add optional public connection fields the adapter needs:

- `signaling_host: string | null`
- `signaling_port: number | null`
- `media_host: string | null`
- `media_port: number | null`

`signaling_url` remains a human-readable / legacy hint
(`http://{host}:{signal_port}` when available).

## Acceptance gate

1. With streaming Kit running and `URBANTWIN_API_BASE` set, the dashboard
   viewport reaches `connected` with a non-null MediaStream.
2. With Kit stopped, `/api/stream/config` stays `offline` and the mock/offline
   path is used.
3. Fixture / mock mode never advertises an available stream.
4. Reconnect / teardown via Retry and unmount do not leave orphan sessions
   (best-effort `terminate` / `close`).
5. Argus `main` unchanged; work stays on `phase13-streaming-kit`.

## Out of scope

- Kit messaging / camera / overlay delivery (Phase 15)
- Cloud session manager, auth, multi-tenant streams
- Changing Phase 1–8 scene layers
- Merging to `main`
