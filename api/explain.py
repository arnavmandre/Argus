"""Constrained run explanations: bounded payload, deterministic default, optional LLM."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable

RECOMMENDATION_LABELS: dict[str, str] = {
    "increase_shade": "Increase shade",
    "improve_drainage": "Improve drainage",
    "alternative_pedestrian_routes": "Open alternative pedestrian routes",
    "no_major_intervention": "No major intervention needed",
}

_LLM_SYSTEM_PROMPT = (
    "You summarize UrbanTwin simulation results for operators. "
    "Use ONLY facts present in the user JSON payload. "
    "Do NOT invent metrics, locations, commands, interventions, effectiveness "
    "claims, or medical advice. "
    "If the payload is sparse, say so briefly. "
    "Write plain prose (no markdown headings)."
)

RouteProblemKeys = ("id", "from", "to", "via_zones", "crowding")
BuildingProblemKeys = ("id", "name", "zone", "issues")


def build_explanation_payload(report: dict) -> dict:
    """Extract a bounded, JSON-serializable payload from a simulator report."""
    before = report.get("before") if isinstance(report.get("before"), dict) else {}
    after = report.get("after") if isinstance(report.get("after"), dict) else {}
    advisor = report.get("advisor") if isinstance(report.get("advisor"), dict) else {}

    recommendations: list[dict[str, str]] = []
    for rid in advisor.get("recommendations") or []:
        if isinstance(rid, str):
            recommendations.append(
                {"id": rid, "label": RECOMMENDATION_LABELS.get(rid, rid)}
            )

    warnings_and_limitations: list[str] = []
    for key in ("warnings", "limitations"):
        block = report.get(key)
        if isinstance(block, list):
            warnings_and_limitations.extend(str(item) for item in block)
    explanation = advisor.get("explanation")
    if isinstance(explanation, list):
        warnings_and_limitations.extend(str(item) for item in explanation)

    problem_buildings: list[dict] = []
    for raw in before.get("problem_buildings") or []:
        if not isinstance(raw, dict):
            continue
        problem_buildings.append(
            {k: raw[k] for k in BuildingProblemKeys if k in raw}
        )

    problem_routes: list[dict] = []
    for raw in before.get("problem_routes") or []:
        if not isinstance(raw, dict):
            continue
        problem_routes.append({k: raw[k] for k in RouteProblemKeys if k in raw})

    scenario = report.get("scenario")
    if not isinstance(scenario, dict):
        scenario = {}

    before_metrics = before.get("metrics")
    after_metrics = after.get("metrics")
    if not isinstance(before_metrics, dict):
        before_metrics = {}
    if not isinstance(after_metrics, dict):
        after_metrics = {}

    return {
        "scenario": dict(scenario),
        "before_metrics": dict(before_metrics),
        "after_metrics": dict(after_metrics),
        "advisor_summary": str(advisor.get("summary") or ""),
        "recommendations": recommendations,
        "problem_zones": [
            str(z) for z in (before.get("problem_zones") or []) if z is not None
        ],
        "problem_buildings": problem_buildings,
        "problem_routes": problem_routes,
        "warnings_and_limitations": warnings_and_limitations,
        "citizen_counts": {
            "before": len(before.get("citizens") or []),
            "after": len(after.get("citizens") or []),
        },
    }


def explain_run(
    payload: dict,
    *,
    llm_callable: Callable[[dict], str] | None = None,
) -> dict:
    """Return an explanation envelope; default path is deterministic (no network)."""
    claims = _claims_from_payload(payload)
    if llm_callable is None:
        url = os.environ.get("URBANTWIN_LLM_URL", "").strip()
        if url:
            llm_callable = lambda p, u=url: _default_llm_call(u, p)

    if llm_callable is not None:
        try:
            text = llm_callable(payload)
            text = str(text).strip()
            if text:
                return {"source": "llm", "text": text, "claims": claims}
        except Exception as exc:  # noqa: BLE001 — fall back to deterministic
            return {
                "source": "deterministic",
                "text": _deterministic_text(payload),
                "claims": claims,
                "unavailable_reason": f"LLM request failed: {exc}",
            }

    return {
        "source": "deterministic",
        "text": _deterministic_text(payload),
        "claims": claims,
    }


def _claims_from_payload(payload: dict) -> list[str]:
    claims: list[str] = []
    scenario = payload.get("scenario") or {}
    if scenario:
        claims.append(
            "scenario:"
            + ",".join(f"{k}={scenario[k]}" for k in sorted(scenario))
        )
    for arm in ("before_metrics", "after_metrics"):
        metrics = payload.get(arm) or {}
        if isinstance(metrics, dict):
            for key in sorted(metrics):
                claims.append(f"{arm}:{key}={metrics[key]}")
    summary = payload.get("advisor_summary")
    if summary:
        claims.append(f"advisor_summary:{summary[:120]}")
    for rec in payload.get("recommendations") or []:
        if isinstance(rec, dict) and rec.get("id"):
            claims.append(f"recommendation:{rec['id']}")
    for zone in payload.get("problem_zones") or []:
        claims.append(f"problem_zone:{zone}")
    counts = payload.get("citizen_counts") or {}
    if counts:
        claims.append(
            f"citizen_counts:before={counts.get('before', 0)},"
            f"after={counts.get('after', 0)}"
        )
    return claims


def _deterministic_text(payload: dict) -> str:
    parts: list[str] = []
    scenario = payload.get("scenario") or {}
    if scenario:
        parts.append(
            "Scenario: "
            f"temperature {scenario.get('temperature')} °C, "
            f"humidity {scenario.get('humidity')} %, "
            f"rainfall {scenario.get('rainfall')} mm (prototype scale), "
            f"population equivalent {scenario.get('population')}."
        )

    before = payload.get("before_metrics") or {}
    after = payload.get("after_metrics") or {}
    if before or after:
        lines = []
        keys = sorted(set(before) | set(after))
        for key in keys:
            b = before.get(key)
            a = after.get(key)
            if a is not None and b is not None and a != b:
                lines.append(f"{key}: {b} → {a}")
            elif b is not None:
                lines.append(f"{key} (before): {b}")
            elif a is not None:
                lines.append(f"{key} (after): {a}")
        if lines:
            parts.append("Key metrics:\n" + "\n".join(lines))

    summary = payload.get("advisor_summary")
    if summary:
        parts.append(f"Advisor summary: {summary}")

    recs = payload.get("recommendations") or []
    if recs:
        labels = [
            r.get("label") or r.get("id")
            for r in recs
            if isinstance(r, dict)
        ]
        parts.append(
            "Recommendations (deterministic advisor; not LLM-authored): "
            + "; ".join(labels)
            + "."
        )

    zones = payload.get("problem_zones") or []
    if zones:
        parts.append("Problem zones named in the report: " + ", ".join(zones) + ".")

    buildings = payload.get("problem_buildings") or []
    if buildings:
        names = []
        for b in buildings[:8]:
            if isinstance(b, dict):
                label = b.get("name") or b.get("id")
                zone = b.get("zone")
                names.append(f"{label} ({zone})" if zone else str(label))
        suffix = "…" if len(buildings) > 8 else ""
        parts.append(
            "Problem buildings listed in the report: "
            + ", ".join(names)
            + suffix
        )

    routes = payload.get("problem_routes") or []
    if routes:
        ids = [
            str(r.get("id"))
            for r in routes[:6]
            if isinstance(r, dict) and r.get("id")
        ]
        suffix = "…" if len(routes) > 6 else ""
        parts.append("Problem routes listed in the report: " + ", ".join(ids) + suffix)

    notes = payload.get("warnings_and_limitations") or []
    if notes:
        parts.append(
            "Limitations and advisor notes from the report:\n"
            + "\n".join(f"• {n}" for n in notes[:6])
            + ("…" if len(notes) > 6 else "")
        )

    counts = payload.get("citizen_counts") or {}
    if counts.get("before") or counts.get("after"):
        parts.append(
            f"Simulated citizens in report: before arm {counts.get('before', 0)}, "
            f"after arm {counts.get('after', 0)} (counts only; no individual records "
            "in this explanation)."
        )

    if not parts:
        return (
            "No bounded explanation fields were present in the simulator report "
            "for this run."
        )
    return "\n\n".join(parts)


def _default_llm_call(url: str, payload: dict) -> str:
    body = {
        "messages": [
            {"role": "system", "content": _LLM_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:200]}") from exc

    parsed: Any = json.loads(raw)
    if isinstance(parsed, dict):
        if isinstance(parsed.get("text"), str):
            return parsed["text"]
        choices = parsed.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict) and isinstance(message.get("content"), str):
                    return message["content"]
                if isinstance(first.get("text"), str):
                    return first["text"]
    raise RuntimeError("LLM response did not contain recognizable text")
