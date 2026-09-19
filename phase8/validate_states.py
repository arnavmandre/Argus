"""Validate variant isolation and equal stress scenario/metrics across before/after."""
import json
import subprocess
import sys
from pathlib import Path
from pxr import Usd,UsdGeom

HERE=Path(__file__).parent
MAIN=HERE/'scene/main.usda'


def read(name):
    subprocess.run([sys.executable,str(HERE/'switch_state.py'),name],check=True,capture_output=True,text=True)
    stage=Usd.Stage.Open(str(MAIN)); world=stage.GetPrimAtPath('/World')
    selected=world.GetVariantSet('demoState').GetVariantSelection()
    interventions=list(stage.GetPrimAtPath('/World/Interventions').GetChildren())
    intervention_facts=[{'type':p.GetAttribute('urbantwin:type').Get(),
                         'has_canopy':p.GetChild('Canopy').IsA(UsdGeom.Cube)} for p in interventions]
    simulation=stage.GetPrimAtPath('/World/Simulation')
    metrics={}
    for scope in ['HeatZones','CrowdZones']:
        metrics[scope]={p.GetName():(p.GetAttribute('urbantwin:value').Get(),p.GetAttribute('urbantwin:class').Get())
                        for p in stage.GetPrimAtPath('/World/Simulation/'+scope).GetChildren()}
    agents=UsdGeom.PointInstancer(stage.GetPrimAtPath('/World/Simulation/Agents/AgentInstancer'))
    return {'selected':selected,'interventions':intervention_facts,'temperature':simulation.GetAttribute('urbantwin:temperatureC').Get(),
            'population':simulation.GetAttribute('urbantwin:populationEquivalent').Get(),'metrics':metrics,
            'positions':list(agents.GetPositionsAttr().Get()),'routes':sorted(p.GetName() for p in stage.GetPrimAtPath('/World/Simulation/Routes').GetChildren())}


stressed=read('stressed'); intervention=read('intervention')
assert stressed['selected']=='Stressed' and intervention['selected']=='Intervention'
assert not stressed['interventions'] and len(intervention['interventions'])==1
proposal=intervention['interventions'][0]
assert proposal=={'type':'ADD_SHADE','has_canopy':True}
for key in ['temperature','population','metrics','positions','routes']:
    assert stressed[key]==intervention[key],key
assert stressed['temperature']==45 and stressed['population']==100000
# Restore the demo opening state.
subprocess.run([sys.executable,str(HERE/'switch_state.py'),'stressed'],check=True,capture_output=True,text=True)
print(json.dumps({'result':'PASS','states':['Stressed','Intervention'],'stress_interventions':0,
                  'intervention_interventions':1,'unchanged':['scenario','agents','routes','heat','crowding'],
                  'active_state':'Stressed'},indent=2))
