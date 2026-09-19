"""Verify Phase 6 values, classes, colors and changed-state visualization."""
import json
from pathlib import Path
import tempfile
from pxr import Usd,UsdGeom
from omniverse_bridge import OmniverseBridge

ROOT=Path(__file__).resolve().parents[1]
MOCK=ROOT/'phase3/mock_data'


def force_reload(stage):
    for layer in stage.GetLayerStack(includeSessionLayers=False): layer.Reload(True)


def inspect(stage,state):
    for edge_id,values in state['edges'].items():
        for scope,metric,colors in [('CrowdZones','crowding',OmniverseBridge.CROWD_COLORS),
                                    ('HeatZones','heat_exposure',OmniverseBridge.HEAT_COLORS)]:
            prim=stage.GetPrimAtPath(f'/World/Simulation/{scope}/{edge_id}')
            assert prim.IsA(UsdGeom.BasisCurves)
            value=values[metric]; category=OmniverseBridge.metric_class(value)
            assert prim.GetAttribute('urbantwin:value').Get()==value
            assert prim.GetAttribute('urbantwin:class').Get()==category
            color=UsdGeom.BasisCurves(prim).GetDisplayColorAttr().Get()[0]
            assert all(abs(a-b)<1e-6 for a,b in zip(color,colors[category]))
    assert len(stage.GetPrimAtPath('/World/Simulation/HeatZones').GetChildren())==len(state['edges'])
    assert len(stage.GetPrimAtPath('/World/Simulation/CrowdZones').GetChildren())==len(state['edges'])
    assert stage.GetPrimAtPath('/World/Simulation/Agents/AgentInstancer')
    assert stage.GetPrimAtPath('/World/Simulation/Routes').GetChildren()


with tempfile.TemporaryDirectory() as folder:
    bridge=OmniverseBridge(folder)
    normal=json.loads((MOCK/'mock_normal.json').read_text(encoding='utf-8'))
    stress=json.loads((MOCK/'mock_stress.json').read_text(encoding='utf-8'))
    bridge.load_state(MOCK/'mock_normal.json')
    stage=Usd.Stage.Open(str(Path(folder)/'main.usda')); inspect(stage,normal)
    normal_heat=UsdGeom.BasisCurves(stage.GetPrimAtPath('/World/Simulation/HeatZones/edge_1255')).GetDisplayColorAttr().Get()
    normal_crowd=UsdGeom.BasisCurves(stage.GetPrimAtPath('/World/Simulation/CrowdZones/edge_1255')).GetDisplayColorAttr().Get()
    bridge.load_state(MOCK/'mock_stress.json'); force_reload(stage); inspect(stage,stress)
    assert UsdGeom.BasisCurves(stage.GetPrimAtPath('/World/Simulation/HeatZones/edge_1255')).GetDisplayColorAttr().Get()!=normal_heat
    assert UsdGeom.BasisCurves(stage.GetPrimAtPath('/World/Simulation/CrowdZones/edge_1255')).GetDisplayColorAttr().Get()!=normal_crowd
    assert stage.GetPrimAtPath('/World/Simulation/CrowdZones/edge_1255').GetAttribute('urbantwin:class').Get()=='high'
print('PASS: 156 heat + crowd overlays match JSON; normal-to-stress values change colors; problem edge is high crowd')
