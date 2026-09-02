"""`case.json`: the join between authored members and generated runs.

The authored case names `scenarios/e1_office.toml`; the consumer plays
`out/the-grain-scene-01`. Neither side can derive the other - a run tag does not
exist until its leaf has been generated - so the mapping is supplied once, here,
and checked as a set equality in both directions like every other closure.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stage_gen.orchestration.case_binding import bind_case
from stage_gen.orchestration.case_bundle import (
    CaseBundleError,
    build_case_runtime,
    publish_case,
)
from tests.unit.components.case.package import write_case_package

RUN_TAGS = {
    "b_office": "the-grain-office",
    "b_motor_court": "the-grain-motor-court",
    "b_statements": "the-grain-statements",
}


def _with_runs(tmp_path: Path) -> tuple[Path, Path]:
    package = tmp_path / "package"
    package.mkdir()
    write_case_package(package)
    runs = tmp_path / "out"
    for tag in RUN_TAGS.values():
        (runs / tag).mkdir(parents=True)
    return package, runs


def test_the_published_document_is_the_case_verbatim_plus_one_field(tmp_path: Path) -> None:
    package, runs = _with_runs(tmp_path)

    published = publish_case(
        package,
        "episode_one",
        run_tags=RUN_TAGS,
        output=runs / "the-grain-episode-one",
        runs_root=runs,
    )
    document = json.loads(published.output.read_text(encoding="utf-8"))

    assert document["kind"] == "case-runtime-v1"
    assert document["case_id"] == "episode_one"
    assert document["entry"] == "b_office"
    # Facts cross verbatim: the consumer seeds its state from the same declaration
    # the proof read.
    assert {fact["fact_id"] for fact in document["facts"]} == {
        "took_the_job",
        "window_before",
        "rang_the_bell",
    }
    beats = {beat["beat_id"]: beat for beat in document["beats"]}
    assert beats["b_motor_court"]["member"] == "rooms/motor_court/room.toml"
    assert beats["b_motor_court"]["run_tag"] == "the-grain-motor-court"
    assert beats["b_statements"]["terminal"] is True
    assert beats["b_statements"]["reads"] == ["rang_the_bell"]
    # A run tag locates the run; for a scenario the id locates the leaf inside it,
    # keyed the way that run's own manifest keys its scenarios. A room run
    # publishes one room, so a room beat carries no id at all.
    assert beats["b_office"]["scenario_id"] == "office"
    assert beats["b_statements"]["scenario_id"] == "statements"
    assert "scenario_id" not in beats["b_motor_court"]


def test_several_beats_may_share_one_run(tmp_path: Path) -> None:
    """One `dialogue-scene` run binds many scenarios so the cast is drawn once."""

    package, runs = _with_runs(tmp_path)
    (runs / "the-grain-scene").mkdir()
    shared = {
        "b_office": "the-grain-scene",
        "b_motor_court": "the-grain-motor-court",
        "b_statements": "the-grain-scene",
    }

    published = publish_case(
        package,
        "episode_one",
        run_tags=shared,
        output=runs / "the-grain-episode-one",
        runs_root=runs,
    )
    beats = {beat.beat_id: beat for beat in published.runtime.beats}

    assert beats["b_office"].run_tag == beats["b_statements"].run_tag == "the-grain-scene"
    # Same run, different leaves: the id is what tells them apart.
    assert beats["b_office"].scenario_id == "office"
    assert beats["b_statements"].scenario_id == "statements"


def test_a_beat_with_no_run_is_refused(tmp_path: Path) -> None:
    package, _ = _with_runs(tmp_path)
    bound = bind_case(package, "episode_one")
    partial = {key: value for key, value in RUN_TAGS.items() if key != "b_statements"}

    with pytest.raises(CaseBundleError, match="no run tag was supplied for beats: b_statements"):
        build_case_runtime(bound, partial)


def test_a_run_for_a_beat_the_case_does_not_declare_is_refused(tmp_path: Path) -> None:
    package, _ = _with_runs(tmp_path)
    bound = bind_case(package, "episode_one")

    with pytest.raises(CaseBundleError, match="beats the case does not declare: b_elsewhere"):
        build_case_runtime(bound, {**RUN_TAGS, "b_elsewhere": "the-grain-nowhere"})


def test_a_named_run_that_is_not_on_disk_is_refused_offline(tmp_path: Path) -> None:
    """The consumer would 500; this says so before anyone opens a browser."""

    package, runs = _with_runs(tmp_path)
    tags = {**RUN_TAGS, "b_statements": "the-grain-never-generated"}

    with pytest.raises(CaseBundleError, match="b_statements -> the-grain-never-generated"):
        publish_case(
            package,
            "episode_one",
            run_tags=tags,
            output=runs / "the-grain-episode-one",
            runs_root=runs,
        )


def test_publishing_proves_the_case_and_binds_its_leaves_first(tmp_path: Path) -> None:
    """A case that cannot be played is refused here, not discovered by a player."""

    package, runs = _with_runs(tmp_path)
    (package / "scenarios/statements.scenario").write_text(
        "label statements:\n    end left_alone\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="does not match its authored digest"):
        publish_case(
            package,
            "episode_one",
            run_tags=RUN_TAGS,
            output=runs / "the-grain-episode-one",
            runs_root=runs,
        )


def test_the_runs_root_defaults_to_the_output_parent(tmp_path: Path) -> None:
    package, runs = _with_runs(tmp_path)

    published = publish_case(
        package,
        "episode_one",
        run_tags=RUN_TAGS,
        output=runs / "the-grain-episode-one",
    )

    assert published.output == runs / "the-grain-episode-one" / "case.json"
    assert len(published.document_sha256) == 64
