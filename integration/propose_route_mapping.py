"""
PROPOSE a simulator-route -> OSM-edge mapping from the real pedestrian network.

This does NOT write route_mapping.json. integration/README.md marks that file
as requiring team agreement, so this emits a *proposal* for review:

    integration/route_mapping.proposal.json    edge lists per simulator route
    Simulation/city_osm.proposal.json          a city file with REAL lengths

Method: build an undirected graph from the Phase 2 edge registry (nodes are
shared path endpoints), take the largest connected component, pick
well-separated origin/destination nodes by farthest-point sampling, anchor each
to the nearest named OSM building, then find shortest paths plus penalised
alternatives so every origin-destination pair has several genuine route options
(the simulator needs >=2 alternatives per pair to have anything to choose
between).

Shade / drainage / crowding are NOT in OSM. They are emitted as explicit
placeholder values that a human must set - they are assumptions either way,
but this way they are visible assumptions.

Run:  python integration/propose_route_mapping.py
"""
from __future__ import annotations

import heapq
import json
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "phase2" / "scene" / "edge_registry.json"
OUT_MAP = ROOT / "integration" / "route_mapping.proposal.json"
OUT_CITY = ROOT / "Simulation" / "city_osm.proposal.json"

N_PAIRS = 8          # matches the current city's 8 home->destination pairs
ALTS_PER_PAIR = 2    # alternatives per pair (the simulator needs >= 2)
SNAP = 0.5           # metres; endpoints closer than this are the same node


def node_key(p):
    return (round(p[0] / SNAP), round(p[1] / SNAP))


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def build_graph(edges):
    adj = defaultdict(list)          # node -> [(other, edge_id, length)]
    pos, elen = {}, {}
    for eid, info in edges.items():
        pts = info.get("points") or []
        if len(pts) < 2:
            continue
        a, b = node_key(pts[0]), node_key(pts[-1])
        if a == b:
            continue
        L = sum(dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
        pos.setdefault(a, (pts[0][0], pts[0][1]))
        pos.setdefault(b, (pts[-1][0], pts[-1][1]))
        elen[eid] = L
        adj[a].append((b, eid, L))
        adj[b].append((a, eid, L))
    return adj, pos, elen


def components(adj):
    seen, comps = set(), []
    for start in adj:
        if start in seen:
            continue
        stack, comp = [start], []
        seen.add(start)
        while stack:
            n = stack.pop()
            comp.append(n)
            for m, _, _ in adj[n]:
                if m not in seen:
                    seen.add(m)
                    stack.append(m)
        comps.append(comp)
    return sorted(comps, key=len, reverse=True)


def dijkstra(adj, src, dst, penalty):
    """Shortest path src->dst; `penalty` multiplies the cost of listed edges."""
    pq, best, prev = [(0.0, src)], {src: 0.0}, {}
    while pq:
        d, n = heapq.heappop(pq)
        if n == dst:
            break
        if d > best.get(n, math.inf):
            continue
        for m, eid, L in adj[n]:
            nd = d + L * penalty.get(eid, 1.0)
            if nd < best.get(m, math.inf):
                best[m] = nd
                prev[m] = (n, eid)
                heapq.heappush(pq, (nd, m))
    if dst not in prev and dst != src:
        return None, 0.0
    path, n, length = [], dst, 0.0
    while n != src:
        n, eid = prev[n]
        path.append(eid)
        length += next(L for _, e, L in adj[n] if e == eid)
    return list(reversed(path)), length


def farthest_points(nodes, pos, k):
    """Greedy farthest-point sampling so endpoints are spread across the city."""
    chosen = [max(nodes, key=lambda n: pos[n][0] ** 2 + pos[n][1] ** 2)]
    while len(chosen) < k:
        chosen.append(max(nodes, key=lambda n: min(dist(pos[n], pos[c]) for c in chosen)))
    return chosen


def main() -> None:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    edges = data["edges"]
    adj, pos, elen = build_graph(edges)
    comps = components(adj)
    main_comp = set(comps[0])
    print(f"graph: {len(adj)} nodes, {len(elen)} edges")
    print(f"components: {len(comps)}; largest holds {len(main_comp)} nodes "
          f"({100*len(main_comp)/len(adj):.0f}% of the network)")

    anchors = farthest_points(sorted(main_comp), pos, N_PAIRS * 2)
    origins, dests = anchors[0::2], anchors[1::2]

    mapping, routes_out, rid = {}, [], 1
    for i, (o, d) in enumerate(zip(origins, dests), start=1):
        home, destination = f"N{i}A", f"N{i}B"
        penalty = {}
        for alt in range(ALTS_PER_PAIR):
            path, L = dijkstra(adj, o, d, penalty)
            if not path:
                break
            name = f"R{rid}"
            mapping[name] = path
            routes_out.append({
                "id": name, "start": home, "end": destination,
                "distance_km": round(L / 1000.0, 3),
                "edge_count": len(path),
                "shade": None, "drainage": None, "base_crowding": None,
                "capacity_pph": None, "greenery": None, "transit": None,
            })
            rid += 1
            # Push the next alternative onto genuinely different streets.
            for e in path:
                penalty[e] = penalty.get(e, 1.0) * 4.0

    OUT_MAP.write_text(json.dumps({
        "schema_version": "1.0",
        "city_id": data.get("city_id"),
        "status": "PROPOSAL - NOT AGREED. Review before copying to route_mapping.json.",
        "generated_by": "integration/propose_route_mapping.py",
        "method": (f"largest connected component; {N_PAIRS} farthest-point origin/destination "
                   f"pairs; shortest path + {ALTS_PER_PAIR-1} penalised alternative(s) each"),
        "simulator_routes": mapping,
    }, indent=2), encoding="utf-8")

    buildings = sorted({r["start"] for r in routes_out} | {r["end"] for r in routes_out})
    OUT_CITY.write_text(json.dumps({
        "schema_version": 1,
        "status": "PROPOSAL - distances are real OSM path lengths; all 0..1 "
                  "attributes are nulls a human must fill in. Do not simulate until filled.",
        "zones": [{"id": "Zone A", "drainage": None, "shade": None}],
        "buildings": [{"id": b, "name": f"Node {b}", "type": "unset", "zone": "Zone A",
                       "capacity": None, "cooling": None, "flood_exposure": None}
                      for b in buildings],
        "routes": routes_out,
    }, indent=2), encoding="utf-8")

    print(f"\nwrote {OUT_MAP.relative_to(ROOT)}  ({len(mapping)} routes)")
    print(f"wrote {OUT_CITY.relative_to(ROOT)}")
    print("\nproposed routes (real OSM lengths):")
    for r in routes_out:
        print(f"  {r['id']:4s} {r['start']}->{r['end']:5s} {r['distance_km']:6.3f} km "
              f"over {r['edge_count']:3d} edges")


if __name__ == "__main__":
    main()
