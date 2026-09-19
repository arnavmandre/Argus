"""Stamp root-layer USD timeline metadata for Kit playback.

USD reads start/end time codes from the stage's ROOT layer only — values on a
sublayer are ignored — so animated agents need the demo stage stamped too.
"""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from pxr import Sdf


def stamp_demo_timeline(
    demo_stage: Path,
    *,
    timestamps: Sequence[float],
    fps: float = 24.0,
) -> None:
    """Update only timeline metadata on an existing root stage layer."""
    if not demo_stage.exists():
        return
    demo = Sdf.Layer.FindOrOpen(str(demo_stage))
    if not demo:
        return
    if len(timestamps) > 1:
        demo.startTimeCode = timestamps[0] * fps
        demo.endTimeCode = timestamps[-1] * fps
        demo.timeCodesPerSecond = fps
        demo.framesPerSecond = fps
    else:
        # Going back to a still snapshot must not leave a stale timeline
        # advertising frames that no longer exist.
        demo.ClearStartTimeCode()
        demo.ClearEndTimeCode()
        demo.ClearTimeCodesPerSecond()
        demo.ClearFramesPerSecond()
    demo.Save()
