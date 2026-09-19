"""Phase 4 JSON-to-OpenUSD agent bridge. Run with normal Python or Kit Python."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

from pxr import Gf, Sdf, Usd, UsdGeom

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'phase3'))
from validate_mock_data import load_and_validate  # noqa: E402


class OmniverseBridge:
    """Consume complete snapshots and author only the Phase 4 Agents scope."""

    def __init__(self, output_dir=Path(__file__).parent / 'scene'):
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _numeric_id(agent_id):
        # Deterministic positive int64; the original string ID remains authoritative.
        return int.from_bytes(hashlib.sha256(agent_id.encode('utf-8')).digest()[:8], 'big') & ((1 << 63) - 1)

    def load_state(self, json_path):
        json_path = Path(json_path).resolve()
        validation = load_and_validate(json_path)  # complete validation before any output changes
        data = json.loads(json_path.read_text(encoding='utf-8'))
        numeric_ids = [self._numeric_id(a['id']) for a in data['agents']]
        if len(numeric_ids) != len(set(numeric_ids)):
            raise ValueError('Agent IDs collide in the deterministic USD integer-ID mapping.')
        self._write_agents_layer(data, numeric_ids)
        self._write_main_layer()
        return {**validation, 'source': str(json_path), 'output': str(self.output_dir / 'main.usda')}

    def _atomic_stage(self, final_name, author):
        final_path = self.output_dir / final_name
        fd, temporary = tempfile.mkstemp(prefix=final_name + '.', suffix='.tmp.usda', dir=self.output_dir)
        os.close(fd)
        temporary = Path(temporary)
        try:
            stage = Usd.Stage.CreateNew(str(temporary))
            UsdGeom.SetStageMetersPerUnit(stage, 1)
            UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
            stage.SetDefaultPrim(UsdGeom.Xform.Define(stage, '/World').GetPrim())
            author(stage)
            stage.GetRootLayer().Save()
            del stage
            os.replace(temporary, final_path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _write_agents_layer(self, data, numeric_ids):
        def author(stage):
            simulation = UsdGeom.Scope.Define(stage, '/World/Simulation')
            agents_scope = UsdGeom.Scope.Define(stage, '/World/Simulation/Agents')
            simulation.GetPrim().CreateAttribute('urbantwin:runId', Sdf.ValueTypeNames.String).Set(data['run_id'])
            simulation.GetPrim().CreateAttribute('urbantwin:sequence', Sdf.ValueTypeNames.Int64).Set(data['sequence'])
            simulation.GetPrim().CreateAttribute('urbantwin:timestamp', Sdf.ValueTypeNames.Double).Set(data['timestamp'])
            simulation.GetPrim().CreateAttribute('urbantwin:dataKind', Sdf.ValueTypeNames.String).Set(data['data_kind'])
            simulation.GetPrim().CreateAttribute('urbantwin:label', Sdf.ValueTypeNames.String).Set(data['label'])
            simulation.GetPrim().CreateAttribute('urbantwin:temperatureC', Sdf.ValueTypeNames.Double).Set(data['scenario']['temperature_c'])
            simulation.GetPrim().CreateAttribute('urbantwin:populationEquivalent', Sdf.ValueTypeNames.Int64).Set(data['scenario']['population_equivalent'])
            agents_scope.GetPrim().CreateAttribute('urbantwin:representativeAgentCount', Sdf.ValueTypeNames.Int).Set(len(data['agents']))
            if not data['agents']:
                return
            instancer = UsdGeom.PointInstancer.Define(stage, '/World/Simulation/Agents/AgentInstancer')
            prototype = UsdGeom.Capsule.Define(stage, '/World/Simulation/Agents/AgentInstancer/Prototypes/Capsule')
            prototype.CreateAxisAttr(UsdGeom.Tokens.z)
            prototype.CreateHeightAttr(1.2)
            prototype.CreateRadiusAttr(.25)
            prototype.AddTranslateOp().Set(Gf.Vec3d(0, 0, .85))
            prototype.CreateDisplayColorAttr([Gf.Vec3f(.12, .46, .95)])
            instancer.CreatePrototypesRel().SetTargets([prototype.GetPath()])
            instancer.CreateProtoIndicesAttr([0] * len(data['agents']))
            instancer.CreatePositionsAttr([Gf.Vec3f(a['x'], a['y'], a['z']) for a in data['agents']])
            instancer.CreateIdsAttr(numeric_ids)
            prim = instancer.GetPrim()
            prim.CreateAttribute('urbantwin:agentIds', Sdf.ValueTypeNames.StringArray).Set([a['id'] for a in data['agents']])
            prim.CreateAttribute('urbantwin:stress', Sdf.ValueTypeNames.FloatArray).Set([a['stress'] for a in data['agents']])
            prim.CreateAttribute('urbantwin:heatExposure', Sdf.ValueTypeNames.FloatArray).Set([a['heat_exposure'] for a in data['agents']])
            prim.CreateAttribute('urbantwin:routesJson', Sdf.ValueTypeNames.StringArray).Set([json.dumps(a['route']) for a in data['agents']])
            prim.CreateAttribute('urbantwin:coordinateMeaning', Sdf.ValueTypeNames.String).Set('metres; X east, Y north, Z up; position Z is foot elevation')
        self._atomic_stage('agents.usda', author)

    def _write_main_layer(self):
        def author(stage):
            relative_base = Path(os.path.relpath(ROOT / 'phase2/scene/main.usda', self.output_dir)).as_posix()
            stage.GetRootLayer().subLayerPaths = ['agents.usda', relative_base]
        self._atomic_stage('main.usda', author)

    # Full-snapshot semantics implement create/update/remove/reset in one operation.
    spawn_agents = load_state
    update_agents = load_state

    def reset_agents(self, template_json):
        data = json.loads(Path(template_json).read_text(encoding='utf-8'))
        data['agents'] = []
        fd, name = tempfile.mkstemp(suffix='.json')
        os.close(fd)
        path = Path(name)
        try:
            path.write_text(json.dumps(data), encoding='utf-8')
            return self.load_state(path)
        finally:
            path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('state', type=Path)
    parser.add_argument('--out', type=Path, default=Path(__file__).parent / 'scene')
    args = parser.parse_args()
    print(json.dumps(OmniverseBridge(args.out).load_state(args.state), indent=2))


if __name__ == '__main__':
    main()
