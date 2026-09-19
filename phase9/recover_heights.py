"""
Recover real building heights that Phase 1 discarded.

Phase 1 only emits ways tagged `building=*` (build_city.py:80). In this OSM
extract the real 3D massing lives on 430 `building:part` ways, which carry no
`building` tag and are therefore never imported. The result: only 3 of 623
buildings have a surveyed height, and 490 sit at the flat 12 m default.

This reads those parts straight out of the cached OSM file, matches each one to
the building footprint that contains it, and authors corrected heights as an
`over` layer. Phase 1 bytes are never touched, so the manifest hash - and with
it `city_id` and the whole Phase 2-8 contract - stays valid.

Buildings are extruded prisms: points[:n] is the footprint ring at z=0.04 and
points[n:] the same ring lifted to the roof (build_city.py:62-68). Changing the
height is therefore just rewriting the z of the top ring - no re-extrusion, and
the footprint XY is provably untouched.

Run:  python phase9/recover_heights.py
Out:  phase9/scene/heights.usda
"""
from __future__ import annotations

import collections
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

from pxr import Sdf, Usd, UsdGeom

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OSM = ROOT / "phase1" / "data" / "sample.osm"
BASE = ROOT / "phase1" / "scene" / "main.usda"
OUT = HERE / "scene" / "heights.usda"

MAX_HEIGHT = 300.0          # same sanity bound Phase 1 uses
LEVEL_METRES = 3.0          # same assumption Phase 1 uses for building:levels

# Typical heights by OSM building class, metres. Used only where the building
# has no surveyed height and no level count - i.e. Phase 1 fell back to a flat
# 12 m. These are inferred, not measured, and are labelled as such on the prim.
TYPE_HEIGHTS = {
    "house": 7.5, "terrace": 8.0, "bungalow": 4.0,
    "apartments": 18.0, "dormitory": 18.0, "residential": 15.0,
    "university": 16.0, "college": 16.0, "school": 11.0,
    "hospital": 20.0, "hotel": 21.0, "office": 18.0, "commercial": 15.0,
    "retail": 7.0, "supermarket": 8.0, "kiosk": 3.0,
    "church": 14.0, "museum": 14.0, "public": 14.0, "train_station": 10.0,
    "chimney": 25.0, "garage": 3.0, "garages": 3.0, "shed": 3.0, "roof": 4.0,
}
NEIGHBOUR_K = 8             # neighbours polled when interpolating an untagged building
INFERRED_RANGE = (5.0, 32.0)


def parse_height(tags: dict) -> tuple[float, str] | tuple[None, None]:
    """Metres from OSM tags, preferring a surveyed height over a level count."""
    raw = tags.get("height")
    if raw:
        try:
            h = float(str(raw).removesuffix(" m").strip())
            if 0 < h < MAX_HEIGHT:
                return h, "osm_building_part"
        except ValueError:
            pass
    raw = tags.get("building:levels")
    if raw:
        try:
            h = float(raw) * LEVEL_METRES
            if 0 < h < MAX_HEIGHT:
                return h, "osm_building_part_levels"
        except ValueError:
            pass
    return None, None


def point_in_ring(pt, ring) -> bool:
    """Standard ray-casting test."""
    x, y = pt
    inside = False
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
        if (y0 > y) != (y1 > y):
            xc = (x1 - x0) * (y - y0) / (y1 - y0) + x0
            if x < xc:
                inside = not inside
    return inside


