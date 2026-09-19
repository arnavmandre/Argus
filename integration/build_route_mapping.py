"""
UrbanTwin AI - route mapping builder.

Fills in `integration/route_mapping.json`: for each abstract simulator route
(R1..R18) an ORDERED list of real Phase 2 `edge_*` IDs, plus the true walking
distance of that path in metres.

Why this exists
---------------
The simulator models 8 abstract buildings joined by 18 abstract routes. The
Omniverse scene is a real OSM tile with 2,291 pedestrian edges. Nothing can be
rendered, and no agent can be positioned, until those two are related.

How it works
------------
1. Build an undirected walking graph from `phase2/scene/edge_registry.json`,
   joining edges that share an OSM node ID.
2. Place one anchor node per simulator building. Anchors come from
   `route_anchors.json` if present; otherwise they are chosen by farthest-point
   sampling over the largest connected component, which spreads them across the
   tile deterministically.
3. For each simulator building pair, compute genuinely distinct walking paths
   with a penalty-based k-shortest-paths search, and assign them to that pair's
   routes ordered by the simulator's own distance_km (shortest sim route gets
   the shortest real path), so the relative geometry stays consistent.

IMPORTANT
---------
Auto-chosen anchors are geometrically real but semantically provisional: the
tool does not know which OSM building is "the hospital". The output is marked
`"status": "PROVISIONAL"` until a human sets anchors in `route_anchors.json`.
Do not present auto-anchored output as a surveyed mapping.

Usage:
    python integration/build_route_mapping.py            # build (provisional)
    python integration/build_route_mapping.py --report   # print, write nothing
"""
from __future__ import annotations

import argparse
import heapq
import json
import math
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REGISTRY = REPO / "phase2" / "scene" / "edge_registry.json"
SIM_CITY = REPO / "Simulation" / "city.json"
ANCHORS = Path(__file__).resolve().parent / "route_anchors.json"
OUT = Path(__file__).resolve().parent / "route_mapping.json"

PENALTY = 3.0        # weight multiplier on edges already used, for path diversity


# --------------------------------------------------------------------------
# graph
# --------------------------------------------------------------------------

def load_graph():
    """-> (adjacency, node_xy, edge_len, city_id)"""
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    edges = reg["edges"]

    adj = defaultdict(list)          # node -> [(other, edge_id, length_m)]
    node_xy = {}
    edge_len = {}

    for eid, rec in edges.items():
        nodes = rec.get("osm_node_ids") or []
        pts = rec.get("points") or []
        if len(nodes) < 2 or len(pts) < 2:
            continue
        a, b = str(nodes[0]), str(nodes[-1])
        length = 0.0
        for p, q in zip(pts, pts[1:]):
            length += math.dist(p[:2], q[:2])
        if length <= 0:
            continue
        node_xy.setdefault(a, tuple(pts[0][:2]))
        node_xy.setdefault(b, tuple(pts[-1][:2]))
        edge_len[eid] = length
        adj[a].append((b, eid, length))
        adj[b].append((a, eid, length))

    return adj, node_xy, edge_len, reg["city_id"]


def largest_component(adj):
    seen, best = set(), []
    for start in adj:
        if start in seen:
            continue
        stack, comp = [start], []
        seen.add(start)
        while stack:
            n = stack.pop()
            comp.append(n)
            for nb, _, _ in adj[n]:
                if nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        if len(comp) > len(best):
            best = comp
    return set(best)


def shortest_path(adj, src, dst, penalised):
    """Dijkstra returning (ordered edge ids, metres) or (None, inf)."""
    dist = {src: 0.0}
    prev = {}
    pq = [(0.0, src)]
    done = set()
    while pq:
        d, n = heapq.heappop(pq)
        if n in done:
            continue
        done.add(n)
        if n == dst:
            break
        for nb, eid, length in adj[n]:
            w = length * (PENALTY if eid in penalised else 1.0)
            nd = d + w
            if nd < dist.get(nb, math.inf):
                dist[nb] = nd
                prev[nb] = (n, eid)
                heapq.heappush(pq, (nd, nb))
    if dst not in dist:
        return None, math.inf

    # Walk the predecessor chain back to the source. The returned distance is
    # the PENALISED cost; callers recompute true metres from edge_len.
    path, node = [], dst
    while node != src:
        node, eid = prev[node]
        path.append(eid)
    path.reverse()
    return path, dist[dst]


