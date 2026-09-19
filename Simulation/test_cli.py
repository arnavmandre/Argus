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


if __name__ == "__main__":
    unittest.main()
