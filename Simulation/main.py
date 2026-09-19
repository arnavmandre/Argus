"""
UrbanTwin AI — Person 1 Simulation Engine
24-hour hackathon MVP

Pure Python, deterministic, transparent heuristics.
No Omniverse dependency.

Core pipeline:
Temperature + Humidity + Rainfall + Population
    -> environment metrics (zones + buildings)
    -> synthetic citizens (loaded from citizens.json)
    -> route choice (home building -> destination building)
    -> human-centric metrics
    -> Urban Advisor
    -> interventions
    -> rerun / compare

What changed vs. the first version
    * Buildings live inside zones. They are route endpoints, have their own
      heat / flood / crowding numbers, and feed the headline metrics and the
      Advisor.
    * Citizens are NOT generated in code. They are read from citizens.json
      (see load_citizens). Each citizen has a home building and a destination
      building and chooses among the routes that connect them.
    * Accessibility has been removed from the model entirely (no metric, no
      zone/building/route/citizen field, no route penalty, no intervention).
      HEI is re-weighted without it.

Prototype metrics are intentionally heuristic and are NOT medical,
meteorological, hydrological, or real-world predictive measurements.
"""

from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
from math import exp
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import json
import sys


# ---------------------------------------------------------------------------
# Tunable constants (kept in one place so they are easy to explain / tweak)
# ---------------------------------------------------------------------------

DEFAULT_CITIZENS_PATH = Path(__file__).with_name("citizens.json")

# Share of the city population that makes a trip in the simulated peak window.
# Building "arrivals" = population * PEAK_TRIP_SHARE * (share of citizens heading there).
PEAK_TRIP_SHARE = 0.15

# How much building-entrance crowding counts in the headline crowding metric
# (the rest comes from corridor/route crowding).
BUILDING_CROWD_WEIGHT = 0.30

# A building is reported as a "problem building" when a signal passes these.
BUILDING_ISSUE_THRESHOLDS = {"heat": 50.0, "rain": 40.0, "crowd": 70.0}


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def norm(x: float, lo: float, hi: float) -> float:
    """Normalize to 0..1, safely."""
    if hi <= lo:
        raise ValueError("Invalid normalization range")
    return clamp((x - lo) / (hi - lo), 0.0, 1.0)


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + exp(-x))


def mean(values) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


# ---------------------------------------------------------------------------
# City model
# ---------------------------------------------------------------------------

@dataclass
class Zone:
    id: str
    drainage: float       # 0 = poor, 1 = excellent
    shade: float          # 0 = no shade, 1 = highly shaded


@dataclass
class Building:
    """A place inside a zone. Also a route endpoint (home or destination)."""
    id: str
    name: str
    type: str              # residential | transit_hub | office | school | hospital | market | ...
    zone: str              # id of the Zone this building sits in
    capacity: int          # people its entrances/surroundings can absorb in the peak window
                           # (0 is fine for buildings that are never a destination)
    cooling: float         # 0 = no indoor refuge / AC ... 1 = fully climate-controlled
    flood_exposure: float  # 0 = raised / protected ... 1 = ground floor in a flood path


@dataclass
class Route:
    id: str
    start: str             # building id
    end: str               # building id
    distance_km: float
    shade: float
    drainage: float
    base_crowding: float
    transit: float = 0.0
    via_zones: Tuple[str, ...] = ()   # zones the route passes through (for reporting/visualisation)


@dataclass
class Citizen:
    id: str
    archetype: str
    home: str              # building id
    destination: str       # building id
    heat_tolerance: float
    rain_tolerance: float
    crowd_tolerance: float
    walking_speed_kmh: float
    green_preference: float
    transit_preference: float
    weight: float = 1.0    # relative share of the population this agent stands for