def k_distinct_paths(adj, edge_len, src, dst, k):
    """k genuinely different walking routes, by penalising reused edges."""
    out, penalised = [], set()
    for _ in range(k):
        path, _ = shortest_path(adj, src, dst, penalised)
        if not path:
            break
        true_len = sum(edge_len[e] for e in path)
        if path not in [p for p, _ in out]:
            out.append((path, true_len))
        penalised.update(path)
    # Penalised search finds paths in order of PENALISED cost, which is not the
    # same order as true metres. Sort so the shortest real walk is first.
    out.sort(key=lambda pl: pl[1])
    return out


# --------------------------------------------------------------------------
# anchors
# --------------------------------------------------------------------------

INSET = 0.62     # keep auto anchors inside the central 62% of the tile


def farthest_point_anchors(node_xy, pool, n):
    """Deterministic, well-spread anchor nodes."""
    # Pure farthest-point sampling drives every anchor onto the tile boundary,
    # which makes routes hug the edge of the imported area. Restrict to an
    # inset core first so anchors sit inside the city.
    xs = [node_xy[nd][0] for nd in pool]
    ys = [node_xy[nd][1] for nd in pool]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    hw, hh = (max(xs) - min(xs)) / 2 * INSET, (max(ys) - min(ys)) / 2 * INSET
    core = {nd for nd in pool
            if abs(node_xy[nd][0] - cx) <= hw and abs(node_xy[nd][1] - cy) <= hh}
    pool = sorted(core) if len(core) >= n * 20 else sorted(pool)
    start = min(pool, key=lambda nd: (node_xy[nd][0] ** 2 + node_xy[nd][1] ** 2))
    picked = [start]
    while len(picked) < n:
        best, best_d = None, -1.0
        for nd in pool:
            if nd in picked:
                continue
            d = min(math.dist(node_xy[nd], node_xy[p]) for p in picked)
            if d > best_d:
                best, best_d = nd, d
        picked.append(best)
    return picked


def resolve_anchors(building_ids, node_xy, pool):
    if ANCHORS.exists():
        cfg = json.loads(ANCHORS.read_text(encoding="utf-8"))
        chosen = cfg.get("anchors", {})
        missing = [b for b in building_ids if b not in chosen]
        if missing:
            raise SystemExit(f"route_anchors.json is missing anchors for: {missing}")
        bad = [b for b, nd in chosen.items() if str(nd) not in node_xy]
        if bad:
            raise SystemExit(f"route_anchors.json names unknown OSM nodes: {bad}")
        return {b: str(chosen[b]) for b in building_ids}, "HUMAN_ANCHORED"

    picked = farthest_point_anchors(node_xy, pool, len(building_ids))
    return dict(zip(building_ids, picked)), "PROVISIONAL"


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------

