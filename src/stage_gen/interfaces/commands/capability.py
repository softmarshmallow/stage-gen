"""``stage-gen capability``: one headless provider or media call, outside any graph.

Each call writes one file and prints the artifact result as one JSON line. An audition is
several of these calls whose chosen output a run later adopts by digest.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from stage_gen.capabilities import HeadlessRuntime
    from stage_gen.config import StageGenConfig

CAPABILITIES = (
    "image",
    "remove-background",
    "music",
    "sound-effect",
    "speech",
    "video",
    "inspect-video",
)


def _confirm(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm a paid provider call when stdin is not a terminal",
    )


def register(parser: argparse.ArgumentParser) -> None:
    calls = parser.add_subparsers(dest="capability", required=True)

    image = calls.add_parser("image", help="draw one image")
    image.add_argument("--output", required=True, help="file to write the image to")
    image.add_argument("--aspect-ratio", default="1:1", help="width:height of the image")
    image.add_argument(
        "--reference", action="append", default=[], help="a reference image; repeatable"
    )
    image.add_argument("prompt", nargs="+", help="what to draw")
    _confirm(image)

    background = calls.add_parser("remove-background", help="cut one image from its background")
    background.add_argument(
        "--input", required=True, dest="input_path", help="the image to cut out"
    )
    background.add_argument("--output", required=True, help="file to write the cutout to")
    _confirm(background)

    music = calls.add_parser("music", help="compose one music clip")
    music.add_argument("--output", required=True, help="file to write the clip to")
    music.add_argument(
        "--format", choices=("mp3", "wav"), default="mp3", help="audio format of the clip"
    )
    music.add_argument("prompt", nargs="+", help="what to compose")
    _confirm(music)

    sound_effect = calls.add_parser("sound-effect", help="make one sound effect")
    sound_effect.add_argument("--output", required=True, help="file to write the effect to")
    sound_effect.add_argument(
        "--duration", required=True, type=float, dest="duration", help="seconds of sound"
    )
    sound_effect.add_argument(
        "--prompt-influence",
        type=float,
        default=None,
        dest="prompt_influence",
        help="how closely to follow the prompt, 0 to 1 (default: the provider's)",
    )
    sound_effect.add_argument("--loop", action="store_true", help="ask for a seamless loop")
    sound_effect.add_argument("prompt", nargs="+", help="the sound to make")
    _confirm(sound_effect)

    speech = calls.add_parser("speech", help="speak one line in a provider voice")
    speech.add_argument("--output", required=True, help="file to write the line to")
    speech.add_argument("--voice", required=True, help="the provider voice id")
    speech.add_argument(
        "--stability",
        type=float,
        default=None,
        help="voice stability, 0 to 1 (default: the provider's)",
    )
    speech.add_argument(
        "--language",
        default=None,
        dest="language_code",
        help="language code (default: the provider's)",
    )
    speech.add_argument("text", nargs="+", help="the line to speak")
    _confirm(speech)

    # The audition pair. Video is the most expensive route this CLI reaches and it takes
    # no seed, so drawing a brief twice costs twice and answers differently. These two
    # exist so the drawing and the choosing happen outside a run, where the frames can be
    # looked at and only the chosen file is carried into a package.
    video = calls.add_parser("video", help="draw one video clip")
    video.add_argument("--output", required=True, help="file to write the clip to")
    video.add_argument(
        "--duration", required=True, type=float, dest="duration", help="seconds of video"
    )
    video.add_argument(
        "--resolution", default="720p", help="a resolution the video route offers (default: 720p)"
    )
    video.add_argument(
        "--aspect-ratio", default="16:9", dest="aspect_ratio", help="width:height of the clip"
    )
    video.add_argument(
        "--reference", action="append", default=[], help="a reference image; repeatable"
    )
    video.add_argument("prompt", nargs="+", help="what to film")
    _confirm(video)

    inspect_video = calls.add_parser(
        "inspect-video", help="write a contact sheet of one clip, locally and for free"
    )
    inspect_video.add_argument(
        "--input", required=True, dest="input_path", help="the clip to inspect"
    )
    inspect_video.add_argument("--output", required=True, help="where to write the contact sheet")
    inspect_video.add_argument(
        "--duration",
        type=float,
        default=None,
        dest="duration",
        help="the length to hold the clip to; defaults to the length it actually is",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace, stdout: TextIO) -> int:
    import asyncio

    from stage_gen.config import load_config

    return asyncio.run(dispatch(args, config=load_config(), runtime=None, stdout=stdout))


async def dispatch(
    args: argparse.Namespace,
    *,
    config: StageGenConfig,
    runtime: HeadlessRuntime | None,
    stdout: TextIO,
) -> int:
    from stage_gen.application import UsageError
    from stage_gen.capabilities import (
        generate_image_artifact,
        generate_music,
        generate_sound_effect,
        generate_speech,
        generate_video,
        inspect_video,
        remove_background,
    )

    if args.capability == "inspect-video":
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
        raise UsageError(
            f"capability {args.capability} makes a paid provider call; pass --yes to "
            "confirm it when stdin is not a terminal"
        )
    if args.capability == "image":
        aspect_ratio: str = args.aspect_ratio
        if aspect_ratio != "auto":
            pieces = aspect_ratio.split(":")
            if len(pieces) != 2 or not all(piece.isdigit() and int(piece) > 0 for piece in pieces):
                raise UsageError("--aspect-ratio must be auto or positive <width>:<height>")
        result = await generate_image_artifact(
            prompt=" ".join(args.prompt).strip(),
            output_path=args.output,
            aspect_ratio=aspect_ratio,
            reference_paths=args.reference,
            config=config,
            runtime=runtime,
        )
    elif args.capability == "remove-background":
        result = await remove_background(
            input_path=args.input_path,
            output_path=args.output,
            config=config,
            runtime=runtime,
        )
    elif args.capability == "music":
        result = await generate_music(
            prompt=" ".join(args.prompt).strip(),
            output_path=args.output,
            output_format=args.format,
            config=config,
            runtime=runtime,
        )
    elif args.capability == "sound-effect":
        result = await generate_sound_effect(
            prompt=" ".join(args.prompt).strip(),
            output_path=args.output,
            duration_seconds=args.duration,
            prompt_influence=args.prompt_influence,
            loop=args.loop,
            config=config,
            runtime=runtime,
        )
    elif args.capability == "video":
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
    elif args.capability == "speech":
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
        raise UsageError(f"unsupported capability: {args.capability}")
    stdout.write(f"{json.dumps(result.to_dict(), separators=(',', ':'))}\n")
    return 0
