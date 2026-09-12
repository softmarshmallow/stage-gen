#!/usr/bin/env python3
"""Verify maintained Godot owners with explicit offline, media and native adapters.

Run from any directory. The default checks do not need generated art, a display,
an audio device, provider credentials or the optional game-preparation packages.
Media and rendered checks remain visible and can be requested explicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING or __package__:
    from .check_suites import ALIASES, OWNERS, ROOT, Owner, Suite, declared_suites, inventory_errors
else:
    from check_suites import ALIASES, OWNERS, ROOT, Owner, Suite, declared_suites, inventory_errors

CREDENTIALS = (
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "FAL_KEY",
    "ELEVENLABS_API_KEY",
    "TRIPO_API_KEY",
)


@dataclass(frozen=True)
class Outcome:
    owner: str
    suite: str
    status: str
    detail: str
    seconds: float = 0.0


def environment() -> dict[str, str]:
    result = {key: value for key, value in os.environ.items() if key not in CREDENTIALS}
    result["_STAGE_GEN_DISABLE_DOTENV"] = "1"
    return result


def engine() -> str:
    return (
        os.environ.get("GODOT")
        or shutil.which("godot")
        or "/Applications/Godot.app/Contents/MacOS/Godot"
    )


def execute(command: list[str], timeout: float) -> tuple[int, str, float]:
    started = time.monotonic()
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=environment(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.returncode, result.stdout + result.stderr, time.monotonic() - started
    except subprocess.TimeoutExpired as exc:

        def decoded(value: bytes | str | None) -> str:
            return value.decode(errors="replace") if isinstance(value, bytes) else value or ""

        output = f"Timed out after {timeout:g}s\n" + decoded(exc.stdout) + decoded(exc.stderr)
        return 1, output, time.monotonic() - started
    except OSError as exc:
        return 1, str(exc), time.monotonic() - started


def passed(returncode: int, output: str, success: str) -> bool:
    return (
        returncode == 0 and "SCRIPT ERROR:" not in output and re.search(success, output) is not None
    )


def media_requirements(owner: Owner) -> list[Path]:
    """Inspect the two games' existing authored bindings; this is not a game schema."""
    project = owner.project
    if owner.name not in {"afterlight", "command_link"}:
        return []
    references: set[str] = set()
    catalogs = [project / "assets/manpu/catalog.json"]
    if owner.name == "afterlight":
        catalog = json.loads((project / "assets/catalog.json").read_text())
        references.update("assets/" + entry["file"] for entry in catalog["assets"])
        catalogs.append(project / "voice/manifest.json")
    else:
        catalogs.append(project / "assets/locations/catalog.json")
        references.update(
            f"assets/character_{name}.png"
            for name in ("full_open", "full_closed", "touch", "second_standing", "third_standing")
        )
        references.add("assets/opening/title.ogv")

    def collect(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"file", "path", "background"} and isinstance(child, str):
                    references.add(child.removeprefix("res://"))
                else:
                    collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    for source in catalogs:
        collect(json.loads(source.read_text()))
    paths = []
    for reference in sorted(references):
        path = project / reference
        if not path.resolve().is_relative_to(project.resolve()):
            raise ValueError(f"{owner.name}: content binding escapes project: {reference}")
        paths.append(path)
    return paths


def prerequisite(suite: Suite, owner: Owner, external_root: Path | None) -> str:
    if suite.level == "offline":
        return ""
    try:
        missing = [
            path.relative_to(owner.project).as_posix()
            for path in media_requirements(owner)
            if not path.is_file()
        ]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return f"unreadable content bindings: {exc}"
    if missing:
        return f"{len(missing)} missing prepared files: " + ", ".join(missing[:4])
    if suite.prerequisite and (external_root is None or not external_root.is_dir()):
        return suite.prerequisite
    if suite.prerequisite and external_root is not None:
        external_missing = [
            path.relative_to(owner.project).as_posix()
            for path in media_requirements(owner)
            if not (external_root / path.relative_to(owner.project)).is_file()
        ]
        if external_missing:
            return f"{len(external_missing)} missing external prepared files: " + ", ".join(
                external_missing[:4]
            )
    return ""


