"""Private collection adapter for capabilities."""

from __future__ import annotations

import argparse
import json
import sys
from typing import TextIO

from stage_gen.application import (
    UsageError as CliUsageError,
)
from stage_gen.capabilities import (
    HeadlessRuntime,
    generate_image_artifact,
    generate_music,
    generate_sound_effect,
    generate_speech,
    generate_video,
    inspect_video,
    remove_background,
)
from stage_gen.config import (
    StageGenConfig,
)


async def dispatch(
    args: argparse.Namespace,
    *,
    config: StageGenConfig,
    runtime: HeadlessRuntime | None,
    stdout: TextIO,
) -> int:
    if args.command == "inspect-video":
        # No provider, no spend, and so no confirmation: this is the free half of the
        # audition pair, and it is what somebody reads before deciding whether the
        # expensive half was worth it.
        report = await inspect_video(
            input_path=args.input_path,
            output_path=args.output,
            expected_seconds=args.duration,
        )
        stdout.write(f"{json.dumps(report, separators=(',', ':'))}\n")
        return 0
    # One paid call, no plan, no cache: the only spend in this CLI that nothing
    # prices first. A person at a terminal has typed the prompt they are paying
    # for; a script has not, so it says so with --yes or is refused.
    if not args.yes and not sys.stdin.isatty():
        raise CliUsageError(
            f"{args.command} makes a paid provider call; pass --yes to confirm it "
            "when stdin is not a terminal"
        )
    if args.command == "generate-image":
        aspect_ratio: str = args.aspect_ratio
        if aspect_ratio != "auto":
            pieces = aspect_ratio.split(":")
            if len(pieces) != 2 or not all(piece.isdigit() and int(piece) > 0 for piece in pieces):
                raise CliUsageError("--aspect-ratio must be auto or positive <width>:<height>")
        result = await generate_image_artifact(
            prompt=" ".join(args.prompt).strip(),
            output_path=args.output,
            aspect_ratio=aspect_ratio,
            reference_paths=args.reference,
            config=config,
            runtime=runtime,
        )
    elif args.command == "remove-background":
        result = await remove_background(
            input_path=args.input_path,
            output_path=args.output,
            config=config,
            runtime=runtime,
        )
    elif args.command == "generate-music":
        result = await generate_music(
            prompt=" ".join(args.prompt).strip(),
            output_path=args.output,
            output_format=args.format,
            config=config,
            runtime=runtime,
        )
    elif args.command == "generate-sound-effect":
        result = await generate_sound_effect(
            prompt=" ".join(args.prompt).strip(),
            output_path=args.output,
            duration_seconds=args.duration,
            prompt_influence=args.prompt_influence,
            loop=args.loop,
            config=config,
            runtime=runtime,
        )
    elif args.command == "generate-video":
        result = await generate_video(
            prompt=" ".join(args.prompt).strip(),
            output_path=args.output,
            duration_seconds=args.duration,
            resolution=args.resolution,
            aspect_ratio=args.aspect_ratio,
            reference_paths=args.reference,
            config=config,
            runtime=runtime,
        )
    elif args.command == "generate-speech":
        result = await generate_speech(
            text=" ".join(args.text).strip(),
            output_path=args.output,
            voice=args.voice,
            stability=args.stability,
            language_code=args.language_code,
            config=config,
            runtime=runtime,
        )
    else:
        raise CliUsageError(f"unsupported command: {args.command}")
    stdout.write(f"{json.dumps(result.to_dict(), separators=(',', ':'))}\n")
    return 0
