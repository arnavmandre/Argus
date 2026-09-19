"""
UrbanTwin AI â€” Person 1 Simulation Engine
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
    * The city (zones, buildings, routes) is NOT hardcoded. It is read from
      city.json (see load_city), exactly like the citizens.
    * Citizens are NOT generated in code. They are read from citizens.json
      (see load_citizens). Each citizen has a home building and a destination
      building and chooses among the routes that connect them.
    * Accessibility has been removed from the model entirely (no metric, no
      zone/building/route/citizen field, no route penalty, no intervention).
      HEI is re-weighted without it.

What changed in the audit pass
    * Corridor crowding is now EMERGENT. It used to be the population slider
      multiplied by a fixed per-route constant, which meant a corridor nobody
      walked down could report higher congestion than one carrying thousands.
      Route choice and congestion are now solved together by iteration
      (see route_congestion and the assignment loop in simulate), damped with
      the method of successive averages so the flow does not stampede between
      corridors. Routes declare capacity_pph.
    * Citizen profiles now reach the headline metrics. Per-citizen comfort used
      to be computed and then discarded, so identical results came out whether
      the population was maximally heat-sensitive or maximally heat-tolerant.
      It is now aggregated into `citizen_comfort` and carries the largest
      single weight in the Human Experience Index.
    * walking_speed_kmh is no longer a dead parameter. Route cost is a function
      of travel TIME, and heat/rain/crowd exposure accumulate over that time,
      so slow walkers and long detours cost more.
    * greenery is its own route property instead of an alias for shade (an
      arcade shades without being green). Falls back to shade when absent.
    * HEI is a weighted average of four bounded pillars whose weights sum to
      1.0. It previously re-added heat and crowding on top of pillars that
      already contained them, double-counting both.

Prototype metrics are intentionally heuristic and are NOT medical,
meteorological, hydrological, or real-world predictive measurements.
"""

from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
from math import exp
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import argparse
import json
import sys


# ---------------------------------------------------------------------------
# Tunable constants (kept in one place so they are easy to explain / tweak)
# ---------------------------------------------------------------------------

DEFAULT_CITY_PATH = Path(__file__).with_name("city.json")
DEFAULT_CITIZENS_PATH = Path(__file__).with_name("citizens.json")

# Share of the city population that makes a trip in the simulated peak window.
# Building "arrivals" = population * PEAK_TRIP_SHARE * (share of citizens heading there).
PEAK_TRIP_SHARE = 0.15

# How much building-entrance crowding counts in the headline crowding metric
# (the rest comes from corridor/route crowding).
BUILDING_CROWD_WEIGHT = 0.30

# A building is reported as a "problem building" when a signal passes these.
BUILDING_ISSUE_THRESHOLDS = {"heat": 50.0, "rain": 40.0, "crowd": 70.0}

# --- Emergent corridor crowding -------------------------------------------
# Route crowding = ambient share (how intrinsically busy/narrow the corridor is,
# independent of our agents) + induced share (how many simulated pedestrians
# actually chose it, against its capacity). Raising AMBIENT_CROWD_SHARE makes
# crowding more of a fixed property; lowering it makes crowding more emergent.
AMBIENT_CROWD_SHARE = 0.30

# Used when a route in city.json does not declare capacity_pph. Pedestrians per
# hour the corridor absorbs before it reads as fully congested.
DEFAULT_ROUTE_CAPACITY_PPH = 1500.0

# Route choice is solved by iteration: choose -> measure congestion -> choose
# again, so citizens react to the crowd they themselves create.
#
# Everyone picking the single cheapest route at once makes raw iteration
# oscillate (the whole flow stampedes between two corridors and never settles).
# We damp it with the method of successive averages: on pass k the measured
# load is blended into the running load with weight 1/k, which is the standard
# fix for this in traffic assignment and converges to a stable split.
# Measured on the demo city: 4, 6 and 10 passes agree to within 0.3% on headline
# crowding, so 8 is comfortably inside the converged range.
CROWDING_PASSES = 8

# --- Route cost weights ----------------------------------------------------
# All in the same arbitrary "cost units". Ratios are what matter: they set how
# many minutes of extra walking a citizen will accept to avoid heat/rain/crowds.
# Exposure terms are per hour of travel, so a longer or slower trip accumulates
# more stress; TIME_COST_PER_HOUR keeps a ~0.3 h walk near its old cost scale.
TIME_COST_PER_HOUR = 8.0
HEAT_COST_PER_HOUR = 24.0
COLD_COST_PER_HOUR = 18.0
RAIN_COST_PER_HOUR = 24.0
CROWD_COST_PER_HOUR = 18.0
TRANSIT_BONUS = 1.5      # flat draw of a transit-served corridor
GREEN_BONUS = 1.2        # flat draw of a green corridor

