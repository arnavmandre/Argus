import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ExportInterfaceTests(unittest.TestCase):
    def test_fixture_exporter_documents_run_id(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "integration" / "export_api_mocks.py"), "--help"],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertIn("--run-id", result.stdout)

    def test_validator_documents_explicit_artifact_paths(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "integration" / "validate_integration.py"), "--help"],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        for option in ("--report", "--snapshot", "--after", "--stage", "--registry"):
            self.assertIn(option, result.stdout)


if __name__ == "__main__":
    unittest.main()
