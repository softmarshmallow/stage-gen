"""The chunk grammar: what the words mean, what the schema may say, and how feedback returns."""

from __future__ import annotations

from collections.abc import Iterator, Mapping

import pytest

from stage_gen.components.platformer_map_design import (
    PlatformerProfile,
    build_chunk_prompt,
    build_chunk_schema,
    check,
    expand_chunks,
    translate,
    vocabulary,
)
from stage_gen.components.platformer_map_design import grammar as grammar_module
from stage_gen.components.structured_generation import StructuredOutputSchema

from ._profiles import CHAINED_SHAFT_PROFILE, CLIMBLESS_PROFILE, GROUND_FOOTED_PROFILE


def _nodes(value: object) -> Iterator[Mapping[str, object]]:
    """Every object node in a JSON Schema, so a claim can be made about all of them at once."""

    if isinstance(value, Mapping):
        yield value
        for item in value.values():
            yield from _nodes(item)
    elif isinstance(value, list):
        for item in value:
            yield from _nodes(item)


def _branches(schema: StructuredOutputSchema) -> dict[str, Mapping[str, object]]:
    properties = schema.json_schema["properties"]
    assert isinstance(properties, Mapping)
    chunks = properties["chunks"]
    assert isinstance(chunks, Mapping)
    items = chunks["items"]
    assert isinstance(items, Mapping)
    any_of = items["anyOf"]
    assert isinstance(any_of, list)
    found: dict[str, Mapping[str, object]] = {}
    for branch in any_of:
        assert isinstance(branch, Mapping)
        branch_properties = branch["properties"]
        assert isinstance(branch_properties, Mapping)
        kind = branch_properties["kind"]
        assert isinstance(kind, Mapping)
        enum = kind["enum"]
        assert isinstance(enum, list)
        found[str(enum[0])] = branch
    return found


def _required(branch: Mapping[str, object]) -> list[str]:
    required = branch["required"]
    assert isinstance(required, list)
    return [str(name) for name in required]


def _width_block(prompt: str) -> dict[str, str]:
    """The prompt's WIDTH ACCOUNTING section, read back as ``word -> formula``."""

    body = prompt.partition("WIDTH ACCOUNTING")[2].partition("\n")[2]
    entries: dict[str, str] = {}
    for line in body.partition("\n\n")[0].splitlines():
        word, separator, formula = line.strip().partition(": ")
        assert separator, f"unparsable width accounting line: {line!r}"
        entries[word] = formula
    return entries


def test_the_vocabulary_offers_no_tower_where_climbables_cannot_stand_on_platforms() -> None:
    assert vocabulary(GROUND_FOOTED_PROFILE) == [
        "run",
        "stairs",
        "slope",
        "hollow",
        "hop_chain",
        "perch",
    ]
    assert vocabulary(CHAINED_SHAFT_PROFILE)[-1] == "tower"
    assert "tower" not in vocabulary(GROUND_FOOTED_PROFILE)
    assert "tower" in vocabulary(CHAINED_SHAFT_PROFILE)
    assert set(_branches(build_chunk_schema(GROUND_FOOTED_PROFILE))) == set(
        vocabulary(GROUND_FOOTED_PROFILE)
    )
    assert set(_branches(build_chunk_schema(CHAINED_SHAFT_PROFILE))) == set(
        vocabulary(CHAINED_SHAFT_PROFILE)
    )


def test_a_game_that_declares_no_climbable_variant_gets_neither_perch_nor_tower() -> None:
    """Withholding a word is a branch, and until now no profile ever took it.

    Both other profiles declare climbable variants, so ``perch`` was offered to every game the
    suite ever built a grammar for -- and a table that simply always offered it would have been
    indistinguishable. This game declares none, and its ``climbable_footing`` is the permissive
    ``"any"`` on purpose, so footing cannot be the thing withholding ``tower`` either. All three
    consumers of the table are checked, because the word must vanish from all three at once.
    """

    climbless = build_chunk_prompt(CLIMBLESS_PROFILE, 96)

    assert vocabulary(CLIMBLESS_PROFILE) == ["run", "stairs", "slope", "hollow", "hop_chain"]
    assert set(_branches(build_chunk_schema(CLIMBLESS_PROFILE))) == set(
        vocabulary(CLIMBLESS_PROFILE)
    )
    assert list(_width_block(climbless)) == vocabulary(CLIMBLESS_PROFILE)
    assert "tower" not in climbless
    # ``perch`` survives in exactly one line, pinned here so it cannot spread: the measured-limits
    # block still budgets climbables for a game that draws none. Neither the vocabulary listing
    # nor the width accounting names the word, which is what this test is about.
    assert [line for line in climbless.splitlines() if "perch" in line] == [
        "  - use 0..0 climbables in total across perches."
    ]


