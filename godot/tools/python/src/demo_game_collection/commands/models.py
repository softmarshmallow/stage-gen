"""Private collection adapter for models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TextIO

from demo_game_collection.model_policy import (
    build_repository_model_policy_projection,
    load_active_model_policy_snapshot,
)
from stage_gen.model_policy_maintenance import (
    diff_model_policy_snapshots,
    find_model_policy_repository_root,
    image_provider_capability_gaps,
    load_model_policy_snapshot,
    model_route_report,
)


def dispatch(args: argparse.Namespace, *, stdout: TextIO) -> int:
    active = load_active_model_policy_snapshot()
    repository_root = find_model_policy_repository_root()
    if args.models_command == "routes":
        report = model_route_report(active, repository_root=repository_root)
    else:
        current = active
        provider_gaps: list[dict[str, object]] = []
        if args.image_provider is not None:
            if repository_root is None:
                raise ValueError(
                    "models diff --image-provider requires a stage-gen source checkout"
                )
            provider_gaps = image_provider_capability_gaps(
                active,
                image_provider=args.image_provider,
                recipe_id=args.recipe_id,
            )
            if not provider_gaps:
                current = build_repository_model_policy_projection(
                    repository_root,
                    image_provider=args.image_provider,
                    recipe_id=args.recipe_id,
                ).model_copy(update={"generated_files": active.generated_files})
        report = diff_model_policy_snapshots(
            load_model_policy_snapshot(Path(args.base_path)),
            current,
            recipe_id=args.recipe_id,
            repository_root=repository_root,
            additional_capability_gaps=provider_gaps,
        )
    stdout.write(f"{json.dumps(report, sort_keys=True, separators=(',', ':'))}\n")
    return 0
