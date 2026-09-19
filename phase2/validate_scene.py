"""Check composition, preserved geometry, full ID lookup and rejection behavior."""
import hashlib
import json
from pathlib import Path
from pxr import Usd, UsdGeom
from scene_index import SceneIndex

root = Path(__file__).resolve().parents[1]
stage = Usd.Stage.Open(str(root / 'phase2/scene/main.usda'))
base = Usd.Stage.Open(str(root / 'phase1/scene/main.usda'))
index = SceneIndex(stage)
assert index.registry['city_id'] == hashlib.sha256((root / 'phase1/scene/manifest.json').read_bytes()).hexdigest()
assert UsdGeom.GetStageUpAxis(stage) == 'Z'
assert UsdGeom.GetStageMetersPerUnit(stage) == 1
for group in ['Buildings', 'Roads', 'PedestrianPaths', 'GreenSpaces', 'Transit',
              'Environment', 'Cameras', 'Simulation', 'Simulation/Agents',
              'Simulation/Routes', 'Simulation/HeatZones', 'Simulation/CrowdZones', 'Interventions']:
    assert stage.GetPrimAtPath('/World/' + group), group
paths = set()
for alias, entry in index.edges.items():
    prim = index.get_edge(alias)
    assert index.get_edge(entry['source_id']) == prim
    assert str(prim.GetPath()) not in paths
    paths.add(str(prim.GetPath()))
for prim in base.Traverse():
    if prim.IsA(UsdGeom.Mesh):
        original = UsdGeom.Mesh(prim)
        composed = UsdGeom.Mesh(stage.GetPrimAtPath(prim.GetPath()))
        for getter in ('GetPointsAttr', 'GetFaceVertexCountsAttr', 'GetFaceVertexIndicesAttr', 'GetDisplayColorAttr'):
            assert getattr(original, getter)().Get() == getattr(composed, getter)().Get(), prim.GetPath()
try:
    index.get_edge('edge_DOES_NOT_EXIST')
except KeyError:
    pass
else:
    raise AssertionError('Unknown ID accepted')
try:
    SceneIndex(base)
except ValueError:
    pass
else:
    raise AssertionError('Stage without the matching city ID accepted')
print(json.dumps({'result': 'PASS', 'resolved_aliases': len(paths),
                  'edge_012': str(index.get_edge('edge_012').GetPath()),
                  'base_geometry': 'unchanged', 'unknown_id_and_wrong_city': 'rejected'}, indent=2))
