"""Chunk grammar: the map as a sentence of parameterized set-pieces.

Lineage is Dormans' mission/space grammars: a designer composes named patterns, and the
patterns own their internal correctness. The model emits a left-to-right sequence of chunks
-- runs, staircases, hollows, ladder-fed perches, chained towers, jump chains -- and a
deterministic expander turns each into terrain, platforms, and climbables. Nothing here is
absolute-positioned: every chunk advances a cursor, so the model composes purely in pacing.

What this buys over a walk-the-map encoding:
  - VERTICAL set-pieces are first-class words (tower, hop_chain, shelves), countering the
    measured bias of walk-the-map encodings toward horizontal choreography. Shelves are the
    one word that stacks decks over the SAME columns, and each of its tiers is a lane rather
    than a single deck, which is what a hunting map's storeys are made of; every other chunk
    owns its columns alone.
  - the vocabulary is PROFILE-FILTERED: a tower is only in the grammar when the profile lets
    climbables stand on platforms, so a game's grammar only contains what it can build.
  - validator feedback is TRANSLATED back into chunk vocabulary. A grid encoding loses maps
    because the validator complains about surface ids the model never saw; here every emitted
    column remembers the chunk that produced it.

Total width: chunks that fall short of the map are finished with an implicit flat run (a
format semantic, like RLE right-padding); chunks that overflow are an error naming the chunk
where the map ran out.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from gnode import StructuredOutputSchema
from stage_gen.components.sideview_map_design.capabilities import PlatformerProfile
from stage_gen.components.sideview_map_design.design import Climbable, DesignedMap


@dataclass(frozen=True)
class ChunkSpan:
    """Provenance: which chunk produced which columns."""

    index: int
    kind: str
    start: int
    end: int
    detail: str


@dataclass(frozen=True)
class _Word:
    """One word of the grammar, with everything that word needs in one place.

    This is the single source of the vocabulary. ``vocabulary``, ``_chunk_shapes`` and
    ``build_chunk_prompt`` -- both its vocabulary listing and its width accounting -- all read
    this same table, filtered by the profile, so a word cannot exist in the prompt but not in
    the schema, nor be offered without the arithmetic that budgets it. Adding a word is one
    entry here; a word this game cannot build contributes to none of them.
    """

    name: str
    #: Whether this game can build the word at all. A word it cannot build is not in its grammar.
    available: Callable[[PlatformerProfile], bool]
    #: This word's JSON-schema properties, without the ``kind`` discriminator or the biome tag.
    properties: Callable[[PlatformerProfile], dict[str, object]]
    #: The line the prompt lists this word on.
    prompt_line: str
    #: How many columns this word occupies, in its own parameters. The expander is the authority;
    #: this states the same arithmetic to the model, which cannot budget a width it cannot see.
    width_formula: str


def _always(profile: PlatformerProfile) -> bool:
    return True


def _has_climbables(profile: PlatformerProfile) -> bool:
    return bool(profile.climbable_variants)


def _chains_climbables(profile: PlatformerProfile) -> bool:
    """A tower needs a climbable that may stand on the platform below it."""

    return _has_climbables(profile) and profile.movement.climbable_footing == "any"


def _stacks_by_jumping(profile: PlatformerProfile) -> bool:
    """Shelves stack one jump apart; a platform one tile up would sit on the floor, not float."""

    return profile.movement.max_jumpable_rise >= 2


def _run_properties(profile: PlatformerProfile) -> dict[str, object]:
    return {"len": {"type": "integer", "minimum": 2}}


def _stairs_properties(profile: PlatformerProfile) -> dict[str, object]:
    return {
        "steps": {"type": "integer", "minimum": 1},
        "step_h": {
            "type": "integer",
            "minimum": 1,
            "maximum": profile.movement.max_step_up_tiles,
        },
        "tread": {"type": "integer", "minimum": 1},
        "dir": {"type": "string", "enum": ["up", "down"]},
    }


def _slope_properties(profile: PlatformerProfile) -> dict[str, object]:
    return {
        "rise": {"type": "integer", "minimum": 2},
        "grade": {"type": "string", "enum": ["gentle", "steep"]},
        "dir": {"type": "string", "enum": ["up", "down"]},
    }


def _hollow_properties(profile: PlatformerProfile) -> dict[str, object]:
    return {
        "width": {"type": "integer", "minimum": 2},
        "depth": {
            "type": "integer",
            "minimum": 1,
            "maximum": profile.movement.max_step_up_tiles,
        },
    }


def _hop_chain_properties(profile: PlatformerProfile) -> dict[str, object]:
    movement = profile.movement
    return {
        "count": {"type": "integer", "minimum": 2},
        "jump_rise": {"type": "integer", "enum": sorted(movement.jump_reach)},
        "gap": {
            "type": "integer",
            "minimum": 1,
            "maximum": max(movement.jump_reach.values(), default=1),
        },
        "platform_width": {"type": "integer", "minimum": 2},
        "dir": {"type": "string", "enum": ["up", "down"]},
    }


def _shelves_properties(profile: PlatformerProfile) -> dict[str, object]:
    movement = profile.movement
    return {
        "tiers": {"type": "integer", "minimum": 2, "maximum": 8},
        "decks": {"type": "integer", "minimum": 2},
        "platform_width": {"type": "integer", "minimum": profile.geometry.shelf_min_width_tiles},
        "gap": {"type": "integer", "minimum": 1, "maximum": movement.level_gap_tiles},
        "lean": {"type": "string", "enum": ["left", "right"]},
    }


def _perch_properties(profile: PlatformerProfile) -> dict[str, object]:
    return {
        "platform_width": {"type": "integer", "minimum": 2},
        "climb_rise": {"type": "integer", "enum": sorted(profile.movement.climbable_rise_tiles)},
        "variant": {"type": "string", "enum": list(profile.climbable_variants)},
    }


def _tower_properties(profile: PlatformerProfile) -> dict[str, object]:
    return {
        "storeys": {"type": "integer", "minimum": 2, "maximum": 6},
        **_perch_properties(profile),
    }


#: The grammar, in prompt order. Everything downstream is this table filtered by a profile.
_WORDS: tuple[_Word, ...] = (
    _Word(
        "run",
        _always,
        _run_properties,
        "  run{len}                          flat ground, a breather",
        "len",
    ),
    _Word(
        "stairs",
        _always,
        _stairs_properties,
        "  stairs{steps, step_h, tread, dir}  a staircase; each step is `tread` columns then "
        "a `step_h` change",
        "steps*tread",
    ),
    _Word(
        "slope",
        _always,
        _slope_properties,
        "  slope{rise, grade, dir}            a continuous incline walked without jumping; "
        "gentle rises 1 tile per 2 columns, steep 1 per column",
        "rise (steep) or rise*2 (gentle)",
    ),
    _Word(
        "hollow",
        _always,
        _hollow_properties,
        "  hollow{width, depth}               a dip the player walks through",
        "width",
    ),
    _Word(
        "hop_chain",
        _always,
        _hop_chain_properties,
        "  hop_chain{count, jump_rise, gap, platform_width, dir}  floating platforms in a "
        "rising or falling line, each a jump from the last",
        "count*platform_width + (count+1)*gap",
    ),
    _Word(
        "shelves",
        _stacks_by_jumping,
        _shelves_properties,
        "  shelves{tiers, decks, platform_width, gap, lean}  storeys over ONE stretch of "
        "ground. Each tier is a LINE of `decks` decks split by a `gap` the player hops, so the "
        "tier is a lane to walk and fight along, not a stepping stone. Each tier sits one jump "
        "above the one below and is offset half a deck, so one tier's gaps open over the next "
        "tier's decks and the player has headroom and a way up",
        "decks*platform_width + (decks+1)*gap",
    ),
    _Word(
        "perch",
        _has_climbables,
        _perch_properties,
        "  perch{platform_width, climb_rise, variant}  one climbable-fed platform over flat ground",
        "platform_width + 2",
    ),
    _Word(
        "tower",
        _chains_climbables,
        _tower_properties,
        "  tower{storeys, platform_width, climb_rise, variant}  a vertical stack of "
        "platforms, each storey a climbable footed on the one below -- the tallest thing "
        "in the grammar; use it when the map should go UP",
        "platform_width + 2",
    ),
)


def _profile_words(profile: PlatformerProfile) -> list[_Word]:
    """The table filtered to the words this game can actually build."""

    return [word for word in _WORDS if word.available(profile)]


def vocabulary(profile: PlatformerProfile) -> list[str]:
    """The words this game's grammar contains, in prompt order."""

    return [word.name for word in _profile_words(profile)]


