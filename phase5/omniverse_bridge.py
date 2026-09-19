"""Phase 5 bridge: Phase 4 agents plus supplied route/path-usage overlays."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

from pxr import Gf, Sdf, UsdGeom

ROOT = Path(__file__).resolve().parents[1]
phase4_spec = importlib.util.spec_from_file_location('urbantwin_phase4_bridge', ROOT / 'phase4/omniverse_bridge.py')
phase4_module = importlib.util.module_from_spec(phase4_spec)
phase4_spec.loader.exec_module(phase4_module)
AgentBridge = phase4_module.OmniverseBridge
load_and_validate = phase4_module.load_and_validate


class OmniverseBridge(AgentBridge):
    def __init__(self, output_dir=Path(__file__).parent / 'scene'):
        super().__init__(output_dir)
        registry_path = ROOT / 'phase2/scene/edge_registry.json'
        self.registry = json.loads(registry_path.read_text(encoding='utf-8'))
        self.source_aliases = {v['source_id']: k for k, v in self.registry['edges'].items()}

    def _alias(self, edge_id):
        return edge_id if edge_id in self.registry['edges'] else self.source_aliases[edge_id]

    def load_state(self, json_path):
        json_path = Path(json_path).resolve()
        # Validate before either generated layer changes. Parent validates again before agents.
        load_and_validate(json_path)
        data = json.loads(json_path.read_text(encoding='utf-8'))
        route_count = self._write_routes_layer(data)
        result = super().load_state(json_path)
        return {**result, 'route_segments': route_count}

    spawn_agents = load_state
    update_agents = load_state
    update_routes = load_state

    def _write_routes_layer(self, data):
        usage = {}
        for agent in data['agents']:
            # Count an agent once per segment even if malformed upstream route data repeats it.
            for edge_id in dict.fromkeys(agent['route']):
                alias = self._alias(edge_id)
                usage[alias] = usage.get(alias, 0) + 1

        def author(stage):
            routes = UsdGeom.Scope.Define(stage, '/World/Simulation/Routes')
            routes.GetPrim().CreateAttribute('urbantwin:visualization', Sdf.ValueTypeNames.String).Set(
                'Supplied route usage; orange curves are not calculated routes')
            routes.GetPrim().CreateAttribute('urbantwin:segmentCount', Sdf.ValueTypeNames.Int).Set(len(usage))
            for alias in sorted(usage):
                entry = self.registry['edges'][alias]
                curve = UsdGeom.BasisCurves.Define(stage, f'/World/Simulation/Routes/{alias}')
                curve.CreateTypeAttr(UsdGeom.Tokens.linear)
                curve.CreateWrapAttr(UsdGeom.Tokens.nonperiodic)
                curve.CreateCurveVertexCountsAttr([2])
                points = [Gf.Vec3f(p[0], p[1], p[2] + .35) for p in entry['points']]
                curve.CreatePointsAttr(points)
                curve.CreateWidthsAttr([.7])
                curve.SetWidthsInterpolation(UsdGeom.Tokens.constant)
                curve.CreateDisplayColorAttr([Gf.Vec3f(1.0, .22, .03)])
                prim = curve.GetPrim()
                prim.CreateAttribute('urbantwin:edgeId', Sdf.ValueTypeNames.String).Set(alias)
                prim.CreateAttribute('urbantwin:sourceId', Sdf.ValueTypeNames.String).Set(entry['source_id'])
                prim.CreateAttribute('urbantwin:agentUsageCount', Sdf.ValueTypeNames.Int).Set(usage[alias])
        self._atomic_stage('routes.usda', author)
        return len(usage)

    def _write_main_layer(self):
        def author(stage):
            relative_base = Path(os.path.relpath(ROOT / 'phase2/scene/main.usda', self.output_dir)).as_posix()
            stage.GetRootLayer().subLayerPaths = ['routes.usda', 'agents.usda', relative_base]
        self._atomic_stage('main.usda', author)

    def reset_scene(self, template_json):
        data = json.loads(Path(template_json).read_text(encoding='utf-8'))
        data['agents'] = []
        import tempfile
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
