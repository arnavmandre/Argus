"""Readback checks for Phase 1 artifacts; does not certify viewport appearance."""
import collections
import json
import math
from pathlib import Path
from pxr import Usd, UsdGeom

folder = Path(__file__).parent / 'scene'
manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
stage = Usd.Stage.Open(str(folder/'main.usda'))
assert stage and str(stage.GetDefaultPrim().GetPath()) == '/World'
assert UsdGeom.GetStageUpAxis(stage) == 'Z'
assert UsdGeom.GetStageMetersPerUnit(stage) == 1
assert len(stage.GetUsedLayers()) == 4  # root + two sublayers + anonymous session
counts = collections.Counter()
faces = points = 0
for prim in stage.Traverse():
    if not prim.IsA(UsdGeom.Mesh):
        continue
    mesh = UsdGeom.Mesh(prim)
    vertices = mesh.GetPointsAttr().Get()
    sizes = mesh.GetFaceVertexCountsAttr().Get()
    indices = mesh.GetFaceVertexIndicesAttr().Get()
    assert vertices and sizes and sum(sizes) == len(indices), prim.GetPath()
    assert all(size >= 3 for size in sizes), prim.GetPath()
    assert all(0 <= i < len(vertices) for i in indices), prim.GetPath()
    assert all(math.isfinite(v) for p in vertices for v in p), prim.GetPath()
    assert mesh.GetExtentAttr().Get(), prim.GetPath()
    counts[str(prim.GetPath()).split('/')[2]] += 1
    faces += len(sizes)
    points += len(vertices)
assert dict(counts) == manifest['counts']
assert all(counts[g] > 0 for g in ('Buildings','Roads','PedestrianPaths','GreenSpaces','Transit'))
assert len(manifest['edges']) == counts['PedestrianPaths']
for edge_id, edge in manifest['edges'].items():
    prim = stage.GetPrimAtPath(edge['prim_path'])
    assert prim and prim.GetName() == edge_id
    assert len(edge['points']) == 2
for name in ('Overview','StudyArea'):
    assert stage.GetPrimAtPath('/World/Cameras/'+name).IsA(UsdGeom.Camera)
report = {'result':'PASS: OpenUSD readback and structural checks',
          'openusd_version':list(Usd.GetVersion()), 'mesh_counts':dict(counts),
          'mesh_points':points, 'mesh_faces':faces,
          'mapped_pedestrian_segments':len(manifest['edges']),
          'viewport_rendering':'NOT TESTED — manual Kit inspection required',
          'navigation_performance':'NOT TESTED'}
(folder/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
