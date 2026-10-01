"""``stage-gen plan|run movie-sprite``: the body loop, from argv.

``build_definition`` is the one place a movie-sprite definition is built from argv; the
identity golden plans the paid generate path through it. Everything heavier than argparse
is imported inside the handlers, so building the ``stage-gen`` parser stays cheap.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, TextIO

if TYPE_CHECKING:
    from stage_gen.pipeline import PipelineDefinition
    from stage_gen.workflows.movie_sprite import VideoGenerator

TARGETS = ("prepare", "generate", "adopt", "finish")


def _definition_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input-root", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--authoring", help="Input-relative JSON: canonical_image and optional prompts"
    )
    source.add_argument("--source", help="Input-relative supplied MP4 or transparent Matroska")
    parser.add_argument("--source-provenance", help="Optional original sidecar, relative to inputs")
    parser.add_argument("--finish", required=True, help="Input-relative finishing JSON")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--target", choices=TARGETS, default="finish")
    parser.add_argument("--resolution", choices=("360p", "720p", "1080p", "4k"), default="720p")
    parser.add_argument("--aspect-ratio", choices=("9:16", "16:9"), default="9:16")
    parser.add_argument("--duration", type=int, default=8)
    parser.add_argument(
        "--candidate", default="take-01", help="Distinct identity for a deliberate new draw"
    )


def register_plan(parser: argparse.ArgumentParser) -> None:
    _definition_arguments(parser)
    parser.set_defaults(handler=_plan)


def register_run(parser: argparse.ArgumentParser) -> None:
    _definition_arguments(parser)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument(
        "--replay",
        action="store_true",
        help="Finish from takes the cache already holds; binds no live provider",
    )
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--budget-root", type=Path, help="Persistent budget directory outside run/cache roots"
    )
    parser.add_argument(
        "--budget-usd", help="Fixed positive spending ceiling for this budget account"
    )
    parser.add_argument("--dotenv", type=Path, help="Optional allowlisted provider-key file")
    parser.set_defaults(handler=_run)


def build_definition(
    args: argparse.Namespace, *, generator: VideoGenerator | None = None
) -> PipelineDefinition:
    """The movie-sprite definition the parsed flags describe."""
    from gnode import BindingTable
    from stage_gen.orchestration.movie_sprite_services import movie_sprite_video_binding
    from stage_gen.workflows.movie_sprite import GenerationSettings, create_pipeline

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
    return create_pipeline(
        finish_ref=args.finish,
        authoring_ref=args.authoring,
        settings=settings,
        routes=routes,
        generator=generator,
        supplied_video_ref=args.source,
        supplied_provenance_ref=args.source_provenance,
    )


def _plan(args: argparse.Namespace, stdout: TextIO) -> int:
    from stage_gen.pipeline import plan, write_plan

    planned = plan(build_definition(args), input_root=args.input_root, targets=[args.target])
    write_plan(planned, args.output_root)
    return _report(
        stdout,
        {
            "planned": True,
            "provider_operations": 0,
            "selected_nodes": [node.node_id for node in planned.selected_nodes],
        },
    )


def _run(args: argparse.Namespace, stdout: TextIO) -> int:
    import asyncio

    if args.replay and args.live:
        raise ValueError("--replay binds no live provider")
    if args.live and args.source is not None:
        raise ValueError("--live applies only to an authored generation run")
    if args.live and (args.budget_root is None or args.budget_usd is None):
        raise ValueError("--live requires --budget-root and --budget-usd")
    if args.authoring and args.target != "prepare" and not (args.live or args.replay):
        raise ValueError("generation requires --live; use --replay for cached generation")
    return _report(stdout, asyncio.run(_execute(args)))


async def _execute(args: argparse.Namespace) -> dict[str, Any]:
    import os

    from stage_gen.orchestration.movie_sprite_services import MovieSpriteVideoService
    from stage_gen.pipeline import plan, run

    service: MovieSpriteVideoService | None = None
    # Build and admit before opening credentials, a budget, or any provider service.
    planned = plan(build_definition(args), input_root=args.input_root, targets=[args.target])
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
                build_definition(args, generator=service),
                input_root=args.input_root,
                targets=[args.target],
            )
        result = await run(
            planned,
            output_root=args.output_root,
            cache_root=args.cache_root,
            allow_provider_calls=args.live or args.replay,
            node_timeout_seconds=6000,
        )
        return {
            "status": "succeeded" if result.summary.ok else "failed",
            **result.summary.model_dump(mode="json"),
        }
    finally:
        if service is not None:
            await service.aclose()


def _report(stdout: TextIO, result: dict[str, Any]) -> int:
    stdout.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return 1 if result.get("status") == "failed" else 0