def command_for(suite: Suite, owner: Owner, args: argparse.Namespace, scratch: Path) -> list[str]:
    if suite.adapter == "native":
        command = [
            sys.executable,
            str(ROOT / "tools/run_native_suite.py"),
            "--project",
            owner.name,
            "--timeout",
            str(args.timeout),
            "--jobs",
            str(args.jobs),
        ]
        if owner.name == "ember_hollow":
            command += ["--run", str(args.run or scratch / "ember-hollow-run")]
        return command
    if suite.adapter == "python":
        return [sys.executable, str(owner.project / suite.source)]
    if suite.adapter == "pytest":
        return [sys.executable, "-m", "pytest", "-q", str(owner.project / suite.source)]
    project = scratch / "asset-consumer" if suite.adapter == "asset_consumer" else owner.project
    command = [engine()]
    if suite.level != "rendered":
        command.append("--headless")
    command += [
        "--path",
        str(project),
        "--log-file",
        str(scratch / f"{owner.name}-{suite.name}.log"),
    ]
    if suite.adapter != "application":
        command += ["--script", "res://" + suite.source]
    options = list(suite.arguments)
    if owner.name == "afterlight":
        options += ["--game", "lab" if suite.name == "ambient_voice_lab_checks" else "afterlight"]
    if owner.name == "command_link" and suite.adapter == "application":
        options += ["--game", "command_link", "--route", "game"]
    if suite.name == "route_option_checks":
        options += ["--game", "command_link", "--route", "game", "--language", "ko"]
    if suite.name == "afterlight_external_content_checks" and args.afterlight_content_root:
        options += ["--content-root", str(args.afterlight_content_root)]
    if options:
        command += ["--", *options]
    return command


def prepare_asset_consumer(scratch: Path, timeout: float) -> tuple[int, str, float]:
    destination = scratch / "asset-consumer"
    shutil.copytree(
        ROOT / "templates/asset_consumer",
        destination,
        ignore=shutil.ignore_patterns(".godot", "content", "__pycache__"),
    )

    # A deterministic test image, not generated artwork or a promoted fixture.
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    image = b"\x89PNG\r\n\x1a\n"
    image += chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 8, 8, 6, 0, 0, 0))
    image += chunk(b"IDAT", zlib.compress((b"\x00" + bytes((20, 80, 100, 255)) * 16) * 8))
    image += chunk(b"IEND", b"")
    source = scratch / "consumer-fixture.png"
    source.write_bytes(image)
    Path(str(source) + ".meta.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "artifact": {
                    "sha256": hashlib.sha256(image).hexdigest(),
                    "bytes": len(image),
                    "media_type": "image/png",
                },
            }
        )
    )
    return execute(
        [
            sys.executable,
            str(destination / "prepare.py"),
            "--asset",
            str(source),
            "--project",
            str(destination),
        ],
        timeout,
    )