def _as_int(value: object) -> int:
    """Coerce one decoded JSON scalar to an integer; the schema already constrains the type."""

    if isinstance(value, (int, float, str)):
        return int(value)
    raise TypeError(f"expected an integer chunk parameter, got {type(value).__name__}")


class _ChunkParameterError(ValueError):
    """A chunk parameter that cannot be read, phrased in the model's own vocabulary."""


def _require(chunk: Mapping[str, object], name: str, key: str) -> object:
    if key not in chunk:
        raise _ChunkParameterError(f"{name} is missing the parameter {key!r}")
    return chunk[key]


def _number(chunk: Mapping[str, object], name: str, key: str) -> int:
    """One numeric chunk parameter, or a reportable problem instead of an exception."""

    value = _require(chunk, name, key)
    try:
        return _as_int(value)
    except (TypeError, ValueError):
        raise _ChunkParameterError(f"{name} parameter {key!r} is not a number") from None


def _text(chunk: Mapping[str, object], name: str, key: str) -> str:
    """One textual chunk parameter. Any present value reads as text; only absence is a problem."""

    return str(_require(chunk, name, key))


def _chunk_shapes(profile: PlatformerProfile) -> list[dict[str, object]]:
    """One ``anyOf`` branch per word in ``_WORDS`` this profile can build.

    Two transport facts shape this builder and must not be "cleaned up":

      * the discriminator is ``{"type": "string", "enum": [kind]}`` and never ``{"const": kind}``
        -- the provider rejects ``const`` with ``invalid_json_schema``.
      * ``canonicalize_strict_json_schema`` strips ``minimum``/``maximum``/``minItems`` and forces
        ``required`` to every declared property plus ``additionalProperties: false``. Numeric
        bounds here are therefore ADVISORY: the validator in ``design.check`` is authoritative.
        Because every declared property becomes required, a property the model may legitimately
        omit cannot be declared -- which is why ``storeys`` lives only on the ``tower`` branch
        rather than being an optional field of a shared perch/tower shape. A separate branch is
        how optionality is legitimately expressed under strict output.
    """

    def shape(word: _Word) -> dict[str, object]:
        props = word.properties(profile)
        if profile.biomes:
            props = {**props, "biome": {"type": "string", "enum": list(profile.biomes)}}
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", *props],
            "properties": {"kind": {"type": "string", "enum": [word.name]}, **props},
        }

    return [shape(word) for word in _profile_words(profile)]


