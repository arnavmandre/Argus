#!/usr/bin/env python3
"""
UrbanTwin AI - city generator
=============================
Builds ONE source of truth for the city and writes it in two forms:

  city.json  - the simulation contract (nodes, buildings, paths, trees, shade)
  city.usda  - an OpenUSD scene you open in Omniverse (File > Open)

No third-party libraries are needed to generate the files (the .usda is written
as plain text). `pip install usd-core` is only needed to *validate* it.

Usage
-----
  python urbantwin_city.py --out out                    # baseline city
  python urbantwin_city.py --out out --demo-redesign    # + a test "after" city
  python urbantwin_city.py --out out --preview          # + top-down PNG (needs matplotlib)

Layout: a 3x3 grid of zones, 150 m apart, Y-up, 1 unit = 1 metre.

Everything is deterministic (fixed seed) so teammates get identical cities.
Numbers marked ASSUMPTION are prototype heuristics, not measured values.
"""
import argparse
import copy
import json
import math
import os
import random

SEED = 42

# ---- geometry (metres) ------------------------------------------------------
GRID_M = 150.0        # distance between neighbouring zone centres
PLAZA_M = 40.0        # zone plaza footprint
PARK_M = 60.0         # park lawn footprint
ROAD_W = 12.0
PATH_OFFSET = 10.5    # pedestrian path runs beside the road, this far from its centreline
PATH_W = 4.0          # default pedestrian path width
PATH_TRIM = 20.0      # paths start/end this far from zone centres
CANOPY_R = 4.0        # tree canopy radius that shades the path below it
MAX_TREES_PER_PATH = 40

# ---- prototype heuristics (ASSUMPTION - tune or replace) --------------------
FLOW_PPH_PER_M = 1500   # pedestrian flow capacity, persons/hour per metre of path width
BASELINE_POP = 50_000   # people represented by the baseline city

# ---- layout -----------------------------------------------------------------
# (id, type, display name, grid_x, grid_z)
NODES = [
    ("R1", "residential", "Residential A", -1, -1),
    ("S1", "school",      "School",         0, -1),
    ("PK", "park",        "Central Park",   1, -1),
    ("T1", "transit",     "Transit Hub",   -1,  0),
    ("C1", "commercial",  "Commercial Core", 0,  0),
    ("H1", "hospital",    "Hospital",       1,  0),
    ("R2", "residential", "Residential B", -1,  1),
    ("O1", "office",      "Office District", 0,  1),
    ("R3", "residential", "Residential C",  1,  1),
]
BUILDING_COUNTS = {"R1": 3, "S1": 1, "T1": 1, "C1": 3, "H1": 1, "R2": 2, "O1": 2, "R3": 3}
SLOTS = [(35, 35), (-35, 35), (35, -35), (-35, -35)]  # diagonal offsets, clear of roads
DIMS = {  # type: ((footprint min,max), (height min,max))
    "residential": ((20, 26), (30, 50)),
    "commercial":  ((22, 28), (20, 35)),
    "office":      ((22, 26), (60, 90)),
    "school":      ((26, 26), (12, 12)),
    "hospital":    ((28, 28), (30, 30)),
    "transit":     ((30, 30), (10, 10)),
}
BUILDING_COLORS = {
    "residential": (0.85, 0.75, 0.65), "commercial": (0.60, 0.70, 0.85),
    "office": (0.55, 0.60, 0.70), "school": (0.90, 0.80, 0.40),
    "hospital": (0.95, 0.50, 0.50), "transit": (0.50, 0.50, 0.90),
}
PLAZA_COLORS = {
    "residential": (0.80, 0.78, 0.72), "school": (0.85, 0.83, 0.65),
    "park": (0.40, 0.70, 0.40), "transit": (0.70, 0.72, 0.85),
    "commercial": (0.75, 0.78, 0.85), "hospital": (0.90, 0.80, 0.80),
    "office": (0.72, 0.74, 0.80),
}


