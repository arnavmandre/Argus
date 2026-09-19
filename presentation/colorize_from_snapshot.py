"""
UrbanTwin AI - paint simulator results onto the real city.

Reads the simulator's before/after report plus the route mapping, and authors a
USD layer that:

  * recolours every mapped pedestrian edge by a chosen metric (crowding or heat)
  * places citizens as a single instanced point cloud, coloured by comfort
  * draws a legend so severity is readable without narration

Colour ramp
-----------
Deliberately NOT red/green. Red-green is invisible to the most common form of
colour blindness and washes out against white buildings. This ramp runs
dark blue -> teal -> yellow -> orange -> dark red, which is ordered by
lightness as well as hue, so it also survives greyscale and projector washout.

Agents use a PointInstancer rather than one prim each: 500 separate prims cost
real frame time, one instancer costs almost nothing.

Usage:
    python presentation/colorize_from_snapshot.py                  # before, crowding
    python presentation/colorize_from_snapshot.py --state after
    python presentation/colorize_from_snapshot.py --metric heat
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom, Vt

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
REGISTRY = REPO / "phase2" / "scene" / "edge_registry.json"
MAPPING = REPO / "integration" / "route_mapping.json"
REPORT = REPO / "Simulation" / "urbantwin_demo_output.json"

AGENT_CAP = 500          # phase3 schema limit
PATH_Z = 0.55            # sit above the phase8 route/metric overlays
AGENT_Z = 0.9

# dark blue -> teal -> yellow -> orange -> dark red
RAMP = [
    (0.00, (0.145, 0.196, 0.443)),
    (0.25, (0.129, 0.514, 0.529)),
    (0.50, (0.859, 0.816, 0.278)),
    (0.75, (0.898, 0.522, 0.176)),
    (1.00, (0.612, 0.106, 0.133)),
]


def ramp(t: float) -> Gf.Vec3f:
    t = max(0.0, min(1.0, t))
    for (t0, c0), (t1, c1) in zip(RAMP, RAMP[1:]):
        if t <= t1:
            f = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return Gf.Vec3f(*[a + (b - a) * f for a, b in zip(c0, c1)])
    return Gf.Vec3f(*RAMP[-1][1])


def polyline(points):
    """Flatten a registry 'points' list to 2D and give cumulative lengths."""
    pts = [(p[0], p[1]) for p in points]
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.dist(a, b))
    return pts, cum


def point_along(pts, cum, frac):
    """XY at `frac` (0..1) along a polyline."""
    if len(pts) == 1 or cum[-1] <= 0:
        return pts[0]
    target = max(0.0, min(1.0, frac)) * cum[-1]
    for i, (c0, c1) in enumerate(zip(cum, cum[1:])):
        if target <= c1:
            f = 0.0 if c1 == c0 else (target - c0) / (c1 - c0)
            (x0, y0), (x1, y1) = pts[i], pts[i + 1]
            return (x0 + (x1 - x0) * f, y0 + (y1 - y0) * f)
    return pts[-1]


def build(state: str, metric: str) -> Path:
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    edges = reg["edges"]
    mapping_doc = json.loads(MAPPING.read_text(encoding="utf-8"))
    mapping = mapping_doc["simulator_routes"]
    report = json.loads(REPORT.read_text(encoding="utf-8"))

    if state not in ("before", "after"):
        raise SystemExit("--state must be 'before' or 'after'")
    snap = report[state]

    # --- route metric -> per-edge value (0..1) ---------------------------
    key = {"crowd": "crowding", "crowding": "crowding", "heat": "heat_exposure"}[metric]
    route_rows = {r["id"]: r for r in snap["routes"]}

    edge_value: dict[str, float] = {}
    for rid, edge_ids in mapping.items():
        row = route_rows.get(rid)
        if not row:
            continue
        if key == "crowding":
            value = row["crowding"] / 100.0
        else:
            # Routes do not carry heat directly; use the mean heat exposure of
            # the citizens who actually walked this route.
            walkers = [c["heat_exposure"] for c in snap["citizens"] if c["route"] == rid]
            value = (sum(walkers) / len(walkers) / 100.0) if walkers else 0.0
        for eid in edge_ids:
            # An edge shared by several routes takes the worst value it sees.
            edge_value[eid] = max(edge_value.get(eid, 0.0), value)

    out = ROOT / f"results_{state}_{metric}.usda"
    stage = Usd.Stage.CreateNew(str(out)) if not out.exists() else Usd.Stage.Open(str(out))
    stage.GetRootLayer().Clear()
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())

    root = UsdGeom.Scope.Define(stage, "/World/Results").GetPrim()
    root.CreateAttribute("urbantwin:state", Sdf.ValueTypeNames.String, custom=True).Set(state)
    root.CreateAttribute("urbantwin:metric", Sdf.ValueTypeNames.String, custom=True).Set(key)
    root.CreateAttribute("urbantwin:mappingStatus", Sdf.ValueTypeNames.String,
                         custom=True).Set(mapping_doc.get("status", "UNKNOWN"))
    root.CreateAttribute("urbantwin:legend", Sdf.ValueTypeNames.String, custom=True).Set(
        "0 = low, 1 = high. Colour ramp dark blue -> teal -> yellow -> orange -> dark red."
    )

    # --- coloured edges ---------------------------------------------------
    paths = UsdGeom.Scope.Define(stage, "/World/Results/MetricPaths")
    painted = 0
    for eid, value in sorted(edge_value.items()):
        rec = edges.get(eid)
        if not rec:
            continue
        pts, _ = polyline(rec["points"])
        curve = UsdGeom.BasisCurves.Define(stage, f"{paths.GetPath()}/{eid}")
        curve.CreateTypeAttr("linear")
        curve.CreateCurveVertexCountsAttr([len(pts)])
        curve.CreatePointsAttr([Gf.Vec3f(x, y, PATH_Z) for x, y in pts])
        curve.CreateWidthsAttr([3.0] * len(pts))
        curve.SetWidthsInterpolation(UsdGeom.Tokens.vertex)
        curve.CreateDisplayColorAttr([ramp(value)])
        curve.GetPrim().CreateAttribute(
            f"urbantwin:{key}", Sdf.ValueTypeNames.Double, custom=True
        ).Set(round(value, 4))
        painted += 1

    # --- agents as one instancer -----------------------------------------
    citizens = snap["citizens"][:AGENT_CAP]
    positions, colors, ids = [], [], []
    for i, c in enumerate(citizens):
        edge_ids = mapping.get(c["route"]) or []
        if not edge_ids:
            continue
        # Spread agents deterministically along their own route so they read as
        # a flow rather than a single clump.
        frac = (i + 0.5) / max(len(citizens), 1)
        idx = min(int(frac * len(edge_ids)), len(edge_ids) - 1)
        rec = edges.get(edge_ids[idx])
        if not rec:
            continue
        pts, cum = polyline(rec["points"])
        x, y = point_along(pts, cum, (frac * len(edge_ids)) % 1.0)
        positions.append(Gf.Vec3f(x, y, AGENT_Z))
        # Comfort 0..100, high is good -> invert so red means a bad experience.
        colors.append(ramp(1.0 - c["comfort"] / 100.0))
        ids.append(i)

    if positions:
        inst = UsdGeom.PointInstancer.Define(stage, "/World/Results/Citizens")
        proto = UsdGeom.Sphere.Define(stage, "/World/Results/Citizens/Prototypes/Marker")
        proto.CreateRadiusAttr(1.6)
        proto.CreateDisplayColorAttr([(0.9, 0.9, 0.9)])
        inst.CreatePrototypesRel().SetTargets([proto.GetPath()])
        inst.CreatePositionsAttr(Vt.Vec3fArray(positions))
        inst.CreateProtoIndicesAttr(Vt.IntArray([0] * len(positions)))
        inst.CreateIdsAttr(Vt.Int64Array([int(i) for i in ids]))
        inst.GetPrim().CreateAttribute(
            "primvars:displayColor", Sdf.ValueTypeNames.Color3fArray, custom=False
        ).Set(Vt.Vec3fArray(colors))
        UsdGeom.Primvar(
            inst.GetPrim().GetAttribute("primvars:displayColor")
        ).SetInterpolation(UsdGeom.Tokens.vertex)
        inst.GetPrim().CreateAttribute(
            "urbantwin:colorMeaning", Sdf.ValueTypeNames.String, custom=True
        ).Set("Per-citizen simulated comfort: blue = comfortable, red = poor experience.")

    # --- legend -----------------------------------------------------------
    legend = UsdGeom.Scope.Define(stage, "/World/Results/Legend")
    lx, ly, lz = -360.0, -400.0, 2.0
    for i in range(11):
        t = i / 10.0
        sw = UsdGeom.Mesh.Define(stage, f"{legend.GetPath()}/Swatch_{i:02d}")
        x0, x1 = lx + i * 14.0, lx + i * 14.0 + 13.0
        sw.CreatePointsAttr([(x0, ly, lz), (x1, ly, lz), (x1, ly + 11.0, lz), (x0, ly + 11.0, lz)])
        sw.CreateFaceVertexCountsAttr([4])
        sw.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
        sw.CreateDisplayColorAttr([ramp(t)])
        sw.CreateExtentAttr([(x0, ly, lz), (x1, ly + 11.0, lz)])
    legend.GetPrim().CreateAttribute(
        "urbantwin:caption", Sdf.ValueTypeNames.String, custom=True
    ).Set(f"{key} - left 0 (low) to right 1 (high)")

    stage.GetRootLayer().Save()
    print(f"{painted} edges painted, {len(positions)} citizens placed")
    print(f"mapping status: {mapping_doc.get('status')}")
    print(f"wrote {out}")
    print("Add as a sublayer above presentation.usda, or open directly over the scene.")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="before", choices=["before", "after"])
    ap.add_argument("--metric", default="crowding", choices=["crowding", "crowd", "heat"])
    a = ap.parse_args()
    build(a.state, a.metric)