def build_chunk_schema(profile: PlatformerProfile) -> StructuredOutputSchema:
    low, high = profile.geometry.ground_depth_tiles
    json_schema: dict[str, object] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["design_notes", "start_height_tiles", "chunks"],
        "properties": {
            "design_notes": {
                "type": "string",
                "description": "Plan the composition before writing the sentence.",
            },
            "start_height_tiles": {"type": "integer", "minimum": low, "maximum": high},
            "chunks": {
                "type": "array",
                "minItems": 3,
                "items": {"anyOf": _chunk_shapes(profile)},
            },
        },
    }
    return StructuredOutputSchema(
        name="composed_map",
        description="A map composed as a sequence of pattern chunks.",
        json_schema=json_schema,
    )


def build_chunk_prompt(profile: PlatformerProfile, columns: int) -> str:
    geometry = profile.geometry
    movement = profile.movement
    low, high = geometry.ground_depth_tiles
    low_count, high_count = profile.climbable_count
    rises = sorted(movement.climbable_rise_tiles)
    available = vocabulary(profile)
    words = _profile_words(profile)
    vocabulary_lines = "\n".join(word.prompt_line for word in words)
    width_lines = "\n".join(f"  {word.name}: {word.width_formula}" for word in words)
    reach = ", ".join(
        f"rise {rise}: gap up to {movement.jump_reach[rise]}"
        for rise in sorted(movement.jump_reach)
    )
    rise_span = str(rises) if len(rises) > 1 else f"exactly {rises[0]}"
    tower_clause = " and towers" if "tower" in available else ""
    shelves_clause = (
        f"\n  - a shelves deck is at least {geometry.shelf_min_width_tiles} tiles wide: it is "
        "standing room to fight on, and wider is better; narrow stepping stones are hop_chain's."
        "\n  - a shelves tier is a storey. Give it enough decks to span the ground it covers, "
        "and make the hop between decks about as wide as a deck: at that width the storey "
        "above interlocks with the gaps of the one below, which is both the way up and the "
        "headroom to stand. The map should read as several walkable levels over one floor."
        if "shelves" in available
        else ""
    )
    variants_clause = (
        "\n  - place every declared climbable variant at least once: "
        f"{', '.join(profile.climbable_variants)}."
        if profile.climbable_variants_each_placed
        else ""
    )
    biomes = _biome_section(profile)
    return f"""You compose playable maps for a 2D side-scrolling game from a fixed vocabulary
of set-pieces, like a level designer placing patterns on a strip. You never place absolute
coordinates: each chunk begins where the previous one ended, and a compiler builds the
geometry exactly as composed.

THE VOCABULARY (this game's grammar -- it contains only what this game can build):
{vocabulary_lines}

WIDTH ACCOUNTING (each chunk occupies exactly this many columns -- budget them):
{width_lines}

THIS GAME'S MEASURED LIMITS:
  - the map is {columns} columns wide; chunk widths add left to right. Plan the budget in
    design_notes and make the widths sum to at most {columns}. If your chunks end early the
    map is finished with flat ground; going past {columns} is an error.
  - floor height must stay within {low}..{high} tiles everywhere (start_height_tiles sets the left
    edge; stairs and hollows move it).
  - jump reach: {reach}. Higher rises are impossible at any gap.
  - a climbable rises {rise_span} tile(s).
  - no walkable surface may sit above {geometry.max_walkable_height_tiles} tiles.{shelves_clause}
  - use {low_count}..{high_count} climbables in total across perches{tower_clause}.{variants_clause}

{biomes}Compose with intent: alternate tension and rest, vary your pattern parameters, and let the
map's silhouette have a shape. A sentence of identical chunks is a boring map."""


