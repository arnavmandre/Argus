"""Build independent stressed/intervention stages and package an OpenUSD variant set."""
import importlib.util
import os
from pathlib import Path
from pxr import Usd,UsdGeom

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('urbantwin_phase7_bridge',ROOT/'phase7/omniverse_bridge.py')
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
Bridge=module.OmniverseBridge
HERE=Path(__file__).parent


def stage(path):
    value=Usd.Stage.CreateNew(str(path)); UsdGeom.SetStageMetersPerUnit(value,1)
    UsdGeom.SetStageUpAxis(value,UsdGeom.Tokens.z); value.SetDefaultPrim(UsdGeom.Xform.Define(value,'/World').GetPrim())
    return value


def build():
    states=HERE/'states'; scene=HERE/'scene'; scene.mkdir(parents=True,exist_ok=True)
    sources={'Stressed':ROOT/'phase3/mock_data/mock_stress.json',
             'Intervention':ROOT/'phase3/mock_data/mock_intervention.json'}
    for name,source in sources.items(): Bridge(states/name.lower()).load_state(source)
    variants=stage(scene/'variants.usda'); world=variants.GetDefaultPrim()
    variant_set=world.GetVariantSets().AddVariantSet('demoState')
    for name in sources:
        variant_set.AddVariant(name); variant_set.SetVariantSelection(name)
        with variant_set.GetVariantEditContext():
            relative=Path(os.path.relpath(states/name.lower()/'main.usda',scene)).as_posix()
            world.GetReferences().AddReference(relative)
    variant_set.SetVariantSelection('Stressed'); variants.GetRootLayer().Save()
    write_selection('Stressed')
    main=stage(scene/'main.usda'); main.GetRootLayer().subLayerPaths=['selection.usda','variants.usda']
    main.GetRootLayer().Save()
    print('Built Phase 8 variants: Stressed, Intervention; active: Stressed')


def write_selection(name):
    selection=Usd.Stage.CreateNew(str(HERE/'scene/selection.usda'))
    selection.OverridePrim('/World').GetVariantSets().AddVariantSet('demoState').SetVariantSelection(name)
    selection.GetRootLayer().Save()


if __name__=='__main__': build()
