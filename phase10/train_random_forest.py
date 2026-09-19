"""Train and honestly validate survey-response Random Forest models.

The split unit is participant, never response row. Eight people are held out
once for a final test; five-fold GroupKFold is run only on the remaining
participants. Every forest is compared with a simple baseline and with a
shuffled-label forest. Artifacts and a JSON model card are written to
phase10/models/.

This is a small-sample hackathon benchmark, not proof of real-world accuracy.
"""
from __future__ import annotations

import csv
import hashlib
import json
import warnings
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import (balanced_accuracy_score, f1_score,
                             mean_absolute_error, r2_score)
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

HERE = Path(__file__).resolve().parent
DATA = HERE / "data" / "urban_behavior_dataset.csv"
OUT = HERE / "models"
SEED = 29
HOLDOUT_PEOPLE = 8

NUMERIC = [
    "temperature_c", "crowd_density", "shade_percentage", "age_mid",
    "walking_frequency_code", "heat_sensitivity_code", "public_transport_code",
    "walking_speed_kmh", "green_space_influence", "travel_time_influence",
]
CATEGORICAL = ["rain_level", "green_space_level", "age_group"]
FEATURES = NUMERIC + CATEGORICAL
TARGETS = {
    "comfort": "regression",
    "stress": "regression",
    "walking_likelihood": "regression",
    "avoidance_likelihood": "regression",
    "route_choice": "classification",
}


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def load_rows():
    with DATA.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for key in NUMERIC:
            row[key] = float(row[key]) if row[key] != "" else np.nan
    return rows


def matrix(rows):
    return np.array([[r[k] for k in FEATURES] for r in rows], dtype=object)


