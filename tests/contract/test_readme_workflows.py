"""The README front page lists every workflow as its workflow.toml declares it.

The table between ``<!-- workflows:begin -->`` and ``<!-- workflows:end -->`` names each
installed workflow's title, id and promise, read here from the manifests alone, so a renamed
workflow or a reworded promise has to change both. The README stays a short front page that
keeps its committed hero media.
"""

from __future__ import annotations

import re
from pathlib import Path

from stage_gen.workflows._registry import discover

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
README = REPOSITORY_ROOT / "README.md"
BEGIN = "<!-- workflows:begin -->"
END = "<!-- workflows:end -->"


def _table_rows() -> list[tuple[str, str, str]]:
    text = README.read_text(encoding="utf-8")
    assert text.count(BEGIN) == 1 and text.count(END) == 1
    table = text.split(BEGIN, 1)[1].split(END, 1)[0].strip().splitlines()
    assert table[:2] == ["| Workflow | Id | Promise |", "| --- | --- | --- |"]
    rows: list[tuple[str, str, str]] = []
    for line in table[2:]:
        title, identifier, promise = (cell.strip() for cell in line.strip("|").split("|"))
        linked = re.fullmatch(r"\[(.+)\]\((src/stage_gen/workflows/\w+/page\.mdx)\)", title)
        assert linked is not None, title
        assert (REPOSITORY_ROOT / linked.group(2)).is_file(), linked.group(2)
        rows.append((linked.group(1), identifier.strip("`"), promise))
    return rows


def test_readme_table_lists_every_workflow_with_its_title_and_promise() -> None:
    expected = [(w.manifest.title, w.id, w.manifest.promise) for w in discover()]
    assert len(expected) >= 6
    assert _table_rows() == expected


def test_readme_is_a_short_front_page_with_its_hero_media() -> None:
    text = README.read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 100
    images = re.findall(r"!\[[^\]]+\]\(([^)]+)\)", text)
    assert len(images) >= 3
    for image in images:
        assert (REPOSITORY_ROOT / image).is_file(), image
    # The viewer is named once, with the command that opens it.
    assert "the local read-only client" in text
    assert "stage-gen view" in text