def test_the_chunk_schema_never_emits_const_and_discriminates_with_a_typed_enum() -> None:
    """The provider rejects ``const`` outright, so the discriminator must be a one-value enum."""

    for profile in (GROUND_FOOTED_PROFILE, CHAINED_SHAFT_PROFILE):
        schema = build_chunk_schema(profile)
        for node in _nodes(schema.json_schema):
            assert "const" not in node
        for kind, branch in _branches(schema).items():
            properties = branch["properties"]
            assert isinstance(properties, Mapping)
            assert properties["kind"] == {"type": "string", "enum": [kind]}


def test_the_chunk_schema_survives_strict_output_canonicalization() -> None:
    """Bounds are advisory: the transport strips them, and ``check`` remains authoritative."""

    schema = build_chunk_schema(GROUND_FOOTED_PROFILE)

    assert isinstance(schema, StructuredOutputSchema)
    assert schema.strict is True
    for node in _nodes(schema.json_schema):
        assert not {"minimum", "maximum", "minItems", "maxItems", "default"} & set(node)
        properties = node.get("properties")
        if isinstance(properties, Mapping):
            assert node["required"] == list(properties)
            assert node["additionalProperties"] is False
    # ``storeys`` is a branch of its own rather than an optional field, because strict output
    # makes every declared property required.
    assert _required(_branches(schema)["perch"]) == [
        "kind",
        "platform_width",
        "climb_rise",
        "variant",
        "biome",
    ]
    tower = _branches(build_chunk_schema(CHAINED_SHAFT_PROFILE))["tower"]
    assert "storeys" in _required(tower)


def test_run_stairs_and_hollow_expand_to_the_expected_heights() -> None:
    sentence: dict[str, object] = {
        "design_notes": "terrain only",
        "start_height_tiles": 3,
        "chunks": [
            {"kind": "run", "len": 5},
            {"kind": "stairs", "steps": 2, "step_h": 1, "tread": 4, "dir": "up"},
            {"kind": "hollow", "width": 4, "depth": 2},
            {"kind": "run", "len": 5},
        ],
    }

    designed, errors, spans = expand_chunks(sentence, GROUND_FOOTED_PROFILE, 32)

    assert errors == []
    depths = [designed.ground_depth(column, GROUND_FOOTED_PROFILE) for column in range(24)]
    assert depths == [3] * 9 + [4] * 4 + [3] * 4 + [5] * 7
    assert [(span.index, span.kind, span.start, span.end) for span in spans] == [
        (1, "run", 0, 5),
        (2, "stairs", 5, 13),
        (3, "hollow", 13, 17),
        (4, "run", 17, 22),
    ]


def test_a_gentle_slope_rises_one_tile_per_two_columns_and_a_steep_slope_one_per_column() -> None:
    sentence: dict[str, object] = {
        "design_notes": "inclines",
        "start_height_tiles": 3,
        "chunks": [
            {"kind": "run", "len": 4},
            {"kind": "slope", "rise": 3, "grade": "gentle", "dir": "up"},
            {"kind": "slope", "rise": 2, "grade": "steep", "dir": "down"},
            {"kind": "run", "len": 4},
        ],
    }

    designed, errors, spans = expand_chunks(sentence, GROUND_FOOTED_PROFILE, 32)

    assert errors == []
    gentle, steep = spans[1], spans[2]
    assert gentle.end - gentle.start == 6
    assert steep.end - steep.start == 2
    depths = [designed.ground_depth(column, GROUND_FOOTED_PROFILE) for column in range(16)]
    assert depths == [3, 3, 3, 3, 3, 3, 4, 4, 5, 5, 6, 5, 4, 4, 4, 4]


