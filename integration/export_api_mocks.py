"""
Adapter: simulator report -> frontend mock API responses.

The web frontend in `frontend/` is built against the *proposed* HTTP API in
docs/FRONTEND_BACKEND_HANDOFF.md. That API does not exist yet: there is no
FastAPI service, no job queue and no run store. So that the dashboard is not
built against invented numbers, this script records the real simulator report
as fixtures shaped exactly like the proposed endpoints.

    Simulation/urbantwin_demo_output.json   (the real run, 0-100 metrics)
        -> THIS SCRIPT
        -> frontend/mocks/*.json            (recorded API responses)
        -> frontend/app/api/*               (route handlers serving them)

Every fixture is labelled `"source": "recorded_fixture"` and `/api/health`
reports `mode: "mock"` with every capability false, so the UI can never present
a recorded run as a live backend. When the Python API is built, point
`URBANTWIN_API_BASE` at it and the same route handlers proxy instead.

This script does NOT invent data. Metrics, advisor text, problem places and
behaviour counts are copied from the report; only the API envelope (run ids,
status, pagination, warnings) is added here.

Run:
    python integration/export_api_mocks.py
    python integration/export_api_mocks.py --report Simulation/urbantwin_demo_output.json
"""
from __future__ import annotations

import argparse
import collections
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_REPORT = ROOT / "Simulation" / "urbantwin_demo_output.json"
DEFAULT_MODEL_CARD = ROOT / "phase10" / "models" / "model_card.json"
DEFAULT_OUT = ROOT / "frontend" / "mocks"

RUN_ID = "run_20260919_001"
CITIZEN_SAMPLE = 200     # the report holds 1000; the fixture must stay small
AGENT_CAP = 500          # phase3 schema limit on rendered agents

BEHAVIORS = (
    "CONTINUE",
    "STRESSED",
    "SEEK_SHADE",
    "SEEK_SHELTER",
    "REROUTE",
    "AVOID_AREA",
)

# Kept verbatim from CLAUDE.md / the handoff. The UI renders these; it must not
# write its own version of them.
RUN_WARNINGS = [
    "Recorded fixture: these numbers come from a real run of Simulation/main.py "
    "on city_osm.json, replayed by the mock API. No simulator process ran for "
    "this request.",
    "Environmental, comfort and intervention formulas are heuristic prototypes, "
    "not medical, meteorological, hydraulic or engineering models.",
    "Population is a population equivalent, not a headcount. At most 500 "
    "representative agents are rendered; 1,000 citizens are simulated.",
    "Citizen behavioural parameters are calibrated from 41 survey participants, "
    "but the survey scenarios confound temperature, crowding and shade. Home and "
    "destination placement is a heuristic, not survey data.",
    "Building heights: 223 of 623 meshes come from OSM data; the rest are "
    "inferred from building class or interpolated from neighbours.",
    "The animation interpolates positions between 60 fixed snapshots. It is not "
    "a time-evolving behavioural or collision simulation.",
]


def behavior_counts(citizens):
    """All six behaviours, zero-filled. The legend shows the full palette."""
    seen = collections.Counter(c["behavior"] for c in citizens)
    unknown = set(seen) - set(BEHAVIORS)
    if unknown:
        raise SystemExit(f"report contains unknown behaviours: {sorted(unknown)}")
    return {b: seen.get(b, 0) for b in BEHAVIORS}


def state_summary(state):
    """SimulationState -> the frontend-sized slice of RunSummary."""
    return {
        "metrics": state["metrics"],
        "behavior_counts": behavior_counts(state["citizens"]),
        "problem_zones": state["problem_zones"],
        "problem_buildings": state["problem_buildings"],
        "problem_routes": state["problem_routes"],
        "citizen_count": len(state["citizens"]),
        "interventions": state["interventions"],
    }


def run_summary(report, generated_at, run_id):
    before, after = report["before"], report["after"]
    control = report["control"]
    return {
        "run_id": run_id,
        "status": "complete",
        "source": "recorded_fixture",
        "created_utc": generated_at,
        "scenario": report["scenario"],
        "before": state_summary(before),
        "advisor": report["advisor"],
        "intervention": report["intervention"],
        "after": state_summary(after),
        "delta": report["delta"],
        # The calm-weather control arm of the same report. Not a second run:
        # the simulator emits metrics and recommendations for it, nothing more.
        "control_reference": {
            "scenario": control["scenario"],
            "metrics": control["metrics"],
            "recommendations": control["recommendations"],
        },
        "city": {
            "name": "Russell Square, London",
            "source": "OpenStreetMap",
            "zones": len(before["zones"]),
            "simulation_buildings": len(before["buildings"]),
            "routes": len(before["routes"]),
            "visual_buildings": 623,
            "visual_trees": 511,
            "rendered_agent_cap": AGENT_CAP,
        },
        "artifacts": {
            "omniverse_stage": "phase9/scene/main.usda",
            "snapshot_pattern": "data/simulation_before_*.json",
        },
        "advisor_source": {
            "kind": "deterministic_rules",
            "label": "Deterministic threshold advisor (Simulation/main.py)",
            "detail": "Not an LLM. The simulator is the only authority for "
                      "metrics and intervention effectiveness.",
        },
        "warnings": list(RUN_WARNINGS),
    }


def citizen_page_fixture(report, generated_at, run_id):
    """A bounded slice per state. The full 1000 records never reach the browser."""
    states = {}
    for name in ("before", "after"):
        citizens = report[name]["citizens"]
        states[name] = {
            "items": citizens[:CITIZEN_SAMPLE],
            "total_in_run": len(citizens),
            "included_in_fixture": min(CITIZEN_SAMPLE, len(citizens)),
        }
    return {
        "run_id": run_id,
        "source": "recorded_fixture",
        "created_utc": generated_at,
        "states": states,
    }