# =============================================================================
# City model
# =============================================================================
def build_city(seed=SEED):
    rng = random.Random(seed)
    nodes = [{"id": i, "type": t, "name": n, "x": gx * GRID_M, "z": gz * GRID_M,
              "gx": gx, "gz": gz} for i, t, n, gx, gz in NODES]
    by_id = {n["id"]: n for n in nodes}

    n_res = sum(c for nid, c in BUILDING_COUNTS.items() if by_id[nid]["type"] == "residential")
    buildings = []
    for nid, count in BUILDING_COUNTS.items():
        node = by_id[nid]
        for i in range(count):
            (wmin, wmax), (hmin, hmax) = DIMS[node["type"]]
            w = round(rng.uniform(wmin, wmax), 1)
            sx, sz = SLOTS[i]
            buildings.append({
                "id": f"bld_{nid}_{i}", "node": nid, "type": node["type"],
                "x": node["x"] + sx, "z": node["z"] + sz,
                "w": w, "d": w, "h": round(rng.uniform(hmin, hmax), 1),
                # each residential "building" stands for a block cluster; sums to BASELINE_POP
                "residents": BASELINE_POP // n_res if node["type"] == "residential" else 0,
            })

    grid = {(n["gx"], n["gz"]): n["id"] for n in nodes}
    edges = []
    for (gx, gz) in sorted(grid):
        for dx, dz in ((1, 0), (0, 1)):
            b = grid.get((gx + dx, gz + dz))
            if b:
                a = grid[(gx, gz)]
                touches_park = "PK" in (a, b)
                edges.append({
                    "id": f"e_{a}_{b}", "a": a, "b": b, "width_m": PATH_W,
                    "base_shade": round(rng.uniform(0.15, 0.30) if touches_park
                                        else rng.uniform(0.05, 0.25), 3),
                })

    city = {
        "meta": {
            "generator": "urbantwin_city.py", "seed": seed, "units": "metres, Y-up",
            "baseline_population": BASELINE_POP,
            "flow_capacity_pph_per_m": FLOW_PPH_PER_M,
            "notes": "shade_pct = base_shade + (1-base_shade)*tree_shade. "
                     "capacity_pph = width_m * flow_capacity_pph_per_m (ASSUMPTION).",
        },
        "nodes": nodes, "buildings": buildings, "edges": edges, "trees": [],
        "_tree_counter": 0,
    }
    for e in edges:
        _set_edge_geometry(city, e)

    # park trees (no edge) + initial street trees
    park = by_id["PK"]
    for _ in range(24):
        _new_tree(city, park["x"] + rng.uniform(-24, 24), park["z"] + rng.uniform(-24, 24), None)
    for e in edges:
        n_trees = 6 if "PK" in (e["a"], e["b"]) else rng.choice([0, 0, 1, 2, 3])
        _place_edge_trees(city, e, n_trees)

    recompute_shade(city)
    return city


def _node(city, nid):
    return next(n for n in city["nodes"] if n["id"] == nid)


def _set_edge_geometry(city, e):
    a, b = _node(city, e["a"]), _node(city, e["b"])
    dx, dz = b["x"] - a["x"], b["z"] - a["z"]
    L = math.hypot(dx, dz)
    d = (dx / L, dz / L)
    n = (-d[1], d[0])
    e["p0"] = [round(a["x"] + d[0] * PATH_TRIM + n[0] * PATH_OFFSET, 2),
               round(a["z"] + d[1] * PATH_TRIM + n[1] * PATH_OFFSET, 2)]
    e["p1"] = [round(b["x"] - d[0] * PATH_TRIM + n[0] * PATH_OFFSET, 2),
               round(b["z"] - d[1] * PATH_TRIM + n[1] * PATH_OFFSET, 2)]
    e["length_m"] = round(L - 2 * PATH_TRIM, 2)


def _new_tree(city, x, z, edge_id):
    city["_tree_counter"] += 1
    t = {"id": f"tree_{city['_tree_counter']:04d}", "x": round(x, 2), "z": round(z, 2),
         "edge": edge_id, "canopy_r": CANOPY_R}
    city["trees"].append(t)
    return t


def _place_edge_trees(city, e, count):
    """(Re)place `count` trees evenly along an edge's path, alternating sides."""
    city["trees"] = [t for t in city["trees"] if t["edge"] != e["id"]]
    (x0, z0), (x1, z1), L = e["p0"], e["p1"], e["length_m"]
    d = ((x1 - x0) / L, (z1 - z0) / L)
    n = (-d[1], d[0])
    for i in range(count):
        s = (i + 0.5) / count * L
        side = 1.5 if i % 2 == 0 else -1.5
        _new_tree(city, x0 + d[0] * s + n[0] * side, z0 + d[1] * s + n[1] * side, e["id"])


