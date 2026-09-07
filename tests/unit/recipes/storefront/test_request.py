"""Resolving one authored storefront package, and what it refuses."""

from __future__ import annotations

from pathlib import Path

import pytest

from stage_gen.recipes.storefront.models import DrawLedger
from stage_gen.recipes.storefront.storefront_request import (
    CaptureNotAvailableError,
    apply_rerolls,
    empty_ledger,
    resolve_storefront,
)
from tests.unit.recipes.storefront._fixture import document, resolved, solid_png, write_package


def test_a_package_resolves_to_its_art_its_note_and_its_surfaces(tmp_path: Path) -> None:
    package = resolved(write_package(tmp_path))
    assert package.storefront_id == "test_world"
    assert [item.surface_id for item in package.source.surfaces] == ["icon", "banner"]
    assert [reference.reference_id for reference in package.references] == ["plate"]
    assert package.references[0].media_type == "image/png"
    assert "small warm thing" in package.positioning_text
    assert package.identity()["publication_authorized"] is False


def test_a_reference_whose_bytes_moved_is_refused(tmp_path: Path) -> None:
    root = write_package(tmp_path)
    (root / "references" / "plate.png").write_bytes(solid_png(64, 64, (200, 10, 10)))
    with pytest.raises(ValueError, match="does not match its authored digest"):
        resolved(root)


def test_a_captured_still_is_refused_by_name_with_its_reason(tmp_path: Path) -> None:
    """The deferral has to be visible: a silent substitution reads as a bug.

    A package that asks for a frame of real play and receives a drawn one has
    been answered with something else without being told, so the refusal names
    the surface, says what is missing, and says what to do instead.
    """

    root = write_package(tmp_path)
    doc = document(root)
    doc["surfaces"][1]["source"] = "capture"  # type: ignore[index]
    with pytest.raises(CaptureNotAvailableError) as refusal:
        resolve_storefront(doc, root=root)
    message = str(refusal.value)
    assert "'banner'" in message
    assert "play-and-capture" in message
    assert 'source = "generated"' in message


def test_a_duplicate_surface_id_is_refused(tmp_path: Path) -> None:
    root = write_package(tmp_path)
    doc = document(root)
    doc["surfaces"][1]["surface_id"] = "icon"  # type: ignore[index]
    with pytest.raises(ValueError, match="duplicate surface_id"):
        resolve_storefront(doc, root=root)


def test_an_unknown_surface_kind_is_refused(tmp_path: Path) -> None:
    root = write_package(tmp_path)
    doc = document(root)
    doc["surfaces"][0]["kind"] = "wallpaper"  # type: ignore[index]
    with pytest.raises(ValueError):
        resolve_storefront(doc, root=root)


def test_a_ledger_for_another_package_is_refused(tmp_path: Path) -> None:
    root = write_package(tmp_path)
    with pytest.raises(ValueError, match="not this storefront package"):
        resolved(root, draws=empty_ledger("some_other_world"))


def test_a_ledger_naming_an_undeclared_surface_is_refused(tmp_path: Path) -> None:
    """A reroll of a surface that does not exist is a typo, not a no-op."""

    root = write_package(tmp_path)
    ledger = apply_rerolls(empty_ledger("test_world"), ("icno",))
    with pytest.raises(ValueError, match=r"does not declare: \['icno'\]"):
        resolved(root, draws=ledger)


def test_a_reroll_advances_exactly_one_index() -> None:
    ledger = empty_ledger("test_world")
    assert ledger.draw("icon") == 0
    once = apply_rerolls(ledger, ("icon",))
    assert (once.draw("icon"), once.draw("banner")) == (1, 0)
    twice = apply_rerolls(once, ("icon",))
    assert (twice.draw("icon"), twice.draw("banner")) == (2, 0)


def test_a_negative_draw_index_is_refused() -> None:
    with pytest.raises(ValueError, match="draw index must not be negative"):
        DrawLedger(
            schema_version=1,
            kind="storefront-draw-ledger-v1",
            storefront_id="test_world",
            draws={"icon": -1},
        )
