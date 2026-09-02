#!/usr/bin/env python3
"""Revalidate an accepted runner run into today's cache without provider calls.

Example (every destination must be new)::

    uv run python scripts/revalidate_runner_provider_cache.py \
      --input library/games/iron-petal-unit \
      --source-run out/iron-petal-unit-live-20260902-v5 \
      --structured-sidecar-run out/iron-petal-unit-live-20260902-v4 \
      --staging-run /private/tmp/iron-petal-replay-seed \
      --cache-dir /private/tmp/iron-petal-replay-cache \
      --output out/iron-petal-unit-live-20260902-v6 \
      --listening-review \
        out/iron-petal-unit-live-20260902-v5/soundtrack/external-listening-review.json \
      --invocation-id iron-petal-unit-live-20260902-v6

The command never loads provider credentials and constructs no provider adapter.  A cache-only
verification handler raises if any provider node is not admitted as a current cache hit.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stage_gen.recipes.sideview_runner.replay_cache import (
    revalidate_runner_provider_cache,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, dest="input_path")
    parser.add_argument("--source-run", required=True, type=Path)
    parser.add_argument("--structured-sidecar-run", required=True, type=Path)
    parser.add_argument("--staging-run", required=True, type=Path)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, dest="output_run")
    parser.add_argument("--listening-review", required=True, type=Path)
    parser.add_argument("--invocation-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = asyncio.run(
        revalidate_runner_provider_cache(
            input_path=args.input_path,
            source_run=args.source_run,
            structured_sidecar_run=args.structured_sidecar_run,
            staging_run=args.staging_run,
            cache_dir=args.cache_dir,
            output_run=args.output_run,
            listening_review=args.listening_review,
            invocation_id=args.invocation_id,
        )
    )
    provider_hits = sum(
        node.cache == "hit"
        for node in result.output_summary.nodes
        if node.node_id in {entry["node_id"] for entry in _audit_nodes(result.audit_path)}
    )
    print(f"provider-free replay PASS: {provider_hits} provider cache hits")
    print(f"current graph: {result.output_summary.graph_sha256}")
    print(f"audit: {result.audit_path}")
    return 0


def _audit_nodes(path: Path) -> list[dict[str, object]]:
    import json

    value = json.loads(path.read_text(encoding="utf-8"))
    nodes = value.get("nodes")
    if not isinstance(nodes, list):
        raise ValueError("replay audit has no node list")
    return nodes


if __name__ == "__main__":
    raise SystemExit(main())