def recompute_shade(city):
    """Shade = fraction of the path (sampled every ~2 m) under any tree canopy."""
    for e in city["edges"]:
        (x0, z0), (x1, z1), L = e["p0"], e["p1"], e["length_m"]
        samples = max(2, int(L / 2))
        covered = 0
        for k in range(samples):
            s = (k + 0.5) / samples
            x, z = x0 + (x1 - x0) * s, z0 + (z1 - z0) * s
            if any(math.hypot(x - t["x"], z - t["z"]) <= t["canopy_r"] for t in city["trees"]):
                covered += 1
        e["tree_shade"] = round(covered / samples, 3)
        e["shade_pct"] = round(min(1.0, e["base_shade"] + (1 - e["base_shade"]) * e["tree_shade"]), 3)
        e["capacity_pph"] = int(e["width_m"] * FLOW_PPH_PER_M)
        e["trees"] = [t["id"] for t in city["trees"] if t["edge"] == e["id"]]


# ---- interventions: the fixed menu the AI advisor will choose from ----------
def add_trees(city, edge_id, n):
    """Intervention: plant n more trees along a path, then recompute shade."""
    e = next(x for x in city["edges"] if x["id"] == edge_id)
    total = min(MAX_TREES_PER_PATH, len(e["trees"]) + int(n))
    _place_edge_trees(city, e, total)
    recompute_shade(city)


def widen_path(city, edge_id, new_width_m):
    """Intervention: widen a pedestrian path (raises capacity). Max 8 m to stay clear of the road."""
    e = next(x for x in city["edges"] if x["id"] == edge_id)
    e["width_m"] = float(min(8.0, max(PATH_W, new_width_m)))
    recompute_shade(city)


def city_summary(city):
    e = city["edges"]
    return {
        "buildings": len(city["buildings"]), "paths": len(e), "trees": len(city["trees"]),
        "population": sum(b["residents"] for b in city["buildings"]),
        "avg_path_shade": round(sum(x["shade_pct"] for x in e) / len(e), 3),
        "min_path_shade": min(x["shade_pct"] for x in e),
    }


# =============================================================================
# USD (ASCII .usda) writer - plain text, no pxr dependency
# =============================================================================
def _v3(v):
    return f"({v[0]:.3f}, {v[1]:.3f}, {v[2]:.3f})"


def _col(c):
    return f"[({c[0]:.3f}, {c[1]:.3f}, {c[2]:.3f})]"


def _attr(name, value):
    if isinstance(value, bool):
        return f"custom bool {name} = {'true' if value else 'false'}"
    if isinstance(value, int):
        return f"custom int {name} = {value}"
    if isinstance(value, float):
        return f"custom double {name} = {value:.4f}"
    return f"custom string {name} = {json.dumps(str(value))}"


def _shade_color(shade):
    lo, hi = (0.90, 0.35, 0.25), (0.25, 0.70, 0.40)   # sun-exposed -> shaded
    return tuple(lo[i] + (hi[i] - lo[i]) * shade for i in range(3))


def _cube(name, pos, size, color, attrs=None, rot_y=None, ind=2):
    p = "    " * ind
    L = [f'{p}def Cube "{name}"', f"{p}{{", f"{p}    double size = 1",
         f"{p}    color3f[] primvars:displayColor = {_col(color)}"]
    for k, v in (attrs or {}).items():
        L.append(f"{p}    {_attr(k, v)}")
    ops = ['"xformOp:translate"']
    L.append(f"{p}    double3 xformOp:translate = {_v3(pos)}")
    if rot_y is not None:
        L.append(f"{p}    double xformOp:rotateY = {rot_y:.4f}")
        ops.append('"xformOp:rotateY"')
    L.append(f"{p}    double3 xformOp:scale = {_v3(size)}")
    ops.append('"xformOp:scale"')
    L.append(f"{p}    uniform token[] xformOpOrder = [{', '.join(ops)}]")
    L.append(f"{p}}}")
    return L


