#!/usr/bin/env python3
"""Check or write the provider-free core route and policy snapshot.

Fixture plans belong to their consuming project. The complete historical game
census lives in godot/tools/write_game_model_policy_snapshot.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gnode import atomic_write_text
from stage_gen.image_product import ImageProvider
from stage_gen.model_policy_maintenance import (
    ACTIVE_MODEL_POLICY_SNAPSHOT,
    ModelPolicySnapshotV1,
    build_model_policy_snapshot,
    render_model_policy_snapshot,
)
from stage_gen.model_routes import IMAGE_ROUTE_CATALOG, image_workload_policies

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = REPOSITORY_ROOT / "src/stage_gen" / ACTIVE_MODEL_POLICY_SNAPSHOT


def build_snapshot() -> ModelPolicySnapshotV1:
    """Snapshot core routing without importing or planning any consumer."""
    return build_model_policy_snapshot(
        catalog=IMAGE_ROUTE_CATALOG,
        policy_selections={
            "default": image_workload_policies(),
            **{provider.value: image_workload_policies(provider) for provider in ImageProvider},
        },
        recipes=(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="rewrite the core snapshot")
    args = parser.parse_args(argv)
    rendered = render_model_policy_snapshot(build_snapshot())
    if args.write:
        atomic_write_text(SNAPSHOT_PATH, rendered, mode=0o644)
        print(f"wrote {SNAPSHOT_PATH.relative_to(REPOSITORY_ROOT)}")
        return 0
    if not SNAPSHOT_PATH.is_file() or SNAPSHOT_PATH.read_text(encoding="utf-8") != rendered:
        print("core model-policy snapshot is stale; inspect the diff and run with --write")
        return 1
    print("core model-policy snapshot is current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
