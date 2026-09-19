"""Compose the accepted Phase 1 city with semantic IDs and empty future scopes."""
import hashlib
import json
from pathlib import Path
from pxr import Sdf, Usd, UsdGeom

ROOT = Path(__file__).resolve().parents[1]


def prepare(output=ROOT / 'phase2' / 'scene'):
    source = ROOT / 'phase1' / 'scene'
    manifest_bytes = (source / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    city_id = hashlib.sha256(manifest_bytes).hexdigest()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    registry_path = output / 'edge_registry.json'
    if registry_path.exists():
        registry = json.loads(registry_path.read_text(encoding='utf-8'))
        if registry['city_id'] != city_id:
            raise ValueError('City manifest changed. Create a new output directory for a new city revision; never reassign frozen aliases.')
        mapped = {v['source_id']: v['prim_path'] for v in registry['edges'].values()}
        expected = {k: v['prim_path'] for k, v in manifest['edges'].items()}
        if mapped != expected or len(registry['edges']) != len(expected):
            raise ValueError('Existing registry does not match the frozen city manifest.')
    else:
        registry = {
            'schema_version': '1.0', 'city_id': city_id,
            'description': 'Frozen visual segment aliases; not a routing graph or measured congestion corridors.',
            'origin_wgs84': manifest['origin_wgs84'], 'axes': manifest['axes'],
            'meters_per_unit': 1,
            'edges': {f'edge_{i:03d}': {'source_id': key, **manifest['edges'][key]}
                      for i, key in enumerate(sorted(manifest['edges']), 1)}
        }
    # Verify all targets before writing layers.
    base = Usd.Stage.Open(str(source / 'main.usda'))
    for entry in registry['edges'].values():
        if not base.GetPrimAtPath(entry['prim_path']).IsA(UsdGeom.Mesh):
            raise ValueError(f"Missing path mesh: {entry['prim_path']}")

    def new_stage(name):
        stage = Usd.Stage.CreateNew(str(output / name))
        UsdGeom.SetStageMetersPerUnit(stage, 1)
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        stage.SetDefaultPrim(UsdGeom.Xform.Define(stage, '/World').GetPrim())
        return stage

    semantics = new_stage('semantics.usda')
    semantics.GetDefaultPrim().CreateAttribute('urbantwin:cityId', Sdf.ValueTypeNames.String).Set(city_id)
    for alias, entry in registry['edges'].items():
        prim = semantics.OverridePrim(entry['prim_path'])
        for attr, value in [('edgeId', alias), ('sourceId', entry['source_id']),
                            ('osmWayId', entry['osm_way_id']), ('widthSource', entry['width_source'])]:
            prim.CreateAttribute('urbantwin:' + attr, Sdf.ValueTypeNames.String).Set(value)
        prim.CreateAttribute('urbantwin:centerline', Sdf.ValueTypeNames.Point3dArray).Set(entry['points'])
        prim.CreateAttribute('urbantwin:widthM', Sdf.ValueTypeNames.Double).Set(entry['width_m'])
    semantics.GetRootLayer().Save()
    for filename, scopes in [
        ('simulation.usda', ['Simulation', 'Simulation/Agents', 'Simulation/Routes',
                             'Simulation/HeatZones', 'Simulation/CrowdZones']),
        ('interventions.usda', ['Interventions'])]:
        stage = new_stage(filename)
        for scope in scopes:
            UsdGeom.Scope.Define(stage, '/World/' + scope)
        stage.GetRootLayer().Save()
    main = new_stage('main.usda')
    import os
    base_path = Path(os.path.relpath(source / 'main.usda', output)).as_posix()
    main.GetRootLayer().subLayerPaths = ['interventions.usda', 'simulation.usda', 'semantics.usda', base_path]
    main.GetRootLayer().Save()
    registry_path.write_text(json.dumps(registry, indent=2) + '\n', encoding='utf-8')
    print(f'Prepared {len(registry["edges"])} stable aliases in {output}')
    return registry


if __name__ == '__main__':
    prepare()
