# UrbanTwin AI: Omniverse setup (Kit App Template route)

**Time budget: 60-90 minutes including the first shader compile. Hard gate: if the city isn't visible in a
3D viewport by hour 4 of the hackathon, switch to the 2D fallback (bottom of this page).**

Source of truth: NVIDIA's `kit-app-template` README (github.com/NVIDIA-Omniverse/kit-app-template). It is a
*feature branch* build, meant for prototyping, which is fine for a hackathon. NVIDIA has moved away from the
old Omniverse Launcher, so the steps below use the GitHub template instead.

---

## 0. One person does this first (the "3D machine")

Only one teammate needs Omniverse running. Pick the machine that passes this check:

| Requirement | Needed |
|---|---|
| OS | Windows 10/11, or Linux (Ubuntu 22.04+) |
| GPU | NVIDIA **RTX**-capable (RTX 3070 or better recommended) |
| Driver | Windows >= 551.78, or Linux >= 550.54.15 |
| Internet | Required (downloads the Kit SDK and extensions) |
| Software | Git. Linux also needs `build-essential`. (Visual Studio is only needed for C++ extensions; you don't need it.) |

Check your GPU and driver:
```
nvidia-smi
```
No NVIDIA RTX GPU on the team? Skip to **Plan B**; don't burn hours on this.

## 1. Clone the template

```
git clone https://github.com/NVIDIA-Omniverse/kit-app-template.git
cd kit-app-template
```

## 2. Create the app

Linux: `./repo.sh template new`  |  Windows: `.\repo.bat template new`

First run asks you to accept the Omniverse license terms. Then answer the prompts:

- Select what to create: **Application**
- Template: **Kit Base Editor** (minimal, loads and renders USD; best for us)
- App name (lowercase, alphanumeric): `urbantwin`
- Display name: `UrbanTwin AI`
- Version: `0.1.0`
- Add application layers? **No**

## 3. Build

Linux: `./repo.sh build`  |  Windows: `.\repo.bat build`

Success looks like: `BUILD (RELEASE) SUCCEEDED`.

## 4. Launch

Linux: `./repo.sh launch`  |  Windows: `.\repo.bat launch`

Pick your `urbantwin` app when asked. **The first start takes about 5-8 minutes** while RTX shaders compile.
That's normal; later starts are fast.

## 5. Open the city

In the app: **File > Open** and choose `city.usda` (from this folder's `out/`). Then:

- In the viewport camera menu, select **/World/MainCamera** for the overview shot.
- Open the **Stage** panel and expand `World`. You should see `Zones`, `Roads`, `Paths`, `Buildings`, `Trees`.
- Click any prim under `Paths` and look at the **Property** panel: `urbantwin:shade_pct`, `capacity_pph` etc.
  These custom attributes are how the simulation and the 3D scene stay linked.
- Path colour = shade (red = sun-exposed, green = shaded).

Then **File > Open** `city_redesigned.usda` to see a *test* "after" city with more trees.
(That redesign is hard-coded for testing the before/after toggle; the AI advisor replaces it later.)

## 6. Validate the file independently (optional, 1 minute)

```
pip install usd-core
python validate_usd.py out/city.usda
```

With `usd-core` installed this opens the file with the real OpenUSD library. **I could only run the
structural check, not the pxr check or Omniverse, when generating these files.** If Omniverse or this
validator reports an error, send me the exact message and I'll fix the generator.

---

## Troubleshooting

| Symptom | Try |
|---|---|
| Build fails | Read NVIDIA's `readme-assets/additional-docs/usage_and_troubleshooting.md` in the cloned repo; check driver version first |
| Black / very dark viewport | Lighting: `Sun` and `Sky` are in the file. Check the viewport lighting mode isn't set to "None" |
| App opens but is extremely slow on first launch | Shader compile; wait for it to finish |
| City opens tiny or upside down | Confirm the stage says Y-up, metres (the file sets `upAxis = "Y"`, `metersPerUnit = 1`) |

## Plan B: no RTX GPU, or gate missed

Keep the exact same `city.json` contract and render in 2D instead:

- `python urbantwin_city.py --out out --preview` already draws the top-down map (`preview_*.png`).
- The dashboard (Streamlit) can draw the same map live from `city.json`, and colour it by simulated heat stress.
- Pitch it honestly as "OpenUSD-ready digital twin; 3D Omniverse view planned" and show `city.usda` as the
  scene format. The simulation, advisor and before/after metrics are the core of the demo either way.

## What comes next (not built yet)

1. **Sim -> 3D link:** a small script that writes simulation results (per-path heat stress, crowding) into
   the USD so the city recolours after each run.
2. **Agent visualization:** moving markers for synthetic citizens.
3. **Intervention menu wiring:** `urbantwin_city.py` already exposes `add_trees()` and `widen_path()`, which
   the AI advisor should call by name rather than free-text advice.
