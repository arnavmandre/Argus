"""
Render snapshot agents as a single instanced point cloud.

Uses a UsdGeom.PointInstancer rather than one prim per citizen: 300+ separate
spheres cost real time to draw and bloat the stage, while an instancer is one
prim regardless of population. This matters on an 8 GB laptop GPU.

Agents are binned by stress into a handful of coloured prototypes instead of
carrying a per-instance colour primvar, because prototype indices render
identically everywhere while varying primvars on instancers do not.

Pass several snapshots and the positions become `timeSamples` instead of one
static array, so the citizens walk when the timeline plays. The frames come from
`integration/export_snapshot.py --frames N`, where each agent advances along its
own route at that citizen's own pace (their survey-calibrated walking speed over
the route the simulator picked for them).

Positions between frames are interpolated for display. The simulator decides the
route and the trip duration; it does not emit continuous coordinates.

Colour stays constant across the window on purpose: the metric describes one
simulated equilibrium, and animating it would imply the simulator re-ran.

Run:
    python phase9/agents_instancer.py phase3/mock_data/mock_stress.json
    python phase9/agents_instancer.py <snapshot> --metric heat_exposure
    python phase9/agents_instancer.py data/simulation_before_*.json --metric heat_exposure
    python phase9/agents_instancer.py data/simulation_before_*.json --behavior-report Simulation/urbantwin_demo_output.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom, Vt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from recolor_paths import ramp  # noqa: E402  (shared colour ramp)

OUT = Path(__file__).resolve().parent / "scene" / "generated" / "agents.usda"
# The demo stage. Animating also stamps the timeline range here, because USD
# reads start/end time code from the root layer and ignores sublayers.
DEMO_STAGE = Path(__file__).resolve().parent / "scene" / "main.usda"

BINS = 5          # stress buckets -> prototype spheres
MARKER_RADIUS = 1.6   # metres; readable at ProblemZone zoom, not blobby at street level
MARKER_LIFT = 0.9     # raise markers off the 0.1 m path ribbons

BEHAVIOR_STYLE = {
    "CONTINUE": (0.20, 0.85, 0.30),
    "STRESSED": (1.00, 0.55, 0.08),
    "SEEK_SHADE": (0.95, 0.88, 0.12),
    "SEEK_SHELTER": (0.10, 0.75, 0.95),
    "REROUTE": (0.65, 0.25, 0.90),
    "AVOID_AREA": (0.95, 0.12, 0.12),
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("snapshot", type=Path, nargs="+",
                    help="one snapshot, or a sequence to animate")
    ap.add_argument("--metric", default="stress", help="agent field to colour by (default: stress)")
    ap.add_argument("--behavior-report", type=Path,
                    help="simulator report used to colour agents by explicit behavior")
    ap.add_argument("--behavior-state", choices=["before", "after"], default="before",
                    help="state inside --behavior-report (default: before)")
    ap.add_argument("--radius", type=float, default=MARKER_RADIUS)
    ap.add_argument("--fps", type=float, default=24.0,
                    help="time codes per second on the generated layer")
    ap.add_argument("--out", type=Path, default=OUT,
                    help="generated agent USD layer")
    ap.add_argument("--demo-stage", type=Path, default=DEMO_STAGE,
                    help="root stage whose timeline metadata is updated")
    args = ap.parse_args()

    frames = []
    for path in args.snapshot:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not data.get("agents"):
            raise SystemExit(f"{path}: no 'agents' array")
        frames.append((float(data.get("sequence", 0)),
                       float(data.get("timestamp", 0.0)), path, data))
    frames.sort(key=lambda f: (f[0], f[1]))

    first = frames[0][3]
    agents = first["agents"]
    animated = len(frames) > 1

    behavior_by_id = None
    if args.behavior_report:
        report = json.loads(args.behavior_report.read_text(encoding="utf-8"))
        rows = report.get(args.behavior_state, {}).get("citizens", [])
        behavior_by_id = {str(c["id"]): c.get("behavior", "CONTINUE") for c in rows}
        unknown = sorted(set(behavior_by_id.values()) - set(BEHAVIOR_STYLE))
        if unknown:
            raise SystemExit(f"unknown simulator behavior(s): {unknown}")

    # An agent vanishing mid-animation would silently corrupt the instancer's
    # parallel arrays, so refuse rather than paper over it.
    ids = [a["id"] for a in agents]
    for _seq, _ts, path, data in frames[1:]:
        other = [a["id"] for a in data["agents"]]
        if other != ids:
            raise SystemExit(
                f"{path.name}: agent set differs from {frames[0][2].name} "
                f"({len(other)} vs {len(ids)} agents). Every frame must describe "
                "the same citizens.")

    layer = Sdf.Layer.CreateAnonymous(".usda")
    stage = Usd.Stage.Open(layer)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    stage.SetDefaultPrim(stage.OverridePrim("/World"))

    inst = UsdGeom.PointInstancer.Define(stage, "/World/Agents")
    label = (f"{frames[0][2].name} .. {frames[-1][2].name} ({len(frames)} frames)"
             if animated else frames[0][2].name)
    color_source = (f"{args.behavior_state} behavior" if behavior_by_id else args.metric)
    inst.GetPrim().SetDocumentation(
        f"Synthetic citizens from {label}, coloured by '{color_source}'. "
        "Generated by phase9/agents_instancer.py."
    )
    inst.GetPrim().CreateAttribute(
        "urbantwin:positionSource", Sdf.ValueTypeNames.String, custom=True
    ).Set(
        "Interpolated along each citizen's simulated route for display. The "
        "simulator decides the route and trip duration, not the coordinates."
        if animated else
        "Single simulated snapshot; positions are a still frame."
    )

    proto_paths = []
    prototype_colors = (list(BEHAVIOR_STYLE.items()) if behavior_by_id else
                        [(f"bin{i}", ramp(i / (BINS - 1))) for i in range(BINS)])
    for name, color in prototype_colors:
        p = f"/World/Agents/Prototypes/{name}"
        sphere = UsdGeom.Sphere.Define(stage, p)
        sphere.CreateRadiusAttr(float(args.radius))
        sphere.CreateDisplayColorAttr([Gf.Vec3f(*color)])
        # Prototypes must not draw on their own; only instances of them do.
        UsdGeom.Imageable(sphere).CreateVisibilityAttr(UsdGeom.Tokens.inherited)
        proto_paths.append(Sdf.Path(p))
    UsdGeom.Scope.Define(stage, "/World/Agents/Prototypes")

    # Colour is taken from the first frame and held: the metric describes one
    # simulated equilibrium, so it must not appear to change over the window.
    indices, missing = [], 0
    if behavior_by_id:
        behavior_index = {name: i for i, name in enumerate(BEHAVIOR_STYLE)}
        for a in agents:
            behavior = behavior_by_id.get(str(a["id"]))
            if behavior is None:
                missing += 1
                behavior = "CONTINUE"
            indices.append(behavior_index[behavior])
        inst.GetPrim().CreateAttribute(
            "urbantwin:behaviorLegend", Sdf.ValueTypeNames.String, custom=True
        ).Set(json.dumps({k: list(v) for k, v in BEHAVIOR_STYLE.items()}))
        inst.GetPrim().CreateAttribute(
            "urbantwin:behaviorState", Sdf.ValueTypeNames.String, custom=True
        ).Set(args.behavior_state)
    else:
        for a in agents:
            v = a.get(args.metric)
            if v is None:
                missing += 1
                v = 0.0
            indices.append(min(BINS - 1, max(0, int(float(v) * BINS))))

    def frame_positions(data):
        return Vt.Vec3fArray([
            Gf.Vec3f(float(a["x"]), float(a["y"]), float(a.get("z", 0.0)) + MARKER_LIFT)
            for a in data["agents"]])

    pos_attr = inst.CreatePositionsAttr()
    if animated:
        for _seq, timestamp, _path, data in frames:
            pos_attr.Set(frame_positions(data), Usd.TimeCode(timestamp * args.fps))
        span = frames[-1][1] - frames[0][1]
        stage.SetStartTimeCode(frames[0][1] * args.fps)
        stage.SetEndTimeCode(frames[-1][1] * args.fps)
        stage.SetTimeCodesPerSecond(args.fps)
        stage.SetFramesPerSecond(args.fps)
    else:
        pos_attr.Set(frame_positions(first))
        span = 0.0

    inst.CreateProtoIndicesAttr(Vt.IntArray(indices))
    inst.CreatePrototypesRel().SetTargets(proto_paths)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    stage.GetRootLayer().documentation = (
        f"Generated by phase9/agents_instancer.py from {label}. Do not hand-edit."
    )
    layer.Export(str(args.out))

    # USD reads the timeline range from the stage's ROOT layer only - values on
    # a sublayer are ignored, so Kit would show an empty 0..0 timeline. Stamp
    # the range onto the demo stage too, touching nothing else in it.
    if args.demo_stage.exists():
        demo = Sdf.Layer.FindOrOpen(str(args.demo_stage))
        if demo:
            if animated:
                demo.startTimeCode = frames[0][1] * args.fps
                demo.endTimeCode = frames[-1][1] * args.fps
                demo.timeCodesPerSecond = args.fps
                demo.framesPerSecond = args.fps
            else:
                # Going back to a still snapshot must not leave a stale timeline
                # advertising frames that no longer exist.
                demo.ClearStartTimeCode()
                demo.ClearEndTimeCode()
                demo.ClearTimeCodesPerSecond()
                demo.ClearFramesPerSecond()
            demo.Save()

    hist = [indices.count(i) for i in range(len(proto_paths))]
    print(f"wrote {args.out}")
    print(f"  {len(agents)} agents as 1 PointInstancer, {len(proto_paths)} prototypes"
          + (f" ({missing} missing agent values)" if missing else ""))
    if behavior_by_id:
        print("  behavior counts: " + ", ".join(
            f"{name}={hist[i]}" for i, name in enumerate(BEHAVIOR_STYLE)))
    else:
        print(f"  bins low->high: {hist}")
    if animated:
        print(f"  ANIMATED: {len(frames)} time samples over {span:.0f}s of walking, "
              f"timeCodes 0..{frames[-1][1] * args.fps:.0f} at {args.fps:g} fps")
        print("  Press play in Kit. Positions are interpolated for display only.")


if __name__ == "__main__":
    main()
