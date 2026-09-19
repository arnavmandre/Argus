"""Verify Phase 4 positions, identity arrays, composition and snapshot replacement."""
import json
from pathlib import Path
import tempfile
from pxr import Usd, UsdGeom
from omniverse_bridge import OmniverseBridge

ROOT = Path(__file__).resolve().parents[1]
MOCK = ROOT / 'phase3/mock_data'


def check(stage_path, source_path):
    data = json.loads(source_path.read_text(encoding='utf-8'))
    stage = Usd.Stage.Open(str(stage_path))
    assert stage and stage.GetPrimAtPath('/World/Buildings')
    scope = stage.GetPrimAtPath('/World/Simulation/Agents')
    assert scope.GetAttribute('urbantwin:representativeAgentCount').Get() == len(data['agents'])
    instancer = UsdGeom.PointInstancer(stage.GetPrimAtPath('/World/Simulation/Agents/AgentInstancer'))
    if not data['agents']:
        assert not instancer
        return
    assert instancer
    expected = [(a['x'], a['y'], a['z']) for a in data['agents']]
    actual = [tuple(p) for p in instancer.GetPositionsAttr().Get()]
    assert all(abs(a-b) < 1e-4 for actual_point, expected_point in zip(actual, expected)
               for a, b in zip(actual_point, expected_point)), (actual[0], expected[0])
    assert instancer.GetPrim().GetAttribute('urbantwin:agentIds').Get() == [a['id'] for a in data['agents']]
    assert len(instancer.GetIdsAttr().Get()) == len(set(instancer.GetIdsAttr().Get())) == len(data['agents'])


with tempfile.TemporaryDirectory() as folder:
    bridge = OmniverseBridge(folder)
    normal = MOCK/'mock_normal.json'
    stress = MOCK/'mock_stress.json'
    bridge.load_state(normal); check(Path(folder)/'main.usda', normal)
    bridge.update_agents(stress); check(Path(folder)/'main.usda', stress)
    bridge.reset_agents(stress)
    stage = Usd.Stage.Open(str(Path(folder)/'main.usda'))
    assert stage.GetPrimAtPath('/World/Simulation/Agents').GetAttribute('urbantwin:representativeAgentCount').Get() == 0
    assert not stage.GetPrimAtPath('/World/Simulation/Agents/AgentInstancer')
    bad = json.loads(stress.read_text(encoding='utf-8')); bad['city_id'] = '0'*64
    bad_path = Path(folder)/'bad.json'; bad_path.write_text(json.dumps(bad), encoding='utf-8')
    before = (Path(folder)/'agents.usda').read_bytes()
    try: bridge.load_state(bad_path)
    except ValueError: pass
    else: raise AssertionError('Invalid snapshot accepted')
    assert (Path(folder)/'agents.usda').read_bytes() == before
print('PASS: spawn, coordinate update, removal/reset, composition, and invalid-state rollback')
