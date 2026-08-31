"""One authored scene package, built on disk, for tests that resolve or plan.

A scene is a directory whose members are bound by exact digest, so tests cannot
hand the resolver a dict any more - the bytes have to exist. This writes the
smallest package that resolves, and returns the document so a test can mutate one
field and assert the refusal.
"""

from __future__ import annotations

import hashlib
import tomllib
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

CHARACTER_TOML = """\
schema_version = 1
kind = "character-profile-v1"
profile_id = "mio-researcher"
revision = 1
display_name = "Mio"
age_years = 23
description = "An original final-year student who keeps the seminar notes."
visual_identity = "Young woman of average height with dark eyes and short black hair."
wardrobe = "Navy cardigan over a white collared shirt and a knee-length grey skirt."
invariants = [
  "Short black hair with a single silver pin",
  "Navy cardigan over a white collared shirt",
]

[rights]
status = "unreviewed"
basis = ["Original repository-authored text with no external character reference."]
"""


def cover_png() -> bytes:
    """A deterministic stand-in for the authored identity plate."""

    output = BytesIO()
    Image.new("RGB", (1024, 1536), (40, 60, 110)).save(output, format="PNG")
    return output.getvalue()


def write_scene_package(root: Path, **overrides: object) -> Path:
    """Write a resolvable package under ``root`` and return that directory."""

    root.mkdir(parents=True, exist_ok=True)
    (root / "references").mkdir(exist_ok=True)
    character_bytes = CHARACTER_TOML.encode("utf-8")
    (root / "character.toml").write_bytes(character_bytes)
    cover = cover_png()
    (root / "references/cover.png").write_bytes(cover)
    document = scene_value(
        character_sha256=hashlib.sha256(character_bytes).hexdigest(),
        cover_sha256=hashlib.sha256(cover).hexdigest(),
        **overrides,
    )
    (root / "scene.toml").write_text(_to_toml(document), encoding="utf-8")
    return root


def scene_value(*, character_sha256: str, cover_sha256: str, **overrides: object) -> dict[str, Any]:
    """The authored document, as a plain value a test can mutate before parsing."""

    value: dict[str, Any] = {
        "schema_version": 1,
        "kind": "dialogue-scene-v1",
        "game_id": "seminar_hall",
        "display_name": "Seminar Hall",
        "revision": 1,
        "scene_brief": "A student stays behind in the study lounge after a seminar",
        "identity_reference_id": "cover",
        "character_profile": {
            "schema_version": 1,
            "kind": "character-profile-binding-v1",
            "ref": "character.toml",
            "source_sha256": character_sha256,
        },
        "references": [
            {
                "reference_id": "cover",
                "source": "references/cover.png",
                "source_sha256": cover_sha256,
                "rights_status": "unreviewed",
                "rights_basis": ["Original brand-neutral test fixture."],
            }
        ],
        "background": {"description": "Evening study lounge"},
        "dialogue": [
            {
                "id": "opening",
                "speaker": "Mio",
                "text": "I hoped you would stay after the seminar.",
                "expression_state": "neutral",
            }
        ],
        "presentation": {"slot": "right", "framing_zoom": 70, "source_framing_zoom": 70},
        "transparency_mode": "chroma",
    }
    value.update(overrides)
    return value


def read_scene_value(root: Path) -> dict[str, Any]:
    return tomllib.loads((root / "scene.toml").read_text(encoding="utf-8"))


def _to_toml(value: Any, prefix: str = "") -> str:
    """Just enough TOML for this document shape; tests own no serializer library."""

    scalars: list[str] = []
    tables: list[str] = []
    for key, item in value.items():
        path = f"{prefix}{key}"
        if isinstance(item, dict):
            tables.append(f"\n[{path}]\n{_to_toml(item, f'{path}.')}")
        elif isinstance(item, list) and item and isinstance(item[0], dict):
            tables.extend(f"\n[[{path}]]\n{_to_toml(entry, f'{path}.')}" for entry in item)
        else:
            scalars.append(f"{key} = {_scalar(item)}\n")
    return "".join(scalars) + "".join(tables)


def _scalar(item: Any) -> str:
    if isinstance(item, bool):
        return "true" if item else "false"
    if isinstance(item, int):
        return str(item)
    if isinstance(item, list):
        return "[" + ", ".join(_scalar(entry) for entry in item) + "]"
    escaped = str(item).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
