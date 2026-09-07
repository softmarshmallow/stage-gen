"""The node work that touches bytes: the cut to the ship canvas and its gate."""

from __future__ import annotations

import asyncio
import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from gnode import Node, inspect_image
from stage_gen.config import StageGenConfig
from stage_gen.recipes.storefront.prepared_storefront import (
    StorefrontNodeHandler,
    flatten_alpha,
    make_image_proxy,
)
from stage_gen.recipes.storefront.storefront_graph import (
    build_storefront_graph,
    storefront_graph_profile,
)
from stage_gen.recipes.storefront.surfaces import SurfaceKind, surface
from tests.unit.recipes.storefront._fixture import resolved, solid_png, write_package

PROFILE = storefront_graph_profile(StageGenConfig())


def rgba_png(width: int, height: int, alpha: int) -> bytes:
    buffer = BytesIO()
    Image.new("RGBA", (width, height), (10, 20, 30, alpha)).save(buffer, format="PNG")
    return buffer.getvalue()


def handler_for(tmp_path: Path) -> tuple[StorefrontNodeHandler, Path]:
    package = write_package(tmp_path / "package")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    plan = resolved(package)
    handler = StorefrontNodeHandler(
        build_storefront_graph(plan, profile=PROFILE),
        plan,
        run_dir=run_dir,
        cache_dir=tmp_path / "cache",
    )
    handler._invocation_id = "test"
    return handler, run_dir


def node(handler: StorefrontNodeHandler, node_id: str) -> Node:
    return next(item for item in handler._graph.nodes if item.node_id == node_id)


def test_the_cut_reaches_the_exact_ship_canvas_from_the_draw_canvas(tmp_path: Path) -> None:
    handler, run_dir = handler_for(tmp_path)
    declared = surface(SurfaceKind.FEATURE_GRAPHIC.value)
    drawn = run_dir / "production" / "drawn" / "banner.png"
    drawn.parent.mkdir(parents=True)
    drawn.write_bytes(solid_png(declared.draw_width, declared.draw_height, (30, 60, 90)))

    asyncio.run(handler._normalize(node(handler, "surface-banner-normalize")))

    shipped = (run_dir / "package" / "surfaces" / "banner.png").read_bytes()
    facts = inspect_image(shipped, expected_media_type="image/png")
    assert (facts.width, facts.height) == (declared.ship_width, declared.ship_height)


def test_the_icon_ships_without_an_alpha_band_and_says_it_had_one(tmp_path: Path) -> None:
    """A storefront refuses an icon carrying alpha even when it is fully opaque.

    The band is flattened rather than the picture refused — there is nothing wrong
    with the art — but the provenance records that it had to be, because a picture
    that arrived with alpha is one the route drew differently from what was asked.
    """

    handler, run_dir = handler_for(tmp_path)
    declared = surface(SurfaceKind.APP_ICON.value)
    drawn = run_dir / "production" / "drawn" / "icon.png"
    drawn.parent.mkdir(parents=True)
    drawn.write_bytes(rgba_png(declared.draw_width, declared.draw_height, 255))

    asyncio.run(handler._normalize(node(handler, "surface-icon-normalize")))

    shipped_path = run_dir / "package" / "surfaces" / "icon.png"
    assert inspect_image(shipped_path.read_bytes(), expected_media_type="image/png").has_alpha is (
        False
    )
    sidecar = json.loads(shipped_path.with_suffix(".png.meta.json").read_text(encoding="utf-8"))
    assert sidecar["params"]["alpha_flattened"] is True
    assert sidecar["params"]["publication_authorized"] is False
    assert sidecar["rights"]["status"] == "unreviewed"


def test_the_gate_passes_a_clean_surface_and_records_what_it_measured(
    tmp_path: Path,
) -> None:
    handler, run_dir = handler_for(tmp_path)
    declared = surface(SurfaceKind.APP_ICON.value)
    shipped = run_dir / "package" / "surfaces" / "icon.png"
    shipped.parent.mkdir(parents=True)
    shipped.write_bytes(solid_png(declared.ship_width, declared.ship_height, (10, 10, 10)))

    asyncio.run(handler._validate(node(handler, "surface-icon-validate")))

    record = json.loads(shipped.with_name("icon.validation.json").read_text(encoding="utf-8"))
    assert record["status"] == "pass"
    assert (record["width"], record["height"]) == (declared.ship_width, declared.ship_height)
    assert record["has_alpha"] is False


def test_the_gate_refuses_a_surface_on_the_wrong_canvas(tmp_path: Path) -> None:
    handler, run_dir = handler_for(tmp_path)
    shipped = run_dir / "package" / "surfaces" / "icon.png"
    shipped.parent.mkdir(parents=True)
    shipped.write_bytes(solid_png(1023, 1024, (10, 10, 10)))

    with pytest.raises(ValueError, match="ship canvas is 1023x1024, not 1024x1024"):
        asyncio.run(handler._validate(node(handler, "surface-icon-validate")))


def test_the_gate_refuses_an_icon_that_kept_its_alpha_band(tmp_path: Path) -> None:
    """The gate is independent of the cut: it re-measures what actually shipped."""

    handler, run_dir = handler_for(tmp_path)
    shipped = run_dir / "package" / "surfaces" / "icon.png"
    shipped.parent.mkdir(parents=True)
    shipped.write_bytes(rgba_png(1024, 1024, 255))

    with pytest.raises(ValueError, match="refuses an alpha channel"):
        asyncio.run(handler._validate(node(handler, "surface-icon-validate")))


def test_flatten_alpha_leaves_a_picture_that_never_had_one_untouched() -> None:
    original = solid_png(8, 8, (1, 2, 3))
    flattened, changed = flatten_alpha(original)
    assert changed is False
    assert flattened == original


def test_the_review_proxy_is_smaller_and_opaque() -> None:
    proxy = make_image_proxy(solid_png(2560, 1250, (5, 5, 5)), long_edge=1280)
    facts = inspect_image(proxy, expected_media_type="image/png")
    assert max(facts.width, facts.height) == 1280
    assert facts.has_alpha is False