def estimator(kind: str, seed: int = SEED):
    transform = ColumnTransformer([
        ("numeric", SimpleImputer(strategy="median"), list(range(len(NUMERIC)))),
        ("categorical", Pipeline([
            ("impute", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]), list(range(len(NUMERIC), len(FEATURES)))),
    ])
    forest = (RandomForestRegressor(
        n_estimators=500, min_samples_leaf=3, max_features=0.8,
        random_state=seed, n_jobs=-1,
    ) if kind == "regression" else RandomForestClassifier(
        n_estimators=500, min_samples_leaf=2, max_features="sqrt",
        class_weight="balanced_subsample", random_state=seed, n_jobs=-1,
    ))
    return Pipeline([("features", transform), ("forest", forest)])


def baseline(kind: str):
    model = DummyRegressor(strategy="median") if kind == "regression" else DummyClassifier(strategy="most_frequent")
    return Pipeline([("features", ColumnTransformer([
        ("numeric", SimpleImputer(strategy="median"), list(range(len(NUMERIC)))),
        ("categorical", OneHotEncoder(handle_unknown="ignore"), list(range(len(NUMERIC), len(FEATURES)))),
    ])), ("model", model)])


def score(kind, y_true, y_pred):
    if kind == "regression":
        return {"mae": float(mean_absolute_error(y_true, y_pred)),
                "r2": float(r2_score(y_true, y_pred)) if len(y_true) > 1 else None}
    # Tiny grouped folds can omit a rare class. That is recorded through the
    # low score and trust verdict; suppress sklearn's repetitive console warning.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return {"balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
                "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0))}


def average(items, key):
    vals = [x[key] for x in items if x.get(key) is not None]
    return float(np.mean(vals)) if vals else None


def better(kind, candidate, reference, margin=0.0):
    if kind == "regression":
        return candidate["mae"] < reference["mae"] * (1.0 - margin)
    return candidate["macro_f1"] > reference["macro_f1"] + margin


def main() -> None:
    OUT.mkdir(exist_ok=True)
    rows = load_rows()
    people = sorted({r["participant_id"] for r in rows})
    rng = np.random.default_rng(SEED)
    heldout = set(rng.choice(people, size=HOLDOUT_PEOPLE, replace=False).tolist())
    log(f"loaded {len(rows)} rows from {len(people)} participants")
    log(f"locked final holdout: {len(heldout)} participants; training pool: {len(people)-len(heldout)}")

    card = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "random_seed": SEED,
        "sklearn_version": sklearn.__version__,
        "dataset_sha256": hashlib.sha256(DATA.read_bytes()).hexdigest(),
        "split_policy": "participant-level; 8 final holdout people; 5-fold GroupKFold on remaining people",
        "limitations": [
            "Only 41 participants; most are under 25.",
            "Temperature, crowding and shade co-vary across the four scenarios.",
            "Labels are self-reported intentions, not observed pedestrian behavior.",
            "Avoidance and route-choice each have only one labeled scenario per participant.",
        ],
        "models": {},
    }

    for target, kind in TARGETS.items():
        labelled = [r for r in rows if r[target] != ""]
        train_rows = [r for r in labelled if r["participant_id"] not in heldout]
        test_rows = [r for r in labelled if r["participant_id"] in heldout]
        X, groups = matrix(train_rows), np.array([r["participant_id"] for r in train_rows])
        y = np.array([float(r[target]) for r in train_rows]) if kind == "regression" else np.array([r[target] for r in train_rows])
        X_test = matrix(test_rows)
        y_test = np.array([float(r[target]) for r in test_rows]) if kind == "regression" else np.array([r[target] for r in test_rows])
        log(f"{target}: {len(train_rows)} train rows, {len(test_rows)} unseen rows; starting grouped CV")

        folds, base_folds, shuffled_folds = [], [], []
        splitter = GroupKFold(n_splits=5)
        for fold, (a, b) in enumerate(splitter.split(X, y, groups), 1):
            if set(groups[a]) & set(groups[b]):
                raise RuntimeError("participant leakage detected")
            rf, dumb = estimator(kind, SEED + fold), baseline(kind)
            rf.fit(X[a], y[a]); dumb.fit(X[a], y[a])
            folds.append(score(kind, y[b], rf.predict(X[b])))
            base_folds.append(score(kind, y[b], dumb.predict(X[b])))
            shuffled = y[a].copy(); np.random.default_rng(SEED + 100 + fold).shuffle(shuffled)
            noise = estimator(kind, SEED + 200 + fold); noise.fit(X[a], shuffled)
            shuffled_folds.append(score(kind, y[b], noise.predict(X[b])))

        cv = ({"mae": average(folds, "mae"), "r2": average(folds, "r2")}
              if kind == "regression" else
              {"balanced_accuracy": average(folds, "balanced_accuracy"), "macro_f1": average(folds, "macro_f1")})
        cv_base = ({"mae": average(base_folds, "mae"), "r2": average(base_folds, "r2")}
                   if kind == "regression" else
                   {"balanced_accuracy": average(base_folds, "balanced_accuracy"), "macro_f1": average(base_folds, "macro_f1")})
        cv_shuffle = ({"mae": average(shuffled_folds, "mae"), "r2": average(shuffled_folds, "r2")}
                      if kind == "regression" else
                      {"balanced_accuracy": average(shuffled_folds, "balanced_accuracy"), "macro_f1": average(shuffled_folds, "macro_f1")})

        final, dumb = estimator(kind), baseline(kind)
        final.fit(X, y); dumb.fit(X, y)
        hold = score(kind, y_test, final.predict(X_test))
        hold_base = score(kind, y_test, dumb.predict(X_test))
        beats_baseline = better(kind, hold, hold_base) and better(kind, cv, cv_base)
        beats_shuffle = better(kind, cv, cv_shuffle)
        trust = "promising" if beats_baseline and beats_shuffle else "not_validated"
        if kind == "regression" and hold["mae"] <= 0.75 and beats_baseline and beats_shuffle:
            trust = "supported_for_prototype"
        log(f"{target}: CV={cv}; final_holdout={hold}; baseline={hold_base}; verdict={trust}")

        # Retrain the deployable artifact on all labeled rows only after the
        # untouched holdout score has been recorded in the model card.
        all_X = matrix(labelled)
        all_y = np.array([float(r[target]) for r in labelled]) if kind == "regression" else np.array([r[target] for r in labelled])
        deploy = estimator(kind); deploy.fit(all_X, all_y)
        artifact = OUT / f"{target}_random_forest.joblib"
        joblib.dump(deploy, artifact)
        card["models"][target] = {
            "kind": kind, "labelled_rows": len(labelled),
            "train_rows": len(train_rows), "final_holdout_rows": len(test_rows),
            "cv": cv, "cv_baseline": cv_base, "cv_shuffled_labels": cv_shuffle,
            "final_holdout": hold, "final_holdout_baseline": hold_base,
            "beats_baseline": beats_baseline, "beats_shuffled_labels": beats_shuffle,
            "trust_verdict": trust, "artifact": artifact.name,
            "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            "observed_classes": sorted(set(all_y.tolist())) if kind == "classification" else None,
        }

    card["overall_verdict"] = (
        "prototype_supported" if all(m["trust_verdict"] != "not_validated" for m in card["models"].values())
        else "mixed_results_do_not_claim_overall_accuracy"
    )
    (OUT / "model_card.json").write_text(json.dumps(card, indent=2), encoding="utf-8")
    lines = [
        "# UrbanTwin Random Forest validation report", "",
        f"Overall verdict: **{card['overall_verdict']}**", "",
        "The final test contains eight participants excluded from training and model selection.",
        "All cross-validation splits are also grouped by participant.", "",
        "| Target | Final unseen score | Baseline | Verdict |", "|---|---:|---:|---|",
    ]
    for name, item in card["models"].items():
        if item["kind"] == "regression":
            actual = f"MAE {item['final_holdout']['mae']:.2f}; R2 {item['final_holdout']['r2']:.2f}"
            base = f"MAE {item['final_holdout_baseline']['mae']:.2f}"
        else:
            actual = f"macro F1 {item['final_holdout']['macro_f1']:.2f}"
            base = f"macro F1 {item['final_holdout_baseline']['macro_f1']:.2f}"
        lines.append(f"| {name} | {actual} | {base} | {item['trust_verdict']} |")
    lines += ["", "## Interpretation", "",
              "A lower MAE is better for 1–5 survey scores; a higher macro F1 is better for route choice.",
              "A target is not accepted merely because it has a score: it must beat both the simple baseline and shuffled-label control in grouped cross-validation and beat the baseline on the untouched final participants.",
              "`supported_for_prototype` permits a hackathon demonstration with an explicit limitation. It does not establish city-wide or real-world predictive accuracy.",
              "", "## Known limitations", ""]
    lines.extend(f"- {x}" for x in card["limitations"])
    (OUT / "MODEL_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"complete: overall verdict={card['overall_verdict']}")
    log(f"artifacts and model card written to {OUT}")


if __name__ == "__main__":
    main()