def run(args: argparse.Namespace, scratch: Path) -> list[Outcome]:
    owners = tuple(owner for owner in OWNERS if not args.owner or owner.name in args.owner)
    suites = [
        suite for suite in declared_suites() if suite.owner in {owner.name for owner in owners}
    ]
    errors = inventory_errors(owners, suites)
    if args.only:
        suites = [suite for suite in suites if suite.name == args.only]
        if not suites:
            errors.append(f"no suite matches --only {args.only}")
    if errors:
        return [Outcome("inventory", "declarations", "FAIL", error) for error in errors]
    outcomes: list[Outcome] = []
    if not shutil.which(engine()):
        return [
            Outcome(owner.name, "engine", "BLOCKED", f"Godot unavailable: {engine()}")
            for owner in owners
        ]
    if any(suite.owner == "ember_hollow" for suite in suites) and not args.run:
        code, output, seconds = execute(
            [
                sys.executable,
                str(ROOT / "games/ember_hollow/tools/make_fixture_run.py"),
                str(scratch / "ember-hollow-run"),
            ],
            args.timeout,
        )
        outcomes.append(
            Outcome("ember_hollow", "fixture", "PASS" if code == 0 else "FAIL", output, seconds)
        )
        if code:
            suites = [suite for suite in suites if suite.owner != "ember_hollow"]
    if any(suite.adapter == "asset_consumer" for suite in suites):
        code, output, seconds = prepare_asset_consumer(scratch, args.timeout)
        outcomes.append(
            Outcome(
                "asset_consumer", "preparation", "PASS" if code == 0 else "FAIL", output, seconds
            )
        )
        if code:
            suites = [suite for suite in suites if suite.owner != "asset_consumer"]
    for owner in owners:
        owned = [suite for suite in suites if suite.owner == owner.name]
        # The native adapter imports its own project. Other styles share one import
        # per owner before their separate script/application processes start.
        if owned and owner.convention != "native":
            project = (
                scratch / "asset-consumer" if owner.name == "asset_consumer" else owner.project
            )
            code, output, seconds = execute(
                [
                    engine(),
                    "--headless",
                    "--editor",
                    "--path",
                    str(project),
                    "--log-file",
                    str(scratch / f"{owner.name}-import.log"),
                    "--quit",
                ],
                args.timeout,
            )
            ok = code == 0 and "SCRIPT ERROR:" not in output
            outcomes.append(
                Outcome(owner.name, "import", "PASS" if ok else "FAIL", output, seconds)
            )
            if not ok:
                outcomes.extend(
                    Outcome(owner.name, suite.name, "BLOCKED", "project import failed")
                    for suite in owned
                )
                continue
        for suite in owned:
            missing = prerequisite(suite, owner, args.afterlight_content_root)
            requested = (
                suite.level == "offline"
                or (args.include_media and suite.level == "media")
                or args.include_rendered
            )
            if not requested:
                need = (
                    "--include-rendered (native renderer/audio device)"
                    if suite.level == "rendered"
                    else "--include-media"
                )
                detail = "; ".join(
                    part
                    for part in (
                        need,
                        missing or "prepared media available"
                        if suite.level == "media"
                        else missing,
                    )
                    if part
                )
                outcomes.append(Outcome(owner.name, suite.name, "DEFERRED", detail))
                continue
            if missing:
                outcomes.append(Outcome(owner.name, suite.name, "BLOCKED", missing))
                continue
            print(f"RUN {owner.name}/{suite.name} [{suite.level}]", flush=True)
            command = command_for(suite, owner, args, scratch)
            timeout = (
                args.timeout * max(1, len(list((owner.project / "tests").glob("test_*.gd"))))
                if suite.adapter == "native"
                else args.timeout
            )
            code, output, seconds = execute(command, timeout)
            status = "PASS" if passed(code, output, suite.success) else "FAIL"
            outcomes.append(Outcome(owner.name, suite.name, status, output, seconds))
            print(f"{status} {owner.name}/{suite.name} ({seconds:.1f}s)", flush=True)
            if status == "FAIL":
                print(output, flush=True)
    if not args.owner and not args.only:
        code, output, seconds = execute(
            [sys.executable, "-m", "pytest", "-q", str(ROOT / "tests")], args.timeout
        )
        outcomes.append(
            Outcome("tooling", "python", "PASS" if code == 0 else "FAIL", output, seconds)
        )
    return outcomes


def exit_code(outcomes: list[Outcome]) -> int:
    if not outcomes or any(outcome.status == "FAIL" for outcome in outcomes):
        return 1
    if any(outcome.status == "BLOCKED" for outcome in outcomes):
        return 2
    if not any(
        outcome.status == "PASS" and outcome.suite not in {"import", "preparation", "fixture"}
        for outcome in outcomes
    ):
        return 1
    return 0


