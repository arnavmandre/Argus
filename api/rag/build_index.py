"""CLI for rebuilding the local intervention vector index."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from api.rag.retrieval import build_index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--knowledge", type=Path, default=Path("data/urban_interventions.json"))
    parser.add_argument("--output", type=Path, default=Path("data/.rag_index"))
    args = parser.parse_args()
    print(json.dumps(build_index(args.knowledge, args.output), indent=2))


if __name__ == "__main__":
    main()
