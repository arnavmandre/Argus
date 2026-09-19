"""
Place the street trees and lamps that Phase 1 never imported.

The OSM extract contains 498 surveyed `natural=tree` nodes, 3 `natural=tree_row`
ways and 39 `highway=street_lamp` nodes. Phase 1 only imports closed building /
green polygons and highway centrelines, so all of it was dropped.

These are real positions, not a decorative scatter - which matters for a project
about shade: the trees stand where the trees actually stand.

Everything is drawn with two `UsdGeom.PointInstancer` prims (one for trees, one
for lamps) rather than ~540 separate prims. On an 8 GB laptop GPU that is the
difference between free and noticeable.

Per-tree size and rotation vary deterministically from the OSM node id, so the
row is not visibly cloned but the scene is still byte-identical between runs.

Run:  python phase9/place_trees.py
Out:  phase9/scene/streetscape.usda
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, Vt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OSM = ROOT / "phase1" / "data" / "sample.osm"
OUT = HERE / "scene" / "streetscape.usda"

TREE_ROW_SPACING = 8.0        # metres between trees synthesised along a tree_row
LOOKS = "/World/Phase9Streetscape/Looks"


def projector(root):
    """Same equirectangular projection as phase1/build_city.py:18."""
    b = root.find("bounds").attrib
    west, south, east, north = (float(b[k]) for k in ("minlon", "minlat", "maxlon", "maxlat"))
    lon0, lat0 = (west + east) / 2, (south + north) / 2

    def project(lon, lat):
        return (6378137 * math.radians(lon - lon0) * math.cos(math.radians(lat0)),
                6378137 * math.radians(lat - lat0))

    xmin, ymin = project(west, south)
    xmax, ymax = project(east, north)
    return project, (xmin, ymin, xmax, ymax)


def collect(root):
    project, (xmin, ymin, xmax, ymax) = projector(root)
    nodes = {n.attrib["id"]: n for n in root.findall("node")}
    xy = {i: project(float(n.attrib["lon"]), float(n.attrib["lat"]))
          for i, n in nodes.items()}

    def inside(p):
        return xmin <= p[0] <= xmax and ymin <= p[1] <= ymax

    trees, lamps = [], []
    for nid, n in nodes.items():
        tags = {t.attrib["k"]: t.attrib["v"] for t in n.findall("tag")}
        p = xy[nid]
        if not inside(p):
            continue
        if tags.get("natural") == "tree":
            trees.append((nid, p, tags))
        elif tags.get("highway") == "street_lamp":
            lamps.append((nid, p))

    # tree_row ways describe a line of trees, not a single tree: sample along it.
    for way in root.findall("way"):
        tags = {t.attrib["k"]: t.attrib["v"] for t in way.findall("tag")}
        if tags.get("natural") != "tree_row":
            continue
        pts = [xy[n.attrib["ref"]] for n in way.findall("nd") if n.attrib["ref"] in xy]
        for a, b in zip(pts, pts[1:]):
            span = math.dist(a, b)
            for k in range(1, max(int(span // TREE_ROW_SPACING), 1)):
                t = k * TREE_ROW_SPACING / span
                p = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
                if inside(p):
                    trees.append((f"{way.attrib['id']}_{k}", p, tags))
    return trees, lamps


def jitter(key: str, lo: float, hi: float) -> float:
    """Deterministic value in [lo, hi) from an OSM id - stable across runs."""
    h = 2166136261
    for ch in str(key):
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return lo + (h % 10000) / 10000.0 * (hi - lo)


def material(stage, name, rgb, rough):
    mat = UsdShade.Material.Define(stage, f"{LOOKS}/{name}")
    sh = UsdShade.Shader.Define(stage, f"{LOOKS}/{name}/Shader")
    sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rgb))
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(rough)
    sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    return mat


def build() -> Path:
    root = ET.parse(OSM).getroot()
    trees, lamps = collect(root)
    print(f"{len(trees)} trees (incl. tree_row samples), {len(lamps)} street lamps")

    stage = Usd.Stage.CreateNew(str(OUT)) if not OUT.exists() else Usd.Stage.Open(str(OUT))
    stage.GetRootLayer().Clear()
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    stage.GetRootLayer().documentation = (
        "Street trees and lamps at their surveyed OSM positions, drawn as point "
        "instancers. Regenerate with phase9/place_trees.py."
    )
    scope = UsdGeom.Scope.Define(stage, "/World/Phase9Streetscape").GetPrim()
    scope.CreateAttribute("urbantwin:note", Sdf.ValueTypeNames.String, custom=True).Set(
        f"{len(trees)} trees and {len(lamps)} lamps from surveyed OSM node positions. "
        "Visual only; the simulator's shade values are not derived from these."
    )

    bark = material(stage, "Bark", (0.271, 0.208, 0.157), 0.90)
    canopy = material(stage, "Canopy", (0.216, 0.373, 0.204), 0.88)
    canopy2 = material(stage, "CanopyLight", (0.286, 0.447, 0.239), 0.88)
    metal = material(stage, "LampPost", (0.137, 0.145, 0.157), 0.55)

    # ---- trees ----------------------------------------------------------
    inst = UsdGeom.PointInstancer.Define(stage, "/World/Phase9Streetscape/Trees")
    protos = UsdGeom.Scope.Define(stage, "/World/Phase9Streetscape/Trees/Prototypes")

    proto_paths = []
    for i, (crown_r, crown_z, leaf) in enumerate(
            [(3.2, 6.4, canopy), (4.1, 7.8, canopy2), (2.6, 5.2, canopy)]):
        xf = UsdGeom.Xform.Define(stage, f"{protos.GetPath()}/Tree_{i}")
        trunk = UsdGeom.Cylinder.Define(stage, f"{xf.GetPath()}/Trunk")
        trunk.CreateRadiusAttr(0.22)
        trunk.CreateHeightAttr(crown_z * 0.75)
        trunk.CreateAxisAttr("Z")
        UsdGeom.Xformable(trunk).AddTranslateOp().Set(Gf.Vec3d(0, 0, crown_z * 0.375))
        UsdShade.MaterialBindingAPI.Apply(trunk.GetPrim()).Bind(bark)

        crown = UsdGeom.Sphere.Define(stage, f"{xf.GetPath()}/Crown")
        crown.CreateRadiusAttr(crown_r)
        cx = UsdGeom.Xformable(crown)
        cx.AddTranslateOp().Set(Gf.Vec3d(0, 0, crown_z))
        cx.AddScaleOp().Set(Gf.Vec3f(1.0, 1.0, 0.82))      # slightly flattened
        UsdShade.MaterialBindingAPI.Apply(crown.GetPrim()).Bind(leaf)
        proto_paths.append(xf.GetPath())

    positions, indices, scales, orients, ids = [], [], [], [], []
    for i, (nid, (x, y), _) in enumerate(trees):
        positions.append(Gf.Vec3f(x, y, 0.05))
        indices.append(int(jitter(nid, 0, 3)) % 3)
        s = jitter(f"s{nid}", 0.78, 1.28)
        scales.append(Gf.Vec3f(s, s, jitter(f"h{nid}", 0.85, 1.25)))
        a = math.radians(jitter(f"r{nid}", 0, 360))
        orients.append(Gf.Quath(math.cos(a / 2), 0, 0, math.sin(a / 2)))
        ids.append(i)

    inst.CreatePrototypesRel().SetTargets(proto_paths)
    inst.CreatePositionsAttr(Vt.Vec3fArray(positions))
    inst.CreateProtoIndicesAttr(Vt.IntArray(indices))
    inst.CreateScalesAttr(Vt.Vec3fArray(scales))
    inst.CreateOrientationsAttr(Vt.QuathArray(orients))
    inst.CreateIdsAttr(Vt.Int64Array(ids))

    # ---- lamps ----------------------------------------------------------
    if lamps:
        linst = UsdGeom.PointInstancer.Define(stage, "/World/Phase9Streetscape/StreetLamps")
        lprotos = UsdGeom.Scope.Define(stage, "/World/Phase9Streetscape/StreetLamps/Prototypes")
        lx = UsdGeom.Xform.Define(stage, f"{lprotos.GetPath()}/Lamp")
        post = UsdGeom.Cylinder.Define(stage, f"{lx.GetPath()}/Post")
        post.CreateRadiusAttr(0.09)
        post.CreateHeightAttr(5.0)
        post.CreateAxisAttr("Z")
        UsdGeom.Xformable(post).AddTranslateOp().Set(Gf.Vec3d(0, 0, 2.5))
        UsdShade.MaterialBindingAPI.Apply(post.GetPrim()).Bind(metal)
        head = UsdGeom.Sphere.Define(stage, f"{lx.GetPath()}/Head")
        head.CreateRadiusAttr(0.26)
        UsdGeom.Xformable(head).AddTranslateOp().Set(Gf.Vec3d(0, 0, 5.1))
        UsdShade.MaterialBindingAPI.Apply(head.GetPrim()).Bind(metal)

        linst.CreatePrototypesRel().SetTargets([lx.GetPath()])
        linst.CreatePositionsAttr(Vt.Vec3fArray(
            [Gf.Vec3f(x, y, 0.05) for _, (x, y) in lamps]))
        linst.CreateProtoIndicesAttr(Vt.IntArray([0] * len(lamps)))
        linst.CreateIdsAttr(Vt.Int64Array(list(range(len(lamps)))))

    stage.GetRootLayer().Save()
    print(f"  {len(proto_paths)} tree prototypes, 1 lamp prototype, 2 instancer prims total")
    print(f"wrote {OUT}")
    return OUT


if __name__ == "__main__":
    build()
