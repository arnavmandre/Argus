import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import integration.run_pipeline as pipeline_module
from integration.run_pipeline import PipelineConfig, PipelineError, run_pipeline


class PipelineTests(unittest.TestCase):
    def config(self, root, *, publish=False, frames=3):
        return PipelineConfig(
            root=root,
            run_id="test-run",
            citizens=Path("Simulation/citizens_survey_city_osm.json"),
            city=Path("Simulation/city_osm.json"),
            temperature=31,
            humidity=55,
            rainfall=12,
            population=42000,
            frames=frames,
            duration=6.0,
            publish=publish,
        )

    @staticmethod
    def _argument(command, option):
        return Path(command[command.index(option) + 1])

    def complete_stage(self, name, command, cwd):
        command = [str(part) for part in command]
        if name == "simulation":
            output = self._argument(command, "--output")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text('{"report": true}\n', encoding="utf-8")
        elif name == "snapshot_export":
            output = self._argument(command, "--out-dir")
            output.mkdir(parents=True, exist_ok=True)
            frames = int(command[command.index("--frames") + 1])
            for state in ("before", "after"):
                if frames == 1:
                    paths = [output / f"simulation_{state}.json"]
                else:
                    paths = [
                        output / f"simulation_{state}_{frame:03d}.json"
                        for frame in range(frames)
                    ]
                for frame, path in enumerate(paths):
                    path.write_text(
                        json.dumps({"state": state, "frame": frame}) + "\n",
                        encoding="utf-8",
                    )
        elif name == "runtime_stage":
            output = self._argument(command, "--out")
            output.mkdir(parents=True, exist_ok=True)
            (output / "main.usda").write_text("#usda 1.0\n", encoding="utf-8")
        elif name.startswith("agents_"):
            output = self._argument(command, "--out")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("#usda 1.0\n", encoding="utf-8")
        elif name == "frontend_fixtures":
            output = self._argument(command, "--out")
            run_id = command[command.index("--run-id") + 1]
            files = (
                "health.json",
                "scenarios.json",
                "stream-config.json",
                "model-card.json",
                f"runs/{run_id}.json",
                f"runs/{run_id}.citizens.json",
            )
            for relative in files:
                path = output / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n", encoding="utf-8")
        return {
            "name": name,
            "command": command,
            "seconds": 0.01,
            "stdout": "stage evidence",
        }

    @patch("integration.run_pipeline.run_stage")
    def test_manifest_records_scenario_and_required_artifacts(self, run_stage):
        run_stage.side_effect = self.complete_stage

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = run_pipeline(self.config(root))
            manifest_path = root / "data" / "runs" / "test-run" / "manifest.json"

            self.assertEqual(manifest["run_id"], "test-run")
            self.assertEqual(manifest["scenario"]["temperature"], 31)
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(
                set(manifest["artifacts"]),
                {
                    "simulation_report",
                    "before_snapshots",
                    "after_snapshots",
                    "before_agents_usd",
                    "after_agents_usd",
                    "runtime_stage",
                    "frontend_fixtures",
                },
            )
            self.assertEqual(json.loads(manifest_path.read_text()), manifest)
            self.assertEqual(
                [stage["name"] for stage in manifest["stages"]],
                [
                    "simulation",
                    "snapshot_export",
                    "runtime_stage",
                    "agents_before",
                    "agents_after",
                    "frontend_fixtures",
                    "validation",
                ],
            )
            self.assertTrue(
                all(
                    isinstance(token, str)
                    for stage in manifest["stages"]
                    for token in stage["command"]
                )
            )

    @patch("integration.run_pipeline.run_stage")
    def test_failed_run_keeps_previous_complete_run(self, run_stage):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            completed = root / "data" / "runs" / "test-run"
            completed.mkdir(parents=True)
            marker = completed / "manifest.json"
            marker.write_text(
                '{"status":"complete","old":true}\n', encoding="utf-8"
            )
            run_stage.side_effect = PipelineError("simulation failed")

            with self.assertRaisesRegex(PipelineError, "simulation failed"):
                run_pipeline(self.config(root))

            self.assertTrue(json.loads(marker.read_text(encoding="utf-8"))["old"])

    @patch("integration.run_pipeline.run_stage")
    def test_single_frame_manifest_patterns_identify_snapshot_files(self, run_stage):
        run_stage.side_effect = self.complete_stage

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = run_pipeline(self.config(root, frames=1))
            final = root / "data" / "runs" / "test-run"

            for key in ("before_snapshots", "after_snapshots"):
                self.assertTrue(
                    list(final.glob(manifest["artifacts"][key])),
                    f"{key} pattern must identify its required artifact",
                )

    @patch("integration.run_pipeline.run_stage")
    def test_validation_failure_does_not_publish_compatibility_outputs(
        self, run_stage
    ):
        def fail_validation(name, command, cwd):
            if name == "validation":
                raise PipelineError("validation failed")
            return self.complete_stage(name, command, cwd)

        run_stage.side_effect = fail_validation
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            compatibility = root / "Simulation" / "urbantwin_demo_output.json"
            compatibility.parent.mkdir(parents=True)
            compatibility.write_text("old report\n", encoding="utf-8")

            with self.assertRaisesRegex(PipelineError, "validation failed"):
                run_pipeline(self.config(root, publish=True))

            self.assertEqual(
                compatibility.read_text(encoding="utf-8"), "old report\n"
            )
            self.assertFalse((root / "data" / "simulation_before_000.json").exists())

    @patch("integration.run_pipeline.run_stage")
    def test_shorter_publication_removes_stale_numbered_snapshots(self, run_stage):
        run_stage.side_effect = self.complete_stage
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            data.mkdir()
            for state in ("before", "after"):
                for frame in range(5):
                    (data / f"simulation_{state}_{frame:03d}.json").write_text(
                        "old\n", encoding="utf-8"
                    )

            run_pipeline(self.config(root, publish=True, frames=2))

            self.assertEqual(
                [path.name for path in sorted(data.glob("simulation_before_*.json"))],
                ["simulation_before_000.json", "simulation_before_001.json"],
            )
            self.assertEqual(
                [path.name for path in sorted(data.glob("simulation_after_*.json"))],
                ["simulation_after_000.json", "simulation_after_001.json"],
            )

    @patch("integration.run_pipeline.run_stage")
    def test_promotion_failure_restores_previous_completed_run(self, run_stage):
        run_stage.side_effect = self.complete_stage
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            completed = root / "data" / "runs" / "test-run"
            completed.mkdir(parents=True)
            marker = completed / "manifest.json"
            marker.write_text(
                '{"status":"complete","old":true}\n', encoding="utf-8"
            )
            real_replace = pipeline_module.os.replace

            def fail_staging_promotion(source, destination):
                if (
                    Path(source).name == "test-run.staging"
                    and Path(destination).name == "test-run"
                ):
                    raise OSError("injected promotion failure")
                return real_replace(source, destination)

            with patch(
                "integration.run_pipeline.os.replace",
                side_effect=fail_staging_promotion,
            ):
                with self.assertRaisesRegex(PipelineError, "could not promote"):
                    run_pipeline(self.config(root))

            self.assertTrue(json.loads(marker.read_text(encoding="utf-8"))["old"])
            self.assertFalse((root / "data" / "runs" / "test-run.backup").exists())


if __name__ == "__main__":
    unittest.main()
