"""The published guide holds to what gnode is: its first workflow plans, and every built-in
step it shows names a declared type and only that type's inputs and settings.

Commands are held separately (test_documented_commands.py), and the example projects plan
as written (tests/integration/test_user_doc_examples.py).
"""

from __future__ import annotations

import io
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

from gnode import cli
from gnode_std import plugin

REPOSITORY = Path(__file__).resolve().parents[2]
GUIDE = REPOSITORY / "docs/guide"
FENCE = re.compile(r"^```(?P<info>[^\n`]*)\n(?P<body>.*?)^```", re.M | re.S)
USES = re.compile(r"^gnode/(?P<name>[a-z_.]+)@(?P<major>\d+)$")


def _blocks(path: Path, language: str) -> Iterator[str]:
    for fence in FENCE.finditer(path.read_text(encoding="utf-8")):
        if fence.group("info").strip().split(" ")[0] == language:
            yield fence.group("body")


def _documents() -> list[Path]:
    return sorted(GUIDE.rglob("*.md")) + sorted(GUIDE.rglob("*.yaml"))


def _steps(value: Any) -> Iterator[dict[str, Any]]:
    """Every mapping that names a node type with ``uses:``, however deep."""
    if isinstance(value, dict):
        if isinstance(value.get("uses"), str):
            yield value
        for nested in value.values():
            yield from _steps(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _steps(nested)


def _parsed(path: Path) -> Iterator[Any]:
    texts = [path.read_text(encoding="utf-8")] if path.suffix == ".yaml" else _blocks(path, "yaml")
    for text in texts:
        try:
            yield yaml.safe_load(text)
        except yaml.YAMLError:
            continue  # a fragment with elisions (`{ ... }`) is prose, not a document


def test_every_built_in_step_uses_a_declared_type_and_its_own_settings() -> None:
    declared = {
        (builtin.spec.name, builtin.major): set(builtin.spec.inputs) | set(builtin.spec.params)
        for builtin in plugin().builtins
    }
    problems: list[str] = []
    seen = 0
    for path in _documents():
        relative = path.relative_to(REPOSITORY).as_posix()
        for document in _parsed(path):
            for step in _steps(document):
                match = USES.match(step["uses"])
                if match is None:
                    continue
                seen += 1
                key = (match["name"], int(match["major"]))
                if key not in declared:
                    problems.append(f"{relative}: {step['uses']} is not a built-in type")
                    continue
                settings = step.get("with")
                if isinstance(settings, dict):
                    # `{ ... }` elides the rest of a mapping in prose.
                    unknown = sorted(set(settings) - declared[key] - {"..."})
                    if unknown:
                        problems.append(f"{relative}: {step['uses']} has no {', '.join(unknown)}")
    assert seen > 20, "the scan found too few built-in steps to prove anything"
    assert not problems, "\n".join(problems)


def test_the_first_workflow_plans_on_this_installation(tmp_path: Path) -> None:
    chapter = GUIDE / "01-getting-started.md"
    blocks = list(_blocks(chapter, "yaml"))
    project = next(block for block in blocks if block.startswith("# gnode.yaml\n"))
    icon = next(block for block in blocks if block.startswith("# workflows/icon.yaml\n"))
    (tmp_path / "workflows").mkdir()
    (tmp_path / "gnode.yaml").write_text(project, encoding="utf-8")
    (tmp_path / "workflows/icon.yaml").write_text(icon, encoding="utf-8")

    out, err = io.StringIO(), io.StringIO()
    status = cli.main(
        ["plan", str(tmp_path / "workflows/icon.yaml"), "--name", "copper lantern", "--check"],
        stdout=out,
        stderr=err,
        cwd=tmp_path,
    )

    assert status == 0, out.getvalue() + err.getvalue()
    shown = next(block for block in _blocks(chapter, "") if block.startswith("icon  ·"))
    assert out.getvalue().strip() == shown.strip(), "the chapter's plan output is stale"


def test_the_index_lists_every_chapter_and_example() -> None:
    index = (GUIDE / "README.md").read_text(encoding="utf-8")
    for chapter in sorted(GUIDE.glob("[0-9][0-9]-*.md")):
        assert f"({chapter.name})" in index, chapter.name
    for example in sorted(path for path in (GUIDE / "examples").iterdir() if path.is_dir()):
        assert f"(examples/{example.name}/)" in index, example.name
