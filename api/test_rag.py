"""Grounding, retrieval, validation, and fallback tests for the RAG advisor."""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from api.rag.advisor import advise_run, validate_advisor_response
from api.rag.retrieval import KnowledgeRetriever

ROOT = Path(__file__).resolve().parents[1]


def _report(recommendation="increase_shade"):
    return {
        "scenario": {"temperature": 42, "humidity": 60, "rainfall": 5, "population": 80000},
        "before": {
            "metrics": {"heat_stress": 78, "rain_impact": 8, "crowding": 62},
            "citizens": [], "problem_zones": ["central"],
            "problem_buildings": [{"id": "b1", "name": "Block 1", "zone": "central", "issues": ["heat"]}],
            "problem_routes": [{"id": "r1", "from": "a", "to": "b", "via_zones": ["central"], "crowding": 0.8}],
        },
        "after": {"metrics": {}, "citizens": []},
        "advisor": {
            "summary": "High heat exposure.", "recommendations": [recommendation],
            "explanation": [],
        },
    }


class RetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retriever = KnowledgeRetriever(ROOT / "data" / "urban_interventions.json")

    def test_heat_ranks_shade(self):
        top = self.retriever.retrieve("extreme heat high temperature low shade", 2)
        self.assertTrue(all(row["argus_recommendation_id"] == "increase_shade" for row in top))

    def test_rain_ranks_drainage(self):
        top = self.retriever.retrieve("heavy rainfall flooding poor drainage", 2)
        self.assertTrue(all(row["argus_recommendation_id"] == "improve_drainage" for row in top))

    def test_crowding_ranks_alternative_routes(self):
        top = self.retriever.retrieve("overcrowding route congestion limited pedestrian paths", 2)
        self.assertTrue(all(row["argus_recommendation_id"] == "alternative_pedestrian_routes" for row in top))


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.retrieved = KnowledgeRetriever(
            ROOT / "data" / "urban_interventions.json"
        ).retrieve("high heat low shade", 5)
        self.payload = {
            "problem_zones": ["central"],
            "problem_buildings": [{"id": "b1"}],
            "problem_routes": [{"id": "r1"}],
        }

    def _candidate(self, **changes):
        record = self.retrieved[0]
        recommendation = {
            "knowledge_id": record["knowledge_id"],
            "argus_recommendation_id": record["argus_recommendation_id"],
            "reason": "Simulator heat stress is high.",
            "testable": True,
        }
        recommendation.update(changes)
        return {
            "primary_problem": {"category": "heat", "severity": "high", "target_id": "r1", "evidence": ["heat_stress=78"]},
            "recommendations": [recommendation],
        }

    def test_valid_response(self):
        result = validate_advisor_response(self._candidate(), self.retrieved, self.payload)
        self.assertEqual(result["recommendations"][0]["rank"], 1)

    def test_invalid_llm_action_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported recommendation"):
            validate_advisor_response(
                self._candidate(argus_recommendation_id="build_metro_station"),
                self.retrieved, self.payload,
            )

    def test_hallucinated_route_is_rejected(self):
        candidate = self._candidate()
        candidate["primary_problem"]["target_id"] = "route_does_not_exist"
        with self.assertRaisesRegex(ValueError, "unknown target_id"):
            validate_advisor_response(candidate, self.retrieved, self.payload)

    def test_bad_knowledge_id_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "was not retrieved"):
            validate_advisor_response(
                self._candidate(knowledge_id="FAKE_999"), self.retrieved, self.payload
            )


class AdvisorTests(unittest.TestCase):
    def test_groq_unavailable_falls_back(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            result = advise_run(_report(), root=ROOT)
        self.assertEqual(result["advisor_mode"], "deterministic_fallback")
        self.assertTrue(result["fallback_used"])
        self.assertEqual(result["recommendations"][0]["argus_recommendation_id"], "increase_shade")

    def test_invalid_response_retries_once_then_falls_back(self):
        calls = []

        def invalid(payload):
            calls.append(payload)
            return {"primary_problem": {}, "recommendations": [{
                "knowledge_id": "FAKE", "argus_recommendation_id": "build_metro_station", "testable": True,
            }]}

        result = advise_run(_report(), root=ROOT, llm_callable=invalid)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["advisor_mode"], "deterministic_fallback")

    def test_empty_knowledge_base_falls_back(self):
        class EmptyRetriever:
            backend = "test"
            knowledge_hash = "empty"
            def retrieve(self, query, top_k=5):
                return []

        result = advise_run(_report(), root=ROOT, retriever=EmptyRetriever(), llm_callable=lambda _: {})
        self.assertEqual(result["advisor_mode"], "deterministic_fallback")


if __name__ == "__main__":
    unittest.main()
