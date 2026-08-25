"""Scrolling-preview binding, prompting, and role direction from an authored game contract.

This module is the whole boundary between the recipe and `components.game_contract`. The
component owns what a game contract *is*; this owns what this recipe *does* with one, which is
three things and no more:

1. It renders the authored keywords into a clause every image prompt in the run carries.
2. It resolves a build in heads for any body in the cast, from the game's one table.
3. It states each role's render direction, which is what makes the player and a resident two
   pipelines rather than one with a flag.

The art-direction clause is appended as its own block rather than folded into the canonical style
anchor, and that is a deliberate refusal to touch the anchor. The anchor is a *medium* decision -
anime, photoreal, gouache - chosen from three approved modes, materialized locally from a
digest-bound vocabulary, and persisted as a provider-shaped artifact whose sidecar is re-validated
against a rebuilt request on every read. Adding an authored field to it would change
`canonical_style_anchor_digest` for every anchor in both recipes and invalidate every cached
image. Authored keywords are a different layer with a different lifetime - they say which game
this is, not which medium the repository draws in - so they get their own clause, their own
prefix, and their own idempotence guard, and the anchor is left exactly as it was.

The clause is appended last, after the theme directive and the style anchor, because it is the
most specific direction in the prompt and the closest thing the run has to a house style. Nothing
downstream re-orders it.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass

from stage_gen.components.game_contract import (
    GameContract,
    GameContractBinding,
    GameVocabulary,
    ResidentDirection,
    ResolvedGameContract,
    RoleAnimation,
    RoleOrientation,
)

GAME_RESOLUTION_VERSION = "scrolling-game-contract-resolution-v1"

#: Camera projections this recipe draws. The scrolling preview is a side-scroller and every grid
#: contract, facing review and parallax rule in it assumes that; a game authored for any other
#: camera is refused at the binding rather than part-way through a paid run.
ACCEPTED_PROJECTIONS = ("side_view_2d",)

#: Leading text of the authored art-direction clause. Used to find the clause again so a prompt
#: assembled twice does not carry it twice, exactly as `append_style_anchor_once` guards the
#: canonical anchor.
GAME_DIRECTION_PREFIX = "Game art direction — "


def parse_game_contract_binding(value: object) -> dict[str, object]:
    """Validate the shared binding without adding recipe-local aliases."""

    return GameContractBinding.model_validate(value).model_dump(mode="json")


def assert_projection_supported(contract: GameContract) -> None:
    """Refuse a game drawn for a camera this recipe does not implement."""

    if contract.camera.projection not in ACCEPTED_PROJECTIONS:
        raise ValueError(
            f"scrolling-preview draws {' or '.join(ACCEPTED_PROJECTIONS)}; game "
            f"{contract.game_id!r} is authored for camera {contract.camera.projection!r}"
        )


def game_art_direction_prompt(contract: GameContract) -> str:
    """Render the authored keywords into the clause every image prompt carries.

    Keywords are joined in authored order and end in a full stop, because a trailing fragment
    reads to an image model as an unfinished list and invites it to continue one. Avoidances are
    emitted only when there are any: an empty `Avoid:` sentence is a prompt token spent stating
    nothing, and every clause in this recipe competes for weight with the facing and containment
    directives that were already measured regressing when lengthened.
    """

    keywords = ", ".join(contract.style.keywords)
    clause = f"{GAME_DIRECTION_PREFIX}{keywords}."
    if contract.style.avoid:
        clause = f"{clause} Avoid: {'; '.join(contract.style.avoid)}."
    return clause


def append_game_art_direction_once(prompt: str, contract: GameContract) -> str:
    """Append the art-direction clause, and refuse a prompt that already carries a different one.

    Idempotent rather than unconditional. Prompts in this recipe are assembled by several layers -
    a per-cell rescue re-derives a prompt from its parent, and the turnaround rescue path re-uses
    a parent's first line - so the same clause can legitimately arrive twice. Two *different*
    clauses in one prompt cannot: it would mean two games directed one image, and silently
    keeping either one is worse than failing.
    """

    rendered = game_art_direction_prompt(contract)
    occurrences = prompt.count(GAME_DIRECTION_PREFIX)
    if occurrences == 0:
        return f"{prompt.rstrip()}\n\n{rendered}"
    if occurrences == 1 and rendered in prompt:
        return prompt
    raise ValueError("image prompt already contains a different or malformed game art direction")


@dataclass(frozen=True, slots=True)
class ResidentRenderPlan:
    """Everything the village stages need to draw one resident, resolved from the contract.

    A dataclass rather than loose arguments because these five values must move together: a
    resident drawn as a still but measured as a strip, or posed at a build nobody resolved, is
    exactly the class of mismatch the head-matched runtime turns into a visibly wrong size.
    """

    orientation: RoleOrientation
    animation: RoleAnimation
    frames: int
    allow_pose: bool
    allow_held_prop: bool

    @property
    def is_still(self) -> bool:
        return self.animation == "still"


#: Frames in a resident animation strip, when a game asks for one. Matches the mob idle strip's
#: four cells, because a strip resident is generated through the mob strip's contract.
_STRIP_FRAMES = 4
#: Frames in a still. One drawn cell, and the only reason this is written down is that the web
#: runtime slices a sheet into exactly this many equal columns at load time - a still published
#: as four would render as its own left quarter, with no error anywhere.
_STILL_FRAMES = 1


def resident_render_plan(direction: ResidentDirection) -> ResidentRenderPlan:
    """Resolve the authored resident direction into the geometry the stages draw to."""

    return ResidentRenderPlan(
        orientation=direction.orientation,
        animation=direction.animation,
        frames=_STILL_FRAMES if direction.animation == "still" else _STRIP_FRAMES,
        allow_pose=direction.allow_pose,
        allow_held_prop=direction.allow_held_prop,
    )


def resident_body_anatomy(vocabulary: GameVocabulary, body_kind: str) -> str:
    """The anatomy sentence for a body, which is what an image model can actually draw."""

    return vocabulary.body(body_kind).anatomy


def game_contract_tag_suffix(binding_value: object, *, vocabulary_sha256: str) -> str:
    """Separate run directories by authored game *and* by the vocabulary that expands it.

    Both digests are needed and neither is sufficient. The contract names `warm dusk palette`;
    the vocabulary decides what that phrase becomes in a prompt. Editing the vocabulary's wording
    redirects every image a contract using it produces while leaving the contract's own bytes
    identical, so a tag keyed on the contract alone would serve artwork drawn under wording that
    no longer exists.

    Keyed on the binding `ref` rather than on `source_sha256`, matching
    `character_profile_tag_suffix`: revising a game in place should refresh a run's artwork, not
    strand it in a second directory beside the version that produced it.
    """

    binding = GameContractBinding.model_validate(binding_value)
    ref_sha256 = hashlib.sha256(binding.ref.encode("utf-8")).hexdigest()
    return f"game-v1-{ref_sha256[:10]}-{vocabulary_sha256[:8]}"


def game_identity(resolved: ResolvedGameContract) -> Mapping[str, object]:
    """The identity block embedded in every artifact sidecar a directed run writes."""

    return {
        **resolved.identity(),
        "recipe_resolution_version": GAME_RESOLUTION_VERSION,
        "art_direction_sha256": hashlib.sha256(
            game_art_direction_prompt(resolved.contract).encode("utf-8")
        ).hexdigest(),
    }


__all__ = [
    "ACCEPTED_PROJECTIONS",
    "GAME_DIRECTION_PREFIX",
    "GAME_RESOLUTION_VERSION",
    "ResidentRenderPlan",
    "append_game_art_direction_once",
    "assert_projection_supported",
    "parse_game_contract_binding",
    "resident_body_anatomy",
    "resident_render_plan",
    "game_art_direction_prompt",
    "game_contract_tag_suffix",
    "game_identity",
]
