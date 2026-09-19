"""Author distributed MOCK fixtures using existing OSM ways, not route choice."""
import copy
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).parent / 'mock_data'


def select_corridors(registry):
    source_ids = {v['source_id']: k for k, v in registry['edges'].items()}
    candidates = []
    osm = ET.parse(ROOT / 'phase1/data/sample.osm').getroot()
    for way in osm.findall('way'):
        tags = {t.attrib['k']: t.attrib['v'] for t in way.findall('tag')}
        if tags.get('area') == 'yes' or tags.get('access') in ('private', 'no') or tags.get('foot') in ('private', 'no'):
            continue
        ids = [n.attrib['ref'] for n in way.findall('nd')]
        chain = []

        def finish():
            if not chain:
                return
            entries = [registry['edges'][alias] for alias in chain]
            points = [entries[0]['points'][0]] + [e['points'][1] for e in entries]
            length = sum(math.dist(*e['points']) for e in entries)
            if length >= 35 and math.dist(points[0], points[-1]) >= 25:
                candidates.append({'id': f'way_{way.attrib["id"]}_part_{len(candidates)}',
                                   'osm_way_id': way.attrib['id'], 'name': tags.get('name', 'Mapped pedestrian corridor'),
                                   'edges': list(chain), 'points': points, 'length_m': length,
                                   'center': [sum(p[i] for p in points)/len(points) for i in range(2)]})
            chain.clear()

        for a, b in zip(ids, ids[1:]):
            alias = source_ids.get(f'osm_w{way.attrib["id"]}_n{a}_n{b}')
            if alias is None:
                finish()
                continue
            if chain and math.dist(registry['edges'][chain[-1]]['points'][1], registry['edges'][alias]['points'][0]) > .01:
                finish()
            chain.append(alias)
        finish()
    if len(candidates) < 12:
        raise ValueError('Insufficient mapped corridors for a distributed demo')
    # Spread visual fixtures geographically; do not search for journeys or bridge gaps.
    selected = [max(candidates, key=lambda c: c['length_m'])]
    candidates.remove(selected[0])
    while len(selected) < 24 and candidates:
        candidate = max(candidates, key=lambda c: min(math.dist(c['center'], s['center']) for s in selected))
        selected.append(candidate)
        candidates.remove(candidate)
    return selected


def positions(registry, corridors, count, stressed):
    result = []
    for i in range(count):
        route = corridors[i % len(corridors)]
        group_count = (count - 1 - i % len(corridors)) // len(corridors) + 1
        slot = i // len(corridors)
        distance = route['length_m'] * (slot + .5) / group_count
        for alias in route['edges']:
            a, b = registry['edges'][alias]['points']
            length = math.dist(a, b)
            if distance <= length:
                t = distance / length
                break
            distance -= length
        else:
            t = 1.
        # Alternating lateral lanes stay inside the assumed 2.5m path width.
        dx, dy = b[0]-a[0], b[1]-a[1]
        horizontal = math.hypot(dx, dy)
        offset = .38 if slot % 2 else -.38
        x = a[0]+(b[0]-a[0])*t - dy/horizontal*offset
        y = a[1]+(b[1]-a[1])*t + dx/horizontal*offset
        result.append({'id': f'citizen_{i+1:03d}', 'x': round(x,3), 'y': round(y,3),
                       'z': round(a[2]+(b[2]-a[2])*t+.05,3), 'route': route['edges'],
                       'stress': .78 if stressed else .24, 'heat_exposure': .84 if stressed else .32})
    return result


def main():
    registry = json.loads((ROOT/'phase2/scene/edge_registry.json').read_text(encoding='utf-8'))
    corridors = select_corridors(registry)
    all_edges = sorted({e for c in corridors for e in c['edges']})
    problem_edge = max(corridors[0]['edges'], key=lambda e: math.dist(*registry['edges'][e]['points']))
    states = {}
    for name, sequence, count, stressed in [('normal',0,120,False),('stress',1,300,True)]:
        states[name] = {
            'schema_version': '1.0', 'city_id': registry['city_id'], 'run_id': 'urbantwin-distributed-demo-002',
            'sequence': sequence, 'timestamp': sequence*10., 'data_kind': 'mock',
            'label': f'DEMO / MOCK SIMULATION DATA - DISTRIBUTED {name.upper()}',
            'scenario': {'temperature_c':45 if stressed else 32, 'population_equivalent':100000 if stressed else 50000},
            'agents': positions(registry,corridors,count,stressed),
            'edges': {e: {'crowding': (.91 if e == problem_edge else .58) if stressed else .24,
                          'heat_exposure': .86 if stressed else .34, 'accessibility': .42 if stressed else .76} for e in all_edges},
            'interventions': []}
    states['intervention'] = copy.deepcopy(states['stress'])
    states['intervention'].update(sequence=2, timestamp=20., label='DEMO / MOCK SIMULATION DATA - PROPOSED SHADE; EFFECT NOT SIMULATED')
    states['intervention']['interventions'] = [{'id':'proposal_001','type':'ADD_SHADE','target':problem_edge,'amount':.5}]
    OUT.mkdir(parents=True,exist_ok=True)
    for name, state in states.items():
        (OUT/f'mock_{name}.json').write_text(json.dumps(state,indent=2)+'\n',encoding='utf-8')
    selection = {'status':'DEMO / MOCK SELECTION', 'corridors':corridors,'problem_edge':problem_edge,
                 'note':'Distributed existing OSM ways. Separate corridors are not asserted to connect. No route choice or behavioral simulation.'}
    (OUT/'demo_selection.json').write_text(json.dumps(selection,indent=2)+'\n',encoding='utf-8')
    points = [p for c in corridors for p in c['points']]
    print(json.dumps({'corridors':len(corridors),'segments':len(all_edges),'problem_edge':problem_edge,
                      'route_span_m':[round(max(p[i] for p in points)-min(p[i] for p in points),1) for i in range(2)],
                      'agents':[120,300,300]},indent=2))


if __name__ == '__main__':
    main()