def _tree(t, ind=2):
    p = "    " * ind
    return [
        f'{p}def Xform "{t["id"]}"', f"{p}{{",
        f"{p}    {_attr('urbantwin:canopy_r', float(t['canopy_r']))}",
        f"{p}    {_attr('urbantwin:edge', t['edge'] or 'park')}",
        f"{p}    double3 xformOp:translate = {_v3((t['x'], 0, t['z']))}",
        f'{p}    uniform token[] xformOpOrder = ["xformOp:translate"]',
        f'{p}    def Cylinder "trunk"', f"{p}    {{",
        f"{p}        double height = 3", f"{p}        double radius = 0.3",
        f'{p}        uniform token axis = "Y"',
        f"{p}        color3f[] primvars:displayColor = [(0.40, 0.28, 0.18)]",
        f"{p}        double3 xformOp:translate = (0, 1.5, 0)",
        f'{p}        uniform token[] xformOpOrder = ["xformOp:translate"]', f"{p}    }}",
        f'{p}    def Sphere "canopy"', f"{p}    {{",
        f"{p}        double radius = {t['canopy_r']:.2f}",
        f"{p}        color3f[] primvars:displayColor = [(0.20, 0.55, 0.25)]",
        f"{p}        double3 xformOp:translate = (0, 5.5, 0)",
        f'{p}        uniform token[] xformOpOrder = ["xformOp:translate"]', f"{p}    }}",
        f"{p}}}",
    ]


def write_usda(city, path):
    nodes = {n["id"]: n for n in city["nodes"]}
    out = [
        "#usda 1.0", "(", '    defaultPrim = "World"', "    metersPerUnit = 1",
        '    upAxis = "Y"',
        '    doc = "UrbanTwin AI city - generated by urbantwin_city.py. Edit city.json/the generator, not this file."',
        "    customLayerData = {",
        f'        string generator = "urbantwin_city.py"', f"        int seed = {city['meta']['seed']}",
        "    }", ")", "", 'def Xform "World"', "{",
    ]

    # ground
    out += _cube("Ground", (0, -0.1, 0), (700, 0.2, 700), (0.78, 0.78, 0.74), ind=1)

    def scope(name, body):
        out.append(f'    def Scope "{name}"')
        out.append("    {")
        out.extend(body)
        out.append("    }")

    # zone plazas
    body = []
    for n in city["nodes"]:
        size = PARK_M if n["type"] == "park" else PLAZA_M
        body += _cube(f"zone_{n['id']}", (n["x"], 0.125, n["z"]), (size, 0.25, size),
                      PLAZA_COLORS[n["type"]],
                      {"urbantwin:node_id": n["id"], "urbantwin:zone_type": n["type"],
                       "urbantwin:name": n["name"]})
    scope("Zones", body)

    # roads (one strip per edge)
    body = []
    for e in city["edges"]:
        a, b = nodes[e["a"]], nodes[e["b"]]
        cx, cz = (a["x"] + b["x"]) / 2, (a["z"] + b["z"]) / 2
        horizontal = abs(b["x"] - a["x"]) > 0
        size = (GRID_M, 0.2, ROAD_W) if horizontal else (ROAD_W, 0.2, GRID_M)
        body += _cube(f"road_{e['id']}", (cx, 0.1, cz), size, (0.15, 0.15, 0.17))
    scope("Roads", body)

    # pedestrian paths (colour = shade: red sun-exposed -> green shaded)
    body = []
    for e in city["edges"]:
        (x0, z0), (x1, z1) = e["p0"], e["p1"]
        phi = math.degrees(math.atan2(-(z1 - z0), (x1 - x0)))
        body += _cube(
            e["id"], ((x0 + x1) / 2, 0.3, (z0 + z1) / 2), (e["length_m"], 0.2, e["width_m"]),
            _shade_color(e["shade_pct"]),
            {"urbantwin:kind": "pedestrian_path", "urbantwin:from": e["a"], "urbantwin:to": e["b"],
             "urbantwin:length_m": float(e["length_m"]), "urbantwin:width_m": float(e["width_m"]),
             "urbantwin:base_shade": float(e["base_shade"]),
             "urbantwin:shade_pct": float(e["shade_pct"]),
             "urbantwin:capacity_pph": int(e["capacity_pph"])},
            rot_y=phi)
    scope("Paths", body)

    # buildings
    body = []
    for b in city["buildings"]:
        body += _cube(b["id"], (b["x"], b["h"] / 2 + 0.25, b["z"]), (b["w"], b["h"], b["d"]),
                      BUILDING_COLORS[b["type"]],
                      {"urbantwin:type": b["type"], "urbantwin:node_id": b["node"],
                       "urbantwin:residents": int(b["residents"])})
    scope("Buildings", body)

    # trees
    body = []
    for t in city["trees"]:
        body += _tree(t)
    scope("Trees", body)

    # lights + camera
    out += [
        '    def DistantLight "Sun"', "    {",
        "        float inputs:intensity = 3000", "        float inputs:angle = 1.0",
        "        color3f inputs:color = (1.0, 0.96, 0.9)",
        "        float3 xformOp:rotateXYZ = (-50, 30, 0)",
        '        uniform token[] xformOpOrder = ["xformOp:rotateXYZ"]', "    }",
        '    def DomeLight "Sky"', "    {", "        float inputs:intensity = 600", "    }",
        '    def Camera "MainCamera"', "    {",
        "        float focalLength = 24", "        float2 clippingRange = (1, 5000)",
        "        double3 xformOp:translate = (0, 450, 550)",
        "        float3 xformOp:rotateXYZ = (-39, 0, 0)",
        '        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ"]', "    }",
        "}", "",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))


