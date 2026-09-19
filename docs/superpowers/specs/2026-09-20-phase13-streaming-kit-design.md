# Phase 13 Streaming Kit Application — Design

## Goal

Create a streaming-enabled UrbanTwin Kit application that opens the Phase 9 demo
stage and can be connected to by NVIDIA’s local reference web client on one
Windows RTX machine.

This phase does **not** change the Argus Next.js dashboard. Browser WebRTC
integration is Phase 14.

## Location of work

| Repo | Branch | Role |
|---|---|---|
| `C:\Users\arnav\Argus` | `phase13-streaming-kit` | Design, plan, operator docs only |
| `C:\Users\arnav\omniverse\kit-app-template` | `phase13-streaming-kit` | `urbantwin_streaming.kit` + launch notes |

`main` in Argus is left untouched.

## Design decisions

1. **Streaming layer, not a second base app.** Keep `urbantwin.kit` as the
   desktop editor. Add `source/apps/urbantwin_streaming.kit` that depends on
   `urbantwin` and `omni.kit.livestream.app` (Kit App Template default streaming
   layer). NVIDIA’s tooling names this `{app}_streaming.kit`; the product name
   in Argus docs remains “UrbanTwin streaming Kit” / design alias
   `urbantwin.streaming.kit`.

2. **Stage open via launch argument.** Do not hard-code machine paths into the
   `.kit` file. Launch with
   `--/app/auto_load_usd=<absolute path to phase9/scene/main.usda>` so the same
   kit works on other machines after path substitution.

3. **Local streaming only.** Use the Default Omniverse Kit App Streaming layer,
   not NVCF. Verify with NVIDIA `web-viewer-sample` (stream-only) against a
   `--no-window` launch.

4. **No Argus dashboard or `stream/config` “available” flip.** Health/stream
   endpoints stay honest until Phase 14.

## Acceptance gate

1. `urbantwin_streaming.kit` exists and builds with the kit-app-template tooling.
2. Launch with `--no-window` and auto-load of `phase9/scene/main.usda` starts
   without error (RTX path).
3. NVIDIA reference client can connect to the local streaming session (or a
   documented blocker is recorded with exact error if GPU/driver/SDK blocks it).
4. Argus `docs/PHASE13_STREAMING_KIT.md` records commands and Phase 14 handoff.
5. Argus `main` is unchanged.

## Out of scope

- Next.js WebRTC adapter completion (Phase 14)
- Kit messaging / view-command delivery (Phase 15)
- Changing `api` health/stream capabilities to advertise online
- Linux container packaging
