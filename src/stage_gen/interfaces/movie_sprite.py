"""Command-line access to body-loop assets and the existing separate repaint pipeline."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from gnode import BindingTable
from stage_gen.pipeline import inspect, plan, run, write_plan
from stage_gen.recipes.movie_sprite_body_idle import GenerationSettings, create_pipeline


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Movie sprite body loops and separate face repaint"
    )
    families = parser.add_subparsers(dest="family", required=True)
    body = families.add_parser("body", help="Prepare, generate or finish a body loop")
    body_commands = body.add_subparsers(dest="workflow", required=True)
    idle = body_commands.add_parser("idle", help="Transparent recurring body motion")
    commands = idle.add_subparsers(dest="command", required=True)
    for name in ("plan", "run", "replay"):
        command = commands.add_parser(name)
        command.add_argument("--input-root", type=Path, required=True)
        source = command.add_mutually_exclusive_group(required=True)
        source.add_argument(
            "--authoring", help="Input-relative JSON: canonical_image and optional prompts"
        )
        source.add_argument("--source", help="Input-relative supplied MP4 or transparent Matroska")
        command.add_argument(
            "--source-provenance", help="Optional original sidecar, relative to inputs"
        )
        command.add_argument("--finish", required=True, help="Input-relative finishing JSON")
        command.add_argument("--output-root", type=Path, required=True)
        command.add_argument("--cache-root", type=Path, required=True)
        command.add_argument(
            "--target", choices=("prepare", "generate", "adopt", "finish"), default="finish"
        )
        command.add_argument(
            "--resolution", choices=("360p", "720p", "1080p", "4k"), default="720p"
        )
        command.add_argument("--aspect-ratio", choices=("9:16", "16:9"), default="9:16")
        command.add_argument("--duration", type=int, default=8)
        command.add_argument(
            "--candidate", default="take-01", help="Distinct identity for a deliberate new draw"
        )
        command.add_argument("--live", action="store_true")
        command.add_argument(
            "--budget-root", type=Path, help="Persistent budget directory outside run/cache roots"
        )
        command.add_argument(
            "--budget-usd", help="Fixed positive spending ceiling for this budget account"
        )
        command.add_argument("--dotenv", type=Path, help="Optional allowlisted provider-key file")
    families.add_parser(
        "face", help="Use: face repaint prepare|run|verify (existing portrait pipeline)"
    )
    inspect_command = families.add_parser(
        "inspect", help="Inspect a persisted body run without services"
    )
    inspect_command.add_argument("run", type=Path)
    return parser


async def _execute(args: argparse.Namespace) -> dict[str, Any]:
    from stage_gen.orchestration.movie_sprite_services import (
        MovieSpriteVideoService,
        movie_sprite_video_binding,
    )

    settings = GenerationSettings(
        duration_seconds=args.duration,
        resolution=args.resolution,
        aspect_ratio=args.aspect_ratio,
        candidate_id=args.candidate,
    )
    routes = (
        BindingTable(())
        if args.source
        else BindingTable(
            (
                movie_sprite_video_binding(
                    duration_seconds=args.duration,
                    resolution=args.resolution,
                    aspect_ratio=args.aspect_ratio,
                ),
            )
        )
    )
    service: MovieSpriteVideoService | None = None
    definition_args = dict(
        finish_ref=args.finish,
        authoring_ref=args.authoring,
        settings=settings,
        routes=routes,
        supplied_video_ref=args.source,
        supplied_provenance_ref=args.source_provenance,
    )
    # Build and admit before opening credentials, a budget, or any provider service.
    planned = plan(
        create_pipeline(**definition_args), input_root=args.input_root, targets=[args.target]
    )
    if args.command == "plan":
        write_plan(planned, args.output_root)
        return {
            "planned": True,
            "provider_operations": 0,
            "selected_nodes": [node.node_id for node in planned.selected_nodes],
        }
    needs_provider = any(not node.is_local for node in planned.selected_nodes)
    try:
        if args.live and needs_provider:
            from stage_gen.components.character_3d.budget_pool import BudgetPool
            from stage_gen.config import load_config
            from stage_gen.provider_env import load_provider_dotenv

            assert args.budget_root is not None and args.budget_usd is not None
            budget_root = args.budget_root.resolve()
            for root in (args.input_root, args.output_root, args.cache_root):
                absolute = root.resolve()
                if budget_root.is_relative_to(absolute) or absolute.is_relative_to(budget_root):
                    raise ValueError(
                        "budget root must be separate from input, output and cache roots"
                    )
            overrides = load_provider_dotenv(args.dotenv) if args.dotenv else None
            config = (
                load_config(
                    env={**os.environ, **{str(key): value for key, value in overrides.items()}}
                )
                if overrides is not None
                else load_config()
            )
            budget = BudgetPool(budget_root, "movie-sprite", args.budget_usd)
            service = MovieSpriteVideoService(
                config, budget, live=True, operation_id=args.candidate
            )
            planned = plan(
                create_pipeline(**definition_args, generator=service),
                input_root=args.input_root,
                targets=[args.target],
            )
        result = await run(
            planned,
            output_root=args.output_root,
            cache_root=args.cache_root,
            allow_provider_calls=args.live or args.command == "replay",
            node_timeout_seconds=6000,
        )
        return {
            "status": "succeeded" if result.summary.ok else "failed",
            **result.summary.model_dump(mode="json"),
        }
    finally:
        if service is not None:
            await service.aclose()


def entrypoint() -> None:
    if sys.argv[1:3] == ["face", "repaint"]:
        from stage_gen.interfaces.portrait_motion import entrypoint as portrait_entrypoint

        previous = sys.argv
        sys.argv = [previous[0] + " face repaint", *previous[3:]]
        try:
            portrait_entrypoint()
        finally:
            sys.argv = previous
        return
    parser = _parser()
    args = parser.parse_args()
    if args.family == "inspect":
        print(inspect(args.run).model_dump_json(indent=2))
        return
    if args.family == "face":
        parser.error("use face repaint prepare|run|verify; see face repaint --help")
    if args.command == "replay" and args.live:
        parser.error("replay binds no live provider")
    if args.live and (args.command != "run" or args.source is not None):
        parser.error("--live applies only to an authored generation run")
    if args.live and (args.budget_root is None or args.budget_usd is None):
        parser.error("--live requires --budget-root and --budget-usd")
    if args.command == "run" and args.authoring and args.target != "prepare" and not args.live:
        parser.error("generation requires --live; use replay for cached generation")
    try:
        result = asyncio.run(_execute(args))
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, allow_nan=False))
    if result.get("status") == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    entrypoint()
