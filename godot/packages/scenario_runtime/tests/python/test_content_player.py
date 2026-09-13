"""Authoring-produced local packages activate on the real, unchanged Godot player."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from scenario_authoring import build_content_package, compile_scenario, empty_catalog

PACKAGE = Path(__file__).resolve().parents[2]


def test_two_content_packages_and_failed_replacement(tmp_path: Path) -> None:
    destinations = []
    for name, words, revision in (
        ("first", "The first signal.", 1),
        ("second", "The second signal.", 2),
        ("redefined", "A changed immutable revision.", 1),
    ):
        source = tmp_path / (name + "_source")
        source.mkdir()
        catalog = empty_catalog()
        compiled = compile_scenario(
            f'scenario story\n@hello narrate "{words}"\n@done end complete\n', catalog=catalog
        )
        (source / "catalog.json").write_text(json.dumps(catalog))
        (source / "program.json").write_text(json.dumps(compiled.program))
        destination = tmp_path / name
        build_content_package(
            source,
            destination,
            package_id="signal",
            revision=revision,
            catalog_path="catalog.json",
            programs={"story": "program.json"},
            assets=[],
            capabilities={},
        )
        destinations.append(destination)
    damaged = tmp_path / "damaged"
    shutil.copytree(destinations[1], damaged)
    (damaged / "program.json").write_text("{}")
    malformed = tmp_path / "malformed"
    shutil.copytree(destinations[0], malformed)
    _replace_program(malformed, [])
    incomplete = tmp_path / "incomplete"
    shutil.copytree(destinations[0], incomplete)
    raw = json.loads((incomplete / "program.json").read_text())
    raw.pop("required_capabilities", None)
    raw["nodes"][0]["cues"] = [
        {
            "id": "dust",
            "at": 0,
            "effect": {"type": "particle", "parameters": {"sprite": "ember_sprite"}},
            "instance_id": "dust",
            "target": "air",
        }
    ]
    _replace_program(incomplete, raw)
    oversized = tmp_path / "oversized"
    oversized.mkdir()
    (oversized / "scenario-package.json").write_bytes(b" " * (2 * 1024 * 1024 + 1))
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "OPENAI_API_KEY",
            "OPENROUTER_API_KEY",
            "FAL_KEY",
            "ELEVENLABS_API_KEY",
            "TRIPO_API_KEY",
        }
    }
    environment["_STAGE_GEN_DISABLE_DOTENV"] = "1"
    godot = (
        os.environ.get("GODOT")
        or shutil.which("godot")
        or "/Applications/Godot.app/Contents/MacOS/Godot"
    )
    result = subprocess.run(
        [
            godot,
            "--headless",
            "--path",
            str(PACKAGE),
            "--log-file",
            str(tmp_path / "content.log"),
            "--script",
            "res://tests/content_probe.gd",
            "--",
            str(destinations[0]),
            str(destinations[1]),
            str(damaged),
            str(destinations[2]),
            str(malformed),
            str(incomplete),
            str(oversized),
        ],
        capture_output=True,
        text=True,
        env=environment,
        timeout=45,
    )
    output = result.stdout + result.stderr
    assert (
        result.returncode == 0
        and "scenario_content: 16 checks passed" in output
        and "SCRIPT ERROR:" not in output
    ), output


def _replace_program(package: Path, program: object) -> None:
    payload = json.dumps(program).encode()
    (package / "program.json").write_bytes(payload)
    path = package / "scenario-package.json"
    manifest = json.loads(path.read_text())
    for entry in manifest["files"]:
        if entry["path"] == "program.json":
            entry.update(sha256=hashlib.sha256(payload).hexdigest(), bytes=len(payload))
    path.write_text(json.dumps(manifest))
