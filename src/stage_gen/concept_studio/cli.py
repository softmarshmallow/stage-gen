"""Dedicated CLI for agent-facing game concept work."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Never, TextIO

from stage_gen.config import ConfigError

from .image import generate_concept_image
from .profiles import model_report
from .workspace import (
    check_workspace,
    create_workspace,
    find_repository_root,
    read_regular_file_snapshot,
    select_candidate,
)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise ValueError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="stage-gen-concept",
        description="text-and-image game concept workspace",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    init_parser = commands.add_parser("init", description="create one ignored concept workspace")
    init_parser.add_argument("--slug", required=True, dest="concept_id")
    init_parser.add_argument("--title", required=True)
    init_parser.add_argument("brief", nargs="+")

    commands.add_parser("models", description="list supported concept image profiles")

    image_parser = commands.add_parser("image", description="generate one semantic image candidate")
    image_parser.add_argument("--workspace", required=True, dest="concept_id")
    image_parser.add_argument("--name", required=True, dest="image_name")
    image_parser.add_argument("--model", required=True)
    image_parser.add_argument("--quality", choices=("auto", "low", "medium", "high"))
    image_parser.add_argument("--resolution", choices=("512", "1K", "2K", "4K"))
    image_parser.add_argument("--aspect-ratio", default="16:9")
    image_parser.add_argument("--reference", action="append", default=[])
    prompt_group = image_parser.add_mutually_exclusive_group(required=True)
    prompt_group.add_argument("--prompt")
    prompt_group.add_argument("--prompt-file")
    image_parser.add_argument("--replace", action="store_true")

    select_parser = commands.add_parser("select", description="bind one candidate as cover.png")
    select_parser.add_argument("--workspace", required=True, dest="concept_id")
    select_parser.add_argument("--candidate", required=True)
    select_parser.add_argument("--replace", action="store_true")

    check_parser = commands.add_parser("check", description="validate a concept workspace")
    check_parser.add_argument("--workspace", required=True, dest="concept_id")
    check_parser.add_argument("--draft", action="store_true")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    output = stdout or sys.stdout
    errors = stderr or sys.stderr
    try:
        args = build_parser().parse_args(list(sys.argv[1:] if argv is None else argv))
        repository_root = find_repository_root(Path.cwd())
        if args.command == "init":
            result = create_workspace(
                repository_root,
                concept_id=args.concept_id,
                title=args.title,
                brief=" ".join(args.brief),
            )
        elif args.command == "models":
            result = model_report()
        elif args.command == "image":
            prompt = args.prompt if args.prompt is not None else _read_prompt(args.prompt_file)
            result = asyncio.run(
                generate_concept_image(
                    repository_root=repository_root,
                    concept_id=args.concept_id,
                    image_name=args.image_name,
                    prompt=prompt,
                    model=args.model,
                    quality=args.quality,
                    resolution=args.resolution,
                    aspect_ratio=args.aspect_ratio,
                    reference_paths=args.reference,
                    replace=args.replace,
                )
            )
        elif args.command == "select":
            result = select_candidate(
                repository_root,
                concept_id=args.concept_id,
                candidate=args.candidate,
                replace=args.replace,
            )
        else:
            result = check_workspace(
                repository_root,
                concept_id=args.concept_id,
                draft=args.draft,
            )
        output.write(f"{json.dumps(result, ensure_ascii=False, sort_keys=True)}\n")
        return 0
    except ConfigError as error:
        errors.write(f"stage-gen-concept: configuration: {error}\n")
        return 2
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        errors.write(f"stage-gen-concept: error: {error}\n")
        return 1


def entrypoint() -> None:
    raise SystemExit(main())


def _read_prompt(value: str) -> str:
    try:
        prompt = read_regular_file_snapshot(value, "prompt file").decode("utf-8").strip()
    except UnicodeDecodeError as error:
        raise ValueError("prompt file must contain UTF-8 text") from error
    if not prompt:
        raise ValueError("prompt file must be non-empty")
    return prompt
