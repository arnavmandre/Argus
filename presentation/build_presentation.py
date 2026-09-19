"""
UrbanTwin AI - demo presentation layer.

Authors a non-destructive USD layer that sits OVER the frozen Phase 1/2/8
scene and supplies what a demo needs but a raw OSM import does not:

  * a real sun with soft shadows, so shade and exposure are visible before any
    data is overlaid (this is a heat simulation - shadows are the point)
  * two lighting presets, baseline and extreme heat, as a USD variant set
  * a dark matte ground so the city tile does not float on the viewport grid
  * a non-metallic off-white building material so massing reads at a distance
  * three saved demo cameras (overview / corridor / problem zone)

Nothing in the frozen layers is modified: this is a pure `over`.

Usage:  python presentation/build_presentation.py
Output: presentation/presentation.usda  and  presentation/main.usda
"""
from __future__ import annotations

from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdShade

ROOT = Path(__file__).resolve().parent
CITY_SIZE = (761.9, 779.2)          # metres, from phase1/scene/manifest.json


# --------------------------------------------------------------------------
# camera helper
# --------------------------------------------------------------------------

def look_at(eye, target, up=(0.0, 0.0, 1.0)) -> Gf.Matrix4d:
    """Row-major USD camera transform. USD cameras look down -Z, +Y is up."""
    e, t, u = Gf.Vec3d(*eye), Gf.Vec3d(*target), Gf.Vec3d(*up)
    fwd = (t - e).GetNormalized()
    right = Gf.Cross(fwd, u).GetNormalized()
    cam_up = Gf.Cross(right, fwd).GetNormalized()
    back = -fwd
    m = Gf.Matrix4d(1.0)
    m.SetRow(0, Gf.Vec4d(right[0], right[1], right[2], 0.0))
    m.SetRow(1, Gf.Vec4d(cam_up[0], cam_up[1], cam_up[2], 0.0))
    m.SetRow(2, Gf.Vec4d(back[0], back[1], back[2], 0.0))
    m.SetRow(3, Gf.Vec4d(e[0], e[1], e[2], 1.0))
    return m


def add_camera(stage, path, eye, target, focal=35.0, note=""):
    cam = UsdGeom.Camera.Define(stage, path)
    cam.CreateFocalLengthAttr(focal)
    cam.CreateClippingRangeAttr(Gf.Vec2f(0.1, 10000.0))
    cam.AddTransformOp().Set(look_at(eye, target))
    if note:
        cam.GetPrim().CreateAttribute(
            "urbantwin:shotNote", Sdf.ValueTypeNames.String, custom=True
        ).Set(note)
    return cam


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------

