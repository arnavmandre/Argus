"""Phase 6 bridge: agents, routes, and supplied heat/crowding overlays."""
import argparse
import importlib.util
import json
import math
import os
from pathlib import Path

from pxr import Gf, Sdf, UsdGeom

ROOT = Path(__file__).resolve().parents[1]
phase5_spec = importlib.util.spec_from_file_location('urbantwin_phase5_bridge', ROOT/'phase5/omniverse_bridge.py')
phase5_module = importlib.util.module_from_spec(phase5_spec)
phase5_spec.loader.exec_module(phase5_module)
RouteBridge = phase5_module.OmniverseBridge
load_and_validate = phase5_module.load_and_validate


class OmniverseBridge(RouteBridge):
    CROWD_COLORS = {'low': (.08,.72,.25), 'moderate': (1.0,.62,.02), 'high': (.82,.03,.62)}
    HEAT_COLORS = {'low': (.05,.45,1.0), 'moderate': (1.0,.38,.02), 'high': (1.0,.03,.02)}

    def __init__(self, output_dir=Path(__file__).parent/'scene'):
        super().__init__(output_dir)

    @staticmethod
    def metric_class(value):
        if value < .3: return 'low'
        if value < .7: return 'moderate'
        return 'high'

    def load_state(self, json_path):
        json_path = Path(json_path).resolve()
        load_and_validate(json_path)
        data = json.loads(json_path.read_text(encoding='utf-8'))
        counts = self._write_metrics_layer(data)
        result = super().load_state(json_path)
        return {**result, **counts}

    update_crowding = load_state
    update_heat = load_state

    def _metric_curve(self, stage, scope, alias, entry, metric_name, value, side, colors):
        a,b = entry['points']
        dx,dy = b[0]-a[0],b[1]-a[1]
        length = math.hypot(dx,dy)
        nx,ny = -dy/length*side,dx/length*side
        curve = UsdGeom.BasisCurves.Define(stage,f'/World/Simulation/{scope}/{alias}')
        curve.CreateTypeAttr(UsdGeom.Tokens.linear)
        curve.CreateWrapAttr(UsdGeom.Tokens.nonperiodic)
        curve.CreateCurveVertexCountsAttr([2])
        curve.CreatePointsAttr([Gf.Vec3f(a[0]+nx,a[1]+ny,a[2]+.55),Gf.Vec3f(b[0]+nx,b[1]+ny,b[2]+.55)])
        curve.CreateWidthsAttr([.65])
        curve.SetWidthsInterpolation(UsdGeom.Tokens.constant)
        category = self.metric_class(value)
        curve.CreateDisplayColorAttr([Gf.Vec3f(*colors[category])])
        prim = curve.GetPrim()
        prim.CreateAttribute('urbantwin:edgeId',Sdf.ValueTypeNames.String).Set(alias)
        prim.CreateAttribute('urbantwin:metric',Sdf.ValueTypeNames.String).Set(metric_name)
        prim.CreateAttribute('urbantwin:value',Sdf.ValueTypeNames.Double).Set(value)
        prim.CreateAttribute('urbantwin:class',Sdf.ValueTypeNames.String).Set(category)

    def _write_metrics_layer(self,data):
        crowd = heat = 0
        def author(stage):
            nonlocal crowd,heat
            for scope,metric,side,colors in [('CrowdZones','crowding',-.65,self.CROWD_COLORS),
                                              ('HeatZones','heat_exposure',.65,self.HEAT_COLORS)]:
                root = UsdGeom.Scope.Define(stage,f'/World/Simulation/{scope}')
                root.GetPrim().CreateAttribute('urbantwin:legend',Sdf.ValueTypeNames.String).Set(
                    'Simulation metric display: low [0,0.3), moderate [0.3,0.7), high [0.7,1]')
                root.GetPrim().CreateAttribute('urbantwin:scientificThresholds',Sdf.ValueTypeNames.Bool).Set(False)
                for supplied_id,values in data['edges'].items():
                    if metric not in values: continue
                    alias = self._alias(supplied_id)
                    self._metric_curve(stage,scope,alias,self.registry['edges'][alias],metric,values[metric],side,colors)
                    if metric == 'crowding': crowd += 1
                    else: heat += 1
        self._atomic_stage('metrics.usda',author)
        return {'crowd_segments':crowd,'heat_segments':heat}

    def _write_main_layer(self):
        def author(stage):
            relative_base = Path(os.path.relpath(ROOT/'phase2/scene/main.usda',self.output_dir)).as_posix()
            stage.GetRootLayer().subLayerPaths = ['metrics.usda','routes.usda','agents.usda',relative_base]
        self._atomic_stage('main.usda',author)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('state',type=Path)
    parser.add_argument('--out',type=Path,default=Path(__file__).parent/'scene')
    args=parser.parse_args()
    print(json.dumps(OmniverseBridge(args.out).load_state(args.state),indent=2))


if __name__ == '__main__': main()
