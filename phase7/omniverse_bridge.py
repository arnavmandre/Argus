"""Phase 7 bridge: visualize validated intervention proposals as OpenUSD geometry."""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path

from pxr import Gf, Sdf, UsdGeom

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('urbantwin_phase6_bridge',ROOT/'phase6/omniverse_bridge.py')
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
MetricBridge=module.OmniverseBridge
load_and_validate=module.load_and_validate


class OmniverseBridge(MetricBridge):
    PROPOSED=(.0,.9,1.0)

    def __init__(self,output_dir=Path(__file__).parent/'scene'):
        super().__init__(output_dir)

    @staticmethod
    def _prim_name(intervention_id,index):
        digest=hashlib.sha256(intervention_id.encode('utf-8')).hexdigest()[:10]
        return f'proposal_{index:03d}_{digest}'

    def load_state(self,json_path):
        json_path=Path(json_path).resolve()
        load_and_validate(json_path)
        data=json.loads(json_path.read_text(encoding='utf-8'))
        count=self._write_interventions_layer(data)
        result=super().load_state(json_path)
        return {**result,'intervention_objects':count}

    apply_visual_intervention=load_state

    def _metadata(self,prim,item):
        prim.CreateAttribute('urbantwin:interventionId',Sdf.ValueTypeNames.String).Set(item['id'])
        prim.CreateAttribute('urbantwin:type',Sdf.ValueTypeNames.String).Set(item['type'])
        prim.CreateAttribute('urbantwin:status',Sdf.ValueTypeNames.String).Set('proposed')
        prim.CreateAttribute('urbantwin:visualOnly',Sdf.ValueTypeNames.Bool).Set(True)
        if 'target' in item: prim.CreateAttribute('urbantwin:target',Sdf.ValueTypeNames.String).Set(self._alias(item['target']))
        if 'amount' in item: prim.CreateAttribute('urbantwin:amount',Sdf.ValueTypeNames.Double).Set(item['amount'])

    @staticmethod
    def _segment(entry):
        a,b=entry['points']; dx,dy=b[0]-a[0],b[1]-a[1]
        return a,b,math.hypot(dx,dy),math.degrees(math.atan2(dy,dx))

    def _shade(self,stage,path,item,entry):
        root=UsdGeom.Xform.Define(stage,path); self._metadata(root.GetPrim(),item)
        a,b,length,angle=self._segment(entry); coverage=max(1.,length*item['amount'])
        mid=Gf.Vec3d((a[0]+b[0])/2,(a[1]+b[1])/2,3.0)
        canopy=UsdGeom.Cube.Define(stage,path+'/Canopy')
        canopy.CreateSizeAttr(1); canopy.AddTranslateOp().Set(mid); canopy.AddRotateZOp().Set(angle)
        canopy.AddScaleOp().Set(Gf.Vec3f(coverage,3.0,.18)); canopy.CreateDisplayColorAttr([Gf.Vec3f(*self.PROPOSED)])
        ux,uy=(b[0]-a[0])/length,(b[1]-a[1])/length
        for i,sign in enumerate((-1,1),1):
            post=UsdGeom.Cylinder.Define(stage,f'{path}/Post_{i}')
            post.CreateAxisAttr(UsdGeom.Tokens.z); post.CreateRadiusAttr(.12); post.CreateHeightAttr(3.)
            post.AddTranslateOp().Set(Gf.Vec3d(mid[0]+ux*coverage*.45*sign,mid[1]+uy*coverage*.45*sign,1.5))
            post.CreateDisplayColorAttr([Gf.Vec3f(*self.PROPOSED)])

    def _greenery(self,stage,path,item,entry):
        root=UsdGeom.Xform.Define(stage,path); self._metadata(root.GetPrim(),item)
        a,b,length,_=self._segment(entry); count=max(1,round(1+item['amount']*3))
        for i in range(count):
            t=(i+1)/(count+1); x=a[0]+(b[0]-a[0])*t; y=a[1]+(b[1]-a[1])*t
            trunk=UsdGeom.Cylinder.Define(stage,f'{path}/Tree_{i+1}/Trunk')
            trunk.CreateAxisAttr(UsdGeom.Tokens.z); trunk.CreateRadiusAttr(.16); trunk.CreateHeightAttr(2.4)
            trunk.AddTranslateOp().Set(Gf.Vec3d(x,y,1.2)); trunk.CreateDisplayColorAttr([Gf.Vec3f(.35,.18,.06)])
            crown=UsdGeom.Sphere.Define(stage,f'{path}/Tree_{i+1}/Crown')
            crown.CreateRadiusAttr(1.25); crown.AddTranslateOp().Set(Gf.Vec3d(x,y,3.0))
            crown.CreateDisplayColorAttr([Gf.Vec3f(.05,.9,.2)])

    def _curve(self,stage,path,item,points,width,color=None):
        curve=UsdGeom.BasisCurves.Define(stage,path); self._metadata(curve.GetPrim(),item)
        curve.CreateTypeAttr(UsdGeom.Tokens.linear); curve.CreateWrapAttr(UsdGeom.Tokens.nonperiodic)
        curve.CreateCurveVertexCountsAttr([len(points)])
        curve.CreatePointsAttr([Gf.Vec3f(p[0],p[1],p[2]+.8) for p in points])
        curve.CreateWidthsAttr([width]); curve.SetWidthsInterpolation(UsdGeom.Tokens.constant)
        curve.CreateDisplayColorAttr([Gf.Vec3f(*(color or self.PROPOSED))])
        return curve

    def _write_interventions_layer(self,data):
        def author(stage):
            root=UsdGeom.Scope.Define(stage,'/World/Interventions')
            root.GetPrim().CreateAttribute('urbantwin:status',Sdf.ValueTypeNames.String).Set('PROPOSED - EFFECT NOT SIMULATED')
            root.GetPrim().CreateAttribute('urbantwin:count',Sdf.ValueTypeNames.Int).Set(len(data['interventions']))
            for index,item in enumerate(data['interventions'],1):
                path='/World/Interventions/'+self._prim_name(item['id'],index)
                if item['type']=='ADD_ROUTE':
                    self._curve(stage,path,item,item['points'],1.2)
                    continue
                alias=self._alias(item['target']); entry=self.registry['edges'][alias]
                if item['type']=='ADD_SHADE': self._shade(stage,path,item,entry)
                elif item['type']=='ADD_GREENERY': self._greenery(stage,path,item,entry)
                elif item['type']=='INCREASE_PATH_CAPACITY':
                    self._curve(stage,path,item,entry['points'],entry['width_m']+item['amount']*2)
                elif item['type']=='IMPROVE_ACCESSIBILITY':
                    self._curve(stage,path,item,entry['points'],1.0,(.15,.45,1.0))
        self._atomic_stage('interventions.usda',author)
        return len(data['interventions'])

    def _write_main_layer(self):
        def author(stage):
            base=Path(os.path.relpath(ROOT/'phase2/scene/main.usda',self.output_dir)).as_posix()
            stage.GetRootLayer().subLayerPaths=['interventions.usda','metrics.usda','routes.usda','agents.usda',base]
        self._atomic_stage('main.usda',author)


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('state',type=Path)
    parser.add_argument('--out',type=Path,default=Path(__file__).parent/'scene'); args=parser.parse_args()
    print(json.dumps(OmniverseBridge(args.out).load_state(args.state),indent=2))


if __name__=='__main__': main()