def load_parts():
    """-> [(centroid_xy, height, source)] for every building:part way."""
    root = ET.parse(OSM).getroot()
    b = root.find("bounds").attrib
    west, south, east, north = (float(b[k]) for k in ("minlon", "minlat", "maxlon", "maxlat"))
    lon0, lat0 = (west + east) / 2, (south + north) / 2

    # Identical projection to phase1/build_city.py:18, so coordinates line up
    # with the geometry already in the stage.
    def project(lon, lat):
        return (6378137 * math.radians(lon - lon0) * math.cos(math.radians(lat0)),
                6378137 * math.radians(lat - lat0))

    nodes = {n.attrib["id"]: project(float(n.attrib["lon"]), float(n.attrib["lat"]))
             for n in root.findall("node")}

    parts = []
    for way in root.findall("way"):
        tags = {t.attrib["k"]: t.attrib["v"] for t in way.findall("tag")}
        if "building:part" not in tags:
            continue
        # A way tagged both building and building:part is already imported with
        # its own height; only the part-only ways were lost.
        if tags.get("building") not in (None, "no"):
            continue
        height, source = parse_height(tags)
        if height is None:
            continue
        ids = [n.attrib["ref"] for n in way.findall("nd")]
        pts = [nodes[i] for i in ids if i in nodes]
        if len(pts) < 3:
            continue
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        parts.append(((cx, cy), height, source))
    return parts


def load_footprints(stage):
    """-> {prim_path: (ring_xy, n, current_height)} for every building."""
    out = {}
    scope = stage.GetPrimAtPath("/World/Buildings")
    for prim in scope.GetChildren():
        pts = UsdGeom.Mesh(prim).GetPointsAttr().Get()
        if not pts or len(pts) % 2:
            continue
        n = len(pts) // 2
        ring = [(p[0], p[1]) for p in pts[:n]]
        out[prim.GetPath().pathString] = (ring, n, float(pts[n][2]))
    return out


