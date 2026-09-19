"""Validate snapshots against JSON Schema and the frozen project registry."""
import argparse
import json
import math
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = Path(__file__).parent / 'simulation_state.schema.json'
REGISTRY_PATH = ROOT / 'phase2/scene/edge_registry.json'


class StateValidationError(ValueError):
    pass


def validate_state(data, schema, registry):
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        error = errors[0]
        location = '/'.join(map(str, error.absolute_path)) or '<root>'
        raise StateValidationError(f'{location}: {error.message}')
    if data['city_id'] != registry['city_id']:
        raise StateValidationError('city_id does not match the frozen edge registry')
    known = registry['edges']
    source_to_alias = {value['source_id']: key for key, value in known.items()}
    def resolve(edge_id):
        if edge_id in known: return edge_id
        if edge_id in source_to_alias: return source_to_alias[edge_id]
        raise StateValidationError(f'unknown edge ID: {edge_id}')
    agent_ids = [a['id'] for a in data['agents']]
    if len(agent_ids) != len(set(agent_ids)):
        raise StateValidationError('agent IDs must be unique')
    intervention_ids = [i['id'] for i in data['interventions']]
    if len(intervention_ids) != len(set(intervention_ids)):
        raise StateValidationError('intervention IDs must be unique')
    references = []
    for edge_id in data['edges']:
        references.append((edge_id, resolve(edge_id)))
    for agent in data['agents']:
        references.extend((edge_id, resolve(edge_id)) for edge_id in agent['route'])
    for item in data['interventions']:
        if item['type'] != 'ADD_ROUTE':
            references.append((item['target'], resolve(item['target'])))
    aliases = {}
    for supplied, canonical in references:
        previous = aliases.setdefault(canonical, supplied)
        if previous != supplied:
            raise StateValidationError(f'mixed aliases for one segment: {previous} and {supplied}')
    proposed = [i['new_edge_id'] for i in data['interventions'] if i['type'] == 'ADD_ROUTE']
    if len(proposed) != len(set(proposed)) or set(proposed) & set(known):
        raise StateValidationError('new_edge_id values must be unique and not existing edge IDs')
    # JSON parsers can admit NaN/Infinity although JSON itself cannot.
    def finite(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise StateValidationError('all numeric values must be finite')
        if isinstance(value, dict):
            for child in value.values(): finite(child)
        elif isinstance(value, list):
            for child in value: finite(child)
    finite(data)
    return {'agents': len(data['agents']), 'edges': len(data['edges']),
            'interventions': len(data['interventions'])}


def load_and_validate(path):
    schema = json.loads(SCHEMA_PATH.read_text(encoding='utf-8'))
    registry = json.loads(REGISTRY_PATH.read_text(encoding='utf-8'))
    data = json.loads(Path(path).read_text(encoding='utf-8'), parse_constant=lambda x: (_ for _ in ()).throw(StateValidationError(f'invalid JSON number {x}')))
    return validate_state(data, schema, registry)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='*', type=Path)
    args = parser.parse_args()
    files = args.files or sorted((Path(__file__).parent / 'mock_data').glob('mock_*.json'))
    failed = False
    for path in files:
        try:
            result = load_and_validate(path)
            print(f'PASS {path}: {result}')
        except Exception as error:
            failed = True
            print(f'FAIL {path}: {error}')
    raise SystemExit(1 if failed else 0)
