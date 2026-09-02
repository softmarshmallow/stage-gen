"""Resolving one authored universe package, and the reroll ledger over its entities."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from stage_gen.recipes.universe.universe_request import (
    ResolvedUniverseSource,
    direction_requirements,
    read_universe_document,
    resolve_sample_ledger,
    resolve_universe_source,
    synopsis_paragraphs,
)

FIXTURE = Path("library/games/lantern_ferry")


def _resolve(root: Path = FIXTURE) -> ResolvedUniverseSource:
    return resolve_universe_source(read_universe_document(root), root=root)


def test_the_committed_fixture_package_resolves() -> None:
    resolved = _resolve()
    assert resolved.universe_id == "lantern_ferry"
    assert resolved.medium.medium_id == "anime_2d"
    assert resolved.source.rights.publication_authorized is False
    assert len(resolved.synopsis_paragraphs()) >= 8
    assert len(resolved.direction_requirements()) >= 6
    assert resolved.identity()["publication_authorized"] is False


def test_poster_bytes_must_match_the_digest_the_author_recorded(tmp_path: Path) -> None:
    """A drifted member is a package error, not a confusing schema failure later."""

    root = tmp_path / "package"
    shutil.copytree(FIXTURE, root)
    poster = root / "references" / "poster.png"
    poster.write_bytes(poster.read_bytes() + b"\x00")
    with pytest.raises(ValueError, match=r"digest|sha256"):
        _resolve(root)


def test_an_unknown_medium_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "package"
    shutil.copytree(FIXTURE, root)
    document = root / "universe.toml"
    document.write_text(
        document.read_text(encoding="utf-8").replace(
            'medium = "anime_2d"', 'medium = "claymation"'
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown medium"):
        _resolve(root)


def test_a_package_may_not_authorize_its_own_publication(tmp_path: Path) -> None:
    root = tmp_path / "package"
    shutil.copytree(FIXTURE, root)
    document = root / "universe.toml"
    document.write_text(
        document.read_text(encoding="utf-8").replace(
            "publication_authorized = false", "publication_authorized = true"
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        _resolve(root)


def test_synopsis_paragraphs_skip_headings_and_number_in_reading_order() -> None:
    paragraphs = synopsis_paragraphs(
        "# Title\n\nfirst block\nsecond line\n\n## Part\n\nnext block\n"
    )
    assert paragraphs == [
        ("synopsis_p01", "first block second line"),
        ("synopsis_p02", "next block"),
    ]


def test_direction_requirements_fold_indented_continuations() -> None:
    requirements = direction_requirements(
        "## Requirements\n- direction_one: first line\n  continued here\n- direction_two: second\n"
    )
    assert requirements == [
        ("direction_one", "first line continued here"),
        ("direction_two", "second"),
    ]


def test_duplicate_requirement_ids_are_refused() -> None:
    with pytest.raises(ValueError, match="unique requirement ids"):
        direction_requirements("- direction_one: a\n- direction_one: b\n")


def test_a_fresh_sample_ledger_names_every_entity() -> None:
    ledger = resolve_sample_ledger(
        universe_id="lantern_ferry", entity_ids=("the_ferry", "east_landing")
    )
    assert ledger.samples == {"the_ferry": 0, "east_landing": 0}


def test_a_reroll_advances_exactly_the_entity_it_names() -> None:
    ledger = resolve_sample_ledger(
        universe_id="lantern_ferry",
        entity_ids=("the_ferry", "east_landing"),
        rerolls=("east_landing",),
    )
    assert ledger.samples == {"the_ferry": 0, "east_landing": 1}


def test_rerolls_accumulate_over_a_carried_ledger(tmp_path: Path) -> None:
    first = resolve_sample_ledger(
        universe_id="lantern_ferry",
        entity_ids=("the_ferry", "east_landing"),
        rerolls=("east_landing",),
    )
    prior = tmp_path / "sample-ledger.json"
    prior.write_text(json.dumps(first.model_dump(mode="json")), encoding="utf-8")
    second = resolve_sample_ledger(
        universe_id="lantern_ferry",
        entity_ids=("the_ferry", "east_landing"),
        prior=prior,
        rerolls=("east_landing",),
    )
    assert second.samples == {"the_ferry": 0, "east_landing": 2}


def test_rerolling_an_unplanned_entity_is_refused() -> None:
    with pytest.raises(ValueError, match="does not plan"):
        resolve_sample_ledger(
            universe_id="lantern_ferry", entity_ids=("the_ferry",), rerolls=("ghost",)
        )


def test_a_ledger_from_another_universe_is_refused(tmp_path: Path) -> None:
    other = resolve_sample_ledger(universe_id="elsewhere", entity_ids=("the_ferry",))
    prior = tmp_path / "sample-ledger.json"
    prior.write_text(json.dumps(other.model_dump(mode="json")), encoding="utf-8")
    with pytest.raises(ValueError, match="not 'lantern_ferry'"):
        resolve_sample_ledger(universe_id="lantern_ferry", entity_ids=("the_ferry",), prior=prior)