def test_a_slope_sentence_compiles_and_validates_without_touching_the_validator() -> None:
    sentence: dict[str, object] = {
        "design_notes": "a new word costs one shape, one expansion, one prompt line",
        "start_height_tiles": 3,
        "chunks": [
            {"kind": "run", "len": 10},
            {"kind": "slope", "rise": 3, "grade": "gentle", "dir": "up"},
            {"kind": "perch", "platform_width": 6, "climb_rise": 4, "variant": "root_ladder"},
            {"kind": "slope", "rise": 2, "grade": "steep", "dir": "down"},
            {"kind": "perch", "platform_width": 5, "climb_rise": 4, "variant": "rope_climb"},
            {"kind": "run", "len": 12},
            {
                "kind": "perch",
                "platform_width": 4,
                "climb_rise": 4,
                "variant": "shrine_rope_ladder",
            },
        ],
    }

    designed, errors, spans = expand_chunks(sentence, GROUND_FOOTED_PROFILE, 128)

    assert errors + translate(check(designed, GROUND_FOOTED_PROFILE), spans) == []
    assert designed.ground_depth(14, GROUND_FOOTED_PROFILE) > designed.ground_depth(
        10, GROUND_FOOTED_PROFILE
    )


def test_the_first_hop_chain_platform_clears_the_floor_instead_of_sitting_on_it() -> None:
    """A platform one tile above the ground would be terrain, not a hop; the first hop is 2."""

    sentence: dict[str, object] = {
        "design_notes": "a rising jump chain",
        "start_height_tiles": 3,
        "chunks": [
            {"kind": "run", "len": 4},
            {
                "kind": "hop_chain",
                "count": 3,
                "jump_rise": 1,
                "gap": 4,
                "platform_width": 4,
                "dir": "up",
            },
        ],
    }

    designed, errors, _ = expand_chunks(sentence, GROUND_FOOTED_PROFILE, 64)

    assert errors == []
    platform = GROUND_FOOTED_PROFILE.platform_roles[0].symbol
    heights = sorted(
        {
            height
            for height in range(1, designed.rows + 1)
            for column in range(designed.columns)
            if designed.symbol_at(column, height) == platform
        }
    )
    floor = designed.ground_depth(0, GROUND_FOOTED_PROFILE)
    assert floor == 3
    assert heights == [floor + 2, floor + 3, floor + 4]
    # The chain itself is sound -- every platform is jumpable and none is stranded. The only
    # complaint left is that a map made of one hop chain has no climbables at all.
    assert check(designed, GROUND_FOOTED_PROFILE) == ["0 climbables, outside the profile's 3..8"]


def test_a_hop_chain_gap_beyond_this_games_reach_is_reported() -> None:
    sentence: dict[str, object] = {
        "design_notes": "too far",
        "start_height_tiles": 3,
        "chunks": [
            {
                "kind": "hop_chain",
                "count": 2,
                "jump_rise": 4,
                "gap": 9,
                "platform_width": 4,
                "dir": "up",
            }
        ],
    }

    _, errors, _ = expand_chunks(sentence, CHAINED_SHAFT_PROFILE, 64)

    assert errors == [
        "chunk #1 (hop_chain): gap 9 exceeds this game's reach 3 for a 4-tile jump rise"
    ]


def test_chunks_that_fall_short_are_finished_with_an_implicit_flat_run() -> None:
    """Falling short of the map width is a format semantic, like RLE right-padding."""

    sentence: dict[str, object] = {
        "design_notes": "three chunks for a 128-column map",
        "start_height_tiles": 3,
        "chunks": [
            {"kind": "run", "len": 10},
            {"kind": "stairs", "steps": 2, "step_h": 1, "tread": 4, "dir": "up"},
            {"kind": "perch", "platform_width": 6, "climb_rise": 4, "variant": "root_ladder"},
        ],
    }

    designed, errors, spans = expand_chunks(sentence, GROUND_FOOTED_PROFILE, 128)

    assert errors == []
    assert spans[-1].end == 26
    assert designed.columns == 128
    assert {len(row) for row in designed.grid} == {128}
    assert designed.ground_depth(25, GROUND_FOOTED_PROFILE) == 5
    assert designed.ground_depth(127, GROUND_FOOTED_PROFILE) == 5