def load_meta(stage):
    """-> {prim_path: (osm_tags, heightSource, centroid_xy)}"""
    out = {}
    for prim in stage.GetPrimAtPath("/World/Buildings").GetChildren():
        attr = prim.GetAttribute("urbantwin:osmTags")
        try:
            tags = json.loads(attr.Get()) if attr and attr.Get() else {}
        except (ValueError, TypeError):
            tags = {}
        src = prim.GetAttribute("urbantwin:heightSource")
        pts = UsdGeom.Mesh(prim).GetPointsAttr().Get() or []
        n = max(len(pts) // 2, 1)
        cx = sum(p[0] for p in pts[:n]) / n if pts else 0.0
        cy = sum(p[1] for p in pts[:n]) / n if pts else 0.0
        out[prim.GetPath().pathString] = (tags, (src.Get() if src else "") or "", (cx, cy))
    return out


def infer_heights(footprints, meta, measured):
    """
    Give the 12 m-default buildings a plausible height.

    Only touches buildings Phase 1 could not resolve at all (heightSource
    'assumed_12m'). Two sources, both recorded on the prim:

      inferred_from_building_type  - OSM `building` class has a typical height
      inferred_from_neighbours     - class is the generic `yes`, so take the
                                     median of the nearest buildings whose
                                     height IS known. Spatial interpolation
                                     beats a constant, and in a dense block it
                                     is usually close.

    This is inference, not survey. `urbantwin:heightSource` says so on every
    prim it touches.
    """
    known = [(meta[p][2], h) for p, (h, _) in measured.items()]
    for path, (_, n, cur) in footprints.items():
        if path in measured:
            continue
        if meta[path][1] != "assumed_12m":          # real levels/height: leave alone
            known.append((meta[path][2], cur))

    out = {}
    for path, (_, _, cur) in footprints.items():
        if path in measured:
            continue
        tags, source, centroid = meta[path]
        if source != "assumed_12m":
            continue
        kind = tags.get("building", "")
        if kind in TYPE_HEIGHTS:
            out[path] = (TYPE_HEIGHTS[kind], "inferred_from_building_type")
            continue
        if not known:
            continue
        nearest = sorted(known, key=lambda kh: (kh[0][0] - centroid[0]) ** 2
                                               + (kh[0][1] - centroid[1]) ** 2)[:NEIGHBOUR_K]
        vals = sorted(h for _, h in nearest)
        median = vals[len(vals) // 2]
        lo, hi = INFERRED_RANGE
        out[path] = (max(lo, min(hi, median)), "inferred_from_neighbours")
    return out


def build() -> Path:
    stage = Usd.Stage.Open(str(BASE))
    footprints = load_footprints(stage)
    parts = load_parts()
    print(f"{len(footprints)} buildings, {len(parts)} usable building:part ways")

    # Bucket footprints into a coarse grid so each part tests a handful of
    # candidates instead of all 623.
    CELL = 50.0
    grid = collections.defaultdict(list)
    for path, (ring, _, _) in footprints.items():
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        for gx in range(int(min(xs) // CELL), int(max(xs) // CELL) + 1):
            for gy in range(int(min(ys) // CELL), int(max(ys) // CELL) + 1):
                grid[(gx, gy)].append(path)

    best: dict[str, tuple[float, str]] = {}
    unmatched = 0
    for centroid, height, source in parts:
        cell = (int(centroid[0] // CELL), int(centroid[1] // CELL))
        hit = None
        for path in grid.get(cell, ()):
            if point_in_ring(centroid, footprints[path][0]):
                hit = path
                break
        if hit is None:
            unmatched += 1
            continue
        # Tallest part wins: that is the building's real height.
        if hit not in best or height > best[hit][0]:
            best[hit] = (height, source)

    print(f"{len(best)} buildings matched to a part, {unmatched} parts fell outside any footprint")
    print("  (most unmatched parts belong to buildings Phase 1 never imported -")
    print("   boundary-clipped polygons and unassembled multipolygon relations)")

    meta = load_meta(stage)
    inferred = infer_heights(footprints, meta, best)
    by_source = collections.Counter(s for _, s in inferred.values())
    print(f"{len(inferred)} flat-12m buildings given an inferred height: {dict(by_source)}")
    best = {**inferred, **best}          # measured always wins over inferred

    out_stage = Usd.Stage.CreateNew(str(OUT)) if not OUT.exists() else Usd.Stage.Open(str(OUT))
    out_stage.GetRootLayer().Clear()
    UsdGeom.SetStageUpAxis(out_stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(out_stage, 1.0)
    out_stage.SetDefaultPrim(UsdGeom.Xform.Define(out_stage, "/World").GetPrim())
    out_stage.GetRootLayer().documentation = (
        "Building heights recovered from OSM building:part ways that Phase 1 "
        "discarded. Rewrites only the z of each prism's top ring; footprint XY "
        "is untouched. Regenerate with phase9/recover_heights.py."
    )

    raised = lowered = same = 0
    changes = []
    for path, (height, source) in sorted(best.items()):
        ring, n, current = footprints[path]
        if abs(height - current) < 0.5:
            same += 1
            continue
        over = out_stage.OverridePrim(path)
        mesh = UsdGeom.Mesh(over)
        pts = [(x, y, 0.04) for x, y in ring] + [(x, y, height) for x, y in ring]
        mesh.CreatePointsAttr(pts)
        mesh.CreateExtentAttr(UsdGeom.PointBased.ComputeExtent(mesh.GetPointsAttr().Get()))
        over.CreateAttribute("urbantwin:heightSource", Sdf.ValueTypeNames.String,
                             custom=True).Set(source)
        over.CreateAttribute("urbantwin:heightMetres", Sdf.ValueTypeNames.Double,
                             custom=True).Set(round(height, 2))
        changes.append((path, current, height))
        if height > current:
            raised += 1
        else:
            lowered += 1

    out_stage.GetRootLayer().Save()

    heights = [h for _, _, h in changes]
    print(f"\nrewrote {len(changes)} buildings: {raised} taller, {lowered} shorter, "
          f"{same} already correct")
    if heights:
        print(f"new height range {min(heights):.1f} .. {max(heights):.1f} m")
        for path, was, now in changes[:5]:
            print(f"  {path.split('/')[-1]:24s} {was:5.1f} -> {now:5.1f} m")
    print(f"\nwrote {OUT}")
    return OUT


if __name__ == "__main__":
    build()
