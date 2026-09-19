import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from integration import validate_integration

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

    def test_animation_frames_are_siblings_of_numbered_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "simulation_before_000.json"
            sibling = Path(directory) / "simulation_before_001.json"
            snapshot.touch()
            sibling.touch()

            self.assertEqual(
                validate_integration.animation_frame_paths(snapshot),
                [snapshot, sibling],
            )


if __name__ == "__main__":
    unittest.main()
