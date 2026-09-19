"""
Adapter: simulator output -> canonical v1 visualisation snapshot.

This is the only missing link in the pipeline. Everything downstream already
exists and is tested: `integration/load_snapshot.py` validates a snapshot and
renders it through the Phase 4-7 bridges. Nothing here touches the simulator or
the Omniverse scene - it only translates.

    Simulation/main.py
        -> urbantwin_demo_output.json      (simulator's own report, 0-100)
        -> THIS ADAPTER
        -> simulation_before.json / simulation_after.json  (canonical v1, 0-1)
        -> phase3/validate_mock_data.py
        -> integration/load_snapshot.py
        -> USD

What the adapter owns (per docs/INTEGRATION_CONTRACT.md):

  * the envelope: schema_version, city_id, run_id, sequence, timestamp,
    data_kind, label
  * normalisation, 0-100 -> 0-1
  * route -> edge id mapping
  * agent XYZ, which the simulator does not produce

AGENT POSITIONS ARE VISUAL ONLY
-------------------------------
The simulator decides which route each citizen takes; it does not emit
continuous coordinates. This interpolates a position along that route's real
edge geometry purely so something can be drawn. It never feeds back into the
simulation, and `urbantwin:positionSource` records it in the output.

EDGE MAPPING
------------
Two sources, in order of preference:

  1. the city file's own `osm_edges` on each route - present in
     `Simulation/city_osm.json`, because that city was built FROM the OSM graph.
     Nothing to agree: the geography is already real.
  2. `integration/route_mapping.json`, if the team has agreed one.

A snapshot built from a merely *proposed* mapping is labelled `data_kind: mock`,
so provisional geography cannot be presented as a real simulation run.

Run:
    python integration/export_snapshot.py                     # both states
    python integration/export_snapshot.py --state before
    python integration/export_snapshot.py --report Simulation/urbantwin_demo_output.json
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REGISTRY = ROOT / "phase2" / "scene" / "edge_registry.json"
DEFAULT_REPORT = ROOT / "Simulation" / "urbantwin_demo_output.json"
DEFAULT_CITY = ROOT / "Simulation" / "city_osm.json"
AGREED_MAPPING = HERE / "route_mapping.json"

AGENT_CAP = 500          # phase3 schema limit
FOOT_Z = 0.1             # agent z is foot elevation, metres


def unit(value, scale=100.0):
    """0-100 simulator metric -> 0-1, clamped. The schema rejects anything else."""
    try:
        return max(0.0, min(1.0, float(value) / scale))
    except (TypeError, ValueError):
        return 0.0


def load_edge_map(city_path: Path):
    """-> ({route_id: [edge ids]}, source_label, is_real_geography)"""
    if city_path.exists():
        city = json.loads(city_path.read_text(encoding="utf-8"))
        mapping = {r["id"]: r["osm_edges"] for r in city.get("routes", [])
                   if r.get("osm_edges")}
        if mapping:
            return mapping, f"{city_path.name}:osm_edges", True

    if AGREED_MAPPING.exists():
        doc = json.loads(AGREED_MAPPING.read_text(encoding="utf-8"))
        mapping = {k: v for k, v in doc.get("simulator_routes", {}).items() if v}
        agreed = doc.get("status") == "HUMAN_ANCHORED"
        return mapping, f"route_mapping.json ({doc.get('status')})", agreed

    return {}, "none", False


def polyline(points):
    pts = [(p[0], p[1]) for p in points]
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.dist(a, b))
    return pts, cum


def point_at(pts, cum, frac):
    if len(pts) == 1 or cum[-1] <= 0:
        return pts[0]
    target = max(0.0, min(1.0, frac)) * cum[-1]
    for i, (c0, c1) in enumerate(zip(cum, cum[1:])):
        if target <= c1:
            t = 0.0 if c1 == c0 else (target - c0) / (c1 - c0)
            (x0, y0), (x1, y1) = pts[i], pts[i + 1]
            return (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
    return pts[-1]


JOIN_TOLERANCE = 25.0       # metres; a wider gap means the chain is suspect


def oriented_route_points(edges, edge_ids):
    """
    One continuous polyline for a whole route.

    The edge registry stores each segment in its own arbitrary direction, so
    consecutive edges on a path frequently meet end-to-end, start-to-start, or
    start-to-end. Walking every edge from points[0] to points[-1] therefore
    makes an agent lurch backwards at half the joins.

    This flips each edge to match the direction of travel, producing a chain a
    pedestrian could actually follow.

    -> (points, worst_join_gap_m). Empty list if nothing usable.
    """
    usable = [e for e in edge_ids if e in edges]
    if not usable:
        return [], 0.0

    segments = [[(p[0], p[1]) for p in edges[e]["points"]] for e in usable]
    segments = [s for s in segments if len(s) >= 2]
    if not segments:
        return [], 0.0

    first = segments[0]
    if len(segments) > 1:
        nxt = segments[1]
        # Point the first edge so its far end is the one nearest the second edge.
        if min(math.dist(first[0], nxt[0]), math.dist(first[0], nxt[-1])) < \
           min(math.dist(first[-1], nxt[0]), math.dist(first[-1], nxt[-1])):
            first = first[::-1]

    chain = list(first)
    worst = 0.0
    for seg in segments[1:]:
        tail = chain[-1]
        d_fwd, d_rev = math.dist(tail, seg[0]), math.dist(tail, seg[-1])
        if d_rev < d_fwd:
            seg, gap = seg[::-1], d_rev
        else:
            gap = d_fwd
        worst = max(worst, gap)
        # Skip the duplicated join point so polyline() sees no zero-length span.
        chain.extend(seg[1:] if gap < 1e-6 else seg)
    return chain, worst


def position_on_route(edges, edge_ids, frac, chain_cache=None):
    """
    Position at `frac` (0..1) along a route's oriented geometry. Visual only.

    `chain_cache` keyed by the route's edge tuple avoids re-orienting the same
    route once per agent per frame.
    """
    key = tuple(edge_ids)
    if chain_cache is not None and key in chain_cache:
        chain, cum = chain_cache[key]
    else:
        pts, _worst = oriented_route_points(edges, edge_ids)
        if not pts:
            if chain_cache is not None:
                chain_cache[key] = ([], [0.0])
            return None, None
        chain, cum = polyline(pts)
        if chain_cache is not None:
            chain_cache[key] = (chain, cum)
    if not chain:
        return None, None

    x, y = point_at(chain, cum, max(0.0, min(1.0, frac)))
    current = next((e for e in edge_ids if e in edges), None)
    return (x, y), current


INTERVENTION_TYPES = {
    "shade_boost": "ADD_SHADE",
    "drainage_boost": None,                    # no schema type; reported, not drawn
    "route_capacity_boost": "INCREASE_PATH_CAPACITY",
}


def departure_phase(agent_id: str) -> float:
    """Stable 0-1 offset from the id, so agents do not all set off in lockstep."""
    h = 2166136261
    for ch in str(agent_id):
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return (h % 10000) / 10000.0


def build(report: dict, state: str, edges, edge_map, map_source, real_geometry,
          city_id: str, run_id: str, sequence: int, elapsed: float = 0.0,
          animate: bool = False) -> dict:
    """
    One canonical snapshot.

    With `animate`, each agent is advanced along its own route by `elapsed`
    seconds at that citizen's own pace: the simulator's `travel_minutes` is how
    long THAT person takes on the route THEY chose, which in turn comes from
    their survey-calibrated walking speed. Trips wrap, so corridors stay
    populated instead of emptying after one pass.

    Positions between snapshots are interpolated for display only; the simulator
    decides the route and the duration, not the coordinates.
    """
    snap = report[state]
    metrics = snap["metrics"]
    inputs = snap["inputs"]

    # --- edges ------------------------------------------------------------
    route_rows = {r["id"]: r for r in snap["routes"]}
    heat_by_route = {}
    for c in snap["citizens"]:
        heat_by_route.setdefault(c["route"], []).append(c["heat_exposure"])

    out_edges, unmapped = {}, []
    for rid, row in route_rows.items():
        mapped = edge_map.get(rid)
        if not mapped:
            unmapped.append(rid)
            continue
        crowding = unit(row["crowding"])
        walkers = heat_by_route.get(rid, [])
        heat = unit(sum(walkers) / len(walkers)) if walkers else unit(metrics["heat_stress"])
        for eid in mapped:
            if eid not in edges:
                continue
            prev = out_edges.get(eid)
            # An edge shared by several routes takes the worst value it sees.
            out_edges[eid] = {
                "crowding": max(crowding, prev["crowding"]) if prev else crowding,
                "heat_exposure": max(heat, prev["heat_exposure"]) if prev else heat,
            }

    # --- agents -----------------------------------------------------------
    citizens = snap["citizens"][:AGENT_CAP]
    agents, unplaced = [], 0
    chain_cache = {}
    for i, c in enumerate(citizens):
        mapped = edge_map.get(c["route"]) or []
        if animate:
            # travel_minutes is this citizen's own trip time, from their
            # calibrated walking speed over their chosen route.
            trip_s = max(float(c.get("travel_minutes", 5.0)), 0.1) * 60.0
            # Everyone is already part-way through their trip when the window
            # opens, so the streets are populated from frame 0. Progress only
            # increases and clamps at 1.0: they arrive and stop, rather than
            # teleporting back to their origin the way a cyclic offset did.
            frac = min(1.0, departure_phase(c["id"]) + elapsed / trip_s)
        else:
            frac = (i + 0.5) / max(len(citizens), 1)
        pos, _current = position_on_route(edges, mapped, frac, chain_cache)
        if pos is None:
            unplaced += 1
            continue
        agents.append({
            "id": c["id"],
            "x": round(pos[0], 3), "y": round(pos[1], 3), "z": FOOT_Z,
            "route": [e for e in mapped if e in edges],
            # Comfort is 0-100 and higher is better; stress is its complement.
            "stress": round(unit(100.0 - c["comfort"]), 4),
            "heat_exposure": round(unit(c["heat_exposure"]), 4),
        })

    # --- interventions ------------------------------------------------------
    interventions = []
    applied = report.get("intervention", {}) if state == "after" else {}
    busiest = sorted(out_edges, key=lambda e: out_edges[e]["crowding"], reverse=True)
    for n, (key, amount) in enumerate(sorted(applied.items()), start=1):
        kind = INTERVENTION_TYPES.get(key)
        if not kind or not busiest:
            continue
        interventions.append({
            "id": f"proposal_{n:03d}",
            "type": kind,
            "target": busiest[0] if kind == "ADD_SHADE" else busiest[min(1, len(busiest) - 1)],
            "amount": unit(amount, 1.0),
        })

    mock = not real_geometry
    label = ("DEMO / MOCK SIMULATION DATA - provisional route geography"
             if mock else
             f"UrbanTwin simulation - {state} - {inputs['temperature']}C, "
             f"{inputs['population']:,} population equivalent")

    return {
        "schema_version": "1.0",
        "city_id": city_id,
        "run_id": run_id,
        "sequence": sequence,
        "timestamp": float(sequence) * 10.0,
        "data_kind": "mock" if mock else "simulation",
        "label": label[:256],
        "scenario": {
            "temperature_c": float(inputs["temperature"]),
            "population_equivalent": int(inputs["population"]),
        },
        "agents": agents,
        "edges": out_edges,
        "interventions": interventions,
    }, {"unmapped_routes": unmapped, "unplaced_agents": unplaced,
        "map_source": map_source, "real_geometry": real_geometry}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--city", type=Path, default=DEFAULT_CITY)
    ap.add_argument("--state", choices=["before", "after", "both"], default="both")
    ap.add_argument("--run-id", default="urbantwin-sim-001")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "data")
    ap.add_argument("--frames", type=int, default=1,
                    help="emit N snapshots stepping through time so agents can "
                         "be animated (default 1 = a single still snapshot)")
    ap.add_argument("--duration", type=float, default=60.0,
                    help="seconds of simulated walking the frames span")
    args = ap.parse_args()
    if args.frames < 1:
        raise SystemExit("--frames must be >= 1")

    report = json.loads(args.report.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    edges = registry["edges"]
    edge_map, source, real = load_edge_map(args.city)

    print(f"[SIM]    {args.report.name}: {len(report['before']['citizens'])} citizens, "
          f"{len(report['before']['routes'])} routes")
    print(f"[BRIDGE] edge mapping from {source} -> {len(edge_map)} routes mapped")
    if not edge_map:
        raise SystemExit(
            "no route->edge mapping available.\n"
            "  Build a real-geography city:  python phase9/build_city_from_osm.py\n"
            "  or agree integration/route_mapping.json from the proposal.")
    if not real:
        print("[BRIDGE] mapping is PROVISIONAL -> snapshots labelled data_kind=mock")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    states = ["before", "after"] if args.state == "both" else [args.state]
    animate = args.frames > 1
    written = []

    for state in states:
        step = args.duration / args.frames if animate else 0.0
        frames = []
        for k in range(args.frames):
            elapsed = k * step
            snap, info = build(report, state, edges, edge_map, source, real,
                               registry["city_id"], f"{args.run_id}-{state}",
                               k, elapsed, animate)
            snap["timestamp"] = round(elapsed, 4)
            name = (f"simulation_{state}_{k:03d}.json" if animate
                    else f"simulation_{state}.json")
            out = args.out_dir / name
            out.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
            frames.append(out)
            if k == 0:
                print(f"[BRIDGE] {state:7s} {len(snap['agents']):3d} agents, "
                      f"{len(snap['edges']):4d} edges, "
                      f"{len(snap['interventions'])} intervention(s)")
                if info["unmapped_routes"]:
                    print(f"[BRIDGE]   WARNING {len(info['unmapped_routes'])} routes "
                          f"had no edge mapping: {info['unmapped_routes'][:5]}")
                if info["unplaced_agents"]:
                    print(f"[BRIDGE]   WARNING {info['unplaced_agents']} agents could "
                          "not be positioned")
        written.extend(frames)
        if animate:
            print(f"[BRIDGE] {state:7s} {len(frames)} frames over {args.duration:.0f}s "
                  f"-> {frames[0].name} .. {frames[-1].name}")

    glob = (f"data\\simulation_{states[0]}_*.json" if animate
            else str(written[0]))
    print("\nValidate:  python phase3\\validate_mock_data.py " + glob)
    if animate:
        print("Animate:   python phase9\\agents_instancer.py " + glob
              + " --metric heat_exposure")
    else:
        print("Render:    python integration\\load_snapshot.py " + str(written[0]))


if __name__ == "__main__":
    main()
