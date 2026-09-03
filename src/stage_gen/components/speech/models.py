"""The authored, provider-neutral shape of one spoken line.

A cue that asks for a spoken line - a *bark* in the industry's word: a short,
event-triggered one-liner - states the text the voice reads verbatim, delivery
annotations included, the game-owned voice that reads it, how literally the
voice follows the text, and the longest read the cue's frame budget tolerates.
That is the whole request: the recipe compiles nothing onto the text, and the
author should read the model boundary in ``docs/spec/model-eleven-v3.md``
before writing it.

The voice is named, never identified: ``voice_id`` is resolved through the
game's voice catalog (``voices.toml``), because a provider's voice reference is
an externally-held identity with its own rights and does not belong in a genre
audio contract any more than a model id does.

Playback mixing - gain and the strength-driven rate lift - is consumer data. It
travels with the line in the manifest but stays out of the generation identity,
so rebalancing after listening never re-bills a read.

A read is a lottery and a person picks the winner, so a line carries the same
two fields a generated clip does: ``take``, the reroll ordinal that re-keys
this one read, and ``pinned``, the reviewed audition committed into the
package and republished in place of a fresh draw.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from gnode import PersistedContractModel
from stage_gen.components._game_input import SNAKE_ID_PATTERN, normalized_text
from stage_gen.components.sound_effect.models import FIRST_TAKE, MAX_TAKE, PinnedTake

SPOKEN_LINE_REALIZATION_KIND = "spoken_line_v1"
SPOKEN_LINE_OUTPUT_FORMAT = "mp3"
#: A bark is a line, not a paragraph; the route's own ceiling is far higher.
MAX_SPOKEN_LINE_CHARACTERS = 1000
MIN_SPOKEN_LINE_SECONDS = 0.5
MAX_SPOKEN_LINE_SECONDS = 30.0


class SpokenLineRealization(PersistedContractModel):
    """One provider-read line, requested with the parameters the route honours."""

    kind: Literal["spoken_line_v1"]
    #: Sent to the provider exactly as written, bracketed delivery tags included.
    text: str = Field(min_length=1, max_length=MAX_SPOKEN_LINE_CHARACTERS)
    #: A voice the game's catalog declares; never a provider reference.
    voice_id: str = Field(pattern=SNAKE_ID_PATTERN, max_length=64)
    #: How literally the voice follows the text and its tags. Omitted means
    #: the provider default.
    stability: float | None = Field(default=None, ge=0.0, le=1.0)
    #: The route has no duration control - the model decides how long a line
    #: takes - so the cue states the longest read its frame budget tolerates,
    #: and a longer draw is refused and redrawn, never trimmed.
    max_seconds: float = Field(ge=MIN_SPOKEN_LINE_SECONDS, le=MAX_SPOKEN_LINE_SECONDS)
    #: Playback gain applied by the consumer; the bytes are never touched.
    gain: float = Field(gt=0.0, le=1.0)
    #: Multiplies playback rate by ``1 + event_strength * value``. Zero disables it.
    strength_pitch_multiplier: float = Field(ge=0.0, le=2.0)
    #: The reroll ordinal. Bump it to redraw this line alone.
    take: int = Field(default=FIRST_TAKE, ge=FIRST_TAKE, le=MAX_TAKE)
    #: The reviewed pick. When present the graph buys nothing for this line.
    pinned: PinnedTake | None = None

    @model_validator(mode="after")
    def validate_text(self) -> SpokenLineRealization:
        self.text = normalized_text(self.text, "spoken line text")
        return self

    def generation_identity(
        self, *, provider: str, voice: str, language_code: str | None
    ) -> dict[str, object]:
        """The fields that decide whether a read must be re-bought.

        Takes the resolved voice rather than the catalog name, because the same
        ``voice_id`` recast to a different provider voice is a different asset.
        Deliberately excludes ``gain``, ``strength_pitch_multiplier`` and
        ``max_seconds``: they change how a line is played or judged, not which
        line was read. No seed: measured, a seed pins the length of a read and
        not its waveform, so it cannot make a draw repeatable. ``take`` enters
        only above the first draw, so an existing key is undisturbed until a
        person asks for another.
        """

        identity: dict[str, object] = {
            "text": self.text,
            "provider": provider,
            "voice": voice,
            "output_format": SPOKEN_LINE_OUTPUT_FORMAT,
        }
        if self.stability is not None:
            identity["stability"] = self.stability
        if language_code is not None:
            identity["language_code"] = language_code
        if self.take != FIRST_TAKE:
            identity["take"] = self.take
        return identity


__all__ = [
    "MAX_SPOKEN_LINE_CHARACTERS",
    "MAX_SPOKEN_LINE_SECONDS",
    "MIN_SPOKEN_LINE_SECONDS",
    "SPOKEN_LINE_OUTPUT_FORMAT",
    "SPOKEN_LINE_REALIZATION_KIND",
    "SpokenLineRealization",
]