# --- Human Experience Index ------------------------------------------------
# Weights over four bounded 0..100 pillars; they sum to 1.0 so the index cannot
# leave 0..100 by construction. citizen_comfort carries the largest single
# weight: this is a human-centric twin, so what the simulated people actually
# experienced should dominate the city-average environmental readings.
HEI_WEIGHTS = {
    "citizen_comfort": 0.35,
    "comfort": 0.25,
    "safety": 0.20,
    "mobility": 0.20,
}


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
    base_crowding: float          # ambient busyness when our agents are not counted
    transit: float = 0.0
    greenery: float = -1.0        # 0..1 trees/planting. -1 => fall back to `shade`
    capacity_pph: float = DEFAULT_ROUTE_CAPACITY_PPH   # pedestrians/hour before full congestion
    via_zones: Tuple[str, ...] = ()   # zones the route passes through (for reporting/visualisation)

    @property
    def green(self) -> float:
        """Greenery, defaulting to shade for city files written before the split."""
        return self.shade if self.greenery < 0 else self.greenery


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
# JSON import helpers (shared by city and citizens)
# ---------------------------------------------------------------------------

def _read_json(path: Union[str, Path], what: str):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{what} file not found: {path}")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _is_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


# ---------------------------------------------------------------------------
# City import (JSON)
# ---------------------------------------------------------------------------

def _parse_section(
    data: Dict,
    key: str,
    required: Tuple[str, ...],
    build,
    problems: List[str],
    unit: Tuple[str, ...] = (),
    positive: Tuple[str, ...] = (),
    nonneg: Tuple[str, ...] = (),
    extra_check=None,
) -> list:
    """
    Validate and convert one list ('zones', 'buildings' or 'routes') of the city file.
    `required` keys must exist; range checks apply to any of unit/positive/nonneg
    keys that are present. Problems are appended to `problems` (not raised).
    """
    records = data.get(key)
    if not isinstance(records, list) or not records:
        problems.append(f"'{key}' must be a non-empty list")
        return []

    out, seen = [], set()
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            problems.append(f"{key}[{i}]: not a JSON object")
            continue
        label = f"{key.rstrip('s')} {rec.get('id', f'#{i}')}"

        missing = [k for k in required if k not in rec]
        if missing:
            problems.append(f"{label}: missing {missing}")
            continue

        errs: List[str] = []
        if str(rec["id"]) in seen:
            errs.append("duplicate id")
        seen.add(str(rec["id"]))

        bad = [k for k in unit if k in rec and not (_is_num(rec[k]) and 0.0 <= rec[k] <= 1.0)]
        if bad:
            errs.append(f"{bad} must be numbers in 0..1")
        bad = [k for k in positive if k in rec and not (_is_num(rec[k]) and rec[k] > 0)]
        if bad:
            errs.append(f"{bad} must be numbers > 0")
        bad = [k for k in nonneg if k in rec and not (_is_num(rec[k]) and rec[k] >= 0)]
        if bad:
            errs.append(f"{bad} must be numbers >= 0")
        if extra_check:
            errs.extend(extra_check(rec))

        if errs:
            problems.extend(f"{label}: {e}" for e in errs)
            continue
        out.append(build(rec))
    return out


def _check_via_zones(rec: Dict) -> List[str]:
    v = rec.get("via_zones", [])
    if not isinstance(v, list) or not all(isinstance(z, str) for z in v):
        return ["via_zones must be a list of zone ids"]
    return []


def load_city(path: Union[str, Path] = DEFAULT_CITY_PATH) -> Dict:
    """
    Read the city structure from a JSON file and return
    {"zones": [Zone], "buildings": [Building], "routes": [Route]}.

    File shape:
        {"zones": [...], "buildings": [...], "routes": [...]}
        (extra top-level keys such as 'description' are ignored)

    zone      : id, drainage(0..1), shade(0..1)
    building  : id, name, type, zone, capacity(>=0), cooling(0..1), flood_exposure(0..1)
    route     : id, start, end, distance_km(>0), shade, drainage, base_crowding (0..1);
                optional: transit (0..1, default 0), greenery (0..1, defaults to
                shade), capacity_pph (>0, pedestrians/hour before full
                congestion), via_zones (list of zone ids)

    Unknown keys are ignored. Field-level problems are collected and reported
    together, then cross-references (building->zone, route->building/zone) are checked.
    """
    path = Path(path)
    data = _read_json(path, "City")
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected an object with 'zones', 'buildings' and 'routes'")

    problems: List[str] = []

    zones = _parse_section(
        data, "zones", ("id", "drainage", "shade"),
        lambda r: Zone(id=str(r["id"]), drainage=float(r["drainage"]), shade=float(r["shade"])),
        problems, unit=("drainage", "shade"),
    )
    buildings = _parse_section(
        data, "buildings", ("id", "name", "type", "zone", "capacity", "cooling", "flood_exposure"),
        lambda r: Building(
            id=str(r["id"]), name=str(r["name"]), type=str(r["type"]), zone=str(r["zone"]),
            capacity=int(r["capacity"]), cooling=float(r["cooling"]),
            flood_exposure=float(r["flood_exposure"]),
        ),
        problems, unit=("cooling", "flood_exposure"), nonneg=("capacity",),
    )
    routes = _parse_section(
        data, "routes", ("id", "start", "end", "distance_km", "shade", "drainage", "base_crowding"),
        lambda r: Route(
            id=str(r["id"]), start=str(r["start"]), end=str(r["end"]),
            distance_km=float(r["distance_km"]), shade=float(r["shade"]),
            drainage=float(r["drainage"]), base_crowding=float(r["base_crowding"]),
            transit=float(r.get("transit", 0.0)),
            greenery=float(r["greenery"]) if "greenery" in r else -1.0,
            capacity_pph=float(r.get("capacity_pph", DEFAULT_ROUTE_CAPACITY_PPH)),
            via_zones=tuple(str(z) for z in r.get("via_zones", [])),
        ),
        problems, unit=("shade", "drainage", "base_crowding", "transit", "greenery"),
        positive=("distance_km", "capacity_pph"), extra_check=_check_via_zones,
    )

    if problems:
        raise ValueError(f"{path}: invalid city data:\n  - " + "\n  - ".join(problems))

    city = {"zones": zones, "buildings": buildings, "routes": routes}
    try:
        validate_city(city)
    except ValueError as e:
        raise ValueError(f"{path}: {e}") from None
    return city


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
    data = _read_json(path, "Citizen")

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


