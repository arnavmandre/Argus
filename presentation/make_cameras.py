"""
Generate presentation/scene/cameras.usda.

Demo cameras are authored here rather than flown by hand: under time pressure
a live camera fly-through is the easiest thing to get wrong on stage. Each shot
is a saved prim you can pick from the viewport camera menu.

Run:  python presentation/make_cameras.py
"""
from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom

SCENE = Path(__file__).resolve().parent / "scene" / "cameras.usda"

# The hero pedestrian corridor from phase3/mock_data/demo_selection.json runs
# roughly (-36,-135) -> (-105,-4) -> (-201,-77); its centre is about (-100,-89)
# and it contains the flagged problem edge. All three shots are built around it.
CORRIDOR_CENTRE = Gf.Vec3d(-100, -89, 0)

SHOTS = [
    (
        "Overview",
        Gf.Vec3d(620, -680, 430), Gf.Vec3d(0, 0, 0), 32,
        "Whole 762x779 m tile at ~25 deg elevation. Opening shot.",
    ),
    (
        "Corridor",
        Gf.Vec3d(30, -180, 16), Gf.Vec3d(-120, -70, 3), 35,
        "Near street level along the hero corridor. Shows shade vs sun on the "
        "pavement - use this for the before/after shade intervention.",
    ),
    (
        "ProblemZone",
        Gf.Vec3d(90, -280, 190), CORRIDOR_CENTRE, 30,
        "Tight aerial on the corridor the advisor flags. Use when showing "
        "crowding or heat recolouring.",
    ),
]


def camera_xform(eye: Gf.Vec3d, target: Gf.Vec3d) -> Gf.Matrix4d:
    """World transform for a camera at `eye` looking at `target` (Z-up)."""
    # SetLookAt builds a view matrix (world -> camera); the prim needs its
    # inverse (camera -> world).
    view = Gf.Matrix4d(1).SetLookAt(eye, target, Gf.Vec3d(0, 0, 1))
    return view.GetInverse()


def main() -> None:
    stage = Usd.Stage.CreateNew(str(SCENE)) if not SCENE.exists() else Usd.Stage.Open(str(SCENE))
    stage.SetDefaultPrim(UsdGeom.Xform.Define(stage, "/World").GetPrim())
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)

    stage.OverridePrim("/World/Cameras")

    for name, eye, target, focal, doc in SHOTS:
        cam = UsdGeom.Camera.Define(stage, f"/World/Cameras/{name}")
        cam.GetPrim().SetDocumentation(doc)
        cam.CreateFocalLengthAttr(float(focal))
        cam.CreateClippingRangeAttr(Gf.Vec2f(0.1, 6000))
        # Full-frame back plate so focal lengths read like real camera numbers.
        cam.CreateHorizontalApertureAttr(36.0)
        cam.CreateVerticalApertureAttr(24.0)
        cam.MakeMatrixXform().Set(camera_xform(eye, target))

    stage.GetRootLayer().documentation = (
        "UrbanTwin demo cameras. Regenerate with presentation/make_cameras.py."
    )
    stage.GetRootLayer().Save()
    print(f"wrote {SCENE}")
    for name, eye, target, _, _ in SHOTS:
        d = (Gf.Vec3d(*eye) - Gf.Vec3d(*target)).GetLength()
        print(f"  {name:12s} eye={tuple(eye)} -> target={tuple(target)}  dist={d:.0f} m")


if __name__ == "__main__":
    main()
