"""The fx manifest block: what a runtime reads of both families, versioned once."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping

from stage_gen.components.game_fx.cut_in_nodes import (
    cut_in_artifact_refs,
    plate_id_for,
)
from stage_gen.components.game_fx.models import (
    GameFx,
)
from stage_gen.components.game_fx.sprite import (
    DUST_CELL_KINDS,
)
from stage_gen.components.game_fx.sprite_nodes import (
    sprite_dust_artifact_refs,
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
    block: dict[str, object] = {"moments": moments, "sprite": _sprite_block(fx, read_validation)}
    if fx.cut_in is None:
        block["cut_in"] = None
        return block

    def plate_block(plate_id: str, expected_role: str) -> dict[str, object]:
        _raw, plate_ref, _placement, validation_ref, _evidence, _verdict = cut_in_artifact_refs(
            plate_id
        )
        record = json.loads(read_validation(validation_ref))
        if not isinstance(record, dict) or record.get("plate") != expected_role:
            raise ValueError(f"cut-in {plate_id} validation names a different plate")
        geometry = record.get("geometry")
        if not isinstance(geometry, dict):
            raise ValueError(f"cut-in {plate_id} validation lacks traced geometry")
        if expected_role == "portrait" and not isinstance(geometry.get("placement"), dict):
            raise ValueError(f"cut-in {plate_id} validation carries no admitted placement")
        return {**geometry, "asset": plate_ref}

    frame_block = plate_block("frame", "frame")
    frame_block["mode"] = fx.cut_in.frame.mode
    portraits = []
    for portrait in fx.cut_in.portraits:
        entry = plate_block(plate_id_for("portrait", portrait.portrait_id), "portrait")
        portraits.append({"portrait_id": portrait.portrait_id, **entry})
    block["cut_in"] = {"frame": frame_block, "portraits": portraits}
    return block


def _sprite_block(fx: GameFx, read_validation: Callable[[str], bytes]) -> dict[str, object] | None:
    """The published ``sprite`` block: each atlas's asset and the cells measured from it.

    The cells come from the validate record rather than the declared layout for the same
    reason a cut-in's polygon does: the layout says what was asked for, and only the
    record says what came back.
    """

    dust = None if fx.sprite is None else fx.sprite.dust
    if dust is None:
        return None
    _raw_ref, atlas_ref, validation_ref = sprite_dust_artifact_refs()
    record = json.loads(read_validation(validation_ref))
    if not isinstance(record, dict) or record.get("sprite") != "dust":
        raise ValueError("dust atlas validation names a different sprite")
    cells = record.get("cells")
    if not isinstance(cells, list) or len(cells) != len(DUST_CELL_KINDS):
        raise ValueError("dust atlas validation carries no measured cells")
    return {
        "dust": {
            "asset": atlas_ref,
            "layout": record["layout"],
            "alpha_policy": record["alpha_policy"],
            "canvas": record["canvas"],
            "cells": cells,
        }
    }


__all__ = [
    "FX_MANIFEST_BLOCK_VERSION",
    "fx_manifest_block",
]