def cold_stress(temperature: float) -> float:
    """Prototype cold-exposure signal: 0 at 15 C or warmer, 100 at -10 C."""
    return norm(15.0 - temperature, 0.0, 25.0) * 100.0


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
    crowd_level: float,
    shade_boost: float = 0.0,
    drainage_boost: float = 0.0,
) -> Dict[str, float]:
    """
    Perceived cost of one route for one citizen, in arbitrary cost units.

    Exposure is per hour of travel: the citizen's own walking speed sets how
    long they are out in the heat/rain/crowd, so a slow walker on a long
    sun-exposed route accumulates more stress than a fast walker on a short one.

    `crowd_level` (0..1) is the corridor's current congestion, measured from how
    many simulated pedestrians actually chose it (see route_congestion). It is
    supplied by the caller rather than derived here, so that route choice and
    congestion can be solved together.
    """
    hs = heat_stress(temperature, humidity) / 100
    cs = cold_stress(temperature) / 100
    rain = rainfall_intensity(rainfall)

    effective_shade = clamp(route.shade + shade_boost, 0.0, 1.0)
    effective_drainage = clamp(route.drainage + drainage_boost, 0.0, 1.0)
    effective_green = clamp(route.green + shade_boost, 0.0, 1.0)
    crowd_level = clamp(crowd_level, 0.0, 1.0)

    # How long this citizen is exposed, in hours.
    travel_h = route.distance_km / citizen.walking_speed_kmh

    time_cost = travel_h * TIME_COST_PER_HOUR
    heat_penalty = hs * (1 - effective_shade) * (1 - citizen.heat_tolerance) * travel_h * HEAT_COST_PER_HOUR
    # Cold tolerance was not measured by the survey, so keep this as a shared
    # environmental burden rather than inventing a personal attribute.
    cold_penalty = cs * travel_h * COLD_COST_PER_HOUR
    rain_penalty = rain * (1 - effective_drainage) * (1 - citizen.rain_tolerance) * travel_h * RAIN_COST_PER_HOUR
    crowd_penalty = crowd_level * (1 - citizen.crowd_tolerance) * travel_h * CROWD_COST_PER_HOUR
    transit_bonus = route.transit * citizen.transit_preference * TRANSIT_BONUS
    green_bonus = effective_green * citizen.green_preference * GREEN_BONUS

    total = (
        time_cost
        + heat_penalty
        + cold_penalty
        + rain_penalty
        + crowd_penalty
        - transit_bonus
        - green_bonus
    )

    return {
        "total": total,
        "time": time_cost,
        "travel_hours": travel_h,
        "heat": heat_penalty,
        "cold": cold_penalty,
        "rain": rain_penalty,
        "crowd": crowd_penalty,
        "transit_bonus": transit_bonus,
        "green_bonus": green_bonus,
    }


def route_congestion(
    route: Route,
    pedestrians: float,
    route_capacity_boost: float = 0.0,
) -> float:
    """
    Corridor congestion, 0..1, as ambient busyness plus the load our own
    simulated pedestrians put on it.

    `pedestrians` is the peak-window headcount that chose this route.
    Extra pedestrian capacity (the 'alternative routes' intervention) raises the
    denominator, so the same crowd reads as less congested.
    """
    capacity = max(route.capacity_pph, 1e-9) * (1 + route_capacity_boost)
    utilisation = clamp(pedestrians / capacity, 0.0, 1.0)
    # An empty corridor still reads as somewhat busy if it is intrinsically
    # narrow or has non-simulated traffic; a corridor at capacity reads as full.
    ambient_floor = AMBIENT_CROWD_SHARE * route.base_crowding
    return clamp(ambient_floor + (1 - ambient_floor) * utilisation, 0.0, 1.0)


