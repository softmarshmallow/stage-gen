#!/usr/bin/env python3
"""Run the copied Movie Sprite Actor consumer outside the checkout, without providers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from assemble_standalone import assemble  # noqa: E402 - standalone sibling tool


def check(
    engine: str, *, rendered: bool = False, capture_dir: Path | None = None
) -> dict[str, object]:
    """Assemble a fresh project, execute it and validate its independent evidence."""
    executable = shutil.which(engine)
    if executable is None:
        raise ValueError(f"Godot executable was not found: {engine}")
    if capture_dir is not None and (capture_dir.exists() or capture_dir.is_symlink()):
        raise ValueError("Capture destination already exists; choose a new directory.")
    with tempfile.TemporaryDirectory(prefix="movie-sprite-actor-consumer-") as temporary:
        scratch = Path(temporary).resolve()
        project = scratch / "project"
        assembly = assemble(project)
        captures = capture_dir.resolve() if capture_dir is not None else scratch / "proof"
        command = [executable]
        if not rendered:
            command.append("--headless")
        command += [
            "--path",
            str(project),
            "--log-file",
            str(scratch / "godot.log"),
            "--",
            "--smoke",
            "--capture-dir",
            str(captures),
        ]
        result = subprocess.run(
            command,
            cwd=scratch,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        output = result.stdout + result.stderr
        if result.returncode != 0 or "SCRIPT ERROR:" in output:
            raise ValueError(f"Independent consumer failed ({result.returncode}):\n{output}")
        report_path = captures / "verification.json"
        if not report_path.is_file():
            raise ValueError(f"Independent consumer wrote no verification report:\n{output}")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if not isinstance(report, dict) or report.get("status") != "passed" or report.get("errors"):
            raise ValueError(f"Independent consumer rejected its proof: {report}")
        if report.get("pixel_checks_executed") is not rendered:
            raise ValueError(
                "Independent consumer rendering evidence does not match requested mode."
            )
        minimum_checks = 24 if rendered else 15
        if type(report.get("checks")) is not int or report["checks"] < minimum_checks:
            raise ValueError("Independent consumer did not execute the required checks.")
        if rendered:
            for name in ("independent-consumer.png", "source-frame.png", "registered-face.png"):
                if not (captures / name).is_file():
                    raise ValueError(f"Missing rendered inspection capture: {name}")
        payloads = {
            "movie_sprite_actor": assembly["sdk_files"],
            **assembly["dependency_files"],
        }
        for name, hashes in payloads.items():
            for relative, digest in hashes.items():
                copied = project / "addons" / name / relative
                if copied.is_symlink() or hashlib.sha256(copied.read_bytes()).hexdigest() != digest:
                    raise ValueError(f"Copied addon changed during verification: {name}/{relative}")
        if capture_dir is not None:
            (captures / "engine.log").write_text(output, encoding="utf-8")
            (captures / "assembly.json").write_text(
                json.dumps(assembly, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--engine", default=os.environ.get("GODOT", "godot"), help="Godot executable (or GODOT)"
    )
    parser.add_argument("--rendered", action="store_true", help="Use the native rendering server")
    parser.add_argument("--capture-dir", type=Path, help="New directory for retained evidence")
    args = parser.parse_args(argv)
    try:
        report = check(args.engine, rendered=args.rendered, capture_dir=args.capture_dir)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"Independent consumer check failed: {error}\n")
    print(
        "PASS Movie Sprite Actor independent consumer: "
        f"{report['checks']} checks; {report['renderer']}; "
        "copied addon and content_io hashes intact."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