DEFAULT_CITY = {
    "zones": [
        Zone("Zone A", drainage=0.90, shade=0.35),
        Zone("Zone B", drainage=0.60, shade=0.55),
        Zone("Zone C", drainage=0.25, shade=0.20),
    ],
    "buildings": [
        #         id     name                     type           zone      cap   cool  flood
        Building("H1",   "Riverside Homes",       "residential", "Zone C",    0, 0.25, 0.85),
        Building("H2",   "Old Town Apartments",   "residential", "Zone B",    0, 0.35, 0.50),
        Building("H3",   "Garden Court",          "residential", "Zone A",    0, 0.60, 0.15),
        Building("T1",   "Central Transit Hub",   "transit_hub", "Zone A", 3200, 0.40, 0.35),
        Building("W1",   "Business Park Offices", "office",      "Zone A", 4500, 0.90, 0.20),
        Building("S1",   "City College",          "school",      "Zone B", 3500, 0.55, 0.40),
        Building("HOS1", "City General Hospital", "hospital",    "Zone B", 2400, 0.85, 0.30),
        Building("M1",   "Market Square",         "market",      "Zone C", 5000, 0.15, 0.80),
    ],
    "routes": [
        #      id     from  to     km   shade drain crowd transit via_zones
        # Riverside Homes (Zone C) -> Central Transit Hub (Zone A): the original 4 corridors
        Route("R1",  "H1", "T1",   1.2, 0.20, 0.90, 0.35, 1.00, ("Zone C", "Zone A")),
        Route("R2",  "H1", "T1",   1.5, 0.75, 0.60, 0.25, 0.70, ("Zone C", "Zone B", "Zone A")),
        Route("R3",  "H1", "T1",   1.0, 0.10, 0.25, 0.45, 0.35, ("Zone C",)),
        Route("R4",  "H1", "T1",   1.8, 0.85, 0.85, 0.15, 0.40, ("Zone C", "Zone B", "Zone A")),
        # Riverside Homes -> Market Square (both Zone C)
        Route("R5",  "H1", "M1",   0.8, 0.15, 0.25, 0.40, 0.10, ("Zone C",)),
        Route("R6",  "H1", "M1",   1.3, 0.60, 0.80, 0.25, 0.20, ("Zone C",)),
        # Riverside Homes -> City General Hospital
        Route("R7",  "H1", "HOS1", 2.0, 0.20, 0.30, 0.35, 0.30, ("Zone C", "Zone B")),
        Route("R8",  "H1", "HOS1", 2.6, 0.55, 0.85, 0.20, 0.50, ("Zone C", "Zone A", "Zone B")),
        # Old Town Apartments (Zone B) -> City General Hospital
        Route("R9",  "H2", "HOS1", 0.9, 0.30, 0.60, 0.40, 0.30, ("Zone B",)),
        Route("R10", "H2", "HOS1", 1.2, 0.80, 0.60, 0.20, 0.20, ("Zone B",)),
        # Old Town Apartments -> City College
        Route("R11", "H2", "S1",   0.7, 0.25, 0.65, 0.45, 0.45, ("Zone B",)),
        Route("R12", "H2", "S1",   1.0, 0.80, 0.60, 0.20, 0.25, ("Zone B",)),
        # Old Town Apartments -> Business Park Offices
        Route("R13", "H2", "W1",   1.6, 0.15, 0.60, 0.40, 0.60, ("Zone B", "Zone A")),
        Route("R14", "H2", "W1",   2.0, 0.60, 0.90, 0.20, 0.55, ("Zone B", "Zone A")),
        # Garden Court (Zone A) -> Business Park Offices
        Route("R15", "H3", "W1",   0.8, 0.30, 0.90, 0.35, 0.50, ("Zone A",)),
        Route("R16", "H3", "W1",   1.1, 0.80, 0.90, 0.15, 0.30, ("Zone A",)),
        # Garden Court -> Central Transit Hub
        Route("R17", "H3", "T1",   0.6, 0.25, 0.90, 0.50, 1.00, ("Zone A",)),
        Route("R18", "H3", "T1",   0.9, 0.70, 0.90, 0.25, 0.70, ("Zone A",)),
    ],
}


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_city(city: Dict) -> None:
    """Fail early, with a readable message, if the city data is inconsistent."""
    for key in ("zones", "buildings", "routes"):
        if not city.get(key):
            raise ValueError(f"city_state must contain a non-empty '{key}' list")

    problems: List[str] = []
    zone_ids = {z.id for z in city["zones"]}
    building_ids = [b.id for b in city["buildings"]]

    if len(set(building_ids)) != len(building_ids):
        problems.append("duplicate building ids")

    for b in city["buildings"]:
        if b.zone not in zone_ids:
            problems.append(f"building {b.id} is in unknown zone '{b.zone}'")
    for r in city["routes"]:
        for end in (r.start, r.end):
            if end not in building_ids:
                problems.append(f"route {r.id} endpoint '{end}' is not a building")
        for zid in r.via_zones:
            if zid not in zone_ids:
                problems.append(f"route {r.id} passes through unknown zone '{zid}'")

    if problems:
        raise ValueError("Invalid city_state:\n  - " + "\n  - ".join(problems))


def routes_between(routes: List[Route], a: str, b: str) -> List[Route]:
    """Candidate routes joining two buildings (either direction)."""
    return [r for r in routes if {r.start, r.end} == {a, b}]


def validate_citizens(citizens: List[Citizen], city: Dict) -> None:
    """Every citizen must live/go somewhere that exists AND have a route between them."""
    if not citizens:
        raise ValueError("citizens list is empty")

    building_ids = {b.id for b in city["buildings"]}
    problems: List[str] = []
    missing_pairs = set()

    for c in citizens:
        ok = True
        for role, bid in (("home", c.home), ("destination", c.destination)):
            if bid not in building_ids:
                problems.append(f"{c.id}: {role} '{bid}' is not a building in the city")
                ok = False
        if ok and not routes_between(city["routes"], c.home, c.destination):
            missing_pairs.add(tuple(sorted((c.home, c.destination))))

    for a, b in sorted(missing_pairs):
        problems.append(f"no route connects {a} and {b} (needed by at least one citizen)")

    if problems:
        raise ValueError("Citizens do not match the city:\n  - " + "\n  - ".join(problems))


# ---------------------------------------------------------------------------
# Citizen import (JSON)
# ---------------------------------------------------------------------------

_CITIZEN_UNIT_FIELDS = (
    "heat_tolerance", "rain_tolerance", "crowd_tolerance",
    "green_preference", "transit_preference",
)
_CITIZEN_REQUIRED = (
    "id", "archetype", "home", "destination", *_CITIZEN_UNIT_FIELDS, "walking_speed_kmh",
)