def test_the_overflow_error_names_every_chunk_and_the_width_it_took() -> None:
    """The model cannot fix arithmetic it cannot see, so it is handed the compiler's ledger."""

    sentence: dict[str, object] = {
        "design_notes": "budget blown",
        "start_height_tiles": 3,
        "chunks": [
            {"kind": "run", "len": 100},
            {"kind": "hollow", "width": 40, "depth": 1},
            {"kind": "run", "len": 10},
        ],
    }

    _, errors, _ = expand_chunks(sentence, GROUND_FOOTED_PROFILE, 128)

    assert errors == [
        "the chunks total 150 columns of 128 (#1 run=100, #2 hollow=40, #3 run=10); "
        "shrink or drop 22 columns' worth"
    ]


def test_an_unknown_chunk_kind_is_reported_in_chunk_vocabulary() -> None:
    sentence: dict[str, object] = {
        "design_notes": "a word this game does not have",
        "start_height_tiles": 3,
        "chunks": [{"kind": "run", "len": 8}, {"kind": "spiral", "turns": 3}],
    }

    _, errors, spans = expand_chunks(sentence, GROUND_FOOTED_PROFILE, 128)

    assert errors == ["chunk #2 (spiral) is not a word in this game's grammar"]
    assert (spans[1].start, spans[1].end) == (8, 8)


def test_a_chunk_missing_a_required_parameter_is_reported_and_expansion_continues() -> None:
    """A parameter the model forgot is a chunk-vocabulary problem, not an exception.

    Raising would abandon the whole composition over one bad word and cost the designer loop the
    feedback that would have fixed it. The faulty chunk takes a zero-width span instead, and the
    chunks after it still expand.
    """

    sentence: dict[str, object] = {
        "design_notes": "a run without a length",
        "start_height_tiles": 3,
        "chunks": [
            {"kind": "run"},
            {"kind": "stairs", "steps": 2, "step_h": 1, "tread": 4, "dir": "up"},
            {"kind": "perch", "platform_width": 6, "climb_rise": 4},
        ],
    }

    designed, errors, spans = expand_chunks(sentence, GROUND_FOOTED_PROFILE, 128)

    assert errors == [
        "chunk #1 (run) is missing the parameter 'len'",
        "chunk #3 (perch) is missing the parameter 'variant'",
    ]
    assert [(span.index, span.start, span.end) for span in spans] == [
        (1, 0, 0),
        (2, 0, 8),
        (3, 8, 8),
    ]
    # The stairs between the two faults still walked the floor up, and the implicit flat run
    # finishes the map from the height they left it at.
    assert designed.ground_depth(0, GROUND_FOOTED_PROFILE) == 3
    assert designed.ground_depth(7, GROUND_FOOTED_PROFILE) == 4
    assert designed.ground_depth(127, GROUND_FOOTED_PROFILE) == 4


def test_a_chunk_parameter_that_is_not_a_number_is_reported_and_expansion_continues() -> None:
    """A parameter of the wrong type reads back in the model's own vocabulary, and is skipped."""

    sentence: dict[str, object] = {
        "design_notes": "a hollow measured in adjectives",
        "start_height_tiles": 3,
        "chunks": [
            {"kind": "run", "len": 10},
            {"kind": "hollow", "width": "wide", "depth": 2},
            {
                "kind": "hop_chain",
                "count": None,
                "jump_rise": 1,
                "gap": 4,
                "platform_width": 4,
                "dir": "up",
            },
            {"kind": "run", "len": 12},
        ],
    }

    designed, errors, spans = expand_chunks(sentence, GROUND_FOOTED_PROFILE, 128)

    assert errors == [
        "chunk #2 (hollow) parameter 'width' is not a number",
        "chunk #3 (hop_chain) parameter 'count' is not a number",
    ]
    assert [(span.index, span.start, span.end) for span in spans] == [
        (1, 0, 10),
        (2, 10, 10),
        (3, 10, 10),
        (4, 10, 22),
    ]
    # The hollow never dug, so the floor either side of the two faults is the level it started at.
    assert designed.ground_depth(9, GROUND_FOOTED_PROFILE) == 3
    assert designed.ground_depth(10, GROUND_FOOTED_PROFILE) == 3
    assert designed.ground_depth(127, GROUND_FOOTED_PROFILE) == 3


