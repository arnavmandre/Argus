import tempfile
import unittest
from pathlib import Path

from Simulation import main


class SimulatorCliTests(unittest.TestCase):
    def test_run_demo_uses_explicit_scenario(self):
        scenario = {
            "temperature": 31,
            "humidity": 55,
            "rainfall": 12,
            "population": 42000,
        }
        report = main.run_demo(scenario=scenario)
        self.assertEqual(report["scenario"], scenario)
        self.assertEqual(report["before"]["inputs"], scenario)

    def test_parse_cli_preserves_existing_positional_inputs(self):
        args = main.parse_cli([
            "citizens.json",
            "city.json",
            "--temperature", "31",
            "--humidity", "55",
            "--rainfall", "12",
            "--population", "42000",
            "--output", "report.json",
        ])
        self.assertEqual(args.citizens, Path("citizens.json"))
        self.assertEqual(args.city, Path("city.json"))
        self.assertEqual(args.output, Path("report.json"))
        self.assertEqual(args.temperature, 31)
        self.assertEqual(args.population, 42000)

    def test_user_selection_applies_only_selected_action(self):
        report = main.run_demo(
            scenario={
                "temperature": 40,
                "humidity": 80,
                "rainfall": 80,
                "population": 100000,
            },
            selected_recommendations=["improve_drainage"],
        )
        self.assertEqual(report["advisor_selection"]["mode"], "user_selected")
        self.assertEqual(
            report["advisor_selection"]["recommendation_ids"],
            ["improve_drainage"],
        )
        self.assertEqual(report["intervention"], {"drainage_boost": 0.35})

    def test_cli_accepts_repeated_intervention_ids(self):
        args = main.parse_cli([
            "--intervention-id", "increase_shade",
            "--intervention-id", "improve_drainage",
        ])
        self.assertEqual(
            args.intervention_id,
            ["increase_shade", "improve_drainage"],
        )


if __name__ == "__main__":
    unittest.main()
