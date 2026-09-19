"""Focused negative checks for project-specific validation rules."""
import copy
import json
from pathlib import Path
from validate_mock_data import StateValidationError, validate_state

HERE = Path(__file__).parent
ROOT = HERE.parent
schema = json.loads((HERE/'simulation_state.schema.json').read_text(encoding='utf-8'))
registry = json.loads((ROOT/'phase2/scene/edge_registry.json').read_text(encoding='utf-8'))
valid = json.loads((HERE/'mock_data/mock_stress.json').read_text(encoding='utf-8'))


def rejected(mutator):
    state = copy.deepcopy(valid)
    mutator(state)
    try:
        validate_state(state, schema, registry)
    except StateValidationError:
        return
    raise AssertionError('Invalid state was accepted')


rejected(lambda s: s.update(city_id='0'*64))
rejected(lambda s: s['edges'].update(edge_DOES_NOT_EXIST={'crowding': .5}))
rejected(lambda s: s['agents'][1].update(id=s['agents'][0]['id']))
rejected(lambda s: s['agents'][0].update(stress=1.1))
rejected(lambda s: s.update(label='unlabelled mock'))
print('PASS: wrong city, unknown edge, duplicate agent, out-of-range metric, and unlabelled mock rejected')
