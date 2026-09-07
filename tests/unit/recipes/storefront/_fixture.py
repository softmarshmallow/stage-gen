"""One tiny storefront package on disk, built from bytes the test owns.

Small on purpose: the contracts are exercised end to end and the pictures are
two solid rectangles, so nothing in this fixture is a judgement call and no test
depends on how a real reference happens to look.
"""

from __future__ import annotations

import tomllib
from io import BytesIO
from pathlib import Path

from PIL import Image

from stage_gen.canonical import content_sha256
from stage_gen.recipes.storefront.storefront_request import (
    ResolvedStorefront,
    read_storefront_document,
    resolve_storefront,
)


def solid_png(width: int, height: int, colour: tuple[int, int, int]) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), colour).save(buffer, format="PNG")
    return buffer.getvalue()


def write_package(root: Path, *, surfaces: str | None = None) -> Path:
    """Write ``storefront.toml`` and its siblings under ``root``; return ``root``."""

    (root / "references").mkdir(parents=True, exist_ok=True)
    art = solid_png(64, 64, (40, 60, 90))
    (root / "references" / "plate.png").write_bytes(art)
    (root / "positioning.md").write_text(
        "A small warm thing in a large cold place.\n", encoding="utf-8"
    )
    declared = (
        surfaces
        or """
[[surfaces]]
surface_id = "icon"
kind = "app_icon"
source = "generated"
brief = "One lantern against dusk."

[[surfaces]]
surface_id = "banner"
kind = "feature_graphic"
source = "generated"
brief = "A wide valley with one lit shelter at its centre."
"""
    )
    (root / "storefront.toml").write_text(
        f"""schema_version = 1
kind = "storefront-source-v1"
storefront_id = "test_world"
display_name = "Test World"
revision = 1

[positioning]
source = "positioning.md"

[[references]]
reference_id = "plate"
source = "references/plate.png"
source_sha256 = "{content_sha256(art)}"
role = "visual_evidence_and_art_grammar_only"
{declared}
[rights]
status = "unreviewed"
basis = ["fixture art authored by the test itself"]
publication_authorized = false
""",
        encoding="utf-8",
    )
    return root


def resolved(root: Path, **kwargs: object) -> ResolvedStorefront:
    return resolve_storefront(read_storefront_document(root), root=root, **kwargs)  # type: ignore[arg-type]


def document(root: Path) -> dict[str, object]:
    return tomllib.loads((root / "storefront.toml").read_text(encoding="utf-8"))


__all__ = ["document", "resolved", "solid_png", "write_package"]
