from __future__ import annotations

import hashlib
import importlib.util
import itertools
import os
import re
import shutil
import sys
import tomllib
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, NoReturn

import pytest

from stage_gen.components.game_map.prepared import MAX_UNASSISTED_TERRAIN_RISE_TILES
from stage_gen.components.platformer_map_design import (
    Climbable,
    DesignedMap,
    PlatformerProfile,
    canonical_platformer_chunk_map_design_json,
)
from stage_gen.orchestration.game_package import (
    GamePackageValidationError,
    validate_game_package,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
#: The shipped, digest-pinned library. This module only ever READS it, and the module-scoped
#: guard below is the proof; every test that exercises `apply` works on `_copy_library`'s copy.
SHIPPED_LIBRARY_ROOT = REPOSITORY_ROOT / "library" / "games"
APPLIED_MAP_ID = "crowncrag-road"
APPLIED_GAME_ID = "bellweather"


def _load_script() -> ModuleType:
    path = REPOSITORY_ROOT / "scripts/design_map.py"
    spec = importlib.util.spec_from_file_location("design_map", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCRIPT = _load_script()
#: The consumer the profile has to keep agreeing with. It is imported through the script's own
#: `sys.path` shim rather than at the top of this file, because this test directory is not a
#: package and the repository root is therefore not on `sys.path` during collection.
AUTHOR_TERRAIN = importlib.import_module("scripts.author_terrain")

PROFILE: PlatformerProfile = SCRIPT.BELLWEATHER_SIDE_VIEW
CLIMBABLE_RISE_TILES: int = AUTHOR_TERRAIN.CLIMBABLE_RISE_TILES
MAX_CLIMBABLE_PLACEMENTS: int = AUTHOR_TERRAIN.MAX_CLIMBABLE_PLACEMENTS
MAX_FRAMED_SURFACE_TILES: int = AUTHOR_TERRAIN.MAX_FRAMED_SURFACE_TILES


# ---------------------------------------------------------------------------------------------
# A throwaway copy of the shipped library. The real one is only ever read.
# ---------------------------------------------------------------------------------------------


def _digests(root: Path) -> dict[str, str]:
    """Every file under `root`, keyed by its relative path. Equality is byte equality."""

    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _copy_library(workspace_root: Path) -> Path:
    """A complete throwaway package. The shipped library is only ever read."""

    library_root = workspace_root / "library" / "games"
    shutil.copytree(SHIPPED_LIBRARY_ROOT, library_root)
    return library_root


@pytest.fixture(scope="module", autouse=True)
def _the_shipped_library_is_only_ever_read() -> Iterator[None]:
    """No test in this module may write the digest-pinned library it copies.

    `apply` rewrites three committed, digest-pinned documents in place. A test that aimed it at
    the repository's own `library/games` would not fail loudly; it would corrupt the shipped
    package and re-lock both digests over the damage, which is exactly the defect this module
    exists to pin. Snapshotting the real tree around the whole module makes that impossible to do
    accidentally, including through a helper that forgets to copy first.
    """

    before = _digests(SHIPPED_LIBRARY_ROOT)
    assert before, f"no shipped library at {SHIPPED_LIBRARY_ROOT}; every copy fixture is vacuous"
    yield
    assert _digests(SHIPPED_LIBRARY_ROOT) == before, "a test wrote to the real shipped library"


# ---------------------------------------------------------------------------------------------
# The consumer contract the profile is supposed to restate
# ---------------------------------------------------------------------------------------------


def test_the_bellweather_profile_restates_the_consumers_own_traversal_constants() -> None:
    """The whole point of the profile: the designer's idea of the game cannot drift from it.

    Every number here is imported from the consumer that will actually build the map. If
    `author_terrain` or the prepared map contract retunes one of them and the profile keeps the
    old value, the designer starts composing maps the game cannot express, and nothing else in
    the pipeline would notice until a level failed in the browser.
    """

    assert PROFILE.movement.max_step_up_tiles == MAX_UNASSISTED_TERRAIN_RISE_TILES
    assert PROFILE.movement.climbable_rise_tiles == (CLIMBABLE_RISE_TILES,)
    assert PROFILE.climbable_count[1] == MAX_CLIMBABLE_PLACEMENTS
    assert PROFILE.geometry.max_walkable_height_tiles == MAX_FRAMED_SURFACE_TILES


def test_the_profile_pins_the_jump_arc_measured_off_the_typescript_runtime() -> None:
    """The two traversal constants no Python import can defend, pinned by hand.

    Every number in the test above is imported from the Python consumer that will build the map,
    so a retune there fails on its own. `jump_reach` and `level_gap_tiles` have no Python source
    at all: they are measured off the player's own jump arc in `web/lib/runtime/player.ts` -- the
    source of truth -- and then transcribed into the profile. `jump_reach` is the most
    load-bearing of the lot, because the grammar builds the hop-chain schema straight out of it,
    so a retune of the runtime's jump velocity, gravity, or run speed that nobody transcribes has
    to fail here rather than as an uncrossable gap in a browser.
    """

    movement = PROFILE.movement
    assert movement.jump_reach == {1: 8, 2: 6}
    assert movement.level_gap_tiles == 8

    # The same two numbers restated as the rule the grammar actually applies, so a change that
    # kept the mapping but moved its meaning is caught as well.
    assert movement.reachable(1, 8) is True
    assert movement.reachable(1, 9) is False
    assert movement.reachable(2, 6) is True
    assert movement.reachable(2, 7) is False
    # Nothing above a two-tile rise is jumpable at any gap; that is what a climbable is for.
    assert movement.reachable(3, 0) is False
    assert movement.max_jumpable_rise == 2
    # A level or downward move is bounded too. Treating one as free at any gap is what silently
    # connects two surfaces a whole screen apart.
    assert movement.reachable(0, 8) is True
    assert movement.reachable(0, 9) is False
    assert movement.reachable(-4, 9) is False


def test_the_profile_geometry_is_the_shipped_maps_own_grid(tmp_path: Path) -> None:
    """The profile targets one shipped map, so it drifts the moment that map is a different size.

    Both dimensions are read out of the map document rather than restated here, so resizing the
    shipped matrix without moving the profile fails at this assertion. That pairing is the whole
    safety of `apply`: every normalized coordinate already in the document -- portal endpoints,
    parallax placement -- is expressed against the shipped grid, and a profile one column wider
    would compile a plan that silently moves all of them.
    """

    library_root = _copy_library(tmp_path)
    map_path = library_root / APPLIED_GAME_ID / "maps" / f"{APPLIED_MAP_ID}.toml"
    document = tomllib.loads(map_path.read_text(encoding="utf-8"))
    occupancy = [str(row) for row in document["ground"]["occupancy"]]
    widths = {len(row) for row in occupancy}

    assert len(widths) == 1, f"the shipped occupancy matrix is ragged: {sorted(widths)} wide"
    assert (PROFILE.geometry.rows, PROFILE.geometry.columns) == (len(occupancy), widths.pop())
    # An empty or single-row matrix would satisfy the equality above without meaning anything.
    assert PROFILE.geometry.rows > 1
    assert PROFILE.geometry.columns > 1
    # The framing budget is a bound inside the grid, not the grid itself.
    assert PROFILE.geometry.max_walkable_height_tiles < PROFILE.geometry.rows


def test_the_bellweather_profile_gates_the_biome_channel_off_end_to_end() -> None:
    """game-map-v7 has no per-region style surface, so no column may carry a biome tag."""

    assert PROFILE.biomes == ()
    assert PROFILE.biome_min_span_tiles == 0

    designed, problems = SCRIPT.expand(SCRIPT.example_design(), PROFILE)
    assert problems == []
    assert designed.column_biomes is None


# ---------------------------------------------------------------------------------------------
# The adapter: designed map -> authored level plan
# ---------------------------------------------------------------------------------------------


def _grid(heights: list[int], rows: int, platforms: tuple[tuple[int, int, int], ...]) -> list[str]:
    """Bottom-row-first symbol grid, built the way the grammar's expander builds one."""

    ground = PROFILE.ground_role.symbol
    empty = PROFILE.empty_role.symbol
    platform = PROFILE.platform_roles[0].symbol
    cells = [
        [ground if heights[column] >= height else empty for column in range(len(heights))]
        for height in range(1, rows + 1)
    ]
    for start_column, end_column, height in platforms:
        for column in range(start_column, end_column):
            if heights[column] < height:
                cells[height - 1][column] = platform
    return ["".join(row) for row in cells]


def _designed(
    heights: list[int],
    *,
    rows: int = 8,
    platforms: tuple[tuple[int, int, int], ...] = (),
    climbables: tuple[Climbable, ...] = (),
) -> DesignedMap:
    return DesignedMap(
        PROFILE.profile_id,
        len(heights),
        rows,
        _grid(heights, rows, platforms),
        list(climbables),
    )


def _example_plan() -> Any:
    designed, problems = SCRIPT.expand(SCRIPT.example_design(), PROFILE)
    assert problems == []
    return SCRIPT.to_level_plan(designed, PROFILE, APPLIED_MAP_ID)


def test_the_example_design_compiles_to_an_occupancy_matching_the_designed_grid() -> None:
    designed, _ = SCRIPT.expand(SCRIPT.example_design(), PROFILE)
    plan = SCRIPT.to_level_plan(designed, PROFILE, APPLIED_MAP_ID)
    occupancy = plan.occupancy()

    assert plan.columns == PROFILE.geometry.columns
    assert plan.rows == PROFILE.geometry.rows
    assert len(occupancy) == PROFILE.geometry.rows
    assert {len(row) for row in occupancy} == {PROFILE.geometry.columns}
    assert set("".join(occupancy)) == {"0", "1"}
    # The shallowest floor is three tiles, so the bottom three rows are solid all the way across.
    assert occupancy[-3:] == ["1" * PROFILE.geometry.columns] * 3

    # Re-derive the grid independently: occupancy row 0 is the TOP row, the design's grid index 0
    # is the BOTTOM row, and every non-empty symbol is an occupied cell.
    empty = PROFILE.empty_role.symbol
    expected = [
        "".join("0" if symbol == empty else "1" for symbol in designed.grid[height - 1])
        for height in range(designed.rows, 0, -1)
    ]
    assert occupancy == expected


def test_the_compiled_level_plan_pins_the_walk_surface_to_the_lowest_starting_floor() -> None:
    plan = _example_plan()

    # The left edge is also the lowest ground on this route, so both readings of the walk
    # surface agree; the plan is only well-formed while they do.
    assert plan.ground_heights[0] == min(plan.ground_heights)
    assert plan.walk_surface_row == plan.rows - min(plan.ground_heights)
    assert plan.walk_surface_row == plan.rows - plan.ground_heights[0]


def test_the_compiled_level_plan_satisfies_the_authored_terrain_contract() -> None:
    """The adapter's output is judged by the consumer's own validator, not by the designer's."""

    assert AUTHOR_TERRAIN.validate(_example_plan()) == []


def test_the_adapter_refuses_a_hole_no_authored_ground_height_can_express() -> None:
    heights = [3] * 12
    heights[5] = 0

    with pytest.raises(SCRIPT.MapAdapterError) as raised:
        SCRIPT.to_level_plan(_designed(heights), PROFILE, APPLIED_MAP_ID)

    assert "column 5 has no ground tile" in str(raised.value)
    assert "ground_heights must be at least 1 everywhere" in str(raised.value)


def test_the_adapter_refuses_a_platform_more_than_one_row_thick() -> None:
    designed = _designed([3] * 16, platforms=((4, 8, 4), (4, 8, 5)))

    with pytest.raises(SCRIPT.MapAdapterError) as raised:
        SCRIPT.to_level_plan(designed, PROFILE, APPLIED_MAP_ID)

    assert re.search(
        r"platform s-h5-c4 is more than one row thick at column\(s\) \[4, 5, 6, 7\]",
        str(raised.value),
    )
    assert "an authored ledge is exactly one occupied row" in str(raised.value)


def test_the_adapter_refuses_a_climbable_whose_rise_is_not_the_authored_span() -> None:
    rise = CLIMBABLE_RISE_TILES - 1
    designed = _designed(
        [3] * 16,
        platforms=((4, 10, 3 + rise),),
        climbables=(Climbable("c9", "bellroot_ladder", 6, rise, 3),),
    )

    with pytest.raises(SCRIPT.MapAdapterError) as raised:
        SCRIPT.to_level_plan(designed, PROFILE, APPLIED_MAP_ID)

    assert f"climbable c9 rises {rise} tiles" in str(raised.value)
    assert f"every authored placement spans exactly {CLIMBABLE_RISE_TILES}" in str(raised.value)


# ---------------------------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------------------------


def _write_design(
    path: Path, *, chunks: list[dict[str, object]], start_height_tiles: int = 3
) -> Path:
    design = SCRIPT.persisted_design(
        profile=PROFILE,
        start_height_tiles=start_height_tiles,
        design_notes="a fixture sentence",
        chunks=chunks,
        brief="offline fixture",
    )
    path.write_bytes(canonical_platformer_chunk_map_design_json(design))
    return path


def test_check_accepts_the_canned_example(capsys: pytest.CaptureFixture[str]) -> None:
    assert SCRIPT.main(["check", "--example"]) == 0

    captured = capsys.readouterr()
    assert "design satisfies every rule" in captured.out
    assert "REJECTED" not in captured.out


def test_check_rejects_a_sentence_wider_than_the_grid(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    over_wide = PROFILE.geometry.columns + 40
    design_path = _write_design(
        tmp_path / "too-wide.json", chunks=[{"kind": "run", "len": over_wide}]
    )

    assert SCRIPT.main(["check", "--design", str(design_path)]) == 1

    captured = capsys.readouterr()
    assert "REJECTED" in captured.out
    assert f"the chunks total {over_wide} columns of {PROFILE.geometry.columns}" in captured.out


# ---------------------------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------------------------


def test_render_writes_a_diagnostic_png(tmp_path: Path) -> None:
    out = tmp_path / "diagnostics" / "crowncrag.png"

    assert SCRIPT.main(["render", "--example", "--out", str(out)]) == 0

    assert out.is_file()
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_refuses_to_write_published_media_under_docs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "docs" / "crowncrag.png"

    assert SCRIPT.main(["render", "--example", "--out", str(out)]) == 1

    assert not out.exists()
    assert "refusing to write" in capsys.readouterr().out


# ---------------------------------------------------------------------------------------------
# design: the only live subcommand, behind a double opt-in
# ---------------------------------------------------------------------------------------------


def _forbidden_provider_call(*args: object, **kwargs: object) -> object:
    raise AssertionError("design reached the provider service without both live opt-ins")


@pytest.mark.parametrize(
    ("live_flag", "environment_value"),
    [(False, None), (True, None), (False, "1")],
    ids=["no-flag-no-environment", "flag-without-environment", "environment-without-flag"],
)
def test_design_without_both_live_opt_ins_never_reaches_a_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    live_flag: bool,
    environment_value: str | None,
) -> None:
    """The gate has to close before a service exists, not before a request is sent."""

    if environment_value is None:
        monkeypatch.delenv(SCRIPT.LIVE_ENVIRONMENT_FLAG, raising=False)
    else:
        monkeypatch.setenv(SCRIPT.LIVE_ENVIRONMENT_FLAG, environment_value)
    monkeypatch.setattr(SCRIPT, "_design_samples", _forbidden_provider_call)
    out = tmp_path / "composed.json"
    argv = ["design", "--brief", "a rising pilgrim road", "--out", str(out)]
    if live_flag:
        argv.append("--live")

    assert SCRIPT.main(argv) == 1

    assert not out.exists()
    assert list(tmp_path.iterdir()) == []
    assert "No provider call was made." in capsys.readouterr().out


# ---------------------------------------------------------------------------------------------
# apply: text surgery on a temporary copy of the library, never the real one
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class AppliedPackage:
    """One `apply` run against a throwaway copy, plus the documents as they were before it."""

    workspace_root: Path
    library_root: Path
    map_path: Path
    game_path: Path
    selector_path: Path
    map_before: str
    game_before: str
    selector_before: str

    @property
    def map_after(self) -> str:
        return self.map_path.read_text(encoding="utf-8")

    @property
    def game_after(self) -> str:
        return self.game_path.read_text(encoding="utf-8")

    @property
    def selector_after(self) -> str:
        return self.selector_path.read_text(encoding="utf-8")

    def document_bytes(self) -> dict[str, bytes]:
        """The exact bytes of the three documents `apply` rewrites as one digest chain.

        Bytes rather than parsed values or a digest: a refusal or a rollback has to leave the
        committed source byte-identical, including whitespace, comment placement, and trailing
        newline, and only raw bytes say that.
        """

        return {
            "map": self.map_path.read_bytes(),
            "game.toml": self.game_path.read_bytes(),
            "main.toml": self.selector_path.read_bytes(),
        }


def _target(workspace_root: Path) -> AppliedPackage:
    library_root = _copy_library(workspace_root)
    package = library_root / APPLIED_GAME_ID
    map_path = package / "maps" / f"{APPLIED_MAP_ID}.toml"
    game_path = package / "game.toml"
    selector_path = library_root / "main.toml"
    return AppliedPackage(
        workspace_root=workspace_root,
        library_root=library_root,
        map_path=map_path,
        game_path=game_path,
        selector_path=selector_path,
        map_before=map_path.read_text(encoding="utf-8"),
        game_before=game_path.read_text(encoding="utf-8"),
        selector_before=selector_path.read_text(encoding="utf-8"),
    )


@pytest.fixture(scope="module")
def applied(tmp_path_factory: pytest.TempPathFactory) -> AppliedPackage:
    target = _target(tmp_path_factory.mktemp("applied"))
    assert (
        SCRIPT.main(
            [
                "apply",
                "--example",
                "--map-id",
                APPLIED_MAP_ID,
                "--library-root",
                str(target.library_root),
            ]
        )
        == 0
    )
    return target


def _section(text: str, start: str, end: str) -> str:
    return text[text.index(start) : text.index(end)]


def test_apply_rewrites_the_map_with_the_compiled_terrain_and_placements(
    applied: AppliedPackage,
) -> None:
    plan = _example_plan()
    document = tomllib.loads(applied.map_after)
    shipped = tomllib.loads(applied.map_before)

    # The rewrite is real: neither the terrain nor the placements are what shipped.
    assert document["ground"]["occupancy"] != shipped["ground"]["occupancy"]
    assert len(document["climbable"]["placements"]) == 3
    assert len(shipped["climbable"]["placements"]) == 4

    assert document["ground"]["occupancy"] == plan.occupancy()
    assert document["ground"]["walk_surface_row"] == plan.walk_surface_row
    assert [entry["climbable_id"] for entry in document["climbable"]["placements"]] == [
        climb.climbable_id for climb in plan.climbs
    ]
    assert [entry["variant_id"] for entry in document["climbable"]["placements"]] == [
        climb.variant_id for climb in plan.climbs
    ]
    assert {entry["rise_tiles"] for entry in document["climbable"]["placements"]} == {
        CLIMBABLE_RISE_TILES
    }


def test_apply_bumps_the_map_revision(applied: AppliedPackage) -> None:
    before = tomllib.loads(applied.map_before)
    after = tomllib.loads(applied.map_after)

    assert after["revision"] == before["revision"] + 1
    assert after["map_id"] == before["map_id"]
    assert after["schema_version"] == before["schema_version"]


def test_apply_relocks_both_digests_so_the_package_still_validates(
    applied: AppliedPackage,
) -> None:
    map_digest = hashlib.sha256(applied.map_path.read_bytes()).hexdigest()
    game_digest = hashlib.sha256(applied.game_path.read_bytes()).hexdigest()
    game = tomllib.loads(applied.game_after)
    sources = {entry["map_id"]: entry for entry in game["maps"]}

    assert sources[APPLIED_MAP_ID]["source_sha256"] == map_digest
    assert tomllib.loads(applied.selector_after)["package_sha256"] == game_digest
    # Both links of the chain actually moved; a re-lock that wrote the shipped digests back
    # would satisfy the two equalities above and nothing else.
    assert map_digest != hashlib.sha256(applied.map_before.encode("utf-8")).hexdigest()
    assert game_digest != hashlib.sha256(applied.game_before.encode("utf-8")).hexdigest()

    # The digest of the map that was NOT rewritten must survive: the surgery is anchored on the
    # map's own id, not on its position in the `[[maps]]` array.
    before_sources = {
        entry["map_id"]: entry for entry in tomllib.loads(applied.game_before)["maps"]
    }
    untouched = set(before_sources) - {APPLIED_MAP_ID}
    assert untouched
    for map_id in untouched:
        assert sources[map_id] == before_sources[map_id]

    report = validate_game_package(applied.workspace_root)
    map_ids = report["map_ids"]
    assert report["valid"] is True
    assert report["game_id"] == APPLIED_GAME_ID
    assert isinstance(map_ids, list)
    assert APPLIED_MAP_ID in map_ids


def test_apply_leaves_every_authored_table_it_does_not_own_byte_for_byte(
    applied: AppliedPackage,
) -> None:
    before, after = applied.map_before, applied.map_after
    # Guard against a vacuous pass: everything below only means something because the surgery
    # did change the document.
    assert after != before

    # The whole `[portal]` table, including its endpoints, is the tail of the document.
    assert after[after.index("[portal]") :] == before[before.index("[portal]") :]
    # References and every parallax layer, with their prompts and provenance digests.
    assert _section(after, "[[references]]", "[ground]") == _section(
        before, "[[references]]", "[ground]"
    )
    # The climbable atlas prompts and the comment above the compiled placements.
    assert _section(after, "[climbable]\n", "[[climbable.placements]]") == _section(
        before, "[climbable]\n", "[[climbable.placements]]"
    )
    # Inside `[ground]`, only `occupancy` and `walk_surface_row` may move.
    ground_before = tomllib.loads(before)["ground"]
    ground_after = tomllib.loads(after)["ground"]
    moved = {"occupancy", "walk_surface_row"}
    assert {key: value for key, value in ground_after.items() if key not in moved} == {
        key: value for key, value in ground_before.items() if key not in moved
    }


def test_apply_dry_run_writes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = _target(tmp_path)
    before = _digests(target.library_root)
    revision = int(tomllib.loads(target.map_before)["revision"])

    assert (
        SCRIPT.main(
            [
                "apply",
                "--example",
                "--map-id",
                APPLIED_MAP_ID,
                "--library-root",
                str(target.library_root),
                "--dry-run",
            ]
        )
        == 0
    )

    assert _digests(target.library_root) == before
    captured = capsys.readouterr()
    assert "--dry-run: nothing was written" in captured.out
    assert f"-revision = {revision}" in captured.out
    assert f"+revision = {revision + 1}" in captured.out


# ---------------------------------------------------------------------------------------------
# apply must never resize a map, and must never leave the digest chain half-written
# ---------------------------------------------------------------------------------------------


def _wide_design(path: Path, columns: int) -> Path:
    """A hand-written sentence that declares a grid its own profile does not have."""

    design = SCRIPT.persisted_design(
        profile=PROFILE,
        start_height_tiles=3,
        design_notes="a sentence that claims a wider grid than the profile",
        chunks=[{"kind": "run", "len": columns}],
        brief="offline fixture",
    ).model_copy(update={"columns": columns})
    path.write_bytes(canonical_platformer_chunk_map_design_json(design))
    return path


def test_expand_raises_rather_than_reporting_a_design_that_resizes_the_grid(
    tmp_path: Path,
) -> None:
    """The width disagreement is a raise, not a collected problem, so no caller can print past it.

    `expand` returns its findings as a list that `check` prints and `apply` counts. A design that
    claims a different grid never reaches that list: it would expand onto a grid no map in this
    game has, so it is refused before a single chunk is placed.
    """

    design = SCRIPT.load_design(_wide_design(tmp_path / "wide.json", 200))

    with pytest.raises(SCRIPT.MapAdapterError) as raised:
        SCRIPT.expand(design, PROFILE)

    assert "design declares 200 columns" in str(raised.value)
    assert f"is {PROFILE.geometry.columns} columns wide" in str(raised.value)
    assert "a design may not resize the grid" in str(raised.value)


def test_check_refuses_a_design_that_declares_a_grid_the_profile_does_not_have(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`columns` records the width a sentence was composed against; it is not the designer's."""

    design_path = _wide_design(tmp_path / "wide.json", 200)

    assert SCRIPT.main(["check", "--design", str(design_path)]) == 1

    captured = capsys.readouterr()
    assert "design declares 200 columns" in captured.out
    assert f"is {PROFILE.geometry.columns} columns wide" in captured.out


def test_apply_refuses_a_design_that_would_resize_the_shipped_map(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same guard as the test above, at the only point where it could corrupt something.

    This is the regression pin for the defect itself: the identical 200-column sentence, applied
    to a copy of the shipped 96-column map, silently rewrote the occupancy matrix to the wider
    grid and then re-locked both digests over the result, so the package still validated and
    nothing downstream could tell. The refusal has to leave the digest chain untouched to the
    byte, not merely leave it consistent.
    """

    target = _target(tmp_path)
    before_documents = target.document_bytes()
    before_tree = _digests(target.library_root)
    design_path = _wide_design(tmp_path / "wide.json", 200)

    assert (
        SCRIPT.main(
            [
                "apply",
                "--design",
                str(design_path),
                "--map-id",
                APPLIED_MAP_ID,
                "--library-root",
                str(target.library_root),
            ]
        )
        == 1
    )

    # The map, its game.toml, and main.toml are byte-for-byte what they were.
    assert target.document_bytes() == before_documents
    # And so is every other file in the package; nothing was written anywhere.
    assert _digests(target.library_root) == before_tree
    # Stated as the corruption: the shipped matrix is still its own width, not the design's.
    occupancy = [str(row) for row in tomllib.loads(target.map_after)["ground"]["occupancy"]]
    assert {len(row) for row in occupancy} == {PROFILE.geometry.columns}
    assert len(occupancy) == PROFILE.geometry.rows
    assert "design declares 200 columns" in capsys.readouterr().out


def test_apply_refuses_a_plan_that_is_not_the_shape_of_the_map_it_rewrites(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The plan is checked against the shipped matrix, not only against the profile.

    Every normalized coordinate already in the document -- portal endpoints, parallax placement --
    is expressed against the shipped grid, so a resize would silently move all of them and then
    pin the result with a fresh pair of digests.
    """

    narrowed_columns = PROFILE.geometry.columns - 6
    target = _target(tmp_path)
    narrowed = re.sub(
        r'^  "([01]+)",$',
        lambda match: f'  "{match.group(1)[:narrowed_columns]}",',
        target.map_before,
        flags=re.MULTILINE,
    )
    target.map_path.write_text(narrowed, encoding="utf-8")
    before_documents = target.document_bytes()
    before_tree = _digests(target.library_root)

    assert (
        SCRIPT.main(
            [
                "apply",
                "--example",
                "--map-id",
                APPLIED_MAP_ID,
                "--library-root",
                str(target.library_root),
            ]
        )
        == 1
    )

    assert target.document_bytes() == before_documents
    assert _digests(target.library_root) == before_tree
    captured = capsys.readouterr()
    assert (
        f"the compiled plan is {PROFILE.geometry.rows} rows x {PROFILE.geometry.columns} columns"
        in captured.out
    )
    assert f"is {PROFILE.geometry.rows} rows x {narrowed_columns} columns" in captured.out


def test_apply_restores_all_three_documents_when_the_package_stops_resolving(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The three files are one digest chain, so a post-write failure may not leave two of them."""

    target = _target(tmp_path)
    # Corrupt the digest of the map `apply` does not re-lock, so the package resolves only after
    # every write has already landed.
    target.game_path.write_text(
        re.sub(
            r'(map_id = "sunpetal-crossing"\nsource = "[^"\n]+"\nsource_sha256 = ")[a-f0-9]{64}(")',
            lambda match: f"{match.group(1)}{'0' * 64}{match.group(2)}",
            target.game_before,
            count=1,
        ),
        encoding="utf-8",
    )
    before_documents = target.document_bytes()
    before_tree = _digests(target.library_root)

    assert (
        SCRIPT.main(
            [
                "apply",
                "--example",
                "--map-id",
                APPLIED_MAP_ID,
                "--library-root",
                str(target.library_root),
            ]
        )
        == 1
    )

    assert target.document_bytes() == before_documents
    assert _digests(target.library_root) == before_tree
    captured = capsys.readouterr()
    assert "package no longer resolves after the rewrite" in captured.out
    assert "restored to its pre-apply bytes" in captured.out


def test_apply_restores_all_three_documents_when_the_validation_step_itself_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same rollback, driven by failing the validation step rather than the fixture data.

    The failure is injected into `resolve_game_package`, which `apply` calls only after all three
    writes have landed, and the injected failure reads the documents back before raising. Without
    that reading the test would still pass if `apply` had written nothing at all, which is the
    one way a rollback test goes quietly vacuous.
    """

    target = _target(tmp_path)
    before_documents = target.document_bytes()
    before_tree = _digests(target.library_root)
    mid_apply: list[dict[str, bytes]] = []

    def failing_resolution(package_dir: Path) -> NoReturn:
        mid_apply.append(target.document_bytes())
        raise GamePackageValidationError("invalid_package", "synthetic post-write failure")

    monkeypatch.setattr(SCRIPT, "resolve_game_package", failing_resolution)

    assert (
        SCRIPT.main(
            [
                "apply",
                "--example",
                "--map-id",
                APPLIED_MAP_ID,
                "--library-root",
                str(target.library_root),
            ]
        )
        == 1
    )

    # All three writes had landed when the failure was injected...
    assert len(mid_apply) == 1
    assert mid_apply[0]["map"] != before_documents["map"]
    assert mid_apply[0]["game.toml"] != before_documents["game.toml"]
    assert mid_apply[0]["main.toml"] != before_documents["main.toml"]
    # ...and every one of them is back to the exact bytes it was read with.
    assert target.document_bytes() == before_documents
    assert _digests(target.library_root) == before_tree
    captured = capsys.readouterr()
    assert "package no longer resolves after the rewrite: invalid_package" in captured.out
    assert "restored to its pre-apply bytes" in captured.out


def test_apply_restores_all_three_documents_when_the_rewritten_digest_chain_disagrees(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A resolution that succeeds while reporting a digest nobody just wrote is still a break.

    This is the other half of the post-write check, and the failure arrives as a `MapSurgeryError`
    rather than a package rejection, so it takes the catch-all restore path on its way out. The
    documents still have to come back, and the command still has to report failure.
    """

    class _ForeignDigest:
        """Stands in for a package whose resolved digest is not the one just committed."""

        package_sha256 = "0" * 64

    def resolving_to_a_foreign_digest(package_dir: Path) -> _ForeignDigest:
        return _ForeignDigest()

    target = _target(tmp_path)
    before_documents = target.document_bytes()
    before_tree = _digests(target.library_root)
    monkeypatch.setattr(SCRIPT, "resolve_game_package", resolving_to_a_foreign_digest)

    assert (
        SCRIPT.main(
            [
                "apply",
                "--example",
                "--map-id",
                APPLIED_MAP_ID,
                "--library-root",
                str(target.library_root),
            ]
        )
        == 1
    )

    assert target.document_bytes() == before_documents
    assert _digests(target.library_root) == before_tree
    captured = capsys.readouterr()
    assert "package digest chain is inconsistent after the rewrite" in captured.out
    assert "restored to its pre-apply bytes" in captured.out


def test_apply_restores_the_documents_it_already_wrote_when_it_is_interrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An interrupt between two of the three writes is exactly as damaging as an exception."""

    target = _target(tmp_path)
    before_documents = target.document_bytes()
    before_tree = _digests(target.library_root)
    real_write_text = Path.write_text
    calls = itertools.count(1)

    def interrupted(self: Path, *args: Any, **kwargs: Any) -> int:
        if next(calls) == 2:
            raise KeyboardInterrupt
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", interrupted)

    with pytest.raises(KeyboardInterrupt):
        SCRIPT.main(
            [
                "apply",
                "--example",
                "--map-id",
                APPLIED_MAP_ID,
                "--library-root",
                str(target.library_root),
            ]
        )

    monkeypatch.undo()
    assert target.document_bytes() == before_documents
    assert _digests(target.library_root) == before_tree


_APPLY_ARGUMENTS = ("apply", "--example", "--map-id", APPLIED_MAP_ID, "--library-root")


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores the read-only bit this probe needs")
def test_apply_reports_a_refused_write_as_itself_and_not_as_a_broken_package(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A write the filesystem refused outright leaves the package untouched, and must say so.

    `main.toml` is the third and last of the three writes, so the map and its `game.toml` land
    before the refusal and there is a real rollback to perform -- but `main.toml` itself was never
    written, and `Path.write_text` that fails at the open has not touched a byte of it.

    The rollback used to rewrite all three paths unconditionally, so restoring the read-only file
    it had never written failed, and that manufactured failure was reported as `this package's
    digest chain is broken and needs a manual checkout`. Every file on disk was byte-identical to
    the pristine library at the time. An operator told to go do a manual checkout over an intact
    package is worse off than one told nothing.
    """

    target = _target(tmp_path)
    before_documents = target.document_bytes()
    before_tree = _digests(target.library_root)
    target.selector_path.chmod(0o444)
    try:
        assert SCRIPT.main([*_APPLY_ARGUMENTS, str(target.library_root)]) == 1
    finally:
        target.selector_path.chmod(0o644)

    # The package really is intact: not "resolves again", but the same bytes it was copied with.
    assert target.document_bytes() == before_documents
    assert _digests(target.library_root) == before_tree

    captured = capsys.readouterr()
    # The real cause reaches the operator. It used to be raised over and never printed at all.
    assert "writing the rewritten documents failed" in captured.out
    assert "Permission denied" in captured.out
    # `apply` resolves its own `--library-root`, so the path it prints is the resolved one.
    assert str(target.selector_path.resolve()) in captured.out
    # ...and nothing claims damage that did not happen.
    assert "digest chain is broken" not in captured.out
    assert "manual checkout" not in captured.out
    assert "restored to its pre-apply bytes" in captured.out


def test_apply_reports_the_real_cause_even_when_the_rollback_cannot_finish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """When the chain really is broken, the reason it broke still has to be printed.

    The failure is arranged so that both halves are true at once: `game.toml` cannot be written, so
    the apply aborts, and the map that was already written cannot be put back, so the package is
    genuinely half-rewritten. The broken-chain report is correct here -- but it used to be raised
    as a `MapSurgeryError` from inside the `OSError` handler, ahead of the `print` naming the
    cause, so the operator was handed a manual checkout with no reason attached to it.
    """

    target = _target(tmp_path)
    before_documents = target.document_bytes()
    real_write_text = Path.write_text
    calls: Counter[str] = Counter()

    def failing(self: Path, *args: Any, **kwargs: Any) -> int:
        # Keyed on the file name, not on the Path: `apply` resolves its own `--library-root`, so
        # the objects it writes need not compare equal to this test's under a symlinked tmp_path.
        calls[self.name] += 1
        if self.name == "game.toml":
            raise PermissionError("synthetic refusal writing game.toml")
        if self.name == f"{APPLIED_MAP_ID}.toml" and calls[self.name] == 2:
            raise PermissionError("synthetic refusal restoring the map")
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", failing)
    assert SCRIPT.main([*_APPLY_ARGUMENTS, str(target.library_root)]) == 1
    monkeypatch.undo()

    # The map was written and could not be put back; the other two were never written at all.
    documents = target.document_bytes()
    assert documents["map"] != before_documents["map"]
    assert documents["game.toml"] == before_documents["game.toml"]
    assert documents["main.toml"] == before_documents["main.toml"]

    captured = capsys.readouterr()
    assert "writing the rewritten documents failed" in captured.out
    assert "synthetic refusal writing game.toml" in captured.out
    assert "digest chain is broken and needs a manual checkout" in captured.out
    # Only the document that was written and stayed unrestored is named as damage.
    assert f"{APPLIED_MAP_ID}.toml: synthetic refusal restoring the map" in captured.out
    assert "main.toml" not in captured.out


def test_an_interrupt_propagates_as_itself_even_when_a_document_cannot_be_put_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Ctrl-C is the operator's own signal and may never come back as a surgery error.

    `test_apply_restores_the_documents_it_already_wrote_when_it_is_interrupted` covers the
    interrupt whose rollback succeeds. This is the edge the rollback used to swallow: it raised
    `MapSurgeryError` from inside the `BaseException` handler, ahead of the bare re-raise, so an
    interrupt whose restore also failed surfaced as a value error -- caught by `main`, printed, and
    flattened into an ordinary exit code. Ctrl-C stopped stopping the program.
    """

    target = _target(tmp_path)
    before_documents = target.document_bytes()
    real_write_text = Path.write_text
    calls: Counter[str] = Counter()

    def interrupted(self: Path, *args: Any, **kwargs: Any) -> int:
        calls[self.name] += 1
        if self.name == "game.toml" and calls[self.name] == 1:
            # The interrupt lands after the map is written and before game.toml is...
            raise KeyboardInterrupt
        if self.name == f"{APPLIED_MAP_ID}.toml" and calls[self.name] == 2:
            # ...and the one document that was written cannot be put back.
            raise PermissionError("synthetic refusal restoring the map")
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", interrupted)
    with pytest.raises(KeyboardInterrupt):
        SCRIPT.main([*_APPLY_ARGUMENTS, str(target.library_root)])
    monkeypatch.undo()

    # The restore was attempted and reported honestly; only the report was ever in question.
    captured = capsys.readouterr()
    assert "digest chain is broken and needs a manual checkout" in captured.out
    documents = target.document_bytes()
    assert documents["map"] != before_documents["map"]
    assert documents["game.toml"] == before_documents["game.toml"]
    assert documents["main.toml"] == before_documents["main.toml"]


def test_apply_has_no_default_library_root(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The caller always names the target; the shipped library is never one by omission.

    `--library-root` used to default to the repository's own `library/games`, so an `apply` that
    named no target rewrote digest-pinned committed source in place. Omitting it now has to be an
    argparse error, refused before any handler runs.

    `run_apply` is stubbed out first, and that is not decoration. `build_parser` binds the handler
    by reading the module global, so the stub is what a parse would dispatch to. Without it, this
    test reproduces the defect instead of detecting it: the moment a default came back, the real
    `run_apply` would rewrite and re-lock the repository's own library, and the failure the test
    then reported would be damage it had already done. `reached` is the assertion that carries the
    meaning; the exit code only says how the refusal was spelled.
    """

    reached: list[object] = []

    def refuse_to_apply(args: object) -> int:
        reached.append(args)
        return 1

    monkeypatch.setattr(SCRIPT, "run_apply", refuse_to_apply)
    shipped_before = _digests(SHIPPED_LIBRARY_ROOT)

    with pytest.raises(SystemExit) as raised:
        SCRIPT.main(["apply", "--example", "--map-id", APPLIED_MAP_ID])

    # Nothing was dispatched: argparse refused the invocation, it did not supply a target for it.
    assert reached == []
    assert raised.value.code == 2
    captured = capsys.readouterr()
    assert "the following arguments are required: --library-root" in captured.err
    assert captured.out == ""
    assert _digests(SHIPPED_LIBRARY_ROOT) == shipped_before