def build(report_only=False):
    adj, node_xy, edge_len, city_id = load_graph()
    comp = largest_component(adj)
    print(f"graph: {len(adj)} nodes, {len(edge_len)} edges, "
          f"largest component {len(comp)} nodes")

    city = json.loads(SIM_CITY.read_text(encoding="utf-8"))
    buildings = [b["id"] for b in city["buildings"]]
    routes = city["routes"]

    anchors, status = resolve_anchors(buildings, node_xy, comp)
    print(f"anchors ({status}):")
    for b, nd in anchors.items():
        x, y = node_xy[nd]
        print(f"  {b:5s} -> node {nd:>12s}  at ({x:7.1f}, {y:7.1f})")

    # group simulator routes by the building pair they join
    by_pair = defaultdict(list)
    for r in routes:
        by_pair[tuple(sorted((r["start"], r["end"])))].append(r)

    mapping, distances, failures = {}, {}, []
    for (a, b), rs in sorted(by_pair.items()):
        rs.sort(key=lambda r: r["distance_km"])       # shortest sim route first
        paths = k_distinct_paths(adj, edge_len, anchors[a], anchors[b], len(rs))
        if not paths:
            failures.append(f"{a}-{b}: no walking path between anchors")
            continue
        for i, r in enumerate(rs):
            path, length = paths[min(i, len(paths) - 1)]
            mapping[r["id"]] = path
            distances[r["id"]] = round(length / 1000.0, 3)
        if len(paths) < len(rs):
            failures.append(
                f"{a}-{b}: only {len(paths)} distinct path(s) for {len(rs)} routes "
                f"(duplicates assigned)"
            )

    print(f"\nmapped {len(mapping)}/{len(routes)} routes")
    for rid in sorted(mapping, key=lambda s: int(s[1:])):
        sim_km = next(r["distance_km"] for r in routes if r["id"] == rid)
        print(f"  {rid:4s} {len(mapping[rid]):3d} edges  "
              f"real {distances[rid]:5.2f} km  (sim says {sim_km:.2f} km)")
    for f in failures:
        print(f"  WARNING {f}")

    doc = {
        "schema_version": "1.0",
        "city_id": city_id,
        "status": status,
        "description": (
            "Ordered Phase 2 edge IDs per simulator route, computed as real "
            "walking paths over the OSM pedestrian graph between per-building "
            "anchor nodes."
        ),
        "anchor_mode": status,
        "anchor_note": (
            "Anchors were auto-placed by farthest-point sampling. They are real "
            "graph nodes and the paths between them are real, but which OSM "
            "location represents which simulator building has NOT been agreed by "
            "the team. Set integration/route_anchors.json and rerun before "
            "presenting this as a surveyed mapping."
            if status == "PROVISIONAL" else
            "Anchors were supplied by the team in integration/route_anchors.json."
        ),
        "building_anchors": {
            b: {"osm_node_id": nd, "x": round(node_xy[nd][0], 2),
                "y": round(node_xy[nd][1], 2)}
            for b, nd in anchors.items()
        },
        "route_length_km_real": distances,
        "warnings": failures,
        "simulator_routes": mapping,
    }

    if report_only:
        print("\n--report: nothing written")
        return doc

    OUT.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT}  (status={status})")
    return doc


def apply_distances(doc):
    """
    Rewrite Simulation/city.json route distance_km with the REAL walking
    distances measured on the OSM graph.

    Not done automatically. While the mapping status is PROVISIONAL the anchor
    placement has not been agreed, so these distances describe a geography
    nobody has signed off on - baking them into the simulator would make the
    simulation quietly depend on a guess.
    """
    if doc["status"] != "HUMAN_ANCHORED":
        print("\nREFUSING --apply-distances while mapping status is "
              f"{doc['status']}.\nSet integration/route_anchors.json, rerun, "
              "then apply.")
        return

    raw = SIM_CITY.read_text(encoding="utf-8")
    city = json.loads(raw)
    changed = 0
    for r in city["routes"]:
        real = doc["route_length_km_real"].get(r["id"])
        if real and abs(real - r["distance_km"]) > 1e-9:
            r["distance_km"] = real
            changed += 1
    SIM_CITY.write_text(json.dumps(city, indent=2) + "\n", encoding="utf-8")
    print(f"\nupdated {changed} route distances in {SIM_CITY}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="print, write nothing")
    ap.add_argument("--apply-distances", action="store_true",
                    help="write real OSM walking distances into Simulation/city.json "
                         "(requires a human-anchored mapping)")
    args = ap.parse_args()
    result = build(report_only=args.report)
    if args.apply_distances and not args.report:
        apply_distances(result)
