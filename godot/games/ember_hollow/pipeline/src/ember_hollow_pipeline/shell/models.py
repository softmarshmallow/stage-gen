"""Exact-current authored contract for the game shell: the screens around the game.

``shell.toml`` is a root sibling of ``ui.toml`` and ``fx.toml``. It owns the surfaces a
player meets before and between play — the opening cinematic, the title screen, the
loading screen — and nothing else. Its neighbours own the parts it composes with:
``ui.toml`` owns the panels and buttons a title screen's controls are drawn from, and
``fx.toml`` owns the plate that wipes one screen into the next. One owner per concept.

The document is genre-blind. Which screens a genre can actually show is checked where
that genre resolves, so a package declaring a screen its runtime never enters is refused
offline, before any spend — the same seam the screen-FX moment vocabulary already uses.

Three rules in here are worth reading before the code, because each is a decision rather
than a shape:

**Text is composited, never drawn.** Every string on a shell screen — the game's name,
a shot's card, a loading tip, a button's label — is authored here as text and set by the
host in the package's declared typeface. No prompt may ask for lettering, and one that
does is refused offline. This is not a guess about what image models can spell: every UI
role in this repository declares ``text_free``, and every package's style contract
already forbids "text pseudo-text logos signatures or watermarks". A shell that broke
that rule would be the one place in a package where what is on screen answers to nobody,
and it would take localisation with it.

**A typeface is an input, not a host asset.** A package that composites any text
declares the face it is set in, digest-bound with its licence, and the run publishes it.
See ``docs/decisions/0063-a-typeface-is-a-package-input.md``; without it a title is set
in whatever font the player's machine happens to have.

**A shot's plate is a still or a clip, and that is the only difference.** The opening is
a shot list with moves, durations, cards and transitions. Making a shot a video changes
one field and nothing else, so the cheap mode is not a prototype of the expensive one —
it is the same contract with a different plate.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import (
    PACKAGE_ID_PATTERN,
    SNAKE_ID_PATTERN,
    normalized_text,
    parse_toml_contract,
    unique_values,
)
from stage_gen.components.screen_art.layouts import (
    BACKDROP_DEPTHS,
    CUTOUT_ALPHA_POLICY,
    LOADING_SCREEN_LAYOUT,
    OPAQUE_ALPHA_POLICY,
    OPENING_LAYOUT,
    SHOT_MOVES,
    SHOT_TRANSITIONS,
    TITLE_SCREEN_LAYOUT,
)
from stage_gen.components.screen_art.models import (
    ShellClip,
    ShellClipTake,
    ShellPlate,
    ShellReference,
    ShellTypeface,
)

GAME_SHELL_SCHEMA_VERSION = 3
GAME_SHELL_KIND = "game-shell-v3"

#: Licences whose terms permit redistributing the font file itself, which is what
#: publishing a run does. A face under any other licence is refused offline rather than
#: shipped on trust; adding one to this set is a rights decision, not a convenience.
REDISTRIBUTABLE_FONT_LICENSES: tuple[str, ...] = ("OFL-1.1", "Apache-2.0", "CC0-1.0")

FONT_SUFFIXES = frozenset({".otf", ".ttf"})
#: A clip's reroll counter. A video route accepts no seed, so the only way to ask for a
#: second draw of the same brief is to say so, and the ceiling keeps a typo from buying
#: a hundred of them. Named ``draw`` rather than ``take`` because in this repository's
#: packages a take is the file that was kept, not the attempt that produced it.
FIRST_SHELL_DRAW = 1
MAX_SHELL_DRAW = 12
REFERENCE_SUFFIXES = frozenset({".jpeg", ".jpg", ".png", ".webp"})

#: A prompt that asks for lettering gets lettering, and a model's lettering is the one
#: thing on a shell screen that cannot be reviewed, localised, or spelled reliably. Every
#: string is composited from the fields above instead, so a prompt naming one of these is
#: refused while the package is being read — offline, before any spend.
_LETTERING_TOKEN = re.compile(
    r"\b("
    r"text|texts|lettering|letters|lettered|wordmark|word[\s-]?mark|logotype|logo|logos"
    r"|title|titles|titled|caption|captions|subtitle|subtitles|typography|typeface|font"
    r"|writing|written|inscription|inscribed|signage|banner\s+reading|sign\s+reading"
    r"|spelling|spelled|name\s+of\s+the\s+game"
    r")\b",
    re.IGNORECASE,
)

#: A plate's geometry is its layout's. A prompt that describes the frame's arrangement
#: argues with the template, and the model follows whichever sentence sits nearest the
#: shape — the lesson the screen-FX sprite sheet learned the hard way.
_LAYOUT_TOKEN = re.compile(
    r"\b(grid|gridded|quadrant|quadrants|reading\s+order|left\s+half|right\s+half"
    r"|top\s+half|bottom\s+half|panel\s+layout|tiled\s+layout|split\s+screen)\b",
    re.IGNORECASE,
)


def _clean_prompt(value: str, label: str) -> str:
    prompt = normalized_text(value, label, multiline=True)
    lettering = _LETTERING_TOKEN.search(prompt)
    if lettering is not None:
        raise ValueError(
            f"{label} names {lettering.group(0)!r}: a shell plate is drawn text-free and "
            "every string is composited by the host in the declared typeface"
        )
    layout = _LAYOUT_TOKEN.search(prompt)
    if layout is not None:
        raise ValueError(
            f"{label} names {layout.group(0)!r}: the layout owns the geometry, and a prompt "
            "that describes it competes with the template"
        )
    return prompt


#: What an opening shot may put on the screen. Discriminated on ``mode`` so a reader
#: never has to guess which of the two it is holding.
type ShotPlate = Annotated[ShellPlate | ShellClip, Field(discriminator="mode")]


class BackdropLayer(PersistedContractModel):
    """One parallax layer of a screen's backdrop, at a declared depth.

    The far layer is the picture and is opaque; anything nearer is a cut-out drawn over
    it. A host drifts them at its own rates, which is where the motion on a title screen
    comes from — no frame is generated for it.
    """

    depth: Literal["far", "mid", "near"]
    plate: ShellPlate

    @model_validator(mode="after")
    def validate_alpha_matches_depth(self) -> BackdropLayer:
        expected = OPAQUE_ALPHA_POLICY if self.depth == "far" else CUTOUT_ALPHA_POLICY
        if self.plate.alpha_policy != expected:
            raise ValueError(
                f"a {self.depth} backdrop layer must declare {expected}: the far layer is the "
                "picture and everything nearer is drawn over it"
            )
        return self


class OpeningShot(PersistedContractModel):
    """One shot of the opening cinematic.

    ``seconds`` is how long the shot is held, ``move`` how the host moves over it, and
    ``card`` the one line of authored text set over it. Everything except the plate is
    identical whether the plate is a still or a clip.
    """

    shot_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    plate: ShotPlate
    move: Literal["hold", "push_in", "pull_out", "pan_left", "pan_right"] = "hold"
    seconds: float = Field(gt=0.4, le=30.0)
    card: str | None = None
    out_transition: Literal["cut", "dissolve", "wipe"] = "cut"

    @model_validator(mode="after")
    def validate_plate_suits_the_shot(self) -> OpeningShot:
        if isinstance(self.plate, ShellPlate):
            if self.plate.alpha_policy != OPAQUE_ALPHA_POLICY:
                raise ValueError("an opening shot fills the screen, so its plate is fully opaque")
            return self
        if self.move != "hold":
            raise ValueError(
                f"shot {self.shot_id} moves the camera over a clip that already has one; "
                "a clip shot is held"
            )
        return self

    @field_validator("card")
    @classmethod
    def validate_card(cls, value: str | None) -> str | None:
        return None if value is None else normalized_text(value, "opening shot card")


class Opening(PersistedContractModel):
    """The opening cinematic: an ordered shot list, and how a player gets past it.

    ``music_track`` names a track the package's own soundtrack contract already produces;
    binding one costs no generation. The recipe that hosts this document resolves the id,
    because only it can see that contract.
    """

    layout: Literal["opening_16x9_v1"]
    shots: list[OpeningShot] = Field(min_length=1, max_length=24)
    #: How the last shot gives way to whatever comes next. Three of the four are
    #: presentation the host owns and cost nothing to declare. ``match_title`` is the
    #: one that is a claim about the picture - that the cinematic ends on the screen
    #: the player is about to be looking at - so it is the one that is measured, and
    #: it is refused offline when there is no title screen to match.
    ending: Literal["cut_to_black", "fade_to_black", "hold_last_frame", "match_title"] = (
        "cut_to_black"
    )
    skippable: bool = True
    music_track: str | None = Field(default=None, pattern=SNAKE_ID_PATTERN, max_length=96)

    @field_validator("shots")
    @classmethod
    def validate_shots(cls, value: list[OpeningShot]) -> list[OpeningShot]:
        unique_values((shot.shot_id for shot in value), "opening shot_id")
        return value

    @property
    def seconds(self) -> float:
        """How long the cinematic runs, which a resolver reports and a host holds for."""

        return sum(shot.seconds for shot in self.shots)

    def cards(self) -> tuple[str, ...]:
        return tuple(shot.card for shot in self.shots if shot.card is not None)


class TitleScreen(PersistedContractModel):
    """The screen with the game's name on it and the control that starts play.

    The name itself is not here: it is the package's own display name, composited by the
    host. What is here is the picture it is set over and the optional emblem it is set
    beside.
    """

    layout: Literal["title_screen_16x9_v1"]
    backdrop: list[BackdropLayer] = Field(min_length=1, max_length=3)
    emblem: ShellPlate | None = None

    @field_validator("backdrop")
    @classmethod
    def validate_backdrop(cls, value: list[BackdropLayer]) -> list[BackdropLayer]:
        depths = [layer.depth for layer in value]
        unique_values(depths, "title backdrop depth")
        if depths[0] != "far":
            raise ValueError("a title backdrop starts at its far layer")
        order = {depth: index for index, depth in enumerate(BACKDROP_DEPTHS)}
        if depths != sorted(depths, key=lambda depth: order[depth]):
            raise ValueError("title backdrop layers are declared far to near")
        return value

    @field_validator("emblem")
    @classmethod
    def validate_emblem(cls, value: ShellPlate | None) -> ShellPlate | None:
        if value is not None and value.alpha_policy != CUTOUT_ALPHA_POLICY:
            raise ValueError("an emblem is a shape on air, so it declares a transparent exterior")
        return value


class LoadingBackdropBinding(PersistedContractModel):
    """A loading backdrop taken from art the run already publishes: zero operations.

    This is the default a genre with many maps should want. The recipe resolves
    ``artifact_role`` against its own manifest vocabulary, because only it knows what its
    run publishes; the component's job is to carry the intent without inventing a name.
    """

    source: Literal["run_artifact"]
    artifact_role: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)


class LoadingScreen(PersistedContractModel):
    """The screen shown while the run's own media is decoded.

    Its backdrop is either drawn for it or bound to art the run already has. Tips are
    authored prose; a host picks one with its seeded generator, never the wall clock, so
    a replay shows the same tip.
    """

    layout: Literal["loading_screen_16x9_v1"]
    backdrop: ShellPlate | LoadingBackdropBinding
    tips: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("backdrop")
    @classmethod
    def validate_backdrop(
        cls, value: ShellPlate | LoadingBackdropBinding
    ) -> ShellPlate | LoadingBackdropBinding:
        if isinstance(value, ShellPlate) and value.alpha_policy != OPAQUE_ALPHA_POLICY:
            raise ValueError("a loading backdrop fills the screen, so it is fully opaque")
        return value

    @field_validator("tips")
    @classmethod
    def validate_tips(cls, value: list[str]) -> list[str]:
        normalized = [normalized_text(entry, "loading tip") for entry in value]
        unique_values(normalized, "loading tip")
        return normalized


class GameShell(PersistedContractModel):
    """``shell.toml``: the opening, the title screen and the loading screen of one game.

    Every member is optional and at least one is required, because a package that
    declares a shell with nothing in it is describing a screen it never shows. A package
    that composites any string — and a title screen always does, since it carries the
    game's name — must declare the typeface it is set in.
    """

    schema_version: Literal[3]
    kind: Literal["game-shell-v3"]
    game_id: str = Field(pattern=PACKAGE_ID_PATTERN, max_length=96)
    revision: int = Field(ge=1)
    references: list[ShellReference] = Field(min_length=1, max_length=32)
    typeface: ShellTypeface | None = None
    opening: Opening | None = None
    title: TitleScreen | None = None
    loading: LoadingScreen | None = None

    @field_validator("references")
    @classmethod
    def validate_references(cls, value: list[ShellReference]) -> list[ShellReference]:
        unique_values((entry.reference_id for entry in value), "shell reference_id")
        unique_values((entry.source for entry in value), "shell reference source")
        return value

    @model_validator(mode="after")
    def validate_document(self) -> GameShell:
        if self.opening is None and self.title is None and self.loading is None:
            raise ValueError("a shell document declares at least one screen")

        declared = {entry.reference_id for entry in self.references}
        for label, reference_ids in self.reference_users():
            unknown = sorted(set(reference_ids) - declared)
            if unknown:
                raise ValueError(f"{label} names undeclared references {unknown}")

        if self.opening is not None and self.opening.ending == "match_title" and self.title is None:
            raise ValueError(
                "the opening ends on match_title and this shell declares no title screen, "
                "so there is nothing for its last frame to be measured against"
            )

        if self.composited_text() and self.typeface is None:
            raise ValueError(
                "this shell composites text and declares no typeface: without one every "
                "string is set in whatever face the player's machine happens to have"
            )
        return self

    def plates(self) -> tuple[tuple[str, ShellPlate], ...]:
        """Every generated *still* the document declares, with the label a refusal uses.

        Stills only, deliberately: everything downstream of this joins a role to a
        ``shell/<role>.png``, and a clip has no such file. Clips come back from
        ``clips()``, and anything that needs both asks ``reference_users()``.
        """

        found: list[tuple[str, ShellPlate]] = []
        if self.opening is not None:
            found.extend(
                (f"opening.shots.{shot.shot_id}", shot.plate)
                for shot in self.opening.shots
                if isinstance(shot.plate, ShellPlate)
            )
        if self.title is not None:
            found.extend(
                (f"title.backdrop.{layer.depth}", layer.plate) for layer in self.title.backdrop
            )
            if self.title.emblem is not None:
                found.append(("title.emblem", self.title.emblem))
        if self.loading is not None and isinstance(self.loading.backdrop, ShellPlate):
            found.append(("loading.backdrop", self.loading.backdrop))
        return tuple(found)

    def clips(self) -> tuple[tuple[str, ShellClip], ...]:
        """Every generated clip the document declares, with the shot that holds it."""

        if self.opening is None:
            return ()
        return tuple(
            (f"opening.shots.{shot.shot_id}", shot.plate)
            for shot in self.opening.shots
            if isinstance(shot.plate, ShellClip)
        )

    def reference_users(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        """Every generated thing and the references it names, stills and clips alike.

        The reference check has to see both or a clip could name a reference the document
        never declared and nothing would say so until the provider was already being paid.
        """

        named: list[tuple[str, tuple[str, ...]]] = [
            (label, tuple(plate.reference_ids)) for label, plate in self.plates()
        ]
        named.extend((label, tuple(clip.reference_ids)) for label, clip in self.clips())
        return tuple(named)

    def composited_text(self) -> tuple[str, ...]:
        """Every string the host sets in the typeface, in the order it would be read.

        A declared title screen always contributes: it carries the game's own name, which
        the host takes from the package rather than from this document.
        """

        strings: list[str] = []
        if self.title is not None:
            strings.append("<display_name>")
        if self.opening is not None:
            strings.extend(self.opening.cards())
        if self.loading is not None:
            strings.extend(self.loading.tips)
        return tuple(strings)

    def screen_names(self) -> tuple[str, ...]:
        """The screens this document declares, in the order a player meets them."""

        return tuple(
            name
            for name, present in (
                ("opening", self.opening is not None),
                ("title", self.title is not None),
                ("loading", self.loading is not None),
            )
            if present
        )


def load_game_shell_bytes(data: bytes) -> GameShell:
    """Parse one ``shell.toml``. Unknown keys are refused, dates must be quoted strings."""

    return parse_toml_contract(data, model=GameShell, label="game shell contract")


__all__ = [
    "BackdropLayer",
    "FIRST_SHELL_DRAW",
    "FONT_SUFFIXES",
    "GAME_SHELL_KIND",
    "GAME_SHELL_SCHEMA_VERSION",
    "GameShell",
    "load_game_shell_bytes",
    "LOADING_SCREEN_LAYOUT",
    "LoadingBackdropBinding",
    "LoadingScreen",
    "MAX_SHELL_DRAW",
    "Opening",
    "OPENING_LAYOUT",
    "OpeningShot",
    "REDISTRIBUTABLE_FONT_LICENSES",
    "ShellClip",
    "ShellClipTake",
    "ShellPlate",
    "ShellReference",
    "ShellTypeface",
    "SHOT_MOVES",
    "SHOT_TRANSITIONS",
    "ShotPlate",
    "TITLE_SCREEN_LAYOUT",
    "TitleScreen",
]
