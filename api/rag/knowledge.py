"""Load and validate the local urban-intervention knowledge base."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

REQUIRED_FIELDS = {
    "id",
    "problem_category",
    "problem",
    "conditions",
    "intervention",
    "description",
    "appropriate_when",
    "expected_effects",
    "tradeoffs",
    "argus_recommendation_id",
    "target_metrics",
    "source_title",
    "source_url",
    "source_status",
}


def load_knowledge(path: Path) -> tuple[list[dict], str]:
    raw = path.read_bytes()
    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, list):
        raise ValueError("knowledge base must be a JSON array")
    seen: set[str] = set()
    for index, record in enumerate(parsed):
        if not isinstance(record, dict):
            raise ValueError(f"knowledge record {index} must be an object")
        missing = REQUIRED_FIELDS - record.keys()
        if missing:
            raise ValueError(f"knowledge record {index} is missing {sorted(missing)}")
        knowledge_id = record["id"]
        if not isinstance(knowledge_id, str) or not knowledge_id or knowledge_id in seen:
            raise ValueError(f"invalid or duplicate knowledge id at record {index}")
        seen.add(knowledge_id)
        if record["source_status"] not in {"VERIFIED", "NEEDS_SOURCE"}:
            raise ValueError(f"invalid source_status for {knowledge_id}")
        if record["source_status"] == "VERIFIED" and not record["source_url"]:
            raise ValueError(f"verified record {knowledge_id} requires source_url")
    return parsed, hashlib.sha256(raw).hexdigest()


def searchable_text(record: dict) -> str:
    fields = [
        record["problem_category"], record["problem"],
        " ".join(record["conditions"]), record["intervention"],
        record["description"], record["appropriate_when"],
        " ".join(record["expected_effects"]), " ".join(record["tradeoffs"]),
        record["argus_recommendation_id"], " ".join(record["target_metrics"]),
    ]
    return "\n".join(str(value) for value in fields)
