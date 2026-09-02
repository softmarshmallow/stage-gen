from __future__ import annotations

import re
from pathlib import Path

import pytest

from stage_gen.components._game_input import AuthoredContractLoadError
from stage_gen.components.game_fx import (
    CUT_IN_FRAME_LAYOUT,
    CUT_IN_PORTRAIT_LAYOUT,
    FX_MOMENTS,
    FX_RESERVED_MOMENTS,
    load_game_fx_bytes,
)

PACKAGE = Path(__file__).resolve().parents[3] / "library" / "games" / "iron-petal-unit"


def _source() -> bytes:
    return (PACKAGE / "fx.toml").read_bytes()


def test_canonical_fx_contract_binds_each_moment_to_its_own_portrait() -> None:
    contract = load_game_fx_bytes(_source())

    assert contract.kind == "game-fx-v2"
    assert contract.game_id == "iron-petal-unit"
    assert contract.cut_in is not None
    assert contract.cut_in.frame.mode == "generated_v1"
    assert contract.cut_in.frame.layout == CUT_IN_FRAME_LAYOUT
    assert [entry.portrait_id for entry in contract.cut_in.portraits] == [
        "stage_start",
        "encounter_start",
    ]
    assert contract.cut_in.portraits[0].layout == CUT_IN_PORTRAIT_LAYOUT
    assert contract.moment_names() == ("stage_start", "encounter_start")
    moment = contract.moment("stage_start")
    assert moment is not None
    assert moment.effect == "cut_in"
    assert moment.choreography == "tear_reveal_v1"
    # The document owns plates and bindings; every duration is the consumer's.
    assert "duration" not in contract.model_dump(mode="json")


def test_fx_contract_pins_layouts_and_identity() -> None:
    source = _source()
    with pytest.raises(AuthoredContractLoadError, match="literal_error"):
        load_game_fx_bytes(source.replace(CUT_IN_FRAME_LAYOUT.encode(), b"cut_in_frame_v9"))
    with pytest.raises(AuthoredContractLoadError, match="game-fx-v2"):
        load_game_fx_bytes(source.replace(b'kind = "game-fx-v2"', b'kind = "game-fx-v1"'))


def test_fx_contract_rejects_unknown_and_unused_references() -> None:
    source = _source()
    with pytest.raises(AuthoredContractLoadError, match="unknown IDs"):
        load_game_fx_bytes(source.replace(b'["operator_primary"]', b'["missing_operator"]'))

    unused = source.replace(
        b"[cut_in.frame]",
        b"""[[references]]
reference_id = "unused_style"
source = "references/unused.png"
source_sha256 = "e8d27ab2d83210fe2bf8e4f072588614fbe293de75dae51677a96079f1e9f6a5"
rights_status = "redistribution-approved"
rights_basis = ["Reviewed package evidence."]

[cut_in.frame]""",
    )
    with pytest.raises(AuthoredContractLoadError, match="unused reference IDs"):
        load_game_fx_bytes(unused)


def test_a_moment_must_name_a_declared_portrait_and_every_portrait_must_play() -> None:
    source = _source()
    with pytest.raises(AuthoredContractLoadError, match="unknown cut_in portrait"):
        load_game_fx_bytes(
            source.replace(
                b'portrait_id = "stage_start"\nchoreography', b'portrait_id = "fever"\nchoreography'
            )
        )

    # Only the first binding is displaced: the package now plays two moments,
    # and inserting the orphan twice would trip the uniqueness rule instead.
    orphaned = source.replace(
        b"[[moments]]",
        b"""[[cut_in.portraits]]
portrait_id = "unplayed"
layout = "cut_in_portrait_1536x1024_v1"
alpha_policy = "transparent_exterior_v1"
reference_ids = ["operator_primary"]
prompt = "A quiet look."

[[moments]]""",
        1,
    )
    with pytest.raises(AuthoredContractLoadError, match="no moment plays"):
        load_game_fx_bytes(orphaned)


def test_a_procedural_frame_authors_no_references_and_no_prompt() -> None:
    source = _source()
    with pytest.raises(AuthoredContractLoadError, match="procedural_v1 authors no references"):
        load_game_fx_bytes(source.replace(b'mode = "generated_v1"', b'mode = "procedural_v1"'))

    generated_frame = (
        b'mode = "generated_v1"\n'
        b'layout = "cut_in_frame_1536x1024_v1"\n'
        b'alpha_policy = "transparent_exterior_opaque_body_v1"\n'
        b'reference_ids = ["cover_style"]\n'
        b'prompt = "The cover'
    )
    procedural_frame = (
        b'mode = "procedural_v1"\n'
        b'layout = "cut_in_frame_1536x1024_v1"\n'
        b'alpha_policy = "transparent_exterior_opaque_body_v1"\n'
        b'# prompt = "The cover'
    )
    source = _without_shape(source)
    assert generated_frame in source
    procedural = source.replace(generated_frame, procedural_frame)
    # The cover reference is now unused; drop its whole block so the closure holds.
    cover_block = re.search(
        rb'\[\[references\]\]\nreference_id = "cover_style"\n(?:.+\n)+?\n', procedural
    )
    assert cover_block is not None
    procedural = procedural.replace(cover_block.group(0), b"")
    contract = load_game_fx_bytes(procedural)
    assert contract.cut_in is not None
    assert contract.cut_in.frame.mode == "procedural_v1"
    assert contract.cut_in.frame.prompt is None


def _without_shape(source: bytes) -> bytes:
    """The package authors a frame shape; some rules are about a package that does not."""

    start = source.index(b"shape = ")
    return source[:start] + source[source.index(b"\n", start) + 1 :]


def test_the_authored_shape_is_the_frames_silhouette_and_the_prompt_its_register() -> None:
    contract = load_game_fx_bytes(_source())
    assert contract.cut_in is not None
    shape = contract.cut_in.frame.shape
    assert shape is not None and shape.startswith("One wide shard on a strong diagonal")
    # The silhouette is described by character, never by counts: a countable claim turns the
    # reviewer into a spec checker the image model cannot reliably satisfy.
    assert not any(word in shape for word in ("two or three", "three or four", "half the"))
    assert contract.cut_in.frame.prompt is not None
    assert "print-poster register" in contract.cut_in.frame.prompt
    # A frame with no authored shape falls back to the component's default one.
    bare = load_game_fx_bytes(_without_shape(_source()))
    assert bare.cut_in is not None
    assert bare.cut_in.frame.shape is None


def test_a_portrait_prompt_never_states_an_age() -> None:
    source = _source()
    for phrase in (b"an eleven-year-old child", b"aged 11", b"a cheerful kid", b"12 yr old"):
        aged = source.replace(b"Mira at the instant", phrase + b", Mira at the instant")
        with pytest.raises(AuthoredContractLoadError, match="must not state the subject's age"):
            load_game_fx_bytes(aged)


def test_the_moment_vocabulary_is_closed_and_its_reserve_is_named() -> None:
    assert FX_MOMENTS == ("stage_start", "encounter_start")
    # Promoting a reserved name is a contract bump, so the reserve shrinks by
    # exactly the name that was served.
    assert "encounter_start" not in FX_RESERVED_MOMENTS
    assert "fever_start" in FX_RESERVED_MOMENTS
    with pytest.raises(AuthoredContractLoadError, match="literal_error"):
        load_game_fx_bytes(_source().replace(b'moment = "stage_start"', b'moment = "fever_start"'))
