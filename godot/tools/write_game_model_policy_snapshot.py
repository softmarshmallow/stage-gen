#!/usr/bin/env python3
"""Check or rewrite the executable, provider-free model-policy snapshot.

The fixture census is demo-owned and packaged with ``demo-game-collection``. It records
the checked-in image route catalog and its policy table. Every game builds with gnode,
declares its routes in its own ``gnode.yaml`` and pins its plan through
``godot/tools/write_game_graph_contract.py``, so no recipe plan is recorded here. Checking
and writing only read local files; neither loads credentials or constructs a provider
adapter.

    uv run python godot/tools/write_game_model_policy_snapshot.py
    uv run python godot/tools/write_game_model_policy_snapshot.py --write
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from gnode import atomic_write_text
from stage_gen.image_product import ImageProvider
from stage_gen.model_policy_maintenance import (
    ACTIVE_MODEL_POLICY_SNAPSHOT,
    ModelPolicySnapshotV1,
    build_model_policy_snapshot,
    render_model_policy_snapshot,
)
from stage_gen.model_routes import IMAGE_ROUTE_CATALOG, image_workload_policies

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = (
    REPOSITORY_ROOT / "godot/tools/python/src/demo_game_collection" / ACTIVE_MODEL_POLICY_SNAPSHOT
)


def build_snapshot() -> ModelPolicySnapshotV1:
    policy_selections = {
        "default": image_workload_policies(),
        **{provider.value: image_workload_policies(provider) for provider in ImageProvider},
    }
    return build_model_policy_snapshot(
        catalog=IMAGE_ROUTE_CATALOG, policy_selections=policy_selections, recipes=()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="rewrite the active snapshot instead of only checking it",
    )
    args = parser.parse_args(argv)
    rendered = render_model_policy_snapshot(build_snapshot())
    relative = SNAPSHOT_PATH.relative_to(REPOSITORY_ROOT)
    if args.write:
        atomic_write_text(SNAPSHOT_PATH, rendered, mode=0o644)
        print(f"wrote {relative}")
        return 0
    if not SNAPSHOT_PATH.is_file() or SNAPSHOT_PATH.read_text(encoding="utf-8") != rendered:
        print(f"{relative} is stale; read the diff, then run with --write")
        return 1
    print(f"{relative} is current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