def test_translate_re_anchors_a_grid_vocabulary_complaint_onto_the_owning_chunk() -> None:
    """A complaint about ``s-h7-c19`` is true but unusable; every column knows its chunk."""

    sentence: dict[str, object] = {
        "design_notes": "a breather, a climb, a dip, and a jump chain",
        "start_height_tiles": 3,
        "chunks": [
            {"kind": "run", "len": 10},
            {"kind": "stairs", "steps": 2, "step_h": 1, "tread": 4, "dir": "up"},
            {"kind": "perch", "platform_width": 6, "climb_rise": 4, "variant": "root_ladder"},
        ],
    }
    _, _, spans = expand_chunks(sentence, GROUND_FOOTED_PROFILE, 128)

    translated = translate(["platform s-h7-c19 is more than one tile thick"], spans)

    assert translated == [
        "platform s-h7-c19 is more than one tile thick [inside chunk #3: "
        "perch(platform_width=6, climb_rise=4, variant=root_ladder)]"
    ]
    assert translate(["a complaint naming no column"], spans) == ["a complaint naming no column"]


def test_a_tower_sentence_produces_chained_climbables_with_ascending_foot_heights() -> None:
    sentence: dict[str, object] = {
        "design_notes": "a map that goes up",
        "start_height_tiles": 3,
        "chunks": [
            {"kind": "run", "len": 8},
            {
                "kind": "tower",
                "storeys": 3,
                "platform_width": 6,
                "climb_rise": 5,
                "variant": "iron_ladder",
            },
            {"kind": "hollow", "width": 6, "depth": 2},
            {"kind": "perch", "platform_width": 5, "climb_rise": 4, "variant": "chain"},
            {
                "kind": "hop_chain",
                "count": 3,
                "jump_rise": 2,
                "gap": 5,
                "platform_width": 4,
                "dir": "down",
            },
        ],
    }

    designed, errors, spans = expand_chunks(sentence, CHAINED_SHAFT_PROFILE, 64)

    assert errors + translate(check(designed, CHAINED_SHAFT_PROFILE), spans) == []
    storeys = [climb for climb in designed.climbables if climb.variant_id == "iron_ladder"]
    assert [climb.foot_column for climb in storeys] == [12, 12, 12]
    assert [climb.foot_height_tiles for climb in storeys] == [3, 8, 13]
    assert [climb.rise_tiles for climb in storeys] == [5, 5, 5]


def test_the_prompt_states_this_games_measured_limits_and_no_others() -> None:
    ground_footed = build_chunk_prompt(GROUND_FOOTED_PROFILE, 128)
    chained = build_chunk_prompt(CHAINED_SHAFT_PROFILE, 64)

    # Not merely absent as a declaration: a game with no tower must not read the word anywhere,
    # in a width formula or in prose, under a heading claiming the grammar holds only what it
    # can build. Checking for ``tower{`` alone let both leaks through.
    assert "tower" not in ground_footed
    assert "tower{" in chained
    assert "the map is 128 columns wide" in ground_footed
    assert "the map is 64 columns wide" in chained
    assert "jump reach: rise 1: gap up to 8, rise 2: gap up to 6." in ground_footed
    assert "a climbable rises exactly 4 tile(s)." in ground_footed
    assert "a climbable rises [3, 4, 5, 6] tile(s)." in chained
    assert "use 3..8 climbables in total across perches." in ground_footed
    assert "use 4..12 climbables in total across perches and towers." in chained
    assert "meadow, root_forest, shrine_stone" in ground_footed
    assert "cavern, rust_works, glow_moss" in chained
    assert "meadow" not in chained


def test_the_width_accounting_block_budgets_this_games_vocabulary_and_nothing_else() -> None:
    """The widths are per word, from the same table, so the block cannot drift from the grammar."""

    ground_footed = _width_block(build_chunk_prompt(GROUND_FOOTED_PROFILE, 128))
    chained = _width_block(build_chunk_prompt(CHAINED_SHAFT_PROFILE, 64))

    assert list(ground_footed) == vocabulary(GROUND_FOOTED_PROFILE)
    assert list(chained) == vocabulary(CHAINED_SHAFT_PROFILE)
    # The arithmetic the expander performs, restated to the model unchanged.
    assert ground_footed == {
        "run": "len",
        "stairs": "steps*tread",
        "slope": "rise (steep) or rise*2 (gentle)",
        "hollow": "width",
        "hop_chain": "count*platform_width + (count+1)*gap",
        "perch": "platform_width + 2",
    }
    assert chained == {**ground_footed, "tower": "platform_width + 2"}


