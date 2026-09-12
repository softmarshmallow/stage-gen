"""Exact-current authored contract for screen FX: transitions and overlays.

``fx.toml`` is a root sibling of ``ui.toml``. It owns the generated plates a game
slams over its screen at a *moment* — a stage start, a fever entry, a map change —
and the binding from each moment to the effect that plays there. The choreography
itself (every duration, easing, and offset) is consumer-owned: only the feel depends
on it, so no refusal does.

The document is genre-blind on purpose. Which moments a genre emits is checked where
that genre is resolved, so a visual novel and a runner author the same file shape and
differ only in which moment names their runtime can honour.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, model_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import (
    PACKAGE_ID_PATTERN,
    SNAKE_ID_PATTERN,
    parse_toml_contract,
    unique_values,
)
from stage_gen.components.effects_art.models import (
    CutInDirection,
    CutInFrameDirection,
    CutInPortraitDirection,
    CutInPortraitSubject,
    DustAtlasDirection,
    EffectArtwork,
    FxReference,
    SpriteDirection,
)
from stage_gen_legacy.components.game_fx.cut_in import (
    CUT_IN_FRAME_LAYOUT,
    CUT_IN_PORTRAIT_LAYOUT,
    FRAME_ALPHA_POLICY,
    PORTRAIT_ALPHA_POLICY,
)
from stage_gen_legacy.components.game_fx.sprite import (
    DUST_ALPHA_POLICY,
    DUST_ATLAS_LAYOUT,
)

GAME_FX_SCHEMA_VERSION = 2
GAME_FX_KIND = "game-fx-v2"

#: The moments a package may bind today. Each is emitted by the genres named in
#: ``docs/spec/game/fx.md``; a binding for a moment the hosting genre never emits is
#: refused when that genre resolves.
FX_MOMENTS: tuple[str, ...] = ("stage_start", "encounter_start")
#: Reserved names, documented so the next caller does not invent a synonym.
FX_RESERVED_MOMENTS: tuple[str, ...] = (
    "map_enter",
    "scene_enter",
    "fever_start",
    "run_ended",
)
#: The effect family. ``wipe`` and ``vignette`` are the reserved next members.
FX_EFFECTS: tuple[str, ...] = ("cut_in",)
CUT_IN_CHOREOGRAPHIES: tuple[str, ...] = ("tear_reveal_v1",)

FxMomentName = Literal["stage_start", "encounter_start"]
FxEffectName = Literal["cut_in"]
CutInChoreography = Literal["tear_reveal_v1"]
CutInFrameMode = Literal["generated_v1", "procedural_v1"]

#: A portrait prompt never states the subject's age: the digest-bound reference
#: carries it, and an age token on a face-filling close-up is what the provider's
#: moderation refused twice in the spike. Refused offline, before any spend.
_AGE_TOKEN = re.compile(
    r"(?i)(?:\b\d{1,3}[\s-]*(?:year|yr)s?[\s-]*old\b"
    r"|\b(?:age|aged)\s+\d"
    r"|\b(?:child|children|kid|kids|minor|minors|teen|teens|teenager|teenagers"
    r"|underage|toddler|infant|baby)\b)"
)


class CutInMomentBinding(PersistedContractModel):
    """One moment bound to one cut-in portrait under one choreography."""

    moment: FxMomentName
    effect: FxEffectName
    portrait_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=64)
    choreography: CutInChoreography


#: The binding union. One member today; a second effect kind joins it as a
#: discriminated union on ``effect``.
FxMoment = CutInMomentBinding


class GameFx(EffectArtwork):
    """One root FX document: plates per effect kind, and moment bindings."""

    schema_version: Literal[2]
    kind: Literal["game-fx-v2"]
    game_id: str = Field(pattern=PACKAGE_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    references: list[FxReference] = Field(min_length=1, max_length=32)
    cut_in: CutInDirection | None = None
    sprite: SpriteDirection | None = None
    moments: list[FxMoment] = Field(min_length=1, max_length=16)

    def moment(self, name: str) -> FxMoment | None:
        for entry in self.moments:
            if entry.moment == name:
                return entry
        return None

    def moment_names(self) -> tuple[str, ...]:
        return tuple(entry.moment for entry in self.moments)

    @model_validator(mode="after")
    def validate_layouts(self) -> GameFx:
        if self.cut_in is not None:
            frame = self.cut_in.frame
            if frame.layout != CUT_IN_FRAME_LAYOUT or frame.alpha_policy != FRAME_ALPHA_POLICY:
                raise ValueError(
                    f"cut_in.frame must declare layout {CUT_IN_FRAME_LAYOUT!r} "
                    f"and alpha_policy {FRAME_ALPHA_POLICY!r}"
                )
            for portrait in self.cut_in.portraits:
                if (
                    portrait.layout != CUT_IN_PORTRAIT_LAYOUT
                    or portrait.alpha_policy != PORTRAIT_ALPHA_POLICY
                ):
                    raise ValueError(
                        f"cut_in portrait {portrait.portrait_id} must declare layout "
                        f"{CUT_IN_PORTRAIT_LAYOUT!r} and alpha_policy {PORTRAIT_ALPHA_POLICY!r}"
                    )
        return self

    @model_validator(mode="after")
    def validate_sprite_layouts(self) -> GameFx:
        dust = None if self.sprite is None else self.sprite.dust
        if dust is not None and (
            dust.layout != DUST_ATLAS_LAYOUT or dust.alpha_policy != DUST_ALPHA_POLICY
        ):
            raise ValueError(
                f"sprite.dust must declare layout {DUST_ATLAS_LAYOUT!r} "
                f"and alpha_policy {DUST_ALPHA_POLICY!r}"
            )
        return self

    @model_validator(mode="after")
    def validate_moment_bindings(self) -> GameFx:
        unique_values((entry.moment for entry in self.moments), "fx moment")
        used: set[str] = set()
        for entry in self.moments:
            if entry.effect == "cut_in":
                if self.cut_in is None:
                    raise ValueError(
                        f"moment {entry.moment} binds a cut_in but the document declares none"
                    )
                declared = {portrait.portrait_id for portrait in self.cut_in.portraits}
                if entry.portrait_id not in declared:
                    raise ValueError(
                        f"moment {entry.moment} names unknown cut_in portrait {entry.portrait_id!r}"
                    )
                used.add(entry.portrait_id)
        if self.cut_in is not None:
            unused = sorted({portrait.portrait_id for portrait in self.cut_in.portraits} - used)
            if unused:
                # Paid generation nobody plays is refused, the map-contract rule.
                raise ValueError("cut_in declares portraits no moment plays: " + ", ".join(unused))
        return self

    @model_validator(mode="after")
    def validate_reference_closure(self) -> GameFx:
        unique_values((entry.reference_id for entry in self.references), "FX reference_id")
        unique_values((entry.source for entry in self.references), "FX reference source")
        declared = {entry.reference_id for entry in self.references}
        selected: set[str] = set()
        selections: list[tuple[str, list[str]]] = []
        if self.cut_in is not None:
            selections.append(("cut_in.frame", self.cut_in.frame.reference_ids))
            selections.extend(
                (f"cut_in portrait {portrait.portrait_id}", portrait.reference_ids)
                for portrait in self.cut_in.portraits
            )
        if self.sprite is not None and self.sprite.dust is not None:
            selections.append(("sprite.dust", self.sprite.dust.reference_ids))
        for label, reference_ids in selections:
            unknown = sorted(set(reference_ids) - declared)
            if unknown:
                raise ValueError(f"{label} references unknown IDs: " + ", ".join(unknown))
            selected.update(reference_ids)
        unused = sorted(declared - selected)
        if unused:
            raise ValueError("FX declares unused reference IDs: " + ", ".join(unused))
        return self


def load_game_fx_bytes(data: bytes) -> GameFx:
    return parse_toml_contract(data, model=GameFx, label="game FX contract")


__all__ = [
    "CUT_IN_CHOREOGRAPHIES",
    "DustAtlasDirection",
    "SpriteDirection",
    "FX_EFFECTS",
    "FX_MOMENTS",
    "FX_RESERVED_MOMENTS",
    "GAME_FX_KIND",
    "GAME_FX_SCHEMA_VERSION",
    "CutInDirection",
    "CutInFrameDirection",
    "CutInMomentBinding",
    "CutInPortraitDirection",
    "CutInPortraitSubject",
    "FxMoment",
    "FxReference",
    "GameFx",
    "load_game_fx_bytes",
]
