"""Verify all intervention handlers and no implied metric improvement."""
import copy
import json
from pathlib import Path
import tempfile
from pxr import Usd,UsdGeom
from omniverse_bridge import OmniverseBridge

ROOT=Path(__file__).resolve().parents[1]
stress_path=ROOT/'phase3/mock_data/mock_stress.json'
intervention_path=ROOT/'phase3/mock_data/mock_intervention.json'


def proposals(stage): return list(stage.GetPrimAtPath('/World/Interventions').GetChildren())


with tempfile.TemporaryDirectory() as folder:
    bridge=OmniverseBridge(folder)
    # Production mock: proposed shade is visible and metrics remain exactly stress values.
    result=bridge.load_state(intervention_path)
    assert result['intervention_objects']==1
    stage=Usd.Stage.Open(str(Path(folder)/'main.usda')); items=proposals(stage)
    assert len(items)==1 and items[0].GetAttribute('urbantwin:type').Get()=='ADD_SHADE'
    assert items[0].GetAttribute('urbantwin:status').Get()=='proposed'
    assert items[0].GetChild('Canopy').IsA(UsdGeom.Cube)
    stress=json.loads(stress_path.read_text(encoding='utf-8'))
    intervention=json.loads(intervention_path.read_text(encoding='utf-8'))
    assert stress['edges']==intervention['edges'] and stress['agents']==intervention['agents']
    # Exercise every contract type in one valid fixture.
    all_types=copy.deepcopy(stress); all_types['sequence']=3; all_types['timestamp']=30
    all_types['interventions']=[
      {'id':'shade','type':'ADD_SHADE','target':'edge_1255','amount':.5},
      {'id':'greenery','type':'ADD_GREENERY','target':'edge_1255','amount':.5},
      {'id':'capacity','type':'INCREASE_PATH_CAPACITY','target':'edge_1255','amount':.5},
      {'id':'access','type':'IMPROVE_ACCESSIBILITY','target':'edge_1255','amount':.5},
      {'id':'route','type':'ADD_ROUTE','new_edge_id':'proposal_demo_route','points':[[-20,-20,.1],[0,0,.1],[20,10,.1]]}]
    fixture=Path(folder)/'all.json'; fixture.write_text(json.dumps(all_types),encoding='utf-8')
    bridge.load_state(fixture)
    for layer in stage.GetLayerStack(includeSessionLayers=False): layer.Reload(True)
    found={p.GetAttribute('urbantwin:type').Get():p for p in proposals(stage)}
    assert set(found)=={'ADD_SHADE','ADD_GREENERY','INCREASE_PATH_CAPACITY','IMPROVE_ACCESSIBILITY','ADD_ROUTE'}
    assert found['ADD_SHADE'].GetChild('Canopy').IsA(UsdGeom.Cube)
    assert any(p.IsA(UsdGeom.Sphere) for p in Usd.PrimRange(found['ADD_GREENERY']))
    assert found['INCREASE_PATH_CAPACITY'].IsA(UsdGeom.BasisCurves)
    assert found['IMPROVE_ACCESSIBILITY'].IsA(UsdGeom.BasisCurves)
    assert found['ADD_ROUTE'].IsA(UsdGeom.BasisCurves)
    assert all(p.GetAttribute('urbantwin:visualOnly').Get() is True for p in found.values())
    # Empty intervention state removes prior proposal geometry.
    bridge.load_state(stress_path)
    for layer in stage.GetLayerStack(includeSessionLayers=False): layer.Reload(True)
    assert not proposals(stage)
print('PASS: all five intervention types author proposed geometry; empty state removes it; metrics remain unchanged')