def choose_route(
    citizen: Citizen,
    routes: List[Route],
    temperature: float,
    humidity: float,
    rainfall: float,
    crowd_levels: Dict[str, float],
    interventions: Optional[Dict] = None,
) -> Tuple[str, Dict[str, float]]:
    """Pick the cheapest route among `routes` (already filtered to the citizen's home->destination)."""

    interventions = interventions or {}
    costs = {}

    for r in routes:
        # Target interventions can be attached globally for the MVP.
        costs[r.id] = route_cost(
            r, citizen, temperature, humidity, rainfall,
            crowd_level=crowd_levels.get(r.id, r.base_crowding),
            shade_boost=interventions.get("shade_boost", 0.0),
            drainage_boost=interventions.get("drainage_boost", 0.0),
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
    city_state: Union[None, str, Path, Dict] = None,
    citizens: Union[None, str, Path, List[Citizen]] = None,
    interventions: Optional[Dict] = None,
) -> Dict:
    """
    city_state: None          -> load DEFAULT_CITY_PATH (city.json next to this file)
                str / Path      -> load that JSON file
                Dict            -> a city as returned by load_city() (copied, never mutated)
    citizens: None            -> load DEFAULT_CITIZENS_PATH (citizens.json next to this file)
              str / Path      -> load that JSON file
              List[Citizen]   -> use as-is
    The run is fully deterministic (no randomness anywhere).
    """

    if not (-10 <= temperature <= 45):
        raise ValueError("temperature must be between -10 and 45 degrees C")
    if not (20 <= humidity <= 90):
        raise ValueError("humidity must be between 20 and 90 %")
    if not (0 <= rainfall <= 100):
        raise ValueError("rainfall must be between 0 and 100 mm")
    if not (25_000 <= population <= 100_000):
        raise ValueError("population must be between 25,000 and 100,000")

    interventions = interventions or {}
    if city_state is None or isinstance(city_state, (str, Path)):
        city = load_city(city_state or DEFAULT_CITY_PATH)   # fresh objects on every call
    else:
        city = deepcopy(city_state)                          # never mutate the caller's city
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
    cs = cold_stress(temperature)

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

    # Entrance crowding: average over buildings that people actually travel to.
    destination_ids = [bid for bid, a in arrivals.items() if a > 0]
    building_crowd = mean(bmetrics[bid]["crowd"] for bid in destination_ids)

    # Interventions directly reduce exposure/stress in the prototype.
    effective_heat = clamp(hs * (1 - 0.30 * interventions.get("shade_boost", 0)))
    effective_cold = cs
    effective_rain = clamp(rain * (1 - 0.65 * interventions.get("drainage_boost", 0)))
    capacity_boost = interventions.get("route_capacity_boost", 0.0)

    # --- Citizens choose routes; congestion emerges from those choices ------
    # Solved by iteration: everyone picks a route against the congestion they
    # can currently see, that load is measured, and they pick again. Crowded
    # corridors therefore push later traffic onto alternatives.
    route_ids = [r.id for r in city["routes"]]
    candidates_for = {
        c.id: routes_between(city["routes"], c.home, c.destination) for c in citizens
    }
    trip_people = {c.id: c.weight * people_per_weight * PEAK_TRIP_SHARE for c in citizens}

    # Pass 0 sees ambient busyness only (no simulated pedestrians placed yet).
    crowd_levels = {r.id: route_congestion(r, 0.0, capacity_boost) for r in city["routes"]}
    chosen_by = {}
    cost_of = {}
    route_people = {rid: 0.0 for rid in route_ids}
    route_counts = {rid: 0 for rid in route_ids}

    for k in range(1, CROWDING_PASSES + 1):
        pass_people = {rid: 0.0 for rid in route_ids}
        route_counts = {rid: 0 for rid in route_ids}
        for c in citizens:
            chosen, costs = choose_route(
                c, candidates_for[c.id], temperature, humidity, rainfall,
                crowd_levels, interventions,
            )
            chosen_by[c.id] = chosen
            cost_of[c.id] = costs
            route_counts[chosen] += 1
            pass_people[chosen] += trip_people[c.id]

        # Method of successive averages: blend this pass's loads into the
        # running loads with weight 1/k instead of replacing them outright.
        step = 1.0 / k
        route_people = {
            rid: route_people[rid] + step * (pass_people[rid] - route_people[rid])
            for rid in route_ids
        }
        crowd_levels = {
            r.id: route_congestion(r, route_people[r.id], capacity_boost)
            for r in city["routes"]
        }

    route_crowding = {rid: crowd_levels[rid] * 100.0 for rid in route_ids}

    # Headline corridor crowding is what pedestrians actually walked through,
    # so an empty corridor cannot drag the city average around.
    walked = sum(route_people.values())
    if walked > 0:
        route_crowd = sum(route_crowding[rid] * route_people[rid] for rid in route_ids) / walked
    else:
        route_crowd = mean(route_crowding.values())

    effective_route_crowd = clamp(route_crowd)
    effective_crowd = clamp(
        (1 - BUILDING_CROWD_WEIGHT) * effective_route_crowd
        + BUILDING_CROWD_WEIGHT * building_crowd
    )

    # --- Individual experience on the route each citizen settled on ---------
    citizen_results = []
    route_by_id_local = {r.id: r for r in city["routes"]}

    for c in citizens:
        chosen = chosen_by[c.id]
        costs = cost_of[c.id]
        route = route_by_id_local[chosen]
        dest = building_by_id[c.destination]
        dest_crowd = bmetrics[dest.id]["crowd"]

        effective_route_shade = clamp(
            route.shade + interventions.get("shade_boost", 0), 0.0, 1.0
        )
        local_heat = effective_heat * (1 - effective_route_shade)
        local_cold = effective_cold
        local_rain = effective_rain * (1 - clamp(route.drainage + interventions.get("drainage_boost", 0), 0.0, 1.0))
        local_crowd = route_crowding[chosen]

        # Extreme weather has an immediate burden. Previously a two-minute trip
        # received almost no penalty, making citizens implausibly comfortable.
        # Duration still matters, while the first minutes now have a real dose.
        exposure = 0.55 + 0.45 * clamp(costs["travel_hours"] / 0.30, 0.0, 2.0)

        heat_burden = (
            effective_heat * (1 - 0.65 * effective_route_shade)
            * (0.55 + 0.45 * (1 - c.heat_tolerance))
        )
        cold_burden = local_cold
        rain_burden = (
            effective_rain
            * (1 - 0.65 * clamp(route.drainage + interventions.get("drainage_boost", 0), 0.0, 1.0))
            * (0.55 + 0.45 * (1 - c.rain_tolerance))
        )
        crowd_burden = local_crowd * (0.55 + 0.45 * (1 - c.crowd_tolerance))

        personal_comfort = clamp(
            100
            - 0.70 * heat_burden * exposure
            - 0.58 * cold_burden * exposure
            - 0.42 * rain_burden * exposure
            - 0.30 * crowd_burden * exposure
            # Arrival end of the trip: crowded entrance.
            - 0.08 * dest_crowd * (1 - c.crowd_tolerance)
        )

        stress = clamp(100.0 - personal_comfort)
        flood_risk = max(local_rain, bmetrics[dest.id]["rain"])
        if personal_comfort < 35 or flood_risk >= 70:
            behavior = "AVOID_AREA"
        elif local_rain >= 45 or cold_burden >= 60:
            behavior = "SEEK_SHELTER"
        elif heat_burden >= 55:
            behavior = "SEEK_SHADE"
        elif local_crowd >= 60:
            behavior = "REROUTE"
        elif personal_comfort < 65:
            behavior = "STRESSED"
        else:
            behavior = "CONTINUE"

        citizen_results.append({
            "id": c.id,
            "archetype": c.archetype,
            "home": c.home,
            "destination": c.destination,
            "route": chosen,
            "travel_minutes": round(costs["travel_hours"] * 60, 1),
            "heat_exposure": round(local_heat, 2),
            "cold_exposure": round(local_cold, 2),
            "rain_exposure": round(local_rain, 2),
            "flood_risk": round(flood_risk, 2),
            "crowd_exposure": round(local_crowd, 2),
            "destination_crowding": round(dest_crowd, 2),
            "comfort": round(personal_comfort, 2),
            "stress": round(stress, 2),
            "behavior": behavior,
            "route_cost": round(costs["total"], 2),
        })

    # What the simulated population actually experienced, weighted by how many
    # real people each agent stands for. This is the human-centric metric.
    total_citizen_weight = sum(c.weight for c in citizens)
    citizen_comfort = sum(
        row["comfort"] * c.weight for row, c in zip(citizen_results, citizens)
    ) / total_citizen_weight
    mean_travel_minutes = sum(
        row["travel_minutes"] * c.weight for row, c in zip(citizen_results, citizens)
    ) / total_citizen_weight

    # --- Human-centric aggregate metrics ------------------------------------
    effective_thermal = max(effective_heat, effective_cold)

    safety = clamp(
        100
        - 0.65 * effective_rain
        - 0.20 * effective_thermal
        - 0.15 * effective_crowd
    )

    mobility = clamp(
        100
        - 0.35 * effective_crowd
        - 0.35 * effective_rain
        - 0.15 * effective_thermal
    )

    comfort = clamp(
        100
        - 0.48 * effective_thermal
        - 0.22 * effective_rain
        - 0.20 * effective_crowd
    )

    # Human Experience Index: a weighted average of four bounded 0..100 pillars.
    #
    # citizen_comfort is what the simulated citizens actually experienced on the
    # routes they chose, so their heat/rain/crowd tolerances and walking speeds
    # move this index. The other three are city-average environmental readings.
    #
    # Weights sum to 1.0, so the result is inside 0..100 by construction rather
    # than by clamping. Heat, rain and crowding are not re-added on top: they
    # already sit inside every pillar, and adding them again would silently
    # double-count them.
    hei = clamp(
        HEI_WEIGHTS["citizen_comfort"] * citizen_comfort
        + HEI_WEIGHTS["comfort"] * comfort
        + HEI_WEIGHTS["safety"] * safety
        + HEI_WEIGHTS["mobility"] * mobility
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
            "cold_stress": round(effective_cold, 2),
            "rain_impact": round(effective_rain, 2),
            "crowding": round(effective_crowd, 2),
            "safety": round(safety, 2),
            "mobility": round(mobility, 2),
            # City-average environmental comfort (from heat/rain/crowd readings).
            "comfort": round(comfort, 2),
            # Population-weighted mean of what the simulated citizens experienced.
            "citizen_comfort": round(citizen_comfort, 2),
            "mean_travel_minutes": round(mean_travel_minutes, 2),
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
                "capacity_pph": round(r.capacity_pph),
                "utilisation": round(
                    min(route_people[r.id] / max(r.capacity_pph, 1e-9), 1.0), 3
                ),
                "shade": round(r.shade, 2),
                "greenery": round(r.green, 2),
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

DEFAULT_SCENARIO = {
    "temperature": 40,
    "humidity": 80,
    "rainfall": 80,
    "population": 100_000,
}


def parse_cli(argv=None):
    parser = argparse.ArgumentParser(description="Run the UrbanTwin simulation.")
    parser.add_argument("citizens", type=Path, nargs="?")
    parser.add_argument("city", type=Path, nargs="?")
    parser.add_argument("--temperature", type=float, default=DEFAULT_SCENARIO["temperature"])
    parser.add_argument("--humidity", type=float, default=DEFAULT_SCENARIO["humidity"])
    parser.add_argument("--rainfall", type=float, default=DEFAULT_SCENARIO["rainfall"])
    parser.add_argument("--population", type=int, default=DEFAULT_SCENARIO["population"])
    parser.add_argument("--output", type=Path, default=Path("urbantwin_demo_output.json"))
    return parser.parse_args(argv)


def run_demo(
    citizens: Union[None, str, Path, List[Citizen]] = None,
    city_state: Union[None, str, Path, Dict] = None,
    scenario=None,
) -> Dict:
    scenario = dict(DEFAULT_SCENARIO if scenario is None else scenario)

    before = simulate(**scenario, city_state=city_state, citizens=citizens)
    advisor = urban_advisor(before)
    intervention = recommended_interventions(advisor)
    after = simulate(**scenario, city_state=city_state, citizens=citizens, interventions=intervention)

    # Control scenario: a mild day on the same city with the same citizens.
    # The Advisor's thresholds are not hardwired to always fire - on a calm day
    # it should recommend nothing. Shown in the demo so the compound-stress
    # result above cannot be mistaken for a predetermined script.
    calm_scenario = dict(temperature=26, humidity=40, rainfall=5, population=30_000)
    calm = simulate(**calm_scenario, city_state=city_state, citizens=citizens)
    calm_advisor = urban_advisor(calm)

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
        "control": {
            "scenario": calm_scenario,
            "metrics": calm["metrics"],
            "recommendations": calm_advisor["recommendations"],
        },
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
    assert cold_stress(-10) == 100
    assert cold_stress(15) == 0
    assert zone_rain_impact(80, 0.20) > zone_rain_impact(80, 0.90)
    assert zone_rain_impact(0, 0.20) == 0

    # --- emergent congestion -------------------------------------------------
    r_test = Route("RT", "A", "B", 1.0, 0.5, 0.5, 0.40, capacity_pph=1000)
    empty = route_congestion(r_test, 0)
    busy = route_congestion(r_test, 1000)
    assert empty < busy, (empty, busy)                    # usage drives congestion
    assert empty == AMBIENT_CROWD_SHARE * 0.40            # ambient floor only
    assert busy == 1.0                                    # at capacity
    assert route_congestion(r_test, 5000) == 1.0          # saturates, never exceeds 1
    # Extra capacity relieves the same crowd.
    assert route_congestion(r_test, 1000, 0.40) < busy

    # Congestion tracks the pedestrians who actually chose each route: the
    # busiest corridors must be ones agents picked, not ones they avoided.
    base_for_crowd = simulate(40, 80, 80, 100_000)
    used = [r for r in base_for_crowd["routes"] if r["chosen_by_agents"] > 0]
    unused = [r for r in base_for_crowd["routes"] if r["chosen_by_agents"] == 0]
    assert used, "no route was chosen by anyone"
    assert max(r["crowding"] for r in used) > max(r["crowding"] for r in unused), (
        "unused routes are more congested than used ones - congestion is not emergent"
    )

    # The iterative assignment must be converged, not still oscillating:
    # nearby pass counts have to agree closely.
    global CROWDING_PASSES
    _passes = CROWDING_PASSES
    try:
        seen = []
        for n in (6, 8, 12):
            CROWDING_PASSES = n
            seen.append(simulate(40, 80, 80, 100_000)["metrics"]["crowding"])
        assert max(seen) - min(seen) < 1.0, f"route assignment has not converged: {seen}"
    finally:
        CROWDING_PASSES = _passes

    # Congestion must respond to demand being concentrated on one corridor.
    # Same population, different travel demand => different corridor crowding.
    cits_for_demand = load_citizens()
    concentrated = [Citizen(**{**c.__dict__, "home": "H1", "destination": "T1"}) for c in cits_for_demand]
    conc = simulate(40, 80, 80, 100_000, citizens=concentrated)
    assert conc["metrics"]["crowding"] != base_for_crowd["metrics"]["crowding"]

    # --- interventions on headline metrics ---
    base = simulate(40, 80, 80, 100_000)
    shaded = simulate(40, 80, 80, 100_000, interventions={"shade_boost": 0.25})
    drained = simulate(40, 80, 80, 100_000, interventions={"drainage_boost": 0.35})
    rerouted = simulate(40, 80, 80, 100_000, interventions={"route_capacity_boost": 0.40})

    assert shaded["metrics"]["heat_stress"] < base["metrics"]["heat_stress"]
    assert drained["metrics"]["rain_impact"] < base["metrics"]["rain_impact"]
    assert rerouted["metrics"]["crowding"] < base["metrics"]["crowding"]

    # --- buildings ---
    assert len(base["buildings"]) == len(load_city()["buildings"])

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
    tweaked = load_city()
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
    city0 = load_city()
    assert len(loaded) > 0
    assert len(base["citizens"]) == len(loaded)
    for c in base["citizens"]:
        cand = {r.id for r in routes_between(city0["routes"], c["home"], c["destination"])}
        assert c["route"] in cand                        # chose a route that connects home->destination

    # Explicit list / explicit path give identical results to the default load.
    assert simulate(40, 80, 80, 100_000, citizens=loaded)["metrics"] == base["metrics"]
    assert simulate(40, 80, 80, 100_000, citizens=DEFAULT_CITIZENS_PATH)["metrics"] == base["metrics"]

    # City: default file, explicit path and an already-loaded dict all agree.
    assert simulate(40, 80, 80, 100_000, city_state=DEFAULT_CITY_PATH)["metrics"] == base["metrics"]
    assert simulate(40, 80, 80, 100_000, city_state=load_city())["metrics"] == base["metrics"]
    # A city dict passed in must not be mutated by interventions.
    city_in = load_city()
    shade_before = [z.shade for z in city_in["zones"]]
    simulate(40, 80, 80, 100_000, city_state=city_in, interventions={"shade_boost": 0.25})
    assert [z.shade for z in city_in["zones"]] == shade_before

    # Weights are relative: doubling every weight must not change anything.
    doubled = [Citizen(**{**c.__dict__, "weight": c.weight * 2}) for c in loaded]
    assert simulate(40, 80, 80, 100_000, citizens=doubled)["metrics"] == base["metrics"]

    # --- citizen profiles must reach the headline metrics -------------------
    # This is the whole point of a human-centric twin: swapping the population
    # for a more vulnerable one must move the Human Experience Index.
    sensitive = [Citizen(**{**c.__dict__, "heat_tolerance": 0.0,
                            "rain_tolerance": 0.0, "crowd_tolerance": 0.0}) for c in loaded]
    tolerant = [Citizen(**{**c.__dict__, "heat_tolerance": 1.0,
                           "rain_tolerance": 1.0, "crowd_tolerance": 1.0}) for c in loaded]
    m_sens = simulate(40, 80, 80, 100_000, citizens=sensitive)["metrics"]
    m_tol = simulate(40, 80, 80, 100_000, citizens=tolerant)["metrics"]
    assert m_sens["citizen_comfort"] < m_tol["citizen_comfort"]
    assert m_sens["human_experience_index"] < m_tol["human_experience_index"], (
        "citizen tolerances do not affect HEI"
    )

    # Walking speed is a real parameter: slower walkers are exposed for longer.
    slow = [Citizen(**{**c.__dict__, "walking_speed_kmh": 2.0}) for c in loaded]
    fast = [Citizen(**{**c.__dict__, "walking_speed_kmh": 5.5}) for c in loaded]
    m_slow = simulate(40, 80, 80, 100_000, citizens=slow)["metrics"]
    m_fast = simulate(40, 80, 80, 100_000, citizens=fast)["metrics"]
    assert m_slow["mean_travel_minutes"] > m_fast["mean_travel_minutes"]
    assert m_slow["citizen_comfort"] < m_fast["citizen_comfort"], "walking speed has no effect"

    # Greenery is its own route property, not an alias for shade.
    green_city = load_city()
    for r in green_city["routes"]:
        r.greenery = 0.0
    keen = [Citizen(**{**c.__dict__, "green_preference": 1.0}) for c in loaded]
    assert (simulate(40, 80, 80, 100_000, citizens=keen, city_state=green_city)["citizens"]
            != simulate(40, 80, 80, 100_000, citizens=keen)["citizens"])

    # HEI stays inside 0..100 across the corners of the scenario box.
    for T in (20, 45):
        for H in (20, 90):
            for R in (0, 100):
                for P in (25_000, 100_000):
                    for k, v in simulate(T, H, R, P)["metrics"].items():
                        if k != "mean_travel_minutes":
                            assert 0.0 <= v <= 100.0, (k, v, T, H, R, P)

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

    # --- advisor is threshold-driven, not hardwired --------------------------
    calm = simulate(26, 40, 5, 30_000)
    assert urban_advisor(calm)["recommendations"] == ["no_major_intervention"]
    harsh = urban_advisor(simulate(45, 90, 100, 100_000))["recommendations"]
    assert "no_major_intervention" not in harsh and len(harsh) >= 2, harsh

    # Extreme conditions must reach people, not only aggregate city metrics.
    extreme_hot = simulate(45, 90, 100, 100_000)
    extreme_cold = simulate(-10, 60, 20, 100_000)
    mild = simulate(22, 45, 0, 30_000)
    assert extreme_hot["metrics"]["citizen_comfort"] < 60
    assert extreme_cold["metrics"]["citizen_comfort"] < 60
    assert mild["metrics"]["citizen_comfort"] > extreme_hot["metrics"]["citizen_comfort"]
    assert any(c["behavior"] != "CONTINUE" for c in extreme_hot["citizens"])
    assert any(c["behavior"] in {"SEEK_SHELTER", "AVOID_AREA"}
               for c in extreme_cold["citizens"])

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
        # --- city.json: edits change results; bad files fail clearly ---
        def city_file(mutate):
            raw = json.loads(DEFAULT_CITY_PATH.read_text(encoding="utf-8"))
            mutate(raw)
            f = Path(d) / "city_test.json"
            f.write_text(json.dumps(raw), encoding="utf-8")
            return f

        def set_building(raw, bid, **kw):
            next(b for b in raw["buildings"] if b["id"] == bid).update(kw)

        small_hub = simulate(40, 80, 80, 100_000,
                             city_state=city_file(lambda r: set_building(r, "T1", capacity=800)))
        assert _building(small_hub, "T1")["crowding"] > _building(base, "T1")["crowding"]

        # Older files that still carry 'accessibility' keys must keep loading (ignored).
        load_city(city_file(lambda r: (r["zones"][0].update(accessibility=0.9),
                                       set_building(r, "H1", accessibility=0.1),
                                       r["routes"][0].update(accessibility=0.5))))

        expect_error(lambda: load_city(city_file(lambda r: r.pop("routes"))))                       # missing section
        expect_error(lambda: load_city(city_file(lambda r: r["zones"][0].update(drainage=1.5))))    # out of range
        expect_error(lambda: load_city(city_file(lambda r: r["buildings"].append(dict(r["buildings"][0])))))  # dup id
        expect_error(lambda: load_city(city_file(lambda r: set_building(r, "H1", zone="Zone Z"))))  # unknown zone
        expect_error(lambda: load_city(city_file(lambda r: r["routes"][0].pop("distance_km"))))     # missing field
        expect_error(lambda: load_city(city_file(lambda r: r["routes"][0].update(via_zones="Zone A"))))  # not a list
        expect_error(lambda: load_city("no_such_city.json"), FileNotFoundError)

        # --- citizens.json ---
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

    broken_city = load_city()
    broken_city["buildings"][0].zone = "Zone Z"
    expect_error(lambda: simulate(40, 80, 80, 100_000, city_state=broken_city))

    print("All tests passed.")


def print_demo_summary(demo: Dict) -> None:
    print("\n=== UrbanTwin AI â€” Compound Stress Demo ===")
    s = demo["scenario"]
    print(
        f"Scenario: {s['temperature']}Â°C | {s['humidity']}% RH | "
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

    c = demo["control"]
    cs = c["scenario"]
    print(
        f"\nCONTROL RUN (thresholds are not hardwired): {cs['temperature']}Â°C | "
        f"{cs['humidity']}% RH | {cs['rainfall']} mm | population {cs['population']:,}"
    )
    print(f"  HEI {c['metrics']['human_experience_index']:.2f} -> advisor says: "
          f"{', '.join(c['recommendations'])}")

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
    args = parse_cli()
    scenario = {
        "temperature": args.temperature,
        "humidity": args.humidity,
        "rainfall": args.rainfall,
        "population": args.population,
    }
    run_tests()
    demo = run_demo(citizens=args.citizens, city_state=args.city, scenario=scenario)
    print_demo_summary(demo)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(demo, indent=2) + "\n", encoding="utf-8")
    print(f"\nSaved: {args.output}")
