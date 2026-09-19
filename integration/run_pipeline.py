"""Run the UrbanTwin simulator-to-frontend pipeline in an isolated directory."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import NotRequired, TypedDict


ROOT = Path(__file__).resolve().parents[1]
RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
STAGE_OUTPUT_LIMIT = 4000


@dataclass(frozen=True)
class PipelineConfig:
    root: Path
    run_id: str
    citizens: Path
    city: Path
    temperature: float
    humidity: float
    rainfall: float
    population: int
    frames: int = 60
    duration: float = 60.0
    publish: bool = True


class StageResult(TypedDict):
    name: str
    command: list[str]
    seconds: float
    stdout: str
    stdout_truncated: NotRequired[bool]
    stderr: NotRequired[str]
    stderr_truncated: NotRequired[bool]


class PipelineError(RuntimeError):
    pass


def _tail(text: str, limit: int = STAGE_OUTPUT_LIMIT) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[-limit:], True


def run_stage(name, command, cwd) -> StageResult:
    """Execute one subprocess and retain bounded diagnostic evidence."""
    started = time.perf_counter()
    result = subprocess.run(
        [str(part) for part in command],
        cwd=str(cwd),
        text=True,
        capture_output=True,
    )
    elapsed = round(time.perf_counter() - started, 3)
    if result.returncode:
        stdout, stdout_cut = _tail(result.stdout, 8000)
        stderr, stderr_cut = _tail(result.stderr, 8000)
        raise PipelineError(
            f"{name} failed with exit {result.returncode}\n"
            f"stdout{' (tail)' if stdout_cut else ''}:\n{stdout}\n"
            f"stderr{' (tail)' if stderr_cut else ''}:\n{stderr}"
        )

    stdout, stdout_cut = _tail(result.stdout)
    stderr, stderr_cut = _tail(result.stderr)
    stage: StageResult = {
        "name": name,
        "command": [str(part) for part in command],
        "seconds": elapsed,
        "stdout": stdout,
    }
    if stdout_cut:
        stage["stdout_truncated"] = True
    if stderr:
        stage["stderr"] = stderr
    if stderr_cut:
        stage["stderr_truncated"] = True
    return stage


def _record_stage(name: str, command: list[object], root: Path) -> StageResult:
    """Normalize real and test-double stage results into manifest-safe data."""
    result = dict(run_stage(name, command, root))
    result["name"] = name
    result["command"] = [str(part) for part in command]
    result["seconds"] = float(result.get("seconds", 0.0))
    stdout, stdout_cut = _tail(str(result.get("stdout", "")))
    result["stdout"] = stdout
    if stdout_cut:
        result["stdout_truncated"] = True
    stderr = str(result.get("stderr", ""))
    if stderr:
        stderr, stderr_cut = _tail(stderr)
        result["stderr"] = stderr
        if stderr_cut:
            result["stderr_truncated"] = True
    return result  # type: ignore[return-value]


def _validate_config(config: PipelineConfig) -> None:
    if not RUN_ID_PATTERN.fullmatch(config.run_id):
        raise PipelineError(
            "run ID must use 1-64 letters, digits, dot, underscore or hyphen"
        )
    if config.frames < 1:
        raise PipelineError("frames must be >= 1")
    if config.duration <= 0:
        raise PipelineError("duration must be > 0")


def _snapshot_paths(directory: Path, state: str) -> list[Path]:
    numbered = sorted(directory.glob(f"simulation_{state}_[0-9][0-9][0-9].json"))
    if numbered:
        return numbered
    still = directory / f"simulation_{state}.json"
    return [still] if still.exists() else []


def _normalize_single_snapshots(directory: Path) -> None:
    """Keep manifest patterns valid when the exporter emits a one-frame still."""
    for state in ("before", "after"):
        still = directory / f"simulation_{state}.json"
        numbered = directory / f"simulation_{state}_000.json"
        if still.exists() and not numbered.exists():
            os.replace(still, numbered)


def _require_artifacts(
    report: Path,
    snapshots: Path,
    runtime_scene: Path,
    usd: Path,
    mocks: Path,
    run_id: str,
    frames: int,
) -> tuple[list[Path], list[Path]]:
    before = _snapshot_paths(snapshots, "before")
    after = _snapshot_paths(snapshots, "after")
    required = [
        report,
        runtime_scene / "main.usda",
        usd / "agents_before.usda",
        usd / "agents_after.usda",
        mocks / "health.json",
        mocks / "scenarios.json",
        mocks / "stream-config.json",
        mocks / "model-card.json",
        mocks / "runs" / f"{run_id}.json",
        mocks / "runs" / f"{run_id}.citizens.json",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if len(before) != frames:
        missing.append(f"{snapshots}/simulation_before snapshots ({len(before)}/{frames})")
    if len(after) != frames:
        missing.append(f"{snapshots}/simulation_after snapshots ({len(after)}/{frames})")
    if missing:
        raise PipelineError("pipeline did not create required artifacts:\n  " + "\n  ".join(missing))
    return before, after


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f".{destination.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _publish_snapshots(source_dir: Path, destination_dir: Path) -> None:
    destination_dir.mkdir(parents=True, exist_ok=True)
    source_names: set[str] = set()
    for state in ("before", "after"):
        for source in _snapshot_paths(source_dir, state):
            source_names.add(source.name)
            _atomic_copy(source, destination_dir / source.name)

    for state in ("before", "after"):
        candidates = list(
            destination_dir.glob(f"simulation_{state}_[0-9][0-9][0-9].json")
        )
        candidates.append(destination_dir / f"simulation_{state}.json")
        for stale in candidates:
            if stale.exists() and stale.name not in source_names:
                stale.unlink()


def _publish_compatibility(
    root: Path,
    report: Path,
    snapshots: Path,
    usd: Path,
    mocks: Path,
) -> None:
    _atomic_copy(report, root / "Simulation" / "urbantwin_demo_output.json")
    _publish_snapshots(snapshots, root / "data")
    generated = root / "phase9" / "scene" / "generated"
    _atomic_copy(usd / "agents_before.usda", generated / "agents_before.usda")
    _atomic_copy(usd / "agents_after.usda", generated / "agents_after.usda")
    _atomic_copy(usd / "agents_before.usda", generated / "agents.usda")
    for source in sorted(path for path in mocks.rglob("*") if path.is_file()):
        _atomic_copy(source, root / "frontend" / "mocks" / source.relative_to(mocks))


def _recover_stale_backup(final: Path, backup: Path) -> None:
    if not backup.exists():
        return
    if final.exists():
        shutil.rmtree(backup)
    else:
        os.replace(backup, final)


def _promote_run(staging: Path, final: Path, backup: Path) -> None:
    moved_previous = False
    try:
        if final.exists():
            os.replace(final, backup)
            moved_previous = True
        os.replace(staging, final)
    except OSError as exc:
        if moved_previous and backup.exists():
            displaced = final.with_name(f"{final.name}.failed-{uuid.uuid4().hex}")
            if final.exists():
                os.replace(final, displaced)
            os.replace(backup, final)
            if displaced.exists():
                shutil.rmtree(displaced)
        raise PipelineError(f"could not promote completed run: {exc}") from exc
    if backup.exists():
        shutil.rmtree(backup)


def run_pipeline(config: PipelineConfig) -> dict:
    _validate_config(config)
    root = Path(config.root).resolve()
    runs = root / "data" / "runs"
    staging = runs / f"{config.run_id}.staging"
    final = runs / config.run_id
    backup = runs / f"{config.run_id}.backup"
    runs.mkdir(parents=True, exist_ok=True)
    _recover_stale_backup(final, backup)
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()

    report = staging / "simulation_report.json"
    snapshots = staging / "snapshots"
    runtime = staging / "runtime"
    runtime_scene = runtime / "scene"
    usd = staging / "usd"
    mocks = staging / "frontend-mocks"
    python = sys.executable
    stages: list[StageResult] = []

    try:
        stages.append(
            _record_stage(
                "simulation",
                [
                    python,
                    root / "Simulation" / "main.py",
                    root / config.citizens,
                    root / config.city,
                    "--temperature",
                    config.temperature,
                    "--humidity",
                    config.humidity,
                    "--rainfall",
                    config.rainfall,
                    "--population",
                    config.population,
                    "--output",
                    report,
                ],
                root,
            )
        )
        stages.append(
            _record_stage(
                "snapshot_export",
                [
                    python,
                    root / "integration" / "export_snapshot.py",
                    "--report",
                    report,
                    "--city",
                    root / config.city,
                    "--state",
                    "both",
                    "--run-id",
                    config.run_id,
                    "--out-dir",
                    snapshots,
                    "--frames",
                    config.frames,
                    "--duration",
                    config.duration,
                ],
                root,
            )
        )
        _normalize_single_snapshots(snapshots)
        before = _snapshot_paths(snapshots, "before")
        after = _snapshot_paths(snapshots, "after")
        if not before or not after:
            raise PipelineError("snapshot export did not create both before and after states")

        stages.append(
            _record_stage(
                "runtime_stage",
                [
                    python,
                    root / "integration" / "load_snapshot.py",
                    before[0],
                    "--out",
                    runtime_scene,
                ],
                root,
            )
        )
        for state, frames in (("before", before), ("after", after)):
            stages.append(
                _record_stage(
                    f"agents_{state}",
                    [
                        python,
                        root / "phase9" / "agents_instancer.py",
                        *frames,
                        "--behavior-report",
                        report,
                        "--behavior-state",
                        state,
                        "--out",
                        usd / f"agents_{state}.usda",
                        "--demo-stage",
                        runtime_scene / "main.usda",
                    ],
                    root,
                )
            )
        stages.append(
            _record_stage(
                "frontend_fixtures",
                [
                    python,
                    root / "integration" / "export_api_mocks.py",
                    "--report",
                    report,
                    "--run-id",
                    config.run_id,
                    "--out",
                    mocks,
                ],
                root,
            )
        )

        before, after = _require_artifacts(
            report,
            snapshots,
            runtime_scene,
            usd,
            mocks,
            config.run_id,
            config.frames,
        )
        stages.append(
            _record_stage(
                "validation",
                [
                    python,
                    root / "integration" / "validate_integration.py",
                    "--report",
                    report,
                    "--snapshot",
                    before[0],
                    "--after",
                    after[0],
                    "--stage",
                    runtime_scene / "main.usda",
                    "--registry",
                    root / "phase2" / "scene" / "edge_registry.json",
                ],
                root,
            )
        )
        _require_artifacts(
            report,
            snapshots,
            runtime_scene,
            usd,
            mocks,
            config.run_id,
            config.frames,
        )

        manifest = {
            "schema_version": 1,
            "run_id": config.run_id,
            "status": "complete",
            "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "scenario": {
                "temperature": config.temperature,
                "humidity": config.humidity,
                "rainfall": config.rainfall,
                "population": config.population,
            },
            "animation": {
                "frames": config.frames,
                "duration_seconds": config.duration,
            },
            "artifacts": {
                "simulation_report": "simulation_report.json",
                "before_snapshots": "snapshots/simulation_before_*.json",
                "after_snapshots": "snapshots/simulation_after_*.json",
                "before_agents_usd": "usd/agents_before.usda",
                "after_agents_usd": "usd/agents_after.usda",
                "runtime_stage": "runtime/scene/main.usda",
                "frontend_fixtures": "frontend-mocks",
            },
            "stages": stages,
        }
        manifest_tmp = staging / "manifest.json.tmp"
        manifest_path = staging / "manifest.json"
        manifest_tmp.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(manifest_tmp, manifest_path)

        if config.publish:
            _publish_compatibility(root, report, snapshots, usd, mocks)
        _promote_run(staging, final, backup)
        return manifest
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def parse_cli(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="urbantwin-local-001")
    parser.add_argument(
        "--citizens",
        type=Path,
        default=Path("Simulation/citizens_survey_city_osm.json"),
    )
    parser.add_argument("--city", type=Path, default=Path("Simulation/city_osm.json"))
    parser.add_argument("--temperature", type=float, default=40)
    parser.add_argument("--humidity", type=float, default=80)
    parser.add_argument("--rainfall", type=float, default=80)
    parser.add_argument("--population", type=int, default=100000)
    parser.add_argument("--frames", type=int, default=60)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--no-publish", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_cli(argv)
    config = PipelineConfig(
        root=ROOT,
        run_id=args.run_id,
        citizens=args.citizens,
        city=args.city,
        temperature=args.temperature,
        humidity=args.humidity,
        rainfall=args.rainfall,
        population=args.population,
        frames=args.frames,
        duration=args.duration,
        publish=not args.no_publish,
    )
    try:
        run_pipeline(config)
    except PipelineError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(ROOT / "data" / "runs" / config.run_id / "manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
