"""Switch the Phase 8 demo selection layer between Stressed and Intervention."""
import argparse
import os
from pathlib import Path
import tempfile
from pxr import Usd

HERE=Path(__file__).parent
NAMES={'stressed':'Stressed','intervention':'Intervention'}


def switch(name):
    final=HERE/'scene/selection.usda'; final.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='selection.',suffix='.tmp.usda',dir=final.parent); os.close(fd)
    temp=Path(temp)
    try:
        stage=Usd.Stage.CreateNew(str(temp)); world=stage.OverridePrim('/World')
        world.GetVariantSets().AddVariantSet('demoState').SetVariantSelection(NAMES[name])
        stage.GetRootLayer().Save(); del stage; os.replace(temp,final)
    finally:
        temp.unlink(missing_ok=True)
    print(f'UrbanTwin demo state: {NAMES[name]}')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('state',choices=sorted(NAMES))
    switch(parser.parse_args().state)