def build() -> Path:
    out = ROOT / "presentation.usda"
    stage = Usd.Stage.CreateNew(str(out)) if not out.exists() else Usd.Stage.Open(str(out))
    stage.GetRootLayer().Clear()
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)

    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())

    pres = UsdGeom.Scope.Define(stage, "/World/Presentation").GetPrim()
    pres.CreateAttribute("urbantwin:note", Sdf.ValueTypeNames.String, custom=True).Set(
        "Demo presentation layer: lighting, ground, materials, cameras. "
        "Visual only - contributes no simulation values."
    )

    # ---- ground ----------------------------------------------------------
    # Generous overhang so the tile reads as sitting in a wider dark context
    # instead of as a rectangle floating on the viewport grid.
    ground = UsdGeom.Mesh.Define(stage, "/World/Presentation/DemoGround")
    hw, hh = CITY_SIZE[0] * 2.5, CITY_SIZE[1] * 2.5
    ground.CreatePointsAttr([(-hw, -hh, -0.45), (hw, -hh, -0.45),
                             (hw, hh, -0.45), (-hw, hh, -0.45)])
    ground.CreateFaceVertexCountsAttr([4])
    ground.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
    ground.CreateDisplayColorAttr([(0.055, 0.06, 0.07)])
    ground.CreateExtentAttr([(-hw, -hh, -0.45), (hw, hh, -0.45)])

    # ---- materials -------------------------------------------------------
    mats = UsdGeom.Scope.Define(stage, "/World/Presentation/Materials")

    def pbr(name, rgb, rough, metallic=0.0):
        mat = UsdShade.Material.Define(stage, f"{mats.GetPath()}/{name}")
        sh = UsdShade.Shader.Define(stage, f"{mats.GetPath()}/{name}/Surface")
        sh.CreateIdAttr("UsdPreviewSurface")
        sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rgb))
        sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(rough)
        sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metallic)
        mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
        return mat

    # Warm off-white, high roughness. Flat pure white destroys massing
    # readability and blows out next to a bright sun.
    building_mat = pbr("BuildingSurface", (0.80, 0.785, 0.76), 0.72)
    ground_mat = pbr("GroundSurface", (0.055, 0.06, 0.07), 0.95)
    UsdShade.MaterialBindingAPI.Apply(ground.GetPrim()).Bind(ground_mat)

    # Material binding is inheritable, so binding the Buildings scope reaches
    # all 623 meshes without editing the frozen layer.
    buildings = stage.OverridePrim("/World/Buildings")
    UsdShade.MaterialBindingAPI.Apply(buildings).Bind(building_mat)

    # ---- lighting --------------------------------------------------------
    lights = UsdGeom.Scope.Define(stage, "/World/Presentation/Lighting")

    sun = UsdLux.DistantLight.Define(stage, f"{lights.GetPath()}/KeySun")
    # 0.53 deg is the sun's real angular diameter: crisp shadows with a
    # believable penumbra rather than a hard-edged CG look.
    sun.CreateAngleAttr(0.53)
    sun.CreateIntensityAttr(3200.0)
    sun.CreateColorAttr(Gf.Vec3f(1.0, 0.96, 0.90))
    sun.CreateEnableColorTemperatureAttr(True)
    sun.CreateColorTemperatureAttr(5600.0)
    # Elevation ~38 deg from the south-west: shadows long enough to read shade
    # across the streets, without flattening the facades.
    UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-38.0, 0.0, 35.0))
    sun.GetPrim().CreateAttribute(
        "urbantwin:note", Sdf.ValueTypeNames.String, custom=True
    ).Set("Shadow-casting key light. Shade readability depends on this staying enabled.")

    sky = UsdLux.DomeLight.Define(stage, f"{lights.GetPath()}/Sky")
    sky.CreateIntensityAttr(320.0)
    sky.CreateColorAttr(Gf.Vec3f(0.72, 0.80, 0.95))

    # ---- lighting presets as a variant set -------------------------------
    vset = pres.GetVariantSets().AddVariantSet("lighting")
    presets = (
        # name,           sun I,  sun rgb,             K,      sky I, sky rgb
        ("baseline",      3200.0, (1.00, 0.96, 0.90), 5600.0, 320.0, (0.72, 0.80, 0.95)),
        ("extreme_heat",  5200.0, (1.00, 0.89, 0.74), 4200.0, 210.0, (0.95, 0.80, 0.62)),
    )
    for name, sun_i, sun_rgb, temp, sky_i, sky_rgb in presets:
        vset.AddVariant(name)
        vset.SetVariantSelection(name)
        with vset.GetVariantEditContext():
            s = UsdLux.DistantLight.Get(stage, f"{lights.GetPath()}/KeySun")
            s.CreateIntensityAttr(sun_i)
            s.CreateColorAttr(Gf.Vec3f(*sun_rgb))
            s.CreateColorTemperatureAttr(temp)
            d = UsdLux.DomeLight.Get(stage, f"{lights.GetPath()}/Sky")
            d.CreateIntensityAttr(sky_i)
            d.CreateColorAttr(Gf.Vec3f(*sky_rgb))
    vset.SetVariantSelection("baseline")

    # ---- demo cameras ----------------------------------------------------
    cams = UsdGeom.Scope.Define(stage, "/World/Presentation/DemoCameras")

    # Overview at ~28 deg elevation. The current default view is near top-down,
    # which reads as a map; a lower angle reads as a city.
    add_camera(stage, f"{cams.GetPath()}/Demo_01_Overview",
               eye=(430, -620, 330), target=(0, 30, 0), focal=32,
               note="Opening shot. Whole tile, low enough to show massing.")

    add_camera(stage, f"{cams.GetPath()}/Demo_02_Corridor",
               eye=(120, -230, 14), target=(30, -60, 4), focal=40,
               note="Street level. Aim at the corridor the advisor actually changes.")

    add_camera(stage, f"{cams.GetPath()}/Demo_03_ProblemZone",
               eye=(250, -330, 130), target=(60, -110, 0), focal=45,
               note="Tight on the flagged cluster for the advisor beat.")

    stage.GetRootLayer().Save()

    # ---- demo stage composing presentation over the phase 8 scene --------
    main = ROOT / "main.usda"
    main.write_text(
        '#usda 1.0\n'
        '(\n'
        '    defaultPrim = "World"\n'
        '    metersPerUnit = 1\n'
        '    subLayers = [\n'
        '        @presentation.usda@,\n'
        '        @../phase8/scene/main.usda@\n'
        '    ]\n'
        '    upAxis = "Z"\n'
        ')\n\n'
        'def Xform "World"\n'
        '{\n'
        '}\n',
        encoding="utf-8",
    )
    return out


if __name__ == "__main__":
    p = build()
    print(f"wrote {p}")
    print(f"wrote {p.with_name('main.usda')}")
