"""
Phase 10 step 3 - grow 41 real participants into a synthetic population.

The rule from the brief: do not copy one real person a thousand times. Learn the
population-level pattern and sample from it.

Method - a Gaussian copula:

  1. Push each bounded parameter through a logit so it lives on the whole real
     line (walking speed is standardised instead, it is not a 0-1 quantity).
  2. Estimate the mean vector AND the full covariance matrix across the 41
     fitted participants.
  3. Draw from that multivariate normal.
  4. Invert the transforms to land back in range.

Step 2 is the point. Sampling each parameter independently would manufacture
citizens who are heat-sensitive AND crowd-loving AND fast-walking - combinations
nobody in the sample exhibited. The covariance keeps the real structure, e.g.
the observed -0.30 between heat tolerance and green preference: people who
suffer in heat care more about trees.

Categorical traits (age band, self-rated heat sensitivity) are drawn from the
observed frequencies, conditioned so that an elderly citizen does not come out
walking at 6.7 km/h.

Run:  python phase10/generate_citizens.py [--count 1000] [--seed 7]
Out:  phase10/data/synthetic_citizens.csv
      Simulation/citizens_survey.json   (simulator schema, ready to run)
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = HERE / "data"
FITTED = DATA / "participant_parameters.csv"
OUT_CSV = DATA / "synthetic_citizens.csv"
OUT_JSON = ROOT / "Simulation" / "citizens_survey.json"

UNIT = ["heat_tolerance", "rain_tolerance", "crowd_tolerance",
        "green_preference", "transit_preference"]
SPEED = "walking_speed_kmh"
SPEED_RANGE = (1.8, 7.2)

# Archetype naming is a reporting label only - it never feeds the simulation.
def archetype(row) -> str:
    if row["age_mid"] >= 60:
        return "Elderly citizen"
    if row[SPEED] < 3.6:
        return "Mobility-limited citizen"
    if row["transit_preference"] > 0.6:
        return "Transit-dependent citizen"
    if row["heat_tolerance"] > 0.72:
        return "Outdoor worker"
    if row["age_mid"] <= 24:
        return "Student"
    if row["green_preference"] > 0.85:
        return "Family / parent"
    return "General pedestrian"


def logit(p, eps=1e-3):
    p = np.clip(p, eps, 1 - eps)
    return np.log(p / (1 - p))


def expit(x):
    return 1.0 / (1.0 + np.exp(-x))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--count", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=7,
                    help="fixed so the population is reproducible")
    args = ap.parse_args()

    with FITTED.open(encoding="utf-8") as f:
        fitted = list(csv.DictReader(f))
    if len(fitted) < 5:
        raise SystemExit("not enough fitted participants to estimate a covariance")
    print(f"{len(fitted)} real participants -> {args.count} synthetic citizens")

    AGE_MID = {"Under 18": 16, "18-24": 21, "25-34": 29, "35-44": 39,
               "45-59": 52, "60+": 66}

    # --- observed joint distribution ------------------------------------
    unit_obs = np.array([[float(r[k]) for k in UNIT] for r in fitted])
    speed_obs = np.array([float(r[SPEED]) for r in fitted])

    z = np.column_stack([logit(unit_obs), speed_obs])
    mean = z.mean(axis=0)
    # rowvar=False -> columns are variables. Small sample, so nudge the diagonal
    # to keep the matrix positive definite for the Cholesky factor.
    cov = np.cov(z, rowvar=False) + np.eye(z.shape[1]) * 1e-6

    rng = np.random.default_rng(args.seed)
    draws = rng.multivariate_normal(mean, cov, size=args.count)

    unit_new = expit(draws[:, :len(UNIT)])
    speed_new = np.clip(draws[:, len(UNIT)], *SPEED_RANGE)

    # --- categorical traits from observed frequencies --------------------
    ages = [r["age_group"] for r in fitted]
    age_counts = collections.Counter(ages)
    age_labels = list(age_counts)
    age_p = np.array([age_counts[a] for a in age_labels], dtype=float)
    age_p /= age_p.sum()
    age_draw = rng.choice(len(age_labels), size=args.count, p=age_p)

    # Older citizens should not inherit a young walking speed. Shift each
    # sampled speed toward the observed mean for its own age band.
    band_speed = collections.defaultdict(list)
    for r in fitted:
        band_speed[r["age_group"]].append(float(r[SPEED]))
    band_mean = {a: float(np.mean(v)) for a, v in band_speed.items()}
    overall = float(speed_obs.mean())

    rows = []
    for i in range(args.count):
        age = age_labels[age_draw[i]]
        shift = band_mean.get(age, overall) - overall
        speed = float(np.clip(speed_new[i] + 0.7 * shift, *SPEED_RANGE))
        row = {
            "citizen_id": f"C{i + 1:05d}",
            "age_group": age,
            "age_mid": AGE_MID.get(age, 30),
            SPEED: round(speed, 2),
        }
        for j, k in enumerate(UNIT):
            row[k] = round(float(unit_new[i, j]), 3)
        row["archetype"] = archetype(row)
        rows.append(row)

    fields = ["citizen_id", "archetype", "age_group", "age_mid", SPEED] + UNIT
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    # --- simulator schema -------------------------------------------------
    # home/destination are filled in by whichever city file this is run against;
    # assign_homes.py does that. Written here without them would fail validation,
    # so emit the behavioural half only and let the assigner place them.
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "description": (
            "Synthetic citizens calibrated to 41 real survey participants "
            "(Gaussian copula over logit-transformed parameters, preserving the "
            "observed covariance). Behavioural parameters only - run "
            "phase10/assign_homes.py to attach home/destination for a given "
            "city file. Prototype calibration, not a validated behavioural model."
        ),
        "source": {
            "participants": len(fitted),
            "scenarios_per_participant": 4,
            "observations": len(fitted) * 4,
            "method": "gaussian copula on logit-transformed fitted parameters",
            "seed": args.seed,
        },
        "citizens": [
            {"id": r["citizen_id"], "archetype": r["archetype"],
             "age_group": r["age_group"],
             **{k: r[k] for k in UNIT}, SPEED: r[SPEED], "weight": 1.0}
            for r in rows
        ],
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {OUT_CSV}")
    print(f"wrote {OUT_JSON}\n")
    for k in UNIT + [SPEED]:
        real = np.array([float(r[k]) for r in fitted])
        syn = np.array([r[k] for r in rows])
        print(f"  {k:20s} real {real.mean():5.2f}+-{real.std():4.2f}   "
              f"synthetic {syn.mean():5.2f}+-{syn.std():4.2f}")
    print("\n  archetypes:", dict(collections.Counter(r["archetype"] for r in rows)))
    print("\nNext: python phase10/assign_homes.py   (attach home/destination)")


if __name__ == "__main__":
    main()