def write_json(city, path):
    clean = {k: v for k, v in city.items() if not k.startswith("_")}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2)


# =============================================================================
# Optional 2D preview (also the seed of the fallback dashboard map)
# =============================================================================
def write_preview(city, path, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    fig, ax = plt.subplots(figsize=(8, 8))
    nodes = {n["id"]: n for n in city["nodes"]}
    for n in city["nodes"]:
        s = PARK_M if n["type"] == "park" else PLAZA_M
        ax.add_patch(Rectangle((n["x"] - s / 2, n["z"] - s / 2), s, s, color=PLAZA_COLORS[n["type"]], zorder=1))
        ax.text(n["x"], n["z"], n["id"], ha="center", va="center", fontsize=9, weight="bold", zorder=6)
    for e in city["edges"]:
        a, b = nodes[e["a"]], nodes[e["b"]]
        ax.plot([a["x"], b["x"]], [a["z"], b["z"]], color="#262629", lw=9, solid_capstyle="butt", zorder=2)
        ax.plot([e["p0"][0], e["p1"][0]], [e["p0"][1], e["p1"][1]], color=_shade_color(e["shade_pct"]),
                lw=2 + e["width_m"] / 2, solid_capstyle="butt", zorder=3)
        mx, mz = (e["p0"][0] + e["p1"][0]) / 2, (e["p0"][1] + e["p1"][1]) / 2
        ax.text(mx, mz, f"{int(e['shade_pct'] * 100)}%", fontsize=7, ha="center", va="center",
                color="white", weight="bold", zorder=8,
                bbox=dict(boxstyle="round,pad=0.2", fc="black", ec="none", alpha=0.65))
    for b in city["buildings"]:
        ax.add_patch(Rectangle((b["x"] - b["w"] / 2, b["z"] - b["d"] / 2), b["w"], b["d"],
                               color=BUILDING_COLORS[b["type"]], ec="#333", lw=0.6, zorder=4))
    for t in city["trees"]:
        ax.add_patch(plt.Circle((t["x"], t["z"]), t["canopy_r"], color="#2f8f3f", alpha=0.35, zorder=5))
    ax.set_xlim(-260, 260)
    ax.set_ylim(260, -260)   # z grows downward, matching a top-down view from +Y
    ax.set_aspect("equal")
    ax.set_title(title)
    ax.set_xlabel("x (m)")
    ax.set_ylabel("z (m)")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


# =============================================================================
def main():
    ap = argparse.ArgumentParser(description="Generate the UrbanTwin AI city (USD + JSON).")
    ap.add_argument("--out", default="out")
    ap.add_argument("--demo-redesign", action="store_true",
                    help="also write a hard-coded TEST 'after' city (for checking the before/after toggle)")
    ap.add_argument("--preview", action="store_true", help="also write top-down PNG previews")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    city = build_city()
    write_json(city, os.path.join(args.out, "city.json"))
    write_usda(city, os.path.join(args.out, "city.usda"))
    print("baseline:", city_summary(city))
    if args.preview:
        write_preview(city, os.path.join(args.out, "preview_baseline.png"),
                      "UrbanTwin baseline (path label = shade %)")

    if args.demo_redesign:
        after = copy.deepcopy(city)
        worst = sorted(after["edges"], key=lambda e: e["shade_pct"])[:3]
        for e in worst:
            add_trees(after, e["id"], 14)          # TEST values only - the AI advisor replaces this
        for eid in ("e_T1_C1", "e_R1_T1"):
            widen_path(after, eid, 7.0)
        write_json(after, os.path.join(args.out, "city_redesigned.json"))
        write_usda(after, os.path.join(args.out, "city_redesigned.usda"))
        print("after (TEST redesign):", city_summary(after))
        if args.preview:
            write_preview(after, os.path.join(args.out, "preview_redesigned.png"),
                          "TEST redesign: +trees on 3 worst paths, wider paths at transit")


if __name__ == "__main__":
    main()
