"""
Phase 10 step 2 - turn each participant's answers into simulator parameters.

The simulator needs six behavioural numbers per citizen. This derives them, per
participant, from the survey and records exactly which answers produced each.

    walking_speed_kmh   DIRECT   Q5, self-reported minutes per kilometre
    green_preference    DIRECT   Q8 green-space influence (1-5), nudged by the
                                 Q13 route choice
    transit_preference  DIRECT   Q4 public-transport frequency
    heat_tolerance      DERIVED  Q3 self-rated heat sensitivity + the comfort
                                 collapse from S01 to S03, attributed via Q19
    crowd_tolerance     DERIVED  stress in the medium-crowd scenario S02, the
                                 comfort collapse, and the Q13 route trade-off
    rain_tolerance      DERIVED  Q18 avoidance in the rain scenario S04,
                                 attributed via Q19

A LIMITATION THAT MATTERS
-------------------------
Scenarios S01 -> S02 -> S03 raise temperature AND crowding while lowering shade,
all at once. A comfort drop across them cannot, by itself, be attributed to any
one of the three - the design is confounded.

Two things partially rescue it:

  * Q3 measures heat sensitivity independently of any scenario.
  * Q19 asks which single factor would most drive the respondent to avoid the
    area, which attributes their compound reaction to a named cause.

So the compound slope is shared across the three axes, weighted toward whichever
factor the participant named. That is honest inference from a confounded design,
not a clean per-factor measurement - say so when presenting it. Adding two
decorrelating scenarios (hot-but-empty, cool-but-crowded) would fix it properly.

Run:  python phase10/fit_behaviour.py
Out:  phase10/data/participant_parameters.csv
"""
from __future__ import annotations

import csv
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
OUT = DATA / "participant_parameters.csv"

# How strongly the compound comfort collapse is attributed to each axis,
# depending on the single factor the participant named in Q19.
NAMED = 1.00        # they named this factor
UNNAMED = 0.45      # they did not - it still contributes, but less
FACTOR_AXIS = {
    "Extreme heat": "heat",
    "Heavy rainfall": "rain",
    "Crowding": "crowd",
    "Lack of shelter": "rain",          # shelter is asked in the rain scenario
    "Poor pedestrian infrastructure": None,
    "I would not avoid the area": None,
}

PARAMS = ["heat_tolerance", "rain_tolerance", "crowd_tolerance",
          "walking_speed_kmh", "green_preference", "transit_preference"]


def clamp(x, lo=0.02, hi=0.98):
    return max(lo, min(hi, x))


def num(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load():
    with (DATA / "participants.csv").open(encoding="utf-8") as f:
        participants = {r["participant_id"]: r for r in csv.DictReader(f)}
    responses = {}
    with (DATA / "responses.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            responses.setdefault(r["participant_id"], {})[r["scenario_id"]] = r
    return participants, responses


def main() -> None:
    participants, responses = load()

    # Medians for imputing the handful of blank answers.
    def median_of(getter):
        vals = [v for v in (getter(p) for p in participants.values()) if v is not None]
        return statistics.median(vals) if vals else 0.0

    med_green = median_of(lambda p: num(p["green_space_influence"]))
    med_speed = median_of(lambda p: num(p["walking_speed_kmh"]))

    rows, imputed = [], {"green": 0, "speed": 0, "comfort": 0, "stress": 0, "avoid": 0}

    for pid, p in participants.items():
        r = responses.get(pid, {})
        s1, s2, s3, s4 = (r.get("S01", {}), r.get("S02", {}),
                          r.get("S03", {}), r.get("S04", {}))

        # --- direct measures ------------------------------------------
        speed = num(p["walking_speed_kmh"])
        if speed is None:
            speed, imputed["speed"] = med_speed, imputed["speed"] + 1

        green_raw = num(p["green_space_influence"])
        if green_raw is None:
            green_raw, imputed["green"] = med_green, imputed["green"] + 1
        green = (green_raw - 1) / 4.0

        transit_code = num(p["public_transport_code"], 0.0)
        transit = transit_code / 3.0

        # Choosing a longer shaded/less-crowded route is itself a preference
        # signal: it nudges greenery up and crowd tolerance down.
        choice = (s2.get("route_choice") or "").lower()
        route_shaded = 1.0 if "shaded" in choice else 0.5 if "depends" in choice else 0.0
        green = clamp(0.75 * green + 0.25 * route_shaded)

        # --- the compound collapse -------------------------------------
        c1, c3 = num(s1.get("comfort")), num(s3.get("comfort"))
        if c1 is None or c3 is None:
            env_sens, imputed["comfort"] = 0.5, imputed["comfort"] + 1
        else:
            env_sens = max(0.0, min(1.0, (c1 - c3) / 4.0))

        stress2 = num(s2.get("stress"))
        if stress2 is None:
            stress2, imputed["stress"] = 3.0, imputed["stress"] + 1
        stress_norm = (stress2 - 1) / 4.0

        avoid = num(s4.get("avoidance_likelihood"))
        if avoid is None:
            avoid, imputed["avoid"] = 3.0, imputed["avoid"] + 1
        avoid_norm = (avoid - 1) / 4.0

        axis = FACTOR_AXIS.get(s4.get("avoid_factor", ""), None)
        w = {a: (NAMED if axis == a else UNNAMED) for a in ("heat", "crowd", "rain")}

        # --- derived tolerances ----------------------------------------
        heat_self = (num(p["heat_sensitivity_code"], 2.0) - 1) / 2.0    # 0, .5, 1
        heat_discomfort = 0.50 * heat_self + 0.50 * env_sens * w["heat"]

        crowd_discomfort = (0.40 * stress_norm
                            + 0.30 * env_sens * w["crowd"]
                            + 0.30 * route_shaded)

        rain_discomfort = avoid_norm * (0.60 + 0.40 * w["rain"])

        rows.append({
            "participant_id": pid,
            "age_group": p["age_group"],
            "heat_sensitivity": p["heat_sensitivity"],
            "walking_frequency": p["walking_frequency"],
            "heat_tolerance": round(clamp(1.0 - heat_discomfort), 3),
            "rain_tolerance": round(clamp(1.0 - rain_discomfort), 3),
            "crowd_tolerance": round(clamp(1.0 - crowd_discomfort), 3),
            "walking_speed_kmh": round(speed, 2),
            "green_preference": round(green, 3),
            "transit_preference": round(clamp(transit), 3),
            "env_sensitivity": round(env_sens, 3),
            "named_factor": s4.get("avoid_factor", ""),
        })

    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    print(f"fitted {len(rows)} participants -> {OUT}")
    print(f"imputed blanks: {({k: v for k, v in imputed.items() if v}) or 'none'}\n")
    for key in PARAMS:
        vals = [r[key] for r in rows]
        print(f"  {key:20s} mean {statistics.mean(vals):5.2f}  "
              f"sd {statistics.pstdev(vals):5.2f}  "
              f"range {min(vals):.2f}-{max(vals):.2f}")

    # Correlations are what the synthetic population must preserve.
    print("\n  correlations worth preserving:")
    for a, b in (("heat_tolerance", "crowd_tolerance"),
                 ("heat_tolerance", "green_preference"),
                 ("walking_speed_kmh", "crowd_tolerance"),
                 ("rain_tolerance", "crowd_tolerance")):
        xa, xb = [r[a] for r in rows], [r[b] for r in rows]
        try:
            print(f"    {a} vs {b}: {statistics.correlation(xa, xb):+.2f}")
        except statistics.StatisticsError:
            print(f"    {a} vs {b}: undefined (no variance)")


if __name__ == "__main__":
    main()
