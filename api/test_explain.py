"""Unit tests for constrained run explanations."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from api.explain import build_explanation_payload, explain_run

ROOT = Path(__file__).resolve().parents[1]
DEMO_REPORT = ROOT / "Simulation" / "urbantwin_demo_output.json"


def _payload_json(payload: dict) -> str:
    return json.dumps(payload)


class ExplainPayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not DEMO_REPORT.is_file():
            raise unittest.SkipTest("demo report missing")
        cls.report = json.loads(DEMO_REPORT.read_text(encoding="utf-8"))

    def test_payload_allowlist_excludes_citizen_records(self):
        synthetic = {
            "scenario": {"temperature": 30, "humidity": 50, "rainfall": 10, "population": 1000},
            "before": {
                "metrics": {"human_experience_index": 40.0},
                "citizens": [
                    {
                        "id": "citizen_secret_001",
                        "archetype": "student",
                        "home": "home_anchor_secret",
                        "destination": "dest_anchor_secret",
                        "behavior": "SEEK_SHADE",
                    }
                ],
                "problem_zones": [],
                "problem_buildings": [],
                "problem_routes": [],
            },
            "after": {"metrics": {}, "citizens": []},
            "advisor": {"summary": "", "recommendations": [], "explanation": []},
        }
        payload = build_explanation_payload(synthetic)
        blob = _payload_json(payload)
        self.assertNotIn("citizen_secret_001", blob)
        self.assertNotIn("home_anchor_secret", blob)
        self.assertNotIn("dest_anchor_secret", blob)
        self.assertNotIn("archetype", blob)
        self.assertEqual(payload["citizen_counts"]["before"], 1)

        payload_demo = build_explanation_payload(self.report)
        self.assertEqual(
            payload_demo["citizen_counts"]["before"],
            len(self.report["before"]["citizens"]),
        )

    def test_payload_includes_advisor_and_metrics(self):
        payload = build_explanation_payload(self.report)
        self.assertEqual(payload["scenario"], self.report["scenario"])
        self.assertIn("human_experience_index", payload["before_metrics"])
        self.assertTrue(payload["advisor_summary"])
        self.assertTrue(payload["recommendations"])
        self.assertEqual(
            payload["recommendations"][0]["id"],
            self.report["advisor"]["recommendations"][0],
        )


class ExplainRunTests(unittest.TestCase):
    def test_deterministic_default(self):
        payload = {
            "scenario": {"temperature": 31, "humidity": 55, "rainfall": 12, "population": 42000},
            "before_metrics": {"human_experience_index": 50.0},
            "after_metrics": {"human_experience_index": 60.0},
            "advisor_summary": "Heat stress elevated.",
            "recommendations": [{"id": "increase_shade", "label": "Increase shade"}],
            "problem_zones": ["Zone A1"],
            "problem_buildings": [],
            "problem_routes": [],
            "warnings_and_limitations": ["Heuristic prototype."],
            "citizen_counts": {"before": 10, "after": 10},
        }
        result = explain_run(payload)
        self.assertEqual(result["source"], "deterministic")
        self.assertIn("Heat stress elevated", result["text"])
        self.assertIn("increase_shade", " ".join(result["claims"]))

    def test_llm_success(self):
        payload = {"advisor_summary": "Test.", "recommendations": []}

        def fake_llm(_payload):
            return "LLM summary only from payload."

        result = explain_run(payload, llm_callable=fake_llm)
        self.assertEqual(result["source"], "llm")
        self.assertEqual(result["text"], "LLM summary only from payload.")

    def test_llm_failure_falls_back(self):
        payload = {"advisor_summary": "Fallback.", "recommendations": []}

        def broken_llm(_payload):
            raise RuntimeError("network down")

        result = explain_run(payload, llm_callable=broken_llm)
        self.assertEqual(result["source"], "deterministic")
        self.assertIn("Fallback", result["text"])
        self.assertIn("unavailable_reason", result)


if __name__ == "__main__":
    unittest.main()
