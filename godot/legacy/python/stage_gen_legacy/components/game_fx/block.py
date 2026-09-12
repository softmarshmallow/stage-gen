"""The fx manifest block: what a runtime reads of both families, versioned once."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from stage_gen.components.effects_art.block import effects_art_manifest
from stage_gen_legacy.components.game_fx.models import (
    GameFx,
)

# ---------------------------------------------------------------- manifest


#: The ``fx`` block's own version (C-R3). Declared beside the function that builds it,
#: because the block is the family's, whichever manifest carries it.
FX_MANIFEST_BLOCK_VERSION = "fx-block-v1"


def fx_manifest_block(
    fx: GameFx,
    *,
    read_validation: Callable[[str], bytes],
    lettering: Mapping[str, tuple[str, str]] | None = None,
) -> dict[str, object]:
    """The published ``fx`` block, identical in every consumer's manifest.

    The validate node is the only place the traced geometry exists, so this reads each
    plate's record rather than the declared layout.

    ``lettering`` gives each moment its title and subtitle. It is the host's to
    supply because the words are display names the host already holds - a track
    name, a boss name - and never a generated string: a cut-in that announced a
    model's invention would be the one place in the package where the words on
    screen answered to nobody.
    """

    moments: list[dict[str, object]] = []
    for binding in fx.moments:
        published: dict[str, object] = binding.model_dump(mode="json")
        if lettering is not None:
            words = lettering.get(binding.moment)
            if words is None:
                raise ValueError(f"no lettering was supplied for the {binding.moment} moment")
            published["title"], published["subtitle"] = words
        moments.append(published)
    return {"moments": moments, **effects_art_manifest(fx, read_validation=read_validation)}


__all__ = [
    "FX_MANIFEST_BLOCK_VERSION",
    "fx_manifest_block",
]
