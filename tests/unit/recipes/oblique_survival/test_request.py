"""Reading one authored oblique-survival package, and the digests that bind it."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from stage_gen.recipes.oblique_survival.models import Package, SourceError
from stage_gen.recipes.oblique_survival.survival_request import (
    load_package,
    resolve_survival_source,
    take_path,
)

PACKAGE = Path("library/games/ember-hollow")

#: The committed package's identity, pinned so an unnoticed authored edit is a
#: test failure rather than a surprise on the next run. Only the ten authored
#: TOMLs feed it here -- every take and reference is digested by name, and those
#: twenty entries are byte-identical to the ones the paid run
#: ``spikes/oblique-survival-v0/runs/full-v66`` recorded. The TOML entries are
#: not: re-versioning the document kinds to the repository's identity grammar
#: and declaring the takes by digest rewrote that text. Moving this digest costs
#: two local nodes (``source-lock`` and ``package-manifest``) and no provider
#: operation, because every other node takes the source lock as a barrier rather
#: than as lineage.
SOURCE_DIGEST = "7761c57cb7acba37f0e7fbd0d4134cf690af7865d69110ba5f8d74fcb31f6507"

#: One take that is declared by digest and whose bytes are in the package.
FORAGE_TAKE = "ground/forage.take.png"

#: The shared interface document, optional like music.toml.
UI_DOCUMENT = "ui.toml"


def _copy(tmp_path: Path) -> Path:
    root = tmp_path / "package"
    shutil.copytree(PACKAGE, root)
    return root


def test_the_committed_package_loads() -> None:
    package = load_package(PACKAGE)
    assert package.package_id == "ember-hollow"
    assert package.title == "Ember Hollow"
    assert package.profile == "elevated_oblique_perspective_ground_plane_v1"
    assert package.identity()["publication_authorized"] is False
    assert package.missing_takes == ()
    assert resolve_survival_source(PACKAGE).source_digest() == package.source_digest()


def test_the_source_digest_is_the_one_this_package_text_names() -> None:
    """The package's whole identity, in one number, pinned to the committed bytes."""

    assert load_package(PACKAGE).source_digest() == SOURCE_DIGEST


def test_every_declared_take_digest_is_the_file_it_names() -> None:
    """A declaration is only worth what it is checked against."""

    package = load_package(PACKAGE)
    takes = {
        name: digest
        for name, digest in package.digests.items()
        if ".take." in name and (PACKAGE / name).is_file()
    }
    assert len(takes) == 18
    for name, digest in takes.items():
        assert hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == digest


def test_a_take_declared_by_digest_loads_without_its_bytes(tmp_path: Path) -> None:
    """Planning is a function of the committed text, not of what is on disk.

    The package's large media is kept out of the repository, so the loader has
    to admit a take it cannot read and produce the same digest ledger -- and
    therefore the same graph -- either way. The absence is remembered rather
    than ignored.
    """

    root = _copy(tmp_path)
    (root / FORAGE_TAKE).unlink()

    package = load_package(root)

    assert package.source_digest() == SOURCE_DIGEST
    assert [entry.path for entry in package.missing_takes] == [FORAGE_TAKE]
    absent = package.missing_take(FORAGE_TAKE)
    assert absent is not None
    assert package.digests[FORAGE_TAKE] == absent.sha256


def test_an_absent_take_is_refused_where_its_bytes_are_needed(tmp_path: Path) -> None:
    """The refusal belongs at the adopt node, after the plan has priced the run."""

    root = _copy(tmp_path)
    (root / FORAGE_TAKE).unlink()
    package = load_package(root)

    with pytest.raises(SourceError, match=r"take not on disk: ground/forage\.take\.png"):
        take_path(package, FORAGE_TAKE)

    assert take_path(load_package(PACKAGE), FORAGE_TAKE) == PACKAGE / FORAGE_TAKE


def test_a_take_whose_bytes_disagree_with_its_declared_digest_is_refused(
    tmp_path: Path,
) -> None:
    """A swapped take must be a package error, not a silent re-bill of paid work."""

    root = _copy(tmp_path)
    (root / FORAGE_TAKE).write_bytes(b"\x89PNG\r\n\x1a\nnot the take that was adopted")

    with pytest.raises(SourceError, match="does not match its declared sha256"):
        load_package(root)


def test_a_declared_digest_must_be_a_digest(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    ground = root / "ground.toml"
    ground.write_text(
        ground.read_text(encoding="utf-8").replace(
            load_package(PACKAGE).digests[FORAGE_TAKE], "not-a-digest"
        ),
        encoding="utf-8",
    )

    with pytest.raises(SourceError, match="64 lowercase hexadecimal characters"):
        load_package(root)


def test_the_package_answers_for_its_own_members() -> None:
    package: Package = load_package(PACKAGE)
    assert package.actor(package.player.actor_id) is package.player
    with pytest.raises(SourceError, match="unknown actor"):
        package.actor("nobody")
    with pytest.raises(SourceError, match="unknown biome"):
        package.biome("nowhere")


def test_the_interface_document_loads_with_its_reference_bytes() -> None:
    """ui.toml is the shared game_ui contract; the loader binds its reference the
    way it binds every other authored picture, and carries the bytes the triplet
    hands to the provider."""

    package = load_package(PACKAGE)
    assert package.ui is not None
    assert package.ui.game_id == "ember-hollow"
    assert package.ui.inventory_panel is None
    reference = package.ui.references[0]
    file = package.ui_reference(reference.source)
    assert file.sha256 == reference.source_sha256
    assert hashlib.sha256(file.data).hexdigest() == reference.source_sha256
    assert package.digests[UI_DOCUMENT]
    with pytest.raises(SourceError, match="declares no reference"):
        package.ui_reference("references/nothing.png")


def test_a_package_without_the_interface_document_still_loads(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    (root / UI_DOCUMENT).unlink()
    package = load_package(root)
    assert package.ui is None
    assert package.ui_references == {}
    assert UI_DOCUMENT not in package.digests


def test_an_interface_document_for_another_game_is_refused(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    document = root / UI_DOCUMENT
    document.write_text(
        document.read_text().replace('game_id = "ember-hollow"', 'game_id = "other-hollow"')
    )
    with pytest.raises(SourceError, match="game_id does not match"):
        load_package(root)


def test_an_interface_reference_must_match_its_declared_digest(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    document = root / UI_DOCUMENT
    text = document.read_text()
    declared = "0f55649bf337ab3b057e88cf6854ca23a7142ebca57438f03bbd6cd74ee6ade0"
    assert declared in text
    document.write_text(text.replace(declared, "0" * 64))
    with pytest.raises(SourceError, match="does not match its declared sha256"):
        load_package(root)


def test_a_malformed_interface_document_is_refused_by_name(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    document = root / UI_DOCUMENT
    document.write_text(document.read_text().replace('kind = "game-ui-v5"', 'kind = "game-ui-v3"'))
    with pytest.raises(SourceError, match="not a game-ui-v5 document"):
        load_package(root)