def load_citizens(path: Union[str, Path] = DEFAULT_CITIZENS_PATH) -> List[Citizen]:
    """
    Read synthetic citizens from a JSON file.

    Accepted shapes:
        {"citizens": [ {...}, {...} ]}     (extra top-level keys are ignored)
        [ {...}, {...} ]

    Each citizen needs: id, archetype, home, destination, heat_tolerance,
    rain_tolerance, crowd_tolerance, walking_speed_kmh, green_preference,
    transit_preference.  Optional: weight (default 1.0).
    Unknown keys are ignored, so an older file that still contains
    'accessibility_need' loads without changes.

    Field-level problems are collected and reported together. Whether the
    home/destination buildings and routes exist is checked against the city
    inside simulate().
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Citizen file not found: {path}")

    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    records = data.get("citizens") if isinstance(data, dict) else data
    if not isinstance(records, list) or not records:
        raise ValueError(f"{path}: expected a non-empty list under 'citizens'")

    citizens: List[Citizen] = []
    problems: List[str] = []
    seen = set()

    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            problems.append(f"entry #{i}: not a JSON object")
            continue
        label = str(rec.get("id", f"#{i}"))

        missing = [k for k in _CITIZEN_REQUIRED if k not in rec]
        if missing:
            problems.append(f"{label}: missing {missing}")
            continue

        rec_problems: List[str] = []
        if label in seen:
            rec_problems.append("duplicate id")
        seen.add(label)

        bad = [
            k for k in _CITIZEN_UNIT_FIELDS
            if not isinstance(rec[k], (int, float)) or not 0.0 <= rec[k] <= 1.0
        ]
        if bad:
            rec_problems.append(f"{bad} must be numbers in 0..1")
        if not isinstance(rec["walking_speed_kmh"], (int, float)) or rec["walking_speed_kmh"] <= 0:
            rec_problems.append("walking_speed_kmh must be > 0")
        weight = rec.get("weight", 1.0)
        if not isinstance(weight, (int, float)) or weight <= 0:
            rec_problems.append("weight must be > 0")

        if rec_problems:
            problems.extend(f"{label}: {p}" for p in rec_problems)
            continue

        citizens.append(Citizen(
            id=label,
            archetype=str(rec["archetype"]),
            home=str(rec["home"]),
            destination=str(rec["destination"]),
            heat_tolerance=float(rec["heat_tolerance"]),
            rain_tolerance=float(rec["rain_tolerance"]),
            crowd_tolerance=float(rec["crowd_tolerance"]),
            walking_speed_kmh=float(rec["walking_speed_kmh"]),
            green_preference=float(rec["green_preference"]),
            transit_preference=float(rec["transit_preference"]),
            weight=float(weight),
        ))

    if problems:
        raise ValueError(f"{path}: invalid citizen data:\n  - " + "\n  - ".join(problems))
    return citizens


# ---------------------------------------------------------------------------
# Environment model
# ---------------------------------------------------------------------------

def heat_stress(temperature: float, humidity: float) -> float:
    """
    Transparent prototype heat/humidity model.

    Temperature and humidity are normalized, with an interaction term so
    high temperature + high humidity is disproportionately stressful.
    """
    t = norm(temperature, 20, 45)
    h = norm(humidity, 20, 90)

    raw = 0.65 * t + 0.20 * h + 0.15 * t * h
    return clamp(raw * 100)


def rainfall_intensity(rainfall: float) -> float:
    return norm(rainfall, 0, 100)


def zone_rain_impact(rainfall: float, drainage: float) -> float:
    """
    High rain + poor drainage => high impact.
    """
    rain = rainfall_intensity(rainfall)
    vulnerability = 1.0 - clamp(drainage, 0, 1)
    # Slight nonlinear amplification for severe rainfall.
    raw = 0.72 * rain * vulnerability + 0.28 * (rain ** 1.5) * vulnerability
    return clamp(raw * 100)


def crowding_score(population: int, base_crowding: float = 0.50) -> float:
    """
    Population is scaled against 50K baseline.
    """
    population_factor = norm(population, 25_000, 100_000)
    return clamp((0.25 + 0.75 * population_factor) * base_crowding * 100 / 0.50)


def building_heat_exposure(hs: float, zone: Zone, building: Building) -> float:
    """
    Heat felt at a building's entrance/surroundings.
    City heat stress, reduced by the zone's shade and the building's indoor refuge.
    """
    return clamp(hs * (1 - zone.shade) * (1 - 0.5 * building.cooling))


def building_rain_impact(zone_rain: float, building: Building) -> float:
    """
    Zone rain impact scaled by how exposed the building itself is to flooding.
    flood_exposure = 0.5 leaves the zone value unchanged; 1.0 -> x1.5; 0.0 -> x0.5.
    """
    return clamp(zone_rain * (0.5 + building.flood_exposure))


def building_crowding(arrivals: float, capacity: float) -> float:
    """Peak-window arrivals as a percentage of what the building can absorb (capped at 100)."""
    if arrivals <= 0:
        return 0.0
    if capacity <= 0:
        return 100.0
    return clamp(100.0 * arrivals / capacity)


# ---------------------------------------------------------------------------
# Route choice
# ---------------------------------------------------------------------------

def route_cost(
    route: Route,
    citizen: Citizen,
    temperature: float,
    humidity: float,
    rainfall: float,
    population: int,
    shade_boost: float = 0.0,
    drainage_boost: float = 0.0,
    route_capacity_boost: float = 0.0,
) -> Dict[str, float]:

    hs = heat_stress(temperature, humidity) / 100
    rain = rainfall_intensity(rainfall)

    effective_shade = clamp(route.shade + shade_boost)
    effective_drainage = clamp(route.drainage + drainage_boost)

    # Population drives corridor crowding.
    pop_factor = 0.55 + 0.75 * norm(population, 25_000, 100_000)
    effective_crowd = clamp(route.base_crowding * pop_factor / (1 + route_capacity_boost))

    heat_penalty = hs * (1 - effective_shade) * (1 - citizen.heat_tolerance) * 8.0
    rain_penalty = rain * (1 - effective_drainage) * (1 - citizen.rain_tolerance) * 8.0
    crowd_penalty = effective_crowd * (1 - citizen.crowd_tolerance) * 6.0
    transit_bonus = route.transit * citizen.transit_preference * 1.5
    green_bonus = effective_shade * citizen.green_preference * 1.2

    distance_cost = route.distance_km * 2.0

    total = (
        distance_cost
        + heat_penalty
        + rain_penalty
        + crowd_penalty
        - transit_bonus
        - green_bonus
    )

    return {
        "total": total,
        "distance": distance_cost,
        "heat": heat_penalty,
        "rain": rain_penalty,
        "crowd": crowd_penalty,
    }


def choose_route(
    citizen: Citizen,
    routes: List[Route],
    temperature: float,
    humidity: float,
    rainfall: float,
    population: int,
    interventions: Optional[Dict] = None,
) -> Tuple[str, Dict[str, float]]:
    """Pick the cheapest route among `routes` (already filtered to the citizen's home->destination)."""

    interventions = interventions or {}
    costs = {}

    for r in routes:
        # Target interventions can be attached globally for the MVP.
        costs[r.id] = route_cost(
            r, citizen, temperature, humidity, rainfall, population,
            shade_boost=interventions.get("shade_boost", 0.0),
            drainage_boost=interventions.get("drainage_boost", 0.0),
            route_capacity_boost=interventions.get("route_capacity_boost", 0.0),
        )

    chosen = min(costs, key=lambda rid: costs[rid]["total"])
    return chosen, costs[chosen]


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def simulate(
    temperature: float,
    humidity: float,
    rainfall: float,
    population: int,
    city_state: Optional[Dict] = None,
    citizens: Union[None, str, Path, List[Citizen]] = None,
    interventions: Optional[Dict] = None,
) -> Dict:
    """
    citizens: None            -> load DEFAULT_CITIZENS_PATH (citizens.json next to this file)
              str / Path      -> load that JSON file
              List[Citizen]   -> use as-is
    The run is fully deterministic (no randomness anywhere).
    """

    if not (20 <= temperature <= 45):
        raise ValueError("temperature must be between 20 and 45 °C")
    if not (20 <= humidity <= 90):
        raise ValueError("humidity must be between 20 and 90 %")
    if not (0 <= rainfall <= 100):
        raise ValueError("rainfall must be between 0 and 100 mm")
    if not (25_000 <= population <= 100_000):
        raise ValueError("population must be between 25,000 and 100,000")

    interventions = interventions or {}
    city = deepcopy(city_state or DEFAULT_CITY)
    validate_city(city)

    if citizens is None or isinstance(citizens, (str, Path)):
        citizens = load_citizens(citizens or DEFAULT_CITIZENS_PATH)
    validate_citizens(citizens, city)

    # Apply city-level intervention changes (buildings inherit them through their zone).
    for z in city["zones"]:
        if interventions.get("shade_boost"):
            z.shade = clamp(z.shade + interventions["shade_boost"], 0.0, 1.0)
        if interventions.get("drainage_boost"):
            z.drainage = clamp(z.drainage + interventions["drainage_boost"], 0.0, 1.0)

    zone_by_id = {z.id: z for z in city["zones"]}
    building_by_id = {b.id: b for b in city["buildings"]}

    hs = heat_stress(temperature, humidity)

    zone_rain = {
        z.id: zone_rain_impact(rainfall, z.drainage)
        for z in city["zones"]
    }

    # --- Demand: how many real people each building / route stands for ------
    total_weight = sum(c.weight for c in citizens)
    people_per_weight = population / total_weight

    residents = {b.id: 0.0 for b in city["buildings"]}
    arrivals = {b.id: 0.0 for b in city["buildings"]}
    for c in citizens:
        represented = c.weight * people_per_weight
        residents[c.home] += represented
        arrivals[c.destination] += represented * PEAK_TRIP_SHARE

    # --- Building-level signals ---------------------------------------------
    bmetrics = {}
    for b in city["buildings"]:
        z = zone_by_id[b.zone]
        bmetrics[b.id] = {
            "heat": building_heat_exposure(hs, z, b),
            "rain": building_rain_impact(zone_rain[z.id], b),
            "crowd": building_crowding(arrivals[b.id], b.capacity),
        }

    # City rain impact = average building rain impact
    # (zone drainage x building flood exposure).
    rain = mean(m["rain"] for m in bmetrics.values())

    # Route-level crowding and population scaling.
    route_crowding = {}
    for r in city["routes"]:
        route_crowding[r.id] = crowding_score(population, r.base_crowding)
    route_crowd = mean(route_crowding.values())

    # Entrance crowding: average over buildings that people actually travel to.
    destination_ids = [bid for bid, a in arrivals.items() if a > 0]
    building_crowd = mean(bmetrics[bid]["crowd"] for bid in destination_ids)

    # Interventions directly reduce exposure/stress in the prototype.
    effective_heat = clamp(hs * (1 - 0.30 * interventions.get("shade_boost", 0)))
    effective_rain = clamp(rain * (1 - 0.65 * interventions.get("drainage_boost", 0)))
    # Alternative pedestrian routes relieve corridors, not building entrances.
    effective_route_crowd = clamp(
        route_crowd / (1 + 1.15 * interventions.get("route_capacity_boost", 0))
    )
    effective_crowd = clamp(
        (1 - BUILDING_CROWD_WEIGHT) * effective_route_crowd
        + BUILDING_CROWD_WEIGHT * building_crowd
    )

    # --- Citizens choose routes ---------------------------------------------
    citizen_results = []
    route_counts = {r.id: 0 for r in city["routes"]}
    route_people = {r.id: 0.0 for r in city["routes"]}

    for c in citizens:
        candidates = routes_between(city["routes"], c.home, c.destination)
        chosen, costs = choose_route(
            c, candidates, temperature, humidity, rainfall, population, interventions
        )
        route_counts[chosen] += 1
        route_people[chosen] += c.weight * people_per_weight * PEAK_TRIP_SHARE

        # Individual exposure is based on chosen route.
        route = next(r for r in candidates if r.id == chosen)
        dest = building_by_id[c.destination]
        dest_crowd = bmetrics[dest.id]["crowd"]

        local_heat = effective_heat * (1 - clamp(route.shade + interventions.get("shade_boost", 0), 0.0, 1.0))
        local_rain = effective_rain * (1 - clamp(route.drainage + interventions.get("drainage_boost", 0), 0.0, 1.0))
        local_crowd = effective_route_crowd * (0.65 + 0.70 * route.base_crowding)

        personal_comfort = clamp(
            100
            - 0.52 * local_heat * (1 - c.heat_tolerance)
            - 0.24 * local_rain * (1 - c.rain_tolerance)
            - 0.24 * local_crowd * (1 - c.crowd_tolerance)
            # Arrival end of the trip: crowded entrance.
            - 0.08 * dest_crowd * (1 - c.crowd_tolerance)
        )

        citizen_results.append({
            "id": c.id,
            "archetype": c.archetype,
            "home": c.home,
            "destination": c.destination,
            "route": chosen,
            "heat_exposure": round(local_heat, 2),
            "rain_exposure": round(local_rain, 2),
            "crowd_exposure": round(local_crowd, 2),
            "destination_crowding": round(dest_crowd, 2),
            "comfort": round(personal_comfort, 2),
            "route_cost": round(costs["total"], 2),
        })

    # --- Human-centric aggregate metrics ------------------------------------
    safety = clamp(
        100
        - 0.65 * effective_rain
        - 0.20 * effective_heat
        - 0.15 * effective_crowd
    )

    mobility = clamp(
        100
        - 0.35 * effective_crowd
        - 0.35 * effective_rain
        - 0.15 * effective_heat
    )

    comfort = clamp(
        100
        - 0.48 * effective_heat
        - 0.22 * effective_rain
        - 0.20 * effective_crowd
    )

    # Normalize the original conceptual HEI into a readable 0..100 score.
    # Higher comfort/safety/mobility is better.
    # Heat/crowd are penalties.
    hei = clamp(
        0.40 * comfort
        + 0.20 * safety
        + 0.25 * mobility
        + 0.15 * (100 - effective_heat)
        - 0.10 * effective_crowd
    )

    # --- Problem spotting for the Advisor -----------------------------------
    worst_zone = max(zone_rain, key=zone_rain.get)

    problem_zones = [worst_zone]
    if effective_heat >= 60:
        problem_zones.append("Heat-exposed pedestrian corridors")
    if effective_crowd >= 65:
        problem_zones.append("High-crowding corridors")

    building_rows = []
    for b in city["buildings"]:
        m = bmetrics[b.id]
        issues = []
        if m["rain"] >= BUILDING_ISSUE_THRESHOLDS["rain"]:
            issues.append("flooding")
        if m["crowd"] >= BUILDING_ISSUE_THRESHOLDS["crowd"]:
            issues.append("overcrowding")
        if m["heat"] >= BUILDING_ISSUE_THRESHOLDS["heat"]:
            issues.append("heat exposure")
        building_rows.append({
            "id": b.id,
            "name": b.name,
            "type": b.type,
            "zone": b.zone,
            "capacity": b.capacity,
            "residents": round(residents[b.id]),
            "peak_arrivals": round(arrivals[b.id]),
            "heat_exposure": round(m["heat"], 2),
            "rain_impact": round(m["rain"], 2),
            "crowding": round(m["crowd"], 2),
            "stress": round(max(m["heat"], m["rain"], m["crowd"]), 2),
            "issues": issues,
        })

    problem_buildings = sorted(
        (
            {"id": r["id"], "name": r["name"], "zone": r["zone"],
             "issues": r["issues"], "severity": r["stress"]}
            for r in building_rows if r["issues"]
        ),
        key=lambda r: r["severity"], reverse=True,
    )

    worst_routes = sorted(route_crowding, key=route_crowding.get, reverse=True)[:3]
    route_by_id = {r.id: r for r in city["routes"]}
    problem_routes = [
        {"id": rid, "from": route_by_id[rid].start, "to": route_by_id[rid].end,
         "via_zones": list(route_by_id[rid].via_zones),
         "crowding": round(route_crowding[rid], 2)}
        for rid in worst_routes
    ]

    return {
        "inputs": {
            "temperature": temperature,
            "humidity": humidity,
            "rainfall": rainfall,
            "population": population,
        },
        "metrics": {
            "heat_stress": round(effective_heat, 2),
            "rain_impact": round(effective_rain, 2),
            "crowding": round(effective_crowd, 2),
            "safety": round(safety, 2),
            "mobility": round(mobility, 2),
            "comfort": round(comfort, 2),
            "human_experience_index": round(hei, 2),
        },
        "zones": [
            {
                "id": z.id,
                "drainage": round(z.drainage, 2),
                "shade": round(z.shade, 2),
                "rain_impact": round(zone_rain[z.id], 2),
                "buildings": [b.id for b in city["buildings"] if b.zone == z.id],
            }
            for z in city["zones"]
        ],
        "buildings": building_rows,
        "routes": [
            {
                "id": r.id,
                "from": r.start,
                "to": r.end,
                "via_zones": list(r.via_zones),
                "crowding": round(route_crowding[r.id], 2),
                "chosen_by_agents": route_counts[r.id],
                "peak_pedestrians": round(route_people[r.id]),
            }
            for r in city["routes"]
        ],
        "citizens": citizen_results,
        "problem_zones": problem_zones,
        "problem_buildings": problem_buildings,
        "problem_routes": problem_routes,
        "interventions": interventions,
    }


# ---------------------------------------------------------------------------
# AI Urban Advisor
# ---------------------------------------------------------------------------

def _worst_buildings(result: Dict, metric: str, n: int = 2) -> List[Dict]:
    rows = [b for b in result["buildings"] if b[metric] > 0]
    return sorted(rows, key=lambda b: b[metric], reverse=True)[:n]


def _label(buildings: List[Dict]) -> str:
    return ", ".join(f"{b['name']} ({b['zone']})" for b in buildings)


def urban_advisor(result: Dict) -> Dict:
    """
    Deterministic Advisor for the MVP.

    In the final demo, this structured output can be passed to an LLM to
    generate natural-language explanations. The LLM should only recommend
    interventions supported by this simulation.
    """
    m = result["metrics"]
    recommendations = []
    reasons = []
    affected = {}

    if m["heat_stress"] >= 60:
        worst = _worst_buildings(result, "heat_exposure")
        recommendations.append("increase_shade")
        affected["increase_shade"] = [b["id"] for b in worst]
        reasons.append(
            "High heat exposure is affecting pedestrian comfort"
            + (f"; most exposed: {_label(worst)}." if worst else ".")
        )

    # Thresholds are deliberately set for the hackathon's compound-stress
    # demo so that multiple interacting problems can be surfaced at once.
    if m["rain_impact"] >= 30:
        worst = _worst_buildings(result, "rain_impact")
        recommendations.append("improve_drainage")
        affected["improve_drainage"] = [b["id"] for b in worst]
        reasons.append(
            "Rainfall is creating meaningful safety and mobility penalties"
            + (f"; most flood-prone: {_label(worst)}." if worst else ".")
        )

    if m["crowding"] >= 55:
        worst = _worst_buildings(result, "crowding")
        recommendations.append("alternative_pedestrian_routes")
        affected["alternative_pedestrian_routes"] = [b["id"] for b in worst]
        reasons.append(
            "Population-driven crowding is increasing route congestion"
            + (f"; busiest destinations: {_label(worst)}." if worst else ".")
        )

    if not recommendations:
        recommendations.append("no_major_intervention")
        reasons.append("All prototype stress indicators are below the intervention thresholds.")

    return {
        "summary": " ; ".join(reasons),
        "problem_zones": result["problem_zones"],
        "problem_buildings": result["problem_buildings"],
        "problem_routes": result["problem_routes"],
        "recommendations": recommendations,
        "affected_buildings": affected,
        "explanation": reasons,
        "supported_interventions": {
            "increase_shade": {
                "changes": {"shade_boost": 0.25},
                "effect": "Reduces heat exposure and improves shaded-route attractiveness.",
            },
            "improve_drainage": {
                "changes": {"drainage_boost": 0.35},
                "effect": "Reduces rainfall impact and improves rain-time safety and mobility.",
            },
            "alternative_pedestrian_routes": {
                "changes": {"route_capacity_boost": 0.40},
                "effect": "Redistributes pedestrians and reduces crowding pressure.",
            },
        },
    }


def recommended_interventions(advisor: Dict) -> Dict:
    """Convert Advisor recommendations into simulation parameters."""
    changes = {}
    for rec in advisor["recommendations"]:
        if rec == "increase_shade":
            changes["shade_boost"] = max(changes.get("shade_boost", 0), 0.25)
        elif rec == "improve_drainage":
            changes["drainage_boost"] = max(changes.get("drainage_boost", 0), 0.35)
        elif rec == "alternative_pedestrian_routes":
            changes["route_capacity_boost"] = max(
                changes.get("route_capacity_boost", 0), 0.40
            )
    return changes


# ---------------------------------------------------------------------------
# Before / after demo
# ---------------------------------------------------------------------------

def run_demo(citizens: Union[None, str, Path, List[Citizen]] = None) -> Dict:
    scenario = dict(
        temperature=40,
        humidity=80,
        rainfall=80,
        population=100_000,
    )

    before = simulate(**scenario, citizens=citizens)
    advisor = urban_advisor(before)
    intervention = recommended_interventions(advisor)
    after = simulate(**scenario, citizens=citizens, interventions=intervention)

    before_m = before["metrics"]
    after_m = after["metrics"]

    delta = {
        key: round(after_m[key] - before_m[key], 2)
        for key in before_m
    }

    return {
        "scenario": scenario,
        "before": before,
        "advisor": advisor,
        "intervention": intervention,
        "after": after,
        "delta": delta,
    }


# ---------------------------------------------------------------------------
# Basic tests
# ---------------------------------------------------------------------------

def _building(result: Dict, bid: str) -> Dict:
    return next(b for b in result["buildings"] if b["id"] == bid)


def run_tests() -> None:
    import tempfile

    # --- environment formulas ---
    assert heat_stress(20, 20) < heat_stress(40, 80)
    assert heat_stress(40, 80) > heat_stress(40, 30)          # humidity matters
    assert zone_rain_impact(80, 0.20) > zone_rain_impact(80, 0.90)
    assert zone_rain_impact(0, 0.20) == 0
    assert crowding_score(100_000) > crowding_score(25_000)

    # --- interventions on headline metrics ---
    base = simulate(40, 80, 80, 100_000)
    shaded = simulate(40, 80, 80, 100_000, interventions={"shade_boost": 0.25})
    drained = simulate(40, 80, 80, 100_000, interventions={"drainage_boost": 0.35})
    rerouted = simulate(40, 80, 80, 100_000, interventions={"route_capacity_boost": 0.40})

    assert shaded["metrics"]["heat_stress"] < base["metrics"]["heat_stress"]
    assert drained["metrics"]["rain_impact"] < base["metrics"]["rain_impact"]
    assert rerouted["metrics"]["crowding"] < base["metrics"]["crowding"]

    # --- buildings ---
    assert len(base["buildings"]) == len(DEFAULT_CITY["buildings"])

    # Same rain: a flood-exposed building in a poorly drained zone (H1, Zone C)
    # is hit far harder than one in a well drained zone (H3, Zone A).
    assert _building(base, "H1")["rain_impact"] > 3 * _building(base, "H3")["rain_impact"]

    # Population drives building entrance crowding.
    low_pop = simulate(40, 80, 80, 25_000)
    assert max(b["crowding"] for b in base["buildings"]) > max(b["crowding"] for b in low_pop["buildings"])
    assert low_pop["metrics"]["crowding"] < base["metrics"]["crowding"]

    # Interventions reach individual buildings through their zone.
    assert _building(drained, "H1")["rain_impact"] < _building(base, "H1")["rain_impact"]
    assert _building(shaded, "M1")["heat_exposure"] < _building(base, "M1")["heat_exposure"]
    # Alternative routes do not pretend to fix entrance queues.
    assert _building(rerouted, "T1")["crowding"] == _building(base, "T1")["crowding"]

    # Building properties matter (cooling / flood exposure).
    tweaked = deepcopy(DEFAULT_CITY)
    for b in tweaked["buildings"]:
        if b.id == "M1":
            b.cooling, b.flood_exposure = 0.95, 0.10
    t = simulate(40, 80, 80, 100_000, city_state=tweaked)
    assert _building(t, "M1")["heat_exposure"] < _building(base, "M1")["heat_exposure"]
    assert _building(t, "M1")["rain_impact"] < _building(base, "M1")["rain_impact"]

    # Compound scenario should flag the known-bad buildings.
    flagged = {b["id"] for b in base["problem_buildings"]}
    assert {"H1", "M1"} <= flagged, flagged

    # --- citizens from JSON ---
    loaded = load_citizens()
    assert len(loaded) > 0
    assert len(base["citizens"]) == len(loaded)
    for c in base["citizens"]:
        cand = {r.id for r in routes_between(DEFAULT_CITY["routes"], c["home"], c["destination"])}
        assert c["route"] in cand                        # chose a route that connects home->destination

    # Explicit list / explicit path give identical results to the default load.
    assert simulate(40, 80, 80, 100_000, citizens=loaded)["metrics"] == base["metrics"]
    assert simulate(40, 80, 80, 100_000, citizens=DEFAULT_CITIZENS_PATH)["metrics"] == base["metrics"]

    # Weights are relative: doubling every weight must not change anything.
    doubled = [Citizen(**{**c.__dict__, "weight": c.weight * 2}) for c in loaded]
    assert simulate(40, 80, 80, 100_000, citizens=doubled)["metrics"] == base["metrics"]

    # Determinism: same inputs => same outputs.
    a = simulate(40, 80, 80, 100_000)
    b = simulate(40, 80, 80, 100_000)
    assert a["metrics"] == b["metrics"]
    assert a["routes"] == b["routes"]
    assert a["buildings"] == b["buildings"]

    # Accessibility is gone from all outputs.
    assert "accessibility" not in base["metrics"]
    assert all("accessibility" not in row for row in base["buildings"])
    assert all("accessibility" not in row for row in base["zones"])
    assert all("accessibility" not in row for row in base["routes"])

    # --- validation / error paths ---
    def expect_error(fn, exc=ValueError):
        try:
            fn()
        except exc:
            return
        raise AssertionError("expected an error")

    ghost_home = Citizen("X1", "test", "NOPE", "T1", .5, .5, .5, 4.0, .5, .5)
    expect_error(lambda: simulate(40, 80, 80, 100_000, citizens=[ghost_home]))
    no_route = Citizen("X2", "test", "H3", "HOS1", .5, .5, .5, 4.0, .5, .5)   # exists, but no route
    expect_error(lambda: simulate(40, 80, 80, 100_000, citizens=[no_route]))
    expect_error(lambda: simulate(40, 80, 80, 100_000, citizens=[]))
    expect_error(lambda: load_citizens("does_not_exist.json"), FileNotFoundError)

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bad.json"
        p.write_text(json.dumps({"citizens": [{"id": "Z1", "archetype": "x", "home": "H1"}]}))
        expect_error(lambda: load_citizens(p))                      # missing fields
        p.write_text(json.dumps({"citizens": [dict(
            id="Z2", archetype="x", home="H1", destination="T1", heat_tolerance=1.7,
            rain_tolerance=.5, crowd_tolerance=.5, walking_speed_kmh=4, green_preference=.5,
            transit_preference=.5)]}))
        expect_error(lambda: load_citizens(p))                      # out-of-range value
        # Older files that still carry 'accessibility_need' must keep loading (key is ignored).
        p.write_text(json.dumps({"citizens": [dict(
            id="Z3", archetype="x", home="H1", destination="T1", heat_tolerance=.5,
            rain_tolerance=.5, crowd_tolerance=.5, walking_speed_kmh=4, green_preference=.5,
            transit_preference=.5, accessibility_need=0.9)]}))
        assert len(load_citizens(p)) == 1

    broken_city = deepcopy(DEFAULT_CITY)
    broken_city["buildings"][0].zone = "Zone Z"
    expect_error(lambda: simulate(40, 80, 80, 100_000, city_state=broken_city))

    print("All tests passed.")


def print_demo_summary(demo: Dict) -> None:
    print("\n=== UrbanTwin AI — Compound Stress Demo ===")
    s = demo["scenario"]
    print(
        f"Scenario: {s['temperature']}°C | {s['humidity']}% RH | "
        f"{s['rainfall']} mm | population {s['population']:,}"
    )
    print(f"Citizens simulated: {len(demo['before']['citizens'])}")

    print("\nBEFORE")
    for k, v in demo["before"]["metrics"].items():
        print(f"  {k:26s}: {v:6.2f}")

    print("\nAI URBAN ADVISOR")
    for rec in demo["advisor"]["recommendations"]:
        print(f"  - {rec}")
    print(f"  Problem areas: {', '.join(demo['advisor']['problem_zones'])}")
    for line in demo["advisor"]["explanation"]:
        print(f"  * {line}")
    if demo["advisor"]["problem_buildings"]:
        print("  Problem buildings:")
        for pb in demo["advisor"]["problem_buildings"]:
            print(f"    {pb['id']:5s} {pb['name']} ({pb['zone']}): {', '.join(pb['issues'])}")

    print("\nAPPLIED INTERVENTION")
    print(" ", demo["intervention"] or "none")

    print("\nAFTER")
    for k, v in demo["after"]["metrics"].items():
        print(f"  {k:26s}: {v:6.2f}")

    print("\nCHANGE (after - before)")
    for k, v in demo["delta"].items():
        sign = "+" if v >= 0 else ""
        print(f"  {k:26s}: {sign}{v:6.2f}")

    print("\nBUILDINGS  (before -> after)")
    print(f"  {'':5s} {'name':24s} {'heat':>11s} {'rain':>11s} {'crowd':>11s}")
    for b0, b1 in zip(demo["before"]["buildings"], demo["after"]["buildings"]):
        print(
            f"  {b0['id']:5s} {b0['name']:24s} "
            f"{b0['heat_exposure']:5.0f} ->{b1['heat_exposure']:4.0f} "
            f"{b0['rain_impact']:5.0f} ->{b1['rain_impact']:4.0f} "
            f"{b0['crowding']:5.0f} ->{b1['crowding']:4.0f}"
        )


if __name__ == "__main__":
    # Optional: python urbantwin_simulation.py path/to/citizens.json
    citizens_path = sys.argv[1] if len(sys.argv) > 1 else None

    run_tests()
    demo = run_demo(citizens=citizens_path)
    print_demo_summary(demo)

    # Also save machine-readable output for Person 3 / dashboard integration.
    with open("urbantwin_demo_output.json", "w", encoding="utf-8") as f:
        json.dump(demo, f, indent=2)

    print("\nSaved: urbantwin_demo_output.json")
