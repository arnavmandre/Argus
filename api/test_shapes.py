import json
import unittest
from pathlib import Path

from api.shapes import live_run_summary, live_health

ROOT = Path(__file__).resolve().parents[1]


class ShapeTests(unittest.TestCase):
    def test_live_summary_marks_source_live_and_drops_fixture_warning(self):
        report = json.loads(
            (ROOT / "Simulation" / "urbantwin_demo_output.json").read_text(
                encoding="utf-8"
            )
        )
        summary = live_run_summary(report, "2026-09-19T12:00:00+00:00", "live-run-1")
        self.assertEqual(summary["source"], "live")
        self.assertEqual(summary["status"], "complete")
        self.assertTrue(all("Recorded fixture" not in w for w in summary["warnings"]))

    def test_live_health_capabilities(self):
        health = live_health("2026-09-19T12:00:00+00:00")
        self.assertEqual(health["mode"], "live")
        self.assertTrue(health["capabilities"]["http_api"])
        self.assertTrue(health["capabilities"]["live_simulation"])
        self.assertFalse(health["capabilities"]["omniverse_streaming"])
        self.assertEqual(health["omniverse_stream"], "offline")


if __name__ == "__main__":
    unittest.main()
