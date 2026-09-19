"""Resolve agreed edge IDs to existing USD meshes. No simulator logic."""
import json
from pathlib import Path
from pxr import UsdGeom


class SceneIndex:
    def __init__(self, stage, registry_path=None):
        path = Path(registry_path) if registry_path else Path(__file__).parent / 'scene/edge_registry.json'
        self.registry = json.loads(path.read_text(encoding='utf-8'))
        self.stage = stage
        world = stage.GetPrimAtPath('/World')
        if not world or world.GetAttribute('urbantwin:cityId').Get() != self.registry['city_id']:
            raise ValueError('Stage and edge registry have different city IDs.')
        self.edges = self.registry['edges']
        self.source_aliases = {entry['source_id']: alias for alias, entry in self.edges.items()}

    def get_edge(self, edge_id):
        alias = edge_id if edge_id in self.edges else self.source_aliases.get(edge_id)
        if alias is None:
            raise KeyError(f'Unknown edge ID: {edge_id}')
        prim = self.stage.GetPrimAtPath(self.edges[alias]['prim_path'])
        if not prim or not prim.IsA(UsdGeom.Mesh) or prim.GetAttribute('urbantwin:edgeId').Get() != alias:
            raise ValueError(f'Edge mapping is invalid: {edge_id}')
        return prim


if __name__ == '__main__':
    import argparse
    from pxr import Usd
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('edge_id', nargs='?', default='edge_012')
    args = parser.parse_args()
    stage = Usd.Stage.Open(str(Path(__file__).parent / 'scene/main.usda'))
    print(SceneIndex(stage).get_edge(args.edge_id).GetPath())
