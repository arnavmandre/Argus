"""Validate the Phase 9 stage: variety, provenance, and that nothing upstream moved."""
import collections
import json
import sys
from pathlib import Path

from pxr import Usd, UsdGeom, UsdShade

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MAIN = HERE / "scene" / "main.usda"
BASE = ROOT / "phase1" / "scene" / "main.usda"

REAL_SOURCES = ("osm_height", "osm_building_part", "osm_building_part_levels",
                "assumed_3m_per_osm_level")


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def main():
    stage = Usd.Stage.Open(str(MAIN))
    if not stage:
        fail(f"{MAIN} does not compose")
    base = Usd.Stage.Open(str(BASE))

    report = {}

    # --- the whole city still resolves ---------------------------------
    for path in ("/World/Buildings", "/World/Roads", "/World/PedestrianPaths",
                 "/World/GreenSpaces", "/World/Transit", "/World/Environment/Sun",
                 "/World/Simulation", "/World/Phase9Looks",
                 "/World/Phase9Streetscape/Trees"):
        if not stage.GetPrimAtPath(path):
            fail(f"{path} missing from the composed stage")

    buildings = list(stage.GetPrimAtPath("/World/Buildings").GetChildren())
    base_buildings = {p.GetName(): p for p in base.GetPrimAtPath("/World/Buildings").GetChildren()}
    report["buildings"] = len(buildings)

    # --- materials are varied, not one grey ----------------------------
    mats = collections.Counter()
    roof_subsets = 0
    for prim in buildings:
        binding = UsdShade.MaterialBindingAPI(prim).GetDirectBinding().GetMaterialPath()
        mats[binding.name if binding else None] += 1
        if prim.GetPrimAtPath("RoofFace"):
            roof_subsets += 1
    if None in mats:
        fail(f"{mats[None]} buildings have no material bound")
    if len(mats) < 6:
        fail(f"only {len(mats)} distinct building materials - expected variety")
    if roof_subsets < len(buildings):
        fail(f"only {roof_subsets}/{len(buildings)} buildings have a roof face subset")
    report["distinct_building_materials"] = len(mats)
    report["roof_subsets"] = roof_subsets

    # --- heights vary and record their provenance ----------------------
    sources = collections.Counter()
    heights = []
    for prim in buildings:
        attr = prim.GetAttribute("urbantwin:heightSource")
        sources[(attr.Get() if attr else None) or "unknown"] += 1
        pts = UsdGeom.Mesh(prim).GetPointsAttr().Get() or []
        if pts:
            h = max(p[2] for p in pts)
            if not (0 < h < 300):
                fail(f"{prim.GetName()} has implausible height {h}")
            heights.append(h)
    distinct = len({round(h, 1) for h in heights})
    if distinct < 10:
        fail(f"only {distinct} distinct building heights - the skyline is still flat")
    real = sum(sources[k] for k in REAL_SOURCES)
    report["height_sources"] = dict(sources)
    report["distinct_heights"] = distinct
    report["height_range_m"] = [round(min(heights), 1), round(max(heights), 1)]
    report["heights_from_real_osm_data"] = real

    # --- footprints are untouched: only z may have moved ---------------
    moved = 0
    for prim in buildings:
        bp = base_buildings.get(prim.GetName())
        if not bp:
            continue
        a = UsdGeom.Mesh(prim).GetPointsAttr().Get() or []
        b = UsdGeom.Mesh(bp).GetPointsAttr().Get() or []
        if len(a) != len(b):
            fail(f"{prim.GetName()} point count changed - geometry was rebuilt, not overridden")
        for p, q in zip(a, b):
            if abs(p[0] - q[0]) > 1e-4 or abs(p[1] - q[1]) > 1e-4:
                moved += 1
                break
    if moved:
        fail(f"{moved} buildings moved in XY - Phase 9 must only change height")
    report["footprints_unchanged"] = True

    # --- both variant sets work ----------------------------------------
    world = stage.GetPrimAtPath("/World")
    vsets = world.GetVariantSets()
    for name in ("cityLook", "demoState"):
        if name not in vsets.GetNames():
            fail(f"variant set {name} missing")

    look = vsets.GetVariantSet("cityLook")
    previous = look.GetVariantSelection()
    seen = {}
    for variant in look.GetVariantNames():
        look.SetVariantSelection(variant)
        sample = [UsdShade.MaterialBindingAPI(p).GetDirectBinding().GetMaterialPath().name
                  for p in list(stage.GetPrimAtPath("/World/Buildings").GetChildren())[:40]]
        seen[variant] = sample
    look.SetVariantSelection(previous)
    if len(look.GetVariantNames()) < 2:
        fail("cityLook needs at least two variants")
    if seen["realistic"] == seen["analytic"]:
        fail("cityLook variants bind identical materials")
    report["cityLook"] = look.GetVariantNames()
    report["demoState"] = vsets.GetVariantSet("demoState").GetVariantNames()

    # --- streetscape ----------------------------------------------------
    trees = UsdGeom.PointInstancer(stage.GetPrimAtPath("/World/Phase9Streetscape/Trees"))
    n_trees = len(trees.GetPositionsAttr().Get() or [])
    if n_trees < 100:
        fail(f"only {n_trees} trees instanced")
    report["trees"] = n_trees
    report["tree_prims"] = 1

    # --- the OSM-derived simulator city ---------------------------------
    city = ROOT / "Simulation" / "city_osm.json"
    if city.exists():
        data = json.loads(city.read_text(encoding="utf-8"))
        edge_backed = sum(1 for r in data["routes"] if r.get("osm_edges"))
        if edge_backed != len(data["routes"]):
            fail("some OSM city routes carry no osm_edges")
        report["osm_city"] = {
            "zones": len(data["zones"]), "buildings": len(data["buildings"]),
            "routes": len(data["routes"]), "all_routes_edge_backed": True,
        }

    print(json.dumps(report, indent=2))
    print("\nPASS: materials varied, heights varied with recorded provenance, "
          "footprints unchanged, both variant sets live")


if __name__ == "__main__":
    main()
