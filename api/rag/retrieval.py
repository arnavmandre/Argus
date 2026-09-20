"""Small local semantic index with an honest dependency-free fallback."""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from api.rag.knowledge import load_knowledge, searchable_text

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
TOKEN_RE = re.compile(r"[a-z0-9_]+")


class KnowledgeRetriever:
    def __init__(self, knowledge_path: Path, index_dir: Path | None = None):
        self.knowledge_path = Path(knowledge_path)
        self.records, self.knowledge_hash = load_knowledge(self.knowledge_path)
        self.index_dir = Path(index_dir) if index_dir else self.knowledge_path.parent / ".rag_index"
        self._model = None
        self._index = None
        self.backend = "lexical_fallback"
        self._load_semantic_index()

    def _load_semantic_index(self) -> None:
        metadata_path = self.index_dir / "metadata.json"
        index_path = self.index_dir / "interventions.faiss"
        if not metadata_path.exists() or not index_path.exists():
            return
        try:
            import faiss  # type: ignore
            from sentence_transformers import SentenceTransformer  # type: ignore

            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("knowledge_hash") != self.knowledge_hash:
                return
            if metadata.get("model") != MODEL_NAME:
                return
            self._model = SentenceTransformer(MODEL_NAME, device="cpu")
            self._index = faiss.read_index(str(index_path))
            self.backend = "faiss_minilm"
        except (ImportError, OSError, ValueError, json.JSONDecodeError):
            self._model = None
            self._index = None

    def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        top_k = max(1, min(int(top_k), len(self.records)))
        if self._index is not None and self._model is not None:
            vector = self._model.encode([query], normalize_embeddings=True)
            scores, positions = self._index.search(vector, top_k)
            pairs = zip(scores[0].tolist(), positions[0].tolist())
            return [self._result(self.records[pos], score) for score, pos in pairs if pos >= 0]
        scored = [
            (self._lexical_score(query, searchable_text(record)), record)
            for record in self.records
        ]
        scored.sort(key=lambda item: (-item[0], item[1]["id"]))
        return [self._result(record, score) for score, record in scored[:top_k]]

    @staticmethod
    def _lexical_score(query: str, document: str) -> float:
        q = Counter(TOKEN_RE.findall(query.lower()))
        d = Counter(TOKEN_RE.findall(document.lower()))
        dot = sum(value * d[token] for token, value in q.items())
        denom = math.sqrt(sum(v * v for v in q.values())) * math.sqrt(sum(v * v for v in d.values()))
        return round(dot / denom, 6) if denom else 0.0

    @staticmethod
    def _result(record: dict, score: float) -> dict:
        return {
            "knowledge_id": record["id"],
            "similarity_score": round(float(score), 6),
            "problem_category": record["problem_category"],
            "intervention": record["intervention"],
            "description": record["description"],
            "argus_recommendation_id": record["argus_recommendation_id"],
            "target_metrics": record["target_metrics"],
            "tradeoffs": record["tradeoffs"],
            "source": {
                "title": record["source_title"],
                "url": record["source_url"],
                "status": record["source_status"],
            },
        }


def build_index(knowledge_path: Path, index_dir: Path) -> dict:
    """Explicitly build and persist the MiniLM/FAISS index."""
    import faiss  # type: ignore
    import numpy as np  # type: ignore
    from sentence_transformers import SentenceTransformer  # type: ignore

    records, knowledge_hash = load_knowledge(Path(knowledge_path))
    model = SentenceTransformer(MODEL_NAME, device="cpu")
    vectors = model.encode(
        [searchable_text(record) for record in records],
        normalize_embeddings=True,
        convert_to_numpy=True,
    ).astype(np.float32)
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    index_dir = Path(index_dir)
    index_dir.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_dir / "interventions.faiss"))
    metadata = {
        "knowledge_hash": knowledge_hash,
        "model": MODEL_NAME,
        "record_ids": [record["id"] for record in records],
    }
    (index_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    return {"records": len(records), "knowledge_hash": knowledge_hash, "model": MODEL_NAME}