def _biome_section(profile: PlatformerProfile) -> str:
    """The biome instruction, which names no word of the grammar.

    The vocabulary is profile-filtered, so prose that illustrates itself with a named word
    can name one this game does not have -- which is how ``tower`` used to reach a
    ground-footed prompt. Landmarks are described by the shape they make instead.
    """

    if not profile.biomes:
        return ""
    return f"""BIOMES (appearance only -- physics is identical everywhere). Every chunk declares its
biome from: {", ".join(profile.biomes)}. This is pure intent; art is resolved later. Keep a
biome going for at least {profile.biome_min_span_tiles} columns before switching, and switch
where the map changes shape -- the top of a climb, the far side of a dip -- so the acts of
the map feel deliberate.

"""


def expand_chunks(
    value: Mapping[str, object], profile: PlatformerProfile, columns: int
) -> tuple[DesignedMap, list[str], list[ChunkSpan]]:
    """Expand the sentence. Chunk-level errors speak chunk vocabulary."""

    errors: list[str] = []
    spans: list[ChunkSpan] = []
    geometry, movement = profile.geometry, profile.movement
    ground = profile.ground_role.symbol
    empty = profile.empty_role.symbol
    platform_symbol = profile.platform_roles[0].symbol if profile.platform_roles else empty

    heights: list[int] = []
    biome_cols: list[str] = []
    platforms: list[tuple[int, int, int]] = []  # (start, width, height)
    climbables: list[Climbable] = []
    level = _as_int(value.get("start_height_tiles", 1))
    climb_serial = 0
    current_biome = profile.biomes[0] if profile.biomes else ""

    def emit_flat(width: int) -> int:
        start = len(heights)
        heights.extend([max(1, level)] * width)
        biome_cols.extend([current_biome] * width)
        return start

    raw_chunks = value.get("chunks", [])
    entries = list(raw_chunks) if isinstance(raw_chunks, list) else []
    for index, entry in enumerate(entries):
        chunk: Mapping[str, object] = entry if isinstance(entry, Mapping) else {}
        kind = str(chunk.get("kind", "?"))
        current_biome = str(chunk.get("biome", current_biome))
        start = len(heights)
        name = f"chunk #{index + 1} ({kind})"
        # Every parameter is read BEFORE the chunk emits anything, so a chunk the model wrote
        # without one is reported like any other chunk-level fault and skipped with a
        # zero-width span, rather than raising out of the expander.
        try:
            if kind == "run":
                emit_flat(_number(chunk, name, "len"))
            elif kind == "stairs":
                sign = 1 if _text(chunk, name, "dir") == "up" else -1
                steps = _number(chunk, name, "steps")
                tread = _number(chunk, name, "tread")
                step_h = _number(chunk, name, "step_h")
                for _ in range(steps):
                    emit_flat(tread)
                    level += sign * step_h
                    if level < 1:
                        errors.append(f"{name} walks the floor below the world")
                        level = max(1, level)
            elif kind == "slope":
                tread = 1 if _text(chunk, name, "grade") == "steep" else 2
                sign = 1 if _text(chunk, name, "dir") == "up" else -1
                for _ in range(_number(chunk, name, "rise")):
                    emit_flat(tread)
                    level += sign
                    if level < 1:
                        errors.append(f"{name} walks the floor below the world")
                        level = 1
            elif kind == "hollow":
                depth = _number(chunk, name, "depth")
                width = _number(chunk, name, "width")
                if level - depth < 1:
                    errors.append(f"{name} digs below the world floor")
                    depth = level - 1
                level -= depth
                emit_flat(width)
                level += depth
            elif kind == "hop_chain":
                count = _number(chunk, name, "count")
                rise = _number(chunk, name, "jump_rise")
                gap = _number(chunk, name, "gap")
                width = _number(chunk, name, "platform_width")
                direction = _text(chunk, name, "dir")
                # A platform at rise 1 from the floor would sit ON the ground, not float; the
                # first hop therefore always clears at least 2 tiles, and the gap must be within
                # reach for both the first hop and every later one.
                first = max(rise, 2)
                limit = min(movement.jump_reach.get(rise, 0), movement.jump_reach.get(first, 0))
                if gap > limit:
                    errors.append(
                        f"{name}: gap {gap} exceeds this game's reach {limit} for a "
                        f"{rise}-tile jump rise"
                    )
                hop_start = emit_flat(count * width + (count + 1) * gap)
                for step_index in range(count):
                    step = step_index if direction == "up" else count - 1 - step_index
                    height = level + first + step * rise
                    if height > geometry.max_walkable_height_tiles:
                        errors.append(
                            f"{name} climbs to {height} tiles, above the "
                            f"{geometry.max_walkable_height_tiles}-tile ceiling"
                        )
                        break
                    platforms.append((hop_start + gap + step_index * (width + gap), width, height))
            elif kind == "shelves":
                tiers = _number(chunk, name, "tiers")
                decks = _number(chunk, name, "decks")
                width = _number(chunk, name, "platform_width")
                gap = _number(chunk, name, "gap")
                lean = _text(chunk, name, "lean")
                # Tiers sit one full jump apart, which is as close as they can be and still be
                # reached from below. The offset is half a deck-and-gap period rather than a
                # free parameter: at half a period one tier's gaps fall over the tier below,
                # which is both the standing headroom and the hole the player jumps up through.
                rise = movement.max_jumpable_rise
                if width < geometry.shelf_min_width_tiles:
                    errors.append(
                        f"{name}: platform_width {width} is narrower than this game's "
                        f"{geometry.shelf_min_width_tiles}-tile standing room; a deck that "
                        "narrow is a stepping stone, which is hop_chain's job"
                    )
                # The hop along a tier is a LEVEL crossing, so it is bounded by the level gap
                # rather than by the rise-to-the-next-tier reach. Climbing a tier is the other
                # jump, and the half-period offset is what keeps that one short.
                if gap > movement.level_gap_tiles:
                    errors.append(
                        f"{name}: gap {gap} is wider than this game's level reach "
                        f"{movement.level_gap_tiles}, so the storey cannot be walked across"
                    )
                period = width + gap
                offset = period // 2
                base = emit_flat(decks * width + (decks + 1) * gap)
                for tier in range(tiers):
                    height = level + rise * (tier + 1)
                    if height > geometry.max_walkable_height_tiles:
                        errors.append(
                            f"{name} stacks to {height} tiles, above the "
                            f"{geometry.max_walkable_height_tiles}-tile ceiling"
                        )
                        break
                    shifted = (tier % 2 == 1) if lean == "right" else (tier % 2 == 0)
                    # The offset lane hangs over the gaps of the aligned one, so it carries one
                    # deck fewer and both lanes stay inside the chunk's own columns.
                    count = decks - 1 if shifted else decks
                    lane_start = base + gap + (offset if shifted else 0)
                    for deck in range(count):
                        platforms.append((lane_start + deck * period, width, height))
            elif kind in ("perch", "tower"):
                width = _number(chunk, name, "platform_width")
                rise = _number(chunk, name, "climb_rise")
                # ``storeys`` belongs to ``tower`` alone, so a perch legitimately omits it.
                storeys = _number(chunk, name, "storeys") if "storeys" in chunk else 1
                variant = _text(chunk, name, "variant")
                base = emit_flat(width + 2)
                foot_column = base + 1 + width // 2
                foot_height = level
                for storey in range(storeys):
                    height = level + (storey + 1) * rise
                    if height > geometry.max_walkable_height_tiles:
                        errors.append(
                            f"{name} tops out at {height} tiles, above the "
                            f"{geometry.max_walkable_height_tiles}-tile ceiling"
                        )
                        break
                    platforms.append((base + 1, width, height))
                    climb_serial += 1
                    climbables.append(
                        Climbable(f"c{climb_serial}", variant, foot_column, rise, foot_height)
                    )
                    foot_height = height
            else:
                errors.append(f"{name} is not a word in this game's grammar")
        except _ChunkParameterError as error:
            errors.append(str(error))
        detail = ", ".join(f"{key}={item}" for key, item in chunk.items() if key != "kind")
        spans.append(ChunkSpan(index + 1, kind, start, len(heights), detail))

    if len(heights) > columns:
        # The model cannot fix arithmetic it cannot see: hand back the compiler's own ledger.
        ledger = ", ".join(f"#{s.index} {s.kind}={s.end - s.start}" for s in spans)
        errors.append(
            f"the chunks total {len(heights)} columns of {columns} ({ledger}); shrink or "
            f"drop {len(heights) - columns} columns' worth"
        )
    if len(heights) < columns:
        pad = columns - len(heights)
        heights.extend([heights[-1] if heights else 1] * pad)
        biome_cols.extend([biome_cols[-1] if biome_cols else current_biome] * pad)
    heights = heights[:columns]
    biome_cols = biome_cols[:columns]

    grid = [
        "".join(ground if heights[c] >= h else empty for c in range(columns))
        for h in range(1, geometry.rows + 1)
    ]
    for start_column, width, height in platforms:
        if height < 1 or height > geometry.rows or start_column >= columns:
            continue
        row = list(grid[height - 1])
        for column in range(start_column, min(start_column + width, columns)):
            if heights[column] < height:
                row[column] = platform_symbol
        grid[height - 1] = "".join(row)

    climbables = [climb for climb in climbables if climb.foot_column < columns]
    designed = DesignedMap(
        profile.profile_id,
        columns,
        geometry.rows,
        grid,
        climbables,
        str(value.get("design_notes", "")),
        column_biomes=biome_cols if profile.biomes else None,
    )
    return designed, errors, spans


_COLUMN = re.compile(r"(?:column |-c)(\d+)")


def translate(problems: list[str], spans: list[ChunkSpan]) -> list[str]:
    """Re-anchor validator messages in the vocabulary the model actually wrote.

    A grid encoding loses maps to 'platform s-h6-c104 is more than one tile thick': a true
    complaint the model cannot map back to any of its own declarations. Every column here
    knows its chunk, so the same complaint arrives as 'inside chunk #7 (tower ...)'.
    """

    translated: list[str] = []
    for problem in problems:
        match = _COLUMN.search(problem)
        if match:
            column = int(match.group(1))
            span = next((s for s in spans if s.start <= column < s.end), None)
            if span:
                problem += f" [inside chunk #{span.index}: {span.kind}({span.detail})]"
        translated.append(problem)
    return translated


__all__ = [
    "ChunkSpan",
    "build_chunk_prompt",
    "build_chunk_schema",
    "expand_chunks",
    "translate",
    "vocabulary",
]
