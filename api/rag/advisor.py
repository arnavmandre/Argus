"""Grounded intervention ranking with strict validation and fallback."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Callable

from api.explain import build_explanation_payload
from api.rag.retrieval import KnowledgeRetriever

ALLOWED_RECOMMENDATION_IDS = frozenset({
    "increase_shade", "improve_drainage",
    "alternative_pedestrian_routes", "no_major_intervention",
})
MODEL_NAME = "openai/gpt-oss-120b"
SYSTEM_PROMPT = """You are the Argus AI urban-planning decision-support advisor.
Use simulation numbers only from simulator_evidence and intervention knowledge only
from retrieved_knowledge. Do not invent metrics, locations, evidence, effectiveness,
cost, ROI, or post-intervention outcomes. Only use allowed_recommendation_ids when
testable is true. Rank candidates for simulator testing; do not claim they work.
Return one JSON object only, with primary_problem and recommendations."""

_CACHE: dict[str, dict] = {}


def build_retrieval_query(payload: dict) -> str:
    scenario = payload.get("scenario") or {}
    metrics = payload.get("before_metrics") or {}
    fragments = [
        f"temperature {scenario.get('temperature')} heat exposure heat stress",
        f"rainfall {scenario.get('rainfall')} rain flooding drainage rain impact",
        f"population {scenario.get('population')} crowding congestion pedestrian route",
        str(payload.get("advisor_summary") or ""),
        "problem zones " + " ".join(payload.get("problem_zones") or []),
        "metrics " + " ".join(f"{key} {value}" for key, value in metrics.items()),
    ]
    return ". ".join(fragments)


def advise_run(
    report: dict,
    *,
    root: Path,
    top_k: int = 5,
    llm_callable: Callable[[dict], object] | None = None,
    retriever: KnowledgeRetriever | None = None,
) -> dict:
    payload = build_explanation_payload(report)
    deterministic = _deterministic_fallback(report, "RAG is disabled or unavailable.")
    knowledge_path = Path(root) / "data" / "urban_interventions.json"
    try:
        retriever = retriever or KnowledgeRetriever(knowledge_path)
        retrieved = retriever.retrieve(build_retrieval_query(payload), top_k=top_k)
        if not retrieved:
            return _deterministic_fallback(report, "The knowledge base returned no records.")
    except Exception as exc:  # noqa: BLE001 - availability must never break demo
        return _deterministic_fallback(report, f"Knowledge retrieval failed: {exc}")

    if llm_callable is None:
        if not os.environ.get("GROQ_API_KEY", "").strip():
            deterministic["retrieved_knowledge"] = retrieved
            deterministic["retrieval_backend"] = retriever.backend
            deterministic["unavailable_reason"] = "GROQ_API_KEY is not configured."
            return deterministic
        llm_callable = _groq_call

    request = {
        "simulator_evidence": payload,
        "retrieved_knowledge": retrieved,
        "allowed_recommendation_ids": sorted(ALLOWED_RECOMMENDATION_IDS),
        "limitations": [
            "The simulator is authoritative for all before/after values.",
            "Metrics are heuristic prototype scores, not engineering predictions.",
            "NEEDS_SOURCE records are contextual leads, not verified evidence.",
        ],
    }
    cache_key = hashlib.sha256(json.dumps({
        "request": request, "knowledge_hash": retriever.knowledge_hash,
        "model": MODEL_NAME,
    }, sort_keys=True).encode()).hexdigest()
    if cache_key in _CACHE:
        return dict(_CACHE[cache_key])

    error = ""
    for attempt in range(2):
        try:
            call_payload = dict(request)
            if attempt:
                call_payload["correction"] = f"Previous response was invalid: {error}. Return corrected JSON only."
            candidate = _coerce_json(llm_callable(call_payload))
            validated = validate_advisor_response(candidate, retrieved, payload)
            result = {
                "source": "rag_llm", "advisor_mode": "rag_llm",
                "model": MODEL_NAME, "fallback_used": False,
                "retrieval_backend": retriever.backend,
                "knowledge_hash": retriever.knowledge_hash,
                "primary_problem": validated["primary_problem"],
                "recommendations": validated["recommendations"],
                "retrieved_knowledge": retrieved,
            }
            _CACHE[cache_key] = result
            return dict(result)
        except Exception as exc:  # noqa: BLE001 - retry then safe fallback
            error = str(exc)
    fallback = _deterministic_fallback(report, f"RAG response rejected: {error}")
    fallback["retrieved_knowledge"] = retrieved
    fallback["retrieval_backend"] = retriever.backend
    return fallback


def validate_advisor_response(candidate: object, retrieved: list[dict], payload: dict) -> dict:
    if not isinstance(candidate, dict):
        raise ValueError("response must be an object")
    primary = candidate.get("primary_problem")
    recommendations = candidate.get("recommendations")
    if not isinstance(primary, dict) or not isinstance(recommendations, list):
        raise ValueError("primary_problem and recommendations are required")
    known = {item["knowledge_id"]: item for item in retrieved}
    valid_targets = set(payload.get("problem_zones") or [])
    valid_targets.update(item.get("id") for item in payload.get("problem_buildings") or [])
    valid_targets.update(item.get("id") for item in payload.get("problem_routes") or [])
    target = primary.get("target_id")
    if target not in (None, "") and target not in valid_targets:
        raise ValueError(f"unknown target_id {target!r}")
    output = []
    for rank, rec in enumerate(recommendations, start=1):
        if not isinstance(rec, dict):
            raise ValueError("each recommendation must be an object")
        knowledge_id = rec.get("knowledge_id")
        if knowledge_id not in known:
            raise ValueError(f"knowledge_id {knowledge_id!r} was not retrieved")
        action = rec.get("argus_recommendation_id")
        expected = known[knowledge_id]["argus_recommendation_id"]
        if action != expected or action not in ALLOWED_RECOMMENDATION_IDS:
            raise ValueError(f"unsupported recommendation {action!r}")
        if rec.get("testable") is not True:
            raise ValueError("returned recommendations must be executable and testable")
        output.append({
            "rank": rank, "knowledge_id": knowledge_id,
            "argus_recommendation_id": action,
            "intervention": known[knowledge_id]["intervention"],
            "reason": (
                f"Retrieved record {knowledge_id} maps the reported scenario to "
                f"the executable Argus action {action}. Argus must re-simulate "
                "the action to measure any modeled change."
            ),
            "target_metrics": known[knowledge_id]["target_metrics"],
            "tradeoffs": known[knowledge_id]["tradeoffs"], "testable": True,
            "source": known[knowledge_id]["source"],
        })
    if not output:
        raise ValueError("at least one recommendation is required")
    severity = primary.get("severity")
    if severity not in {"low", "moderate", "high", "unknown"}:
        severity = "unknown"
    first_record = known[output[0]["knowledge_id"]]
    metrics = payload.get("before_metrics") or {}
    grounded_evidence = [
        f"before_metrics.{key}={metrics[key]}"
        for key in first_record["target_metrics"]
        if key in metrics
    ]
    if target:
        grounded_evidence.append(f"target_id={target}")
    return {
        "primary_problem": {
            "category": first_record["problem_category"],
            "severity": severity,
            "target_id": target or None,
            "evidence": grounded_evidence,
        },
        "recommendations": output,
    }


def _deterministic_fallback(report: dict, reason: str) -> dict:
    advisor = report.get("advisor") if isinstance(report.get("advisor"), dict) else {}
    return {
        "source": "deterministic", "advisor_mode": "deterministic_fallback",
        "fallback_used": True, "unavailable_reason": reason,
        "recommendations": [
            {"rank": index + 1, "argus_recommendation_id": action, "testable": True}
            for index, action in enumerate(advisor.get("recommendations") or [])
            if action in ALLOWED_RECOMMENDATION_IDS
        ],
        "retrieved_knowledge": [],
    }


def _coerce_json(value: object) -> object:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _groq_call(payload: dict) -> object:
    try:
        from groq import Groq  # type: ignore
    except ImportError as exc:
        raise RuntimeError("groq package is not installed") from exc
    completion = Groq().chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0.3, max_completion_tokens=2048, top_p=1,
        reasoning_effort="medium", stream=False,
        response_format={"type": "json_object"},
    )
    return completion.choices[0].message.content
