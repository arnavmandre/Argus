"""CLI entry: ``python -m api --host 127.0.0.1 --port 8000``."""
from __future__ import annotations

import argparse
from pathlib import Path

from api.env import load_local_env
from api.server import serve


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="UrbanTwin local HTTP API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repo root (defaults to the parent of the api package)",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve() if args.root else Path(__file__).resolve().parents[1]
    load_local_env(root / ".env")
    serve(args.host, args.port, root=root)


if __name__ == "__main__":
    main()