def test_a_stated_width_formula_is_the_width_the_expander_actually_emits() -> None:
    """A budget the model cannot trust is worse than none: measure the promise against spans."""

    sentence: dict[str, object] = {
        "design_notes": "one chunk of every word, with widths chosen to be distinguishable",
        "start_height_tiles": 3,
        "chunks": [
            {"kind": "run", "len": 7},
            {"kind": "stairs", "steps": 3, "step_h": 1, "tread": 2, "dir": "up"},
            {"kind": "slope", "rise": 4, "grade": "steep", "dir": "down"},
            {"kind": "slope", "rise": 4, "grade": "gentle", "dir": "up"},
            {"kind": "hollow", "width": 5, "depth": 1},
            {
                "kind": "hop_chain",
                "count": 3,
                "jump_rise": 2,
                "gap": 4,
                "platform_width": 3,
                "dir": "up",
            },
            {"kind": "perch", "platform_width": 6, "climb_rise": 4, "variant": "iron_ladder"},
            {
                "kind": "tower",
                "storeys": 2,
                "platform_width": 5,
                "climb_rise": 3,
                "variant": "chain",
            },
        ],
    }

    _, errors, spans = expand_chunks(sentence, CHAINED_SHAFT_PROFILE, 256)

    assert errors == []
    widths = {span.kind: span.end - span.start for span in spans if span.kind != "slope"}
    steep, gentle = spans[2], spans[3]
    assert widths["run"] == 7  # len
    assert widths["stairs"] == 3 * 2  # steps*tread
    assert steep.end - steep.start == 4  # rise (steep)
    assert gentle.end - gentle.start == 4 * 2  # rise*2 (gentle)
    assert widths["hollow"] == 5  # width
    assert widths["hop_chain"] == 3 * 3 + 4 * 4  # count*platform_width + (count+1)*gap
    assert widths["perch"] == 6 + 2  # platform_width + 2
    assert widths["tower"] == 5 + 2  # platform_width + 2


def test_a_word_added_to_the_table_reaches_the_vocabulary_the_schema_and_the_widths_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One entry is the whole cost of a word -- and of withholding one from a game.

    The table is the single source, so a word cannot be offered in the prompt while missing from
    the schema, nor be offered without the arithmetic that budgets its columns. This is the claim
    the module's docstring makes; here it is measured, in both directions.
    """

    def chasm_properties(profile: PlatformerProfile) -> dict[str, object]:
        return {"span": {"type": "integer", "minimum": 2}}

    universal = grammar_module._Word(
        "chasm",
        lambda profile: True,
        chasm_properties,
        "  chasm{span}                        a gulf bridged by nothing",
        "span + 1",
    )
    withheld = grammar_module._Word(
        "aqueduct",
        lambda profile: profile is CHAINED_SHAFT_PROFILE,
        chasm_properties,
        "  aqueduct{span}                     a raised channel this game may not have",
        "span * 3",
    )
    monkeypatch.setattr(grammar_module, "_WORDS", (*grammar_module._WORDS, universal, withheld))

    prompt = build_chunk_prompt(GROUND_FOOTED_PROFILE, 128)

    assert vocabulary(GROUND_FOOTED_PROFILE)[-1] == "chasm"
    assert "chasm" in _branches(build_chunk_schema(GROUND_FOOTED_PROFILE))
    assert "  chasm{span}" in prompt
    assert _width_block(prompt)["chasm"] == "span + 1"
    # A word this game cannot build contributes to none of the three.
    assert "aqueduct" not in vocabulary(GROUND_FOOTED_PROFILE)
    assert "aqueduct" not in _branches(build_chunk_schema(GROUND_FOOTED_PROFILE))
    assert "aqueduct" not in prompt
    assert "aqueduct" in _width_block(build_chunk_prompt(CHAINED_SHAFT_PROFILE, 64))
