"""CLI entry point: python -m app.research.run --manifest path/to/manifest.yaml"""
import argparse
import json
from pathlib import Path

from app.research.runner import load_manifest, run_backtest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a backtest from a manifest YAML file")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=None, help="Output directory (default: manifest parent dir)")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    out_dir = args.out or args.manifest.parent
    print(f"Running backtest run_id={manifest.run_id} strategy={manifest.strategy_id} bars={manifest.bars}")
    metrics = run_backtest(manifest, output_dir=out_dir)
    print(json.dumps(metrics.to_dict(), indent=2))


if __name__ == "__main__":
    main()
