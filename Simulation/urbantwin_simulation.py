
"""
UrbanTwin AI — Person 1 Simulation Engine
24-hour hackathon MVP

Pure Python, deterministic, transparent heuristics.
No Omniverse dependency.

Core pipeline:
Temperature + Humidity + Rainfall + Population
    -> environment metrics
    -> synthetic citizens
    -> route choice
    -> human-centric metrics
    -> Urban Advisor
    -> interventions
    -> rerun / compare

Prototype metrics are intentionally heuristic and are NOT medical,
meteorological, hydrological, or real-world predictive measurements.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from copy import deepcopy
from math import exp
from typing import Dict, List, Optional, Tuple
import json
import random


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


# ---------------------------------------------------------------------------
# City model
# ---------------------------------------------------------------------------

@dataclass
class Zone:
    id: str
    drainage: float       # 0 = poor, 1 = excellent
    shade: float          # 0 = no shade, 1 = highly shaded
    accessibility: float  # 0 = inaccessible, 1 = highly accessible


@dataclass
class Route:
    id: str
    start: str
    end: str
    distance_km: float
    shade: float
    drainage: float
    accessibility: float
    base_crowding: float
    transit: float = 0.0


@dataclass
class Citizen:
    id: str
    archetype: str
    heat_tolerance: float
    rain_tolerance: float
    crowd_tolerance: float
    walking_speed_kmh: float
    green_preference: float
    transit_preference: float
    accessibility_need: float


DEFAULT_CITY = {
    "zones": [
        Zone("Zone A", drainage=0.90, shade=0.35, accessibility=0.90),
        Zone("Zone B", drainage=0.60, shade=0.55, accessibility=0.78),
        Zone("Zone C", drainage=0.25, shade=0.20, accessibility=0.55),
    ],
    "routes": [
        Route("R1", "Residential", "Transit Hub", 1.2, 0.20, 0.90, 0.95, 0.35, 1.00),
        Route("R2", "Residential", "Transit Hub", 1.5, 0.75, 0.60, 0.88, 0.25, 0.70),
        Route("R3", "Residential", "Transit Hub", 1.0, 0.10, 0.25, 0.55, 0.45, 0.35),
        Route("R4", "Residential", "Transit Hub", 1.8, 0.85, 0.85, 0.92, 0.15, 0.40),
    ],
}


ARCHETYPES = [
    dict(name="Young commuter", heat=0.72, rain=0.70, crowd=0.65, speed=5.0, green=0.35, transit=0.80, access=0.10),
    dict(name="Elderly citizen", heat=0.35, rain=0.50, crowd=0.45, speed=3.2, green=0.55, transit=0.70, access=0.65),
    dict(name="Mobility-limited citizen", heat=0.55, rain=0.45, crowd=0.50, speed=2.5, green=0.30, transit=0.60, access=0.95),
    dict(name="Student", heat=0.70, rain=0.65, crowd=0.55, speed=4.8, green=0.45, transit=0.75, access=0.15),
    dict(name="Outdoor worker", heat=0.85, rain=0.80, crowd=0.70, speed=4.2, green=0.25, transit=0.35, access=0.10),
    dict(name="Family / parent", heat=0.60, rain=0.60, crowd=0.45, speed=3.8, green=0.65, transit=0.65, access=0.45),
    dict(name="Transit-dependent citizen", heat=0.55, rain=0.55, crowd=0.50, speed=3.5, green=0.25, transit=0.95, access=0.55),
    dict(name="General pedestrian", heat=0.65, rain=0.65, crowd=0.60, speed=4.5, green=0.40, transit=0.45, access=0.20),
]


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


# ---------------------------------------------------------------------------
# Citizen generation
# ---------------------------------------------------------------------------

def generate_citizens(
    population: int,
    n: int = 80,
    seed: int = 42,
) -> List[Citizen]:
    """
    Create a small representative sample whose behavior is scaled to the
    supplied city population. We do NOT simulate every resident.
    """
    rng = random.Random(seed)

    # Weighted archetype mix; only a small sample is actually simulated.
    weights = [0.16, 0.10, 0.08, 0.16, 0.10, 0.12, 0.10, 0.18]

    citizens = []
    for i in range(n):
        a = rng.choices(ARCHETYPES, weights=weights, k=1)[0]
        # Tiny deterministic variation prevents every member of an archetype
        # from behaving identically.
        jitter = lambda: rng.uniform(-0.04, 0.04)

        citizens.append(
            Citizen(
                id=f"C{i+1:03d}",
                archetype=a["name"],
                heat_tolerance=clamp(a["heat"] + jitter(), 0, 1),
                rain_tolerance=clamp(a["rain"] + jitter(), 0, 1),
                crowd_tolerance=clamp(a["crowd"] + jitter(), 0, 1),
                walking_speed_kmh=max(1.5, a["speed"] + rng.uniform(-0.25, 0.25)),
                green_preference=clamp(a["green"] + jitter(), 0, 1),
                transit_preference=clamp(a["transit"] + jitter(), 0, 1),
                accessibility_need=clamp(a["access"] + jitter(), 0, 1),
            )
        )
    return citizens


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
    effective_access = clamp(route.accessibility + 0.15 * route_capacity_boost)

    # Population drives corridor crowding.
    pop_factor = 0.55 + 0.75 * norm(population, 25_000, 100_000)
    effective_crowd = clamp(route.base_crowding * pop_factor / (1 + route_capacity_boost))

    heat_penalty = hs * (1 - effective_shade) * (1 - citizen.heat_tolerance) * 8.0
    rain_penalty = rain * (1 - effective_drainage) * (1 - citizen.rain_tolerance) * 8.0
    crowd_penalty = effective_crowd * (1 - citizen.crowd_tolerance) * 6.0
    access_penalty = (1 - effective_access) * citizen.accessibility_need * 10.0
    transit_bonus = route.transit * citizen.transit_preference * 1.5
    green_bonus = effective_shade * citizen.green_preference * 1.2

    distance_cost = route.distance_km * 2.0

    total = (
        distance_cost
        + heat_penalty
        + rain_penalty
        + crowd_penalty
        + access_penalty
        - transit_bonus
        - green_bonus
    )

    return {
        "total": total,
        "distance": distance_cost,
        "heat": heat_penalty,
        "rain": rain_penalty,
        "crowd": crowd_penalty,
        "accessibility": access_penalty,
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
    seed: int = 42,
    citizen_count: int = 80,
    interventions: Optional[Dict] = None,
) -> Dict:

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

    # Apply city-level intervention changes.
    for z in city["zones"]:
        if interventions.get("shade_boost"):
            z.shade = clamp(z.shade + interventions["shade_boost"])
        if interventions.get("drainage_boost"):
            z.drainage = clamp(z.drainage + interventions["drainage_boost"])
        if interventions.get("accessibility_boost"):
            z.accessibility = clamp(z.accessibility + interventions["accessibility_boost"])

    hs = heat_stress(temperature, humidity)

    zone_rain = {
        z.id: zone_rain_impact(rainfall, z.drainage)
        for z in city["zones"]
    }
    rain = sum(zone_rain.values()) / len(zone_rain)

    # Route-level crowding and population scaling.
    route_crowding = {}
    for r in city["routes"]:
        route_crowding[r.id] = crowding_score(population, r.base_crowding)

    crowd = sum(route_crowding.values()) / len(route_crowding)

    # Interventions directly reduce exposure/stress in the prototype.
    effective_heat = clamp(hs * (1 - 0.30 * interventions.get("shade_boost", 0)))
    effective_rain = clamp(rain * (1 - 0.65 * interventions.get("drainage_boost", 0)))
    effective_crowd = clamp(
        crowd / (1 + 1.15 * interventions.get("route_capacity_boost", 0))
    )

    citizens = generate_citizens(population, citizen_count, seed)

    citizen_results = []
    route_counts = {r.id: 0 for r in city["routes"]}

    for c in citizens:
        chosen, costs = choose_route(
            c, city["routes"], temperature, humidity, rainfall, population, interventions
        )
        route_counts[chosen] += 1

        # Individual exposure is based on chosen route.
        route = next(r for r in city["routes"] if r.id == chosen)
        local_heat = effective_heat * (1 - clamp(route.shade + interventions.get("shade_boost", 0)))
        local_rain = effective_rain * (1 - clamp(route.drainage + interventions.get("drainage_boost", 0)))
        local_crowd = effective_crowd * (0.65 + 0.70 * route.base_crowding)

        personal_comfort = clamp(
            100
            - 0.52 * local_heat * (1 - c.heat_tolerance)
            - 0.24 * local_rain * (1 - c.rain_tolerance)
            - 0.24 * local_crowd * (1 - c.crowd_tolerance)
        )

        citizen_results.append({
            "id": c.id,
            "archetype": c.archetype,
            "route": chosen,
            "heat_exposure": round(local_heat, 2),
            "rain_exposure": round(local_rain, 2),
            "crowd_exposure": round(local_crowd, 2),
            "comfort": round(personal_comfort, 2),
            "route_cost": round(costs["total"], 2),
        })

    # Human-centric aggregate metrics.
    accessibility = clamp(
        100
        - 0.50 * effective_rain
        - 0.25 * effective_crowd
        - 25 * (1 - sum(z.accessibility for z in city["zones"]) / len(city["zones"]))
    )

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
    # Higher comfort/accessibility/safety/mobility is better.
    # Heat/crowd are penalties.
    hei = clamp(
        0.30 * comfort
        + 0.25 * accessibility
        + 0.15 * safety
        + 0.20 * mobility
        + 0.10 * (100 - effective_heat)
        - 0.10 * effective_crowd
    )

    # Identify problem zones/corridors for the Advisor.
    worst_zone = max(zone_rain, key=zone_rain.get)
    worst_route = max(route_crowding, key=route_crowding.get)

    problem_zones = [worst_zone]
    if effective_heat >= 60:
        problem_zones.append("Heat-exposed pedestrian corridors")
    if effective_crowd >= 65:
        problem_zones.append("High-crowding corridors")

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
            "accessibility": round(accessibility, 2),
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
                "accessibility": round(z.accessibility, 2),
                "rain_impact": round(zone_rain[z.id], 2),
            }
            for z in city["zones"]
        ],
        "routes": [
            {
                "id": r.id,
                "crowding": round(route_crowding[r.id], 2),
                "chosen_by_agents": route_counts[r.id],
            }
            for r in city["routes"]
        ],
        "citizens": citizen_results,
        "problem_zones": problem_zones,
        "interventions": interventions,
    }


# ---------------------------------------------------------------------------
# AI Urban Advisor
# ---------------------------------------------------------------------------

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

    if m["heat_stress"] >= 60:
        recommendations.append("increase_shade")
        reasons.append("High heat exposure is affecting pedestrian comfort.")

    # Thresholds are deliberately set for the hackathon's compound-stress
    # demo so that multiple interacting problems can be surfaced at once.
    if m["rain_impact"] >= 30:
        recommendations.append("improve_drainage")
        reasons.append("Rainfall is creating meaningful accessibility and safety penalties.")

    if m["crowding"] >= 55:
        recommendations.append("alternative_pedestrian_routes")
        reasons.append("Population-driven crowding is increasing route congestion.")

    if not recommendations:
        recommendations.append("no_major_intervention")
        reasons.append("All prototype stress indicators are below the intervention thresholds.")

    return {
        "summary": " ; ".join(reasons),
        "problem_zones": result["problem_zones"],
        "recommendations": recommendations,
        "explanation": reasons,
        "supported_interventions": {
            "increase_shade": {
                "changes": {"shade_boost": 0.25},
                "effect": "Reduces heat exposure and improves shaded-route attractiveness.",
            },
            "improve_drainage": {
                "changes": {"drainage_boost": 0.35},
                "effect": "Reduces rainfall impact and improves rain-time accessibility/safety.",
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

def run_demo() -> Dict:
    scenario = dict(
        temperature=40,
        humidity=80,
        rainfall=80,
        population=100_000,
    )

    before = simulate(**scenario)
    advisor = urban_advisor(before)
    intervention = recommended_interventions(advisor)
    after = simulate(**scenario, interventions=intervention)

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

def run_tests() -> None:
    assert heat_stress(20, 20) < heat_stress(40, 80)
    assert zone_rain_impact(80, 0.20) > zone_rain_impact(80, 0.90)
    assert crowding_score(100_000) > crowding_score(25_000)

    base = simulate(40, 80, 80, 100_000)
    shaded = simulate(40, 80, 80, 100_000, interventions={"shade_boost": 0.25})
    drained = simulate(40, 80, 80, 100_000, interventions={"drainage_boost": 0.35})
    rerouted = simulate(40, 80, 80, 100_000, interventions={"route_capacity_boost": 0.40})

    assert shaded["metrics"]["heat_stress"] < base["metrics"]["heat_stress"]
    assert drained["metrics"]["rain_impact"] < base["metrics"]["rain_impact"]
    assert rerouted["metrics"]["crowding"] < base["metrics"]["crowding"]

    # Determinism: same inputs/seed => same headline outputs.
    a = simulate(40, 80, 80, 100_000, seed=42)
    b = simulate(40, 80, 80, 100_000, seed=42)
    assert a["metrics"] == b["metrics"]
    assert a["routes"] == b["routes"]

    print("All tests passed.")


def print_demo_summary(demo: Dict) -> None:
    print("\n=== UrbanTwin AI — Compound Stress Demo ===")
    s = demo["scenario"]
    print(
        f"Scenario: {s['temperature']}°C | {s['humidity']}% RH | "
        f"{s['rainfall']} mm | population {s['population']:,}"
    )

    print("\nBEFORE")
    for k, v in demo["before"]["metrics"].items():
        print(f"  {k:26s}: {v:6.2f}")

    print("\nAI URBAN ADVISOR")
    for rec in demo["advisor"]["recommendations"]:
        print(f"  - {rec}")
    print(f"  Problem areas: {', '.join(demo['advisor']['problem_zones'])}")

    print("\nAPPLIED INTERVENTION")
    print(" ", demo["intervention"] or "none")

    print("\nAFTER")
    for k, v in demo["after"]["metrics"].items():
        print(f"  {k:26s}: {v:6.2f}")

    print("\nCHANGE (after - before)")
    for k, v in demo["delta"].items():
        sign = "+" if v >= 0 else ""
        print(f"  {k:26s}: {sign}{v:6.2f}")


if __name__ == "__main__":
    run_tests()
    demo = run_demo()
    print_demo_summary(demo)

    # Also save machine-readable output for Person 3 / dashboard integration.
    with open("urbantwin_demo_output.json", "w", encoding="utf-8") as f:
        json.dump(demo, f, indent=2)

    print("\nSaved: urbantwin_demo_output.json")
