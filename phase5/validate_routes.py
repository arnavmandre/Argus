"""Verify route overlays follow route IDs and change when snapshot routes change."""
import json
from collections import Counter
from pathlib import Path
import tempfile
from pxr import Usd, UsdGeom
from omniverse_bridge import OmniverseBridge

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'phase3/mock_data/mock_stress.json'


def route_prims(stage):
    root = stage.GetPrimAtPath('/World/Simulation/Routes')
    return {p.GetName(): p for p in root.GetChildren() if p.IsA(UsdGeom.BasisCurves)}


def force_reload(stage):
    for layer in stage.GetLayerStack(includeSessionLayers=False):
        layer.Reload(True)


with tempfile.TemporaryDirectory() as folder:
    output = Path(folder)
    bridge = OmniverseBridge(output)
    state = json.loads(SOURCE.read_text(encoding='utf-8'))
    bridge.load_state(SOURCE)
    stage = Usd.Stage.Open(str(output/'main.usda'))
    curves = route_prims(stage)
    expected = Counter(edge for a in state['agents'] for edge in set(a['route']))
    assert set(curves) == set(expected)
    assert all(p.GetAttribute('urbantwin:agentUsageCount').Get() == expected[alias] for alias, p in curves.items())
    for alias, prim in curves.items():
        authored = [tuple(p) for p in UsdGeom.BasisCurves(prim).GetPointsAttr().Get()]
        registered = bridge.registry['edges'][alias]['points']
        assert all(abs(a-b) < 1e-4 for p, q in zip(authored, registered)
                   for a, b in zip(p[:2], q[:2]))
    # Valid modified snapshot: all agents now supply only the first two segments.
    changed = json.loads(SOURCE.read_text(encoding='utf-8'))
    changed['sequence'] += 1; changed['timestamp'] += 1
    short_route = changed['agents'][0]['route'][:2]
    for agent in changed['agents']:
        agent['route'] = short_route
    changed_path = output/'changed.json'
    changed_path.write_text(json.dumps(changed), encoding='utf-8')
    bridge.update_routes(changed_path)
    force_reload(stage)
    assert set(route_prims(stage)) == set(short_route)
    assert stage.GetPrimAtPath('/World/Simulation/Agents/AgentInstancer')
    bridge.reset_scene(changed_path)
    force_reload(stage)
    assert not route_prims(stage)
    assert not stage.GetPrimAtPath('/World/Simulation/Agents/AgentInstancer')
print('PASS: supplied IDs create routes, changed IDs change routes, usage counts align, and reset clears routes')
