"""
Phase 10 step 1 - turn the raw Google Form export into the four-table dataset.

Reads `Survey DATA (1).xlsx` (one row per respondent, wide format) and writes
the normalised tables the rest of the pipeline expects:

    phase10/data/participants.csv              who they are
    phase10/data/scenarios.csv                 the four environments shown
    phase10/data/responses.csv                 long format: one row per
                                               participant x scenario
    phase10/data/urban_behavior_dataset.csv    the three joined together

No behavioural modelling happens here - this step only reshapes and encodes.
Human-readable values are kept alongside the numeric encodings so the raw
answers stay auditable.

Privacy: the export's only identifying column is the form Timestamp, which is
dropped. Participants become P001..Pnnn in submission order.

Run:  python phase10/ingest_survey.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE = ROOT / "Survey DATA (1).xlsx"
DATA = HERE / "data"

# --- the four environments the form described, in the order it asked them ---
# Values restate the scenario text shown to respondents; they were not typed in
# by participants.
SCENARIOS = [
    # id,  temp, rain,    crowd, shade, green
    ("S01", 28, "None", 20, 80, "High"),
    ("S02", 35, "None", 50, 50, "Medium"),
    ("S03", 42, "None", 85, 15, "Low"),
    ("S04", 40, "Heavy", 85, 15, "Low"),
]

# Which spreadsheet column answers which question, per scenario.
# Column indices are 0-based into the raw row.
SCENARIO_COLUMNS = {
    "S01": {"comfort": 8, "walking_likelihood": 9},
    "S02": {"comfort": 10, "stress": 11, "route_choice": 12},
    "S03": {"comfort": 13, "stress": 14, "walking_likelihood": 15,
            "improvement_choice": 16},
    "S04": {"avoidance_likelihood": 17, "avoid_factor": 18},
}

PARTICIPANT_COLUMNS = {
    "age_group": 1,
    "walking_frequency": 2,
    "heat_sensitivity": 3,
    "public_transport_usage": 4,
    "walk_pace_per_km": 5,
    "travel_time_influence": 6,
    "green_space_influence": 7,
    "quality_of_life": 19,
    "priority_improvement": 20,
}

# --- encodings (section 8 of the brief) -----------------------------------
WALK_FREQ = {"Rarely": 0, "1-2 times per week": 1, "3-5 times per week": 2, "Daily": 3}
HEAT_SENS = {"Low": 1, "Moderate": 2, "High": 3}
TRANSIT_FREQ = {"Never/ Rarely": 0, "Never/Rarely": 0, "1-2 times per week": 1,
                "3-5 times per week": 2, "Daily": 3}
# Self-reported minutes per kilometre -> km/h, using the band midpoint.
PACE_KMH = {"<10 minutes": 6.7, "10-12 minutes": 5.5, "13-15 minutes": 4.3,
            "16-20 minutes": 3.3, ">20 minutes": 2.6}
AGE_MID = {"Under 18": 16, "18-24": 21, "25-34": 29, "35-44": 39,
           "45-59": 52, "60+": 66}


def clean(value):
    if value is None:
        return ""
    return str(value).strip()


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"survey export not found: {SOURCE}")
    DATA.mkdir(parents=True, exist_ok=True)

    rows = list(openpyxl.load_workbook(SOURCE, data_only=True)["Form Responses 1"].values)
    header, records = rows[0], [r for r in rows[1:] if any(v is not None for v in r)]
    print(f"{len(records)} responses read from {SOURCE.name}")

    # --- scenarios.csv --------------------------------------------------
    with (DATA / "scenarios.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["scenario_id", "temperature_c", "rain_level", "crowd_density",
                    "shade_percentage", "green_space_level"])
        w.writerows(SCENARIOS)

    # --- participants.csv -----------------------------------------------
    participants = []
    for i, rec in enumerate(records, start=1):
        pid = f"P{i:03d}"
        raw = {k: clean(rec[c]) for k, c in PARTICIPANT_COLUMNS.items()}
        participants.append({
            "participant_id": pid,
            "age_group": raw["age_group"],
            "age_mid": AGE_MID.get(raw["age_group"], ""),
            "walking_frequency": raw["walking_frequency"],
            "walking_frequency_code": WALK_FREQ.get(raw["walking_frequency"], ""),
            "heat_sensitivity": raw["heat_sensitivity"],
            "heat_sensitivity_code": HEAT_SENS.get(raw["heat_sensitivity"], ""),
            "public_transport_usage": raw["public_transport_usage"],
            "public_transport_code": TRANSIT_FREQ.get(raw["public_transport_usage"], ""),
            "walk_pace_per_km": raw["walk_pace_per_km"],
            "walking_speed_kmh": PACE_KMH.get(raw["walk_pace_per_km"], ""),
            "travel_time_influence": number(rec[6]) or "",
            "green_space_influence": number(rec[7]) or "",
            "quality_of_life": number(rec[19]) or "",
            "priority_improvement": raw["priority_improvement"],
        })

    with (DATA / "participants.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(participants[0]))
        w.writeheader()
        w.writerows(participants)

    # --- responses.csv (long) -------------------------------------------
    fields = ["participant_id", "scenario_id", "comfort", "stress",
              "walking_likelihood", "avoidance_likelihood", "route_choice",
              "improvement_choice", "avoid_factor"]
    responses = []
    for i, rec in enumerate(records, start=1):
        pid = f"P{i:03d}"
        for sid, cols in SCENARIO_COLUMNS.items():
            row = {"participant_id": pid, "scenario_id": sid}
            for field in fields[2:]:
                col = cols.get(field)
                if col is None:
                    row[field] = ""
                    continue
                value = rec[col]
                row[field] = (number(value) if field in
                              ("comfort", "stress", "walking_likelihood",
                               "avoidance_likelihood") else clean(value))
                if row[field] is None:
                    row[field] = ""
            responses.append(row)

    with (DATA / "responses.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(responses)

    # --- joined dataset --------------------------------------------------
    scen = {s[0]: s for s in SCENARIOS}
    by_pid = {p["participant_id"]: p for p in participants}
    joined_fields = (list(participants[0]) +
                     ["scenario_id", "temperature_c", "rain_level", "crowd_density",
                      "shade_percentage", "green_space_level"] + fields[2:])
    with (DATA / "urban_behavior_dataset.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=joined_fields)
        w.writeheader()
        for r in responses:
            s = scen[r["scenario_id"]]
            out = dict(by_pid[r["participant_id"]])
            out.update({"scenario_id": s[0], "temperature_c": s[1], "rain_level": s[2],
                        "crowd_density": s[3], "shade_percentage": s[4],
                        "green_space_level": s[5]})
            out.update({k: r[k] for k in fields[2:]})
            w.writerow(out)

    # --- completeness report ---------------------------------------------
    missing = {k: sum(1 for p in participants if p[k] in ("", None))
               for k in participants[0] if k != "participant_id"}
    missing = {k: v for k, v in missing.items() if v}
    rated = sum(1 for r in responses if r["comfort"] != "")
    print(f"wrote {DATA/'participants.csv'} ({len(participants)} rows)")
    print(f"wrote {DATA/'scenarios.csv'} ({len(SCENARIOS)} rows)")
    print(f"wrote {DATA/'responses.csv'} ({len(responses)} rows, "
          f"{rated} carrying a comfort rating)")
    print(f"wrote {DATA/'urban_behavior_dataset.csv'}")
    print(f"missing participant fields: {missing or 'none'}")
    print("\nNote: S04 was asked only about avoidance, so it carries no comfort or "
          "stress rating. Rain sensitivity is therefore identified from the "
          "avoidance question, not from a comfort contrast.")


if __name__ == "__main__":
    main()