def scenarios_fixture(run_id):
    """Ranges are the simulator's accepted inputs, per the handoff."""
    return {
        "source": "recorded_fixture",
        "constraints": {
            "temperature": [-10, 45],
            "humidity": [20, 90],
            "rainfall": [0, 100],
            "population": [25000, 100000],
        },
        "units": {
            "temperature": "\u00b0C",
            "humidity": "%",
            "rainfall": "mm (prototype scale)",
            "population": "population equivalent",
        },
        "presets": [
            {
                "id": "baseline",
                "label": "Calm day",
                "description": "The control arm of the recorded report.",
                "temperature": 26,
                "humidity": 40,
                "rainfall": 5,
                "population": 30000,
            },
            {
                "id": "extreme_heat_rain",
                "label": "Extreme heat and rain",
                "description": "The recorded run with full before/after data.",
                "temperature": 40,
                "humidity": 80,
                "rainfall": 80,
                "population": 100000,
            },
        ],
        "recorded_scenario": {
            "run_id": run_id,
            "temperature": 40,
            "humidity": 80,
            "rainfall": 80,
            "population": 100000,
        },
    }


def health_fixture(generated_at):
    """Mock mode. Every capability is false so the UI cannot claim otherwise."""
    return {
        "status": "mock",
        "mode": "mock",
        "source": "recorded_fixture",
        "checked_utc": generated_at,
        "simulator": False,
        "omniverse_stream": "offline",
        "model_card": True,
        "capabilities": {
            "http_api": False,
            "live_simulation": False,
            "omniverse_streaming": False,
            "llm_advisor": False,
            "random_forest_inference": False,
            "run_persistence": False,
        },
        "notes": [
            "No Python HTTP API is running. Responses are recorded fixtures "
            "exported by integration/export_api_mocks.py.",
            "No streaming-enabled Kit application exists yet, so the viewport "
            "shows a recorded-stage placeholder rather than an RTX stream.",
            "The Random Forest models are trained but not wired into the "
            "simulator; the simulator still uses transparent rules.",
        ],
    }


def stream_config_fixture(generated_at):
    return {
        "status": "offline",
        "source": "recorded_fixture",
        "checked_utc": generated_at,
        "signaling_url": None,
        "ice_servers": [],
        "session_token": None,
        "stage": "phase9/scene/main.usda",
        "reason": "No urbantwin.streaming.kit application is configured. NVIDIA "
                  "Kit App Streaming has not been set up for this project yet.",
        "desktop_fallback": ".\\repo.bat launch -n urbantwin.kit",
        "references": [
            "https://docs.omniverse.nvidia.com/ov-web-sdk/latest/index.html",
            "https://docs.omniverse.nvidia.com/kit/docs/kit-app-template/108.0/docs/streaming.html",
        ],
    }


def model_card_fixture(card, generated_at):
    """Sanitized subset: verdicts, holdout scores, limitations. No artifact hashes."""
    models = []
    for target, m in card["models"].items():
        entry = {
            "target": target,
            "kind": m["kind"],
            "trust_verdict": m["trust_verdict"],
            "labelled_rows": m["labelled_rows"],
            "final_holdout_rows": m["final_holdout_rows"],
            "final_holdout": m["final_holdout"],
            "final_holdout_baseline": m["final_holdout_baseline"],
            "beats_baseline": m["beats_baseline"],
            "beats_shuffled_labels": m["beats_shuffled_labels"],
        }
        if m.get("observed_classes"):
            entry["observed_classes"] = m["observed_classes"]
        models.append(entry)
    return {
        "source": "recorded_fixture",
        "exported_utc": generated_at,
        "created_utc": card["created_utc"],
        "sklearn_version": card["sklearn_version"],
        "random_seed": card["random_seed"],
        "split_policy": card["split_policy"],
        "overall_verdict": card["overall_verdict"],
        "limitations": card["limitations"],
        "models": models,
        "wired_into_simulator": False,
        "survey": {
            "participants": 41,
            "scenario_response_rows": 164,
            "synthetic_citizens": 1000,
            "holdout_people": 5,
            "note": "A fresh generator fitted on 36 participants was checked "
                    "against five unseen people. This supports distributional "
                    "consistency, not prediction of an individual's behaviour.",
        },
    }


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    kb = path.stat().st_size / 1024
    print(f"  {path.relative_to(ROOT).as_posix():<52} {kb:7.1f} KB")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--model-card", type=Path, default=DEFAULT_MODEL_CARD)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--run-id", default=RUN_ID)
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    card = json.loads(args.model_card.read_text(encoding="utf-8"))
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    print(f"report     {args.report.relative_to(ROOT).as_posix()}")
    print(f"scenario   {report['scenario']}")
    print(f"citizens   {len(report['before']['citizens'])} simulated, "
          f"{CITIZEN_SAMPLE} recorded per state")
    print("writing:")

    out = args.out
    write(out / "health.json", health_fixture(generated_at))
    write(out / "scenarios.json", scenarios_fixture(args.run_id))
    write(out / "stream-config.json", stream_config_fixture(generated_at))
    write(out / "model-card.json", model_card_fixture(card, generated_at))
    write(out / "runs" / f"{args.run_id}.json",
          run_summary(report, generated_at, args.run_id))
    write(out / "runs" / f"{args.run_id}.citizens.json",
          citizen_page_fixture(report, generated_at, args.run_id))

    before = behavior_counts(report["before"]["citizens"])
    after = behavior_counts(report["after"]["citizens"])
    print(f"behaviour  before {before}")
    print(f"           after  {after}")
    print("done. The frontend serves these through frontend/app/api/*.")


if __name__ == "__main__":
    main()