def report(outcomes: list[Outcome], scope: str = "offline") -> str:
    lines = []
    for outcome in outcomes:
        label = f"{outcome.owner}/{outcome.suite}"
        detail = outcome.detail.strip()
        if outcome.status == "PASS":
            notes: list[str] = []
            pinned = False
            for line in detail.splitlines():
                if "SKIP" in line or "not read here" in line:
                    notes.append(line.strip())
                    pinned = "not read here" in line
                elif pinned and line.startswith("     "):
                    notes.append(line.strip())
                else:
                    pinned = False
            detail = "; ".join(notes)
        lines.append(f"{outcome.status:8s} {label}" + (f": {detail}" if detail else ""))
    counts = {
        status: sum(outcome.status == status for outcome in outcomes)
        for status in ("PASS", "FAIL", "BLOCKED", "DEFERRED")
    }
    lines.append(
        f"Godot {scope} coverage: "
        + ", ".join(f"{count} {status.lower()}" for status, count in counts.items())
    )
    lines.append("Headless checks do not establish rendered or listening acceptance.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", choices=[owner.name for owner in OWNERS], action="append")
    parser.add_argument("--only", help="One declared suite name; unknown or empty selection fails")
    parser.add_argument(
        "--include-media", action="store_true", help="Also require prepared-media checks"
    )
    parser.add_argument(
        "--include-rendered",
        action="store_true",
        help="Require all suites, including native rendering/audio",
    )
    parser.add_argument("--afterlight-content-root", type=Path)
    parser.add_argument(
        "--run", type=Path, help="Existing Ember Hollow run; otherwise create an offline fixture"
    )
    parser.add_argument(
        "--timeout", type=float, default=180.0, help="Per-process timeout in seconds"
    )
    parser.add_argument(
        "--jobs", type=int, default=4, help="Parallel files within the native regression adapter"
    )
    parser.add_argument(
        "--report", type=Path, help="Write the complete machine-readable outcome report"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Validate and list execution adapters without running Godot",
    )
    args = parser.parse_args(argv)
    if args.timeout <= 0 or args.jobs <= 0:
        parser.error("--timeout and --jobs must be positive")
    for field in ("run", "afterlight_content_root"):
        value = getattr(args, field)
        if value is not None:
            setattr(args, field, value.resolve())
    if args.list:
        owners = tuple(owner for owner in OWNERS if not args.owner or owner.name in args.owner)
        suites = [
            suite for suite in declared_suites() if suite.owner in {owner.name for owner in owners}
        ]
        errors = inventory_errors(owners, suites)
        if args.only:
            suites = [suite for suite in suites if suite.name == args.only]
            if not suites:
                errors.append(f"no suite matches --only {args.only}")
        for suite in suites:
            print(f"{suite.owner}/{suite.name}: {suite.level}, {suite.adapter}, {suite.source}")
        for (owner, name), base in ALIASES.items():
            if owner in {item.name for item in owners}:
                print(f"{owner}/{name}: compatibility alias of {base}")
        for error in errors:
            print("FAIL inventory: " + error)
        return 1 if errors else 0
    with tempfile.TemporaryDirectory(prefix="godot-check-") as directory:
        # macOS exposes its temp directory through /var -> /private/var. Content
        # loaders intentionally refuse symlink ancestors, so bind the real root.
        outcomes = run(args, Path(directory).resolve())
    scope = "rendered" if args.include_rendered else "media" if args.include_media else "offline"
    print(report(outcomes, scope), flush=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(
                {
                    "scope": scope,
                    "outcomes": [asdict(outcome) for outcome in outcomes],
                },
                indent=2,
            )
            + "\n"
        )
    return exit_code(outcomes)


if __name__ == "__main__":
    raise SystemExit(main())
