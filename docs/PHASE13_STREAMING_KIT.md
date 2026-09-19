# Phase 13 — UrbanTwin streaming Kit

Local streaming-enabled Kit application for the UrbanTwin Phase 9 demo stage.
This phase does **not** change the Next.js dashboard. Browser WebRTC is Phase 14.

## Repositories / branches

| Repo | Branch | Contents |
|---|---|---|
| Argus | `phase13-streaming-kit` | This doc + design/plan (do not merge to `main` until you choose) |
| Kit App Template | `phase13-streaming-kit` | `source/apps/urbantwin_streaming.kit` + launch wrapper |

Kit checkout:

```text
C:\Users\arnav\omniverse\kit-app-template
```

## What was added

- `source/apps/urbantwin_streaming.kit` — streaming layer over `urbantwin.kit`
  using `omni.kit.livestream.app` (NVIDIA default Kit App Streaming).
- `launch_urbantwin_streaming.bat` — launches with `--no-window` and loads
  `C:\Users\arnav\Argus\phase9\scene\main.usda` via `--/app/auto_load_usd`.

NVIDIA tooling names the file `{app}_streaming.kit`. Argus design docs may say
`urbantwin.streaming.kit`; they mean this file.

## Build

From the Kit App Template root (first time or after kit changes):

```powershell
cd C:\Users\arnav\omniverse\kit-app-template
.\repo.bat build
```

## Launch (streaming host)

```powershell
cd C:\Users\arnav\omniverse\kit-app-template
.\launch_urbantwin_streaming.bat
```

Equivalent manual command:

```powershell
.\repo.bat launch -n urbantwin_streaming.kit -- --no-window `
  --/app/auto_load_usd="C:\Users\arnav\Argus\phase9\scene\main.usda"
```

`--no-window` avoids fighting the streaming client for the main window.

If your Argus clone is not under `C:\Users\arnav\Argus`, edit `STAGE` in
`launch_urbantwin_streaming.bat`.

## Connect a reference client (verification)

1. Clone NVIDIA’s sample (once):

```powershell
git clone https://github.com/NVIDIA-Omniverse/web-viewer-sample.git
```

2. Follow that repo’s Quick Start for **stream only / no UI overlay**.
3. Start the streaming Kit host first, then the sample client in a Chromium browser.

You should see the Russell Square / Phase 9 stage stream from the RTX host.

## What is still offline in Argus

Until Phase 14:

- `GET /api/stream/config` remains `status: "offline"`
- the dashboard viewport keeps the placeholder / mock adapter
- view commands stay allow-listed but undelivered

Do not flip health/stream capabilities to “online” from this phase alone.

## Smoke evidence (2026-09-20)

On branch `phase13-streaming-kit` in the Kit App Template:

1. `.\repo.bat build` succeeded and pulled
   `omni.kit.livestream.app` / `.core` / `.webrtc`.
2. `.\repo.bat launch -n urbantwin_streaming.kit -- --no-window
   --/app/auto_load_usd=C:/Users/arnav/Argus/phase9/scene/main.usda`
   reached `app ready` with:
   - `[ext: omni.kit.livestream.webrtc-…] startup`
   - `[ext: omni.kit.livestream.app-…] startup`
   - `[ext: urbantwin_streaming-0.1.0] startup`
3. Process was stopped after ~60s (agent smoke). Full WebRTC client connect
   with `web-viewer-sample` is still a manual operator step on the RTX machine.

Use forward slashes in `--/app/auto_load_usd` (see the launch bat).

## Recovery

| Symptom | Check |
|---|---|
| Stage not found | `STAGE` path in the launch bat; file exists under `phase9/scene/main.usda` |
| App not listed | Rebuild after adding the `.kit`; name is `urbantwin_streaming.kit` |
| Client cannot connect | Host launched with `--no-window`; firewall; only one stream host |
| Empty stage | Confirm `auto_load_usd` argument was passed and path uses backslashes or forward slashes consistently |
| Wrong branch | Kit work must be on `phase13-streaming-kit`, not Kit `main` |

## Next

**Phase 14** — wire `frontend/lib/viewer/kit-webrtc-adapter.ts` and return a real
signaling URL from the Python API’s stream config (still allow-listed, no secrets
in `NEXT_PUBLIC_*`).
