import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LAYER = ROOT / "phase9" / "scene" / "generated" / "agents.usda"
DEMO_STAGE = ROOT / "phase9" / "scene" / "main.usda"


class AgentRendererCliTests(unittest.TestCase):
    def test_explicit_output_does_not_overwrite_default_layer(self):
        snapshot = ROOT / "phase3" / "mock_data" / "mock_stress.json"
        default_before = (
            DEFAULT_LAYER.read_bytes() if DEFAULT_LAYER.exists() else None
        )
        demo_before = DEMO_STAGE.read_bytes() if DEMO_STAGE.exists() else None
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "agents_before.usda"
            missing_stage = Path(directory) / "no-demo-stage.usda"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "phase9" / "agents_instancer.py"),
                    str(snapshot),
                    "--out",
                    str(output),
                    "--demo-stage",
                    str(missing_stage),
                ],
                check=True,
                cwd=ROOT,
            )
            self.assertTrue(output.exists())
            self.assertIn("PointInstancer", output.read_text(encoding="utf-8"))
            if default_before is not None:
                self.assertEqual(DEFAULT_LAYER.read_bytes(), default_before)
            if demo_before is not None:
                self.assertEqual(DEMO_STAGE.read_bytes(), demo_before)


if __name__ == "__main__":
    unittest.main()
