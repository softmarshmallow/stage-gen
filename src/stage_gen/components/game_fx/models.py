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
from pathlib import PurePosixPath
from typing import Literal

from pydantic import Field, field_validator, model_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import (
    PACKAGE_ID_PATTERN,
    SHA256_PATTERN,
    SNAKE_ID_PATTERN,
    normalized_text,
    parse_toml_contract,
    portable_relative_path,
    unique_values,
)
from stage_gen.components.game_fx.cut_in import (
    CUT_IN_FRAME_LAYOUT,
    CUT_IN_PORTRAIT_LAYOUT,
    FRAME_ALPHA_POLICY,
    PORTRAIT_ALPHA_POLICY,
)
from stage_gen.components.game_fx.sprite import (
    DUST_ALPHA_POLICY,
    DUST_ATLAS_LAYOUT,
    DUST_CELL_KINDS,
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


class FxReference(PersistedContractModel):
    """One digest-bound visual reference selected by an FX plate."""

    reference_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    source: str
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    rights_status: Literal["unreviewed", "restricted", "redistribution-approved"]
    rights_basis: list[str] = Field(min_length=1, max_length=16)

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        source = portable_relative_path(value, "FX reference source")
        if not source.startswith("references/"):
            raise ValueError("FX references must live under references/")
        if PurePosixPath(source).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError("FX references must use PNG, JPEG, or WebP")
        return source

    @field_validator("rights_basis")
    @classmethod
    def validate_rights_basis(cls, value: list[str]) -> list[str]:
        normalized = [normalized_text(entry, "FX reference rights basis") for entry in value]
        unique_values(normalized, "FX reference rights basis")
        return normalized


class CutInFrameDirection(PersistedContractModel):
    """The rip plate: one torn strip, character-agnostic, style-scoped.

    ``generated_v1`` paints it from references and a prompt; ``procedural_v1`` draws it
    locally with no spend and no authored art. Both pass the same gate and publish the
    same contract, so a consumer never learns which one it was handed.

    ``prompt`` is the rip's register — paper, ink, how the tear reads. ``shape`` is its
    silhouette, and it replaces the component's default one strip across the canvas;
    only ``generated_v1`` can act on it, because the procedural draw takes no prose.
    """

    mode: CutInFrameMode
    layout: Literal["cut_in_frame_1536x1024_v1"]
    alpha_policy: Literal["transparent_exterior_opaque_body_v1"]
    reference_ids: list[str] = Field(default_factory=list, max_length=16)
    prompt: str | None = None
    shape: str | None = None

    @field_validator("reference_ids")
    @classmethod
    def validate_reference_ids(cls, value: list[str]) -> list[str]:
        unique_values(value, "cut_in.frame.reference_ids")
        return value

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalized_text(value, "cut_in.frame.prompt", multiline=True)

    @field_validator("shape")
    @classmethod
    def validate_shape(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalized_text(value, "cut_in.frame.shape", multiline=True)

    @model_validator(mode="after")
    def validate_mode_inputs(self) -> CutInFrameDirection:
        if self.mode == "generated_v1":
            if not self.reference_ids or self.prompt is None:
                raise ValueError(
                    "cut_in.frame mode generated_v1 requires reference_ids and a prompt"
                )
        elif self.reference_ids or self.prompt is not None or self.shape is not None:
            raise ValueError(
                "cut_in.frame mode procedural_v1 authors no references, prompt, or shape"
            )
        return self


class DustAtlasDirection(PersistedContractModel):
    """The ground-dust atlas: four clouds on one transparent plate, one per contact.

    ``prompt`` is the dust's register — what the puffs are made of and how they are drawn
    — and nothing about the sheet's layout or the four silhouettes, which the layout fixes
    and the component's brief states. A package that wants different clouds writes a
    different register; a package that wants a different *assignment* of cloud to contact
    is asking for a different layout, which is a new identity rather than a field.

    There is no procedural mode. The runner draws its own dust when no atlas is published,
    and that drawing lives in the consumer where it can be sampled per frame, so a
    ``procedural_v1`` here would be a second implementation of a thing that already exists.
    """

    layout: Literal["fx_dust_atlas_1024x1024_v1"]
    alpha_policy: Literal["transparent_exterior_v1"]
    reference_ids: list[str] = Field(default_factory=list, max_length=16)
    prompt: str

    @field_validator("reference_ids")
    @classmethod
    def validate_reference_ids(cls, value: list[str]) -> list[str]:
        unique_values(value, "sprite.dust.reference_ids")
        return value

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        prompt = normalized_text(value, "sprite.dust.prompt", multiline=True)
        # The layout owns the grid and the four silhouettes. A register that also describes
        # them competes with the brief for the model's attention, and the spike showed which
        # one loses: the sentence nearest the shape wins, whichever one was authored.
        lowered = prompt.lower()
        for banned in ("two-by-two", "2x2", "grid", "quarter", "reading order"):
            if banned in lowered:
                raise ValueError(
                    f"sprite.dust.prompt must not describe the sheet's layout ({banned!r}): "
                    f"the layout {DUST_ATLAS_LAYOUT!r} fixes the grid and the four "
                    f"silhouettes in the order {', '.join(DUST_CELL_KINDS)}"
                )
        return prompt


class SpriteDirection(PersistedContractModel):
    """The world-space sprite family. One member today; a slash or a spark joins it here."""

    dust: DustAtlasDirection | None = None


class CutInPortraitSubject(PersistedContractModel):
    """A drawn actor the plate takes its identity from, instead of an authored file.

    Every portrait needs an identity, and an authored reference can only carry the
    identity of something authored. A boss is *generated*: the run draws its concept
    plate itself, so a portrait announcing that boss has to inherit the face through a
    graph edge to that plate, or the cut-in can announce a machine the fight does not
    contain. That is a lineage the document declares and the hosting genre resolves:
    ``kind`` names the family the id belongs to, and a genre that draws no such actor
    refuses the id rather than guessing.
    """

    kind: Literal["actor_concept_v1"]
    actor_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)


class CutInPortraitDirection(PersistedContractModel):
    """One die-cut plate for one moment: identity from the references or from a drawn
    subject, expression from the prompt."""

    portrait_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=64)
    layout: Literal["cut_in_portrait_1536x1024_v1"]
    alpha_policy: Literal["transparent_exterior_v1"]
    #: Empty only when a ``subject`` carries the identity instead; style references
    #: may still be listed beside one.
    reference_ids: list[str] = Field(default_factory=list, max_length=16)
    prompt: str
    subject: CutInPortraitSubject | None = None

    @field_validator("reference_ids")
    @classmethod
    def validate_reference_ids(cls, value: list[str]) -> list[str]:
        unique_values(value, "cut_in portrait reference_ids")
        return value

    @model_validator(mode="after")
    def validate_identity_source(self) -> CutInPortraitDirection:
        """A plate with neither a reference nor a subject has no identity at all, and
        would be whatever the prompt's prose happened to conjure that attempt."""

        if not self.reference_ids and self.subject is None:
            raise ValueError(
                f"cut_in portrait {self.portrait_id} declares no identity: give it "
                "reference_ids, a subject, or both"
            )
        return self

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        prompt = normalized_text(value, "cut_in portrait prompt", multiline=True)
        match = _AGE_TOKEN.search(prompt)
        if match is not None:
            raise ValueError(
                "cut_in portrait prompt must not state the subject's age "
                f"(found {match.group(0)!r}); the references carry it"
            )
        return prompt


class CutInDirection(PersistedContractModel):
    frame: CutInFrameDirection
    portraits: list[CutInPortraitDirection] = Field(min_length=1, max_length=16)

    @field_validator("portraits")
    @classmethod
    def validate_portraits(
        cls, value: list[CutInPortraitDirection]
    ) -> list[CutInPortraitDirection]:
        unique_values((entry.portrait_id for entry in value), "cut_in portrait_id")
        return value

    def portrait(self, portrait_id: str) -> CutInPortraitDirection:
        for entry in self.portraits:
            if entry.portrait_id == portrait_id:
                return entry
        raise KeyError(portrait_id)


class CutInMomentBinding(PersistedContractModel):
    """One moment bound to one cut-in portrait under one choreography."""

    moment: FxMomentName
    effect: FxEffectName
    portrait_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=64)
    choreography: CutInChoreography


#: The binding union. One member today; a second effect kind joins it as a
#: discriminated union on ``effect``.
FxMoment = CutInMomentBinding


class GameFx(PersistedContractModel):
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
