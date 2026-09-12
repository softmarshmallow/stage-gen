"""Independent screen artwork inputs; games own their screen flow and transitions."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Literal

from pydantic import Field, ValidationInfo, field_validator, model_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import (
    SHA256_PATTERN,
    SNAKE_ID_PATTERN,
    normalized_text,
    portable_relative_path,
    unique_values,
)

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


class ShellReference(PersistedContractModel):
    """One digest-bound visual reference a shell plate is drawn against."""

    reference_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=96)
    source: str
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    rights_status: Literal["unreviewed", "restricted", "redistribution-approved"]
    rights_basis: list[str] = Field(min_length=1, max_length=16)

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        source = portable_relative_path(value, "shell reference source")
        if not source.startswith("references/"):
            raise ValueError("shell references must live under references/")
        if PurePosixPath(source).suffix.lower() not in REFERENCE_SUFFIXES:
            raise ValueError("shell references must use PNG, JPEG, or WebP")
        return source

    @field_validator("rights_basis")
    @classmethod
    def validate_rights_basis(cls, value: list[str]) -> list[str]:
        normalized = [normalized_text(entry, "shell reference rights basis") for entry in value]
        unique_values(normalized, "shell reference rights basis")
        return normalized


class ShellTypeface(PersistedContractModel):
    """The face every composited string on a shell screen is set in.

    The record is the one ``web/public/fonts/*/README.md`` already keeps per face, moved
    from a README convention into a contract a resolver can refuse. ``license`` must be a
    licence that permits redistributing the font file, because publishing a run copies it.
    """

    family: str
    source: str
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    license: str
    license_source: str
    copyright: str
    upstream_source: str
    retrieved: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")

    @field_validator("family", "copyright", "upstream_source")
    @classmethod
    def validate_scalars(cls, value: str, info: ValidationInfo) -> str:
        return normalized_text(value, f"typeface {info.field_name}")

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        source = portable_relative_path(value, "typeface source")
        if not source.startswith("fonts/"):
            raise ValueError("a typeface must live under fonts/")
        if PurePosixPath(source).suffix.lower() not in FONT_SUFFIXES:
            raise ValueError("a typeface must be a TrueType or OpenType file")
        return source

    @field_validator("license_source")
    @classmethod
    def validate_license_source(cls, value: str) -> str:
        source = portable_relative_path(value, "typeface license_source")
        if not source.startswith("fonts/"):
            raise ValueError("a typeface licence must live under fonts/ beside the face")
        return source

    @field_validator("license")
    @classmethod
    def validate_license(cls, value: str) -> str:
        license_id = normalized_text(value, "typeface license")
        if license_id not in REDISTRIBUTABLE_FONT_LICENSES:
            allowed = ", ".join(REDISTRIBUTABLE_FONT_LICENSES)
            raise ValueError(
                f"typeface license {license_id!r} is not known to permit redistributing the "
                f"font file, which publishing a run does; known licences are {allowed}"
            )
        return license_id


class ShellPlate(PersistedContractModel):
    """One generated picture: what it is drawn from, and what it is drawn like.

    It authors no geometry and no lettering. ``alpha_policy`` says whether the plate is a
    picture with no holes or a shape on air, and the layout says where it must stay quiet.

    ``mode`` is required and has no default. A clip is not a still with a flag set: it is
    bought from a different route, gated on things a picture has no answer for, and played
    rather than drawn, so the document says which it is before anything reads it.
    """

    mode: Literal["still"]
    alpha_policy: Literal["fully_opaque_v1", "transparent_exterior_v1"]
    reference_ids: list[str] = Field(min_length=1, max_length=16)
    prompt: str

    @field_validator("reference_ids")
    @classmethod
    def validate_reference_ids(cls, value: list[str]) -> list[str]:
        unique_values(value, "shell plate reference_ids")
        return value

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return _clean_prompt(value, "shell plate prompt")


class ShellClipTake(PersistedContractModel):
    """An auditioned clip kept in the package and adopted instead of drawn.

    Video is the most expensive thing a run buys and the route accepts no seed, so a
    brief is a draw rather than a picture: asking twice costs twice and answers
    differently. A take is the answer somebody already looked at, bound by digest and
    republished through the clip gate at no provider cost - the lever ``sounds.toml``,
    ``music.toml`` and ``ground.toml`` all reach for, spelled the same way.

    The digest is what the package's identity reads, not the bytes. A ten-second clip is
    megabytes, so the file is kept beside the package rather than committed, and a
    package whose takes are absent still loads, still plans and still prices the run --
    the adopt node is where the absence is finally paid for.
    """

    path: str
    sha256: str = Field(pattern=SHA256_PATTERN)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        path = portable_relative_path(value, "shell clip take path")
        if not path.startswith("shell/"):
            raise ValueError("shell clip takes must live under shell/")
        if PurePosixPath(path).suffix.lower() != ".mp4":
            raise ValueError("a shell clip take must be an .mp4 file")
        return path


class ShellClip(PersistedContractModel):
    """One moving picture, standing where a still would.

    It carries no ``alpha_policy`` because video has no alpha, and no resolution because a
    package names a layout and never writes a rectangle. It carries no length either: how
    long the shot runs is the shot's business, and how long a clip the bound route will
    make is that route's, declared on its binding and refused while planning.

    Two ways to fill it, both first-class. Without ``take`` the run buys the brief from the
    bound route, and ``draw`` is the reroll counter that asks for another one - a video
    route accepts no seed, so a second draw of the same brief is bought deliberately.
    With ``take`` the run adopts a clip somebody already auditioned and judged, buys
    nothing, and is no longer bound by what length the route can answer.
    """

    mode: Literal["clip"]
    reference_ids: list[str] = Field(min_length=1, max_length=16)
    prompt: str
    #: The auditioned clip to adopt. Absent means the run draws the brief itself.
    take: ShellClipTake | None = None
    draw: int = Field(default=FIRST_SHELL_DRAW, ge=FIRST_SHELL_DRAW, le=MAX_SHELL_DRAW)

    @field_validator("reference_ids")
    @classmethod
    def validate_reference_ids(cls, value: list[str]) -> list[str]:
        unique_values(value, "shell clip reference_ids")
        return value

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        return _clean_prompt(value, "shell clip prompt")

    @model_validator(mode="after")
    def validate_take_and_draw(self) -> ShellClip:
        if self.take is not None and self.draw != FIRST_SHELL_DRAW:
            raise ValueError(
                "a shell clip that adopts a take cannot also raise draw: the reroll counter "
                "asks the route for another draw, and an adopted shot asks the route for "
                "nothing. Drop the take to draw again, or drop draw to keep the take"
            )
        return self


ImagePlate = ShellPlate
VideoPlate = ShellClip
ImageReferenceBinding = ShellReference
Typeface = ShellTypeface

__all__ = [
    "FIRST_SHELL_DRAW",
    "MAX_SHELL_DRAW",
    "FONT_SUFFIXES",
    "REDISTRIBUTABLE_FONT_LICENSES",
    "ShellReference",
    "ShellTypeface",
    "ShellPlate",
    "ShellClipTake",
    "ShellClip",
    "ImagePlate",
    "VideoPlate",
    "ImageReferenceBinding",
    "Typeface",
]
