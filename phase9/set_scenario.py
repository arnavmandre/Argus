"""
Switch the demo lighting between scenario moods.

The before/after toggle is much more convincing when the light changes with
the weather, not just the path colours - half the perceived difference in a
heat demo comes from the sun. This rewrites the Sun/Sky overrides in
phase9/scene/lighting.usda in place.

Run:
    python phase9/set_scenario.py baseline
    python phase9/set_scenario.py heat
    python phase9/set_scenario.py rain
"""
from __future__ import annotations

import argparse
from pathlib import Path

from pxr import Sdf, Usd, UsdLux

LIGHTING = Path(__file__).resolve().parent / "scene" / "lighting.usda"

PRESETS = {
    # name:      sun intensity, sun colour,           sky intensity, sky colour,       sun rotateXYZ
    "baseline": (4200, (1.00, 0.95, 0.85), 180, (0.75, 0.83, 1.00), (50, 0, -35)),
    # Harsher, higher, yellower: short hard shadows read as midday 42 C.
    "heat":     (6800, (1.00, 0.90, 0.68), 140, (0.90, 0.85, 0.70), (65, 0, -20)),
    # Overcast: kill the sun, lift the dome, go flat and cold.
    "rain":     (600,  (0.80, 0.84, 0.90), 900, (0.62, 0.66, 0.72), (40, 0, -35)),
    # Low warm sun raking across the streets. The most photogenic frame
    # available and it costs nothing - use it for stills and the title shot,
    # not for the heat scenario (a 42 C claim under dusk light reads wrong).
    "dusk":     (2600, (1.00, 0.72, 0.45), 260, (0.42, 0.48, 0.72), (14, 0, -62)),
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("preset", choices=sorted(PRESETS))
    args = ap.parse_args()

    sun_i, sun_c, sky_i, sky_c, rot = PRESETS[args.preset]

    stage = Usd.Stage.Open(str(LIGHTING))
    sun = stage.GetPrimAtPath("/World/Environment/Sun")
    sky = stage.GetPrimAtPath("/World/Environment/Sky")
    if not sun or not sky:
        raise SystemExit(f"{LIGHTING}: expected Sun and Sky overrides")

    sun.GetAttribute("inputs:intensity").Set(float(sun_i))
    sun.GetAttribute("inputs:color").Set(tuple(map(float, sun_c)))
    sun.GetAttribute("xformOp:rotateXYZ").Set(tuple(map(float, rot)))
    sky.GetAttribute("inputs:intensity").Set(float(sky_i))
    sky.GetAttribute("inputs:color").Set(tuple(map(float, sky_c)))

    stage.GetRootLayer().Save()
    print(f"lighting set to '{args.preset}': sun {sun_i} @ {rot}, sky {sky_i}")
    print("Reload the stage in Kit (File > Reopen) to see it.")


if __name__ == "__main__":
    main()
