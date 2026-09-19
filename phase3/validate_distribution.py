"""Check mock route continuity, geographic coverage and citizen-to-path mapping."""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
registry = json.loads((ROOT/'phase2/scene/edge_registry.json').read_text(encoding='utf-8'))
selection = json.loads((ROOT/'phase3/mock_data/demo_selection.json').read_text(encoding='utf-8'))
edges = registry['edges']
for corridor in selection['corridors']:
    assert len(corridor['edges']) == len(set(corridor['edges']))
    for first, second in zip(corridor['edges'], corridor['edges'][1:]):
        assert math.dist(edges[first]['points'][1], edges[second]['points'][0]) < .01


def point_distance(agent, edge):
    a,b = edge['points']
    dx,dy = b[0]-a[0],b[1]-a[1]
    t = max(0,min(1,((agent['x']-a[0])*dx+(agent['y']-a[1])*dy)/(dx*dx+dy*dy)))
    return math.hypot(agent['x']-a[0]-t*dx,agent['y']-a[1]-t*dy)


for name in ['normal','stress']:
    state = json.loads((ROOT/f'phase3/mock_data/mock_{name}.json').read_text(encoding='utf-8'))
    agents = state['agents']
    assert len({tuple(a['route']) for a in agents}) == 24
    assert len({(a['x'],a['y']) for a in agents}) == len(agents)
    assert all(min(point_distance(a, edges[e]) for e in a['route']) < .4 for a in agents)
    span = [max(a[k] for a in agents)-min(a[k] for a in agents) for k in ['x','y']]
    assert min(span) > 650, span
    assert len({(a['x']>0,a['y']>0) for a in agents}) == 4
    print(f'PASS {name}: {len(agents)} mapped citizens, 24 routes, span {span[0]:.1f} x {span[1]:.1f} m')
stress = json.loads((ROOT/'phase3/mock_data/mock_stress.json').read_text(encoding='utf-8'))
intervention = json.loads((ROOT/'phase3/mock_data/mock_intervention.json').read_text(encoding='utf-8'))
assert stress['agents'] == intervention['agents'] and stress['edges'] == intervention['edges']
print('PASS: shade proposal preserves agent positions and metrics')
