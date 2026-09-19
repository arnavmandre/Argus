"""Validate and load one canonical simulator snapshot into an Omniverse scene."""
import argparse
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('urbantwin_phase7_bridge',ROOT/'phase7/omniverse_bridge.py')
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot',type=Path,help='Canonical v1 snapshot JSON')
    parser.add_argument('--out',type=Path,default=Path(__file__).parent/'runtime/scene')
    args=parser.parse_args()
    result=module.OmniverseBridge(args.out).load_state(args.snapshot)
    print(json.dumps(result,indent=2))
    print(f'Open in UrbanTwin: {(args.out.resolve()/"main.usda")}')


if __name__=='__main__': main()
