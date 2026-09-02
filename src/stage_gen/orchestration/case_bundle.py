"""Publish one proven case as `case.json`, the runtime projection a consumer plays.

The authored case names its leaves by package `member`; a consumer plays **runs**.
Nothing joined the two, because nothing could: a run tag does not exist until its
leaf has been generated, so the join cannot be authored beside the case and cannot
be derived from it either. It is supplied here, once, at publication.

The document is the authored case verbatim with one field added per beat, and it
carries its own identity - `case-runtime-v1` - because a beat that has grown a run
tag is a different document from the one the author wrote. Every other recipe in
this repository publishes its runtime manifest beside its authored contract the
same way.

Nothing is generated and no provider is reached. The case is proven and its leaves
are bound first, so a case that cannot be played is refused here rather than
discovered by a player.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from stage_gen.components._game_input import sha256_bytes
from stage_gen.components.case import CaseRuntime
from stage_gen.orchestration.case_binding import BoundCase, bind_case

CASE_RUNTIME_NAME = "case.json"


class CaseBundleError(ValueError):
    """Raised when a proven case cannot be published against the runs it names."""


@dataclass(frozen=True, slots=True)
class PublishedCase:
    runtime: CaseRuntime
    output: Path
    document_sha256: str


def build_case_runtime(bound: BoundCase, run_tags: Mapping[str, str]) -> CaseRuntime:
    """Project one bound case onto the runs its beats were generated into.

    The mapping is checked as a set equality in both directions, the way every
    other closure in this repository is: a beat with no run cannot be played, and
    a run for a beat the case does not declare means the operator is publishing
    one case while thinking of another.
    """

    declared = {beat.beat_id: beat for beat in bound.resolved.case.beats}
    supplied = set(run_tags)
    missing = sorted(set(declared) - supplied)
    if missing:
        raise CaseBundleError(
            "no run tag was supplied for beats: "
            + ", ".join(missing)
            + ". Every beat is played from a run, or the case cannot be walked."
        )
    unknown = sorted(supplied - set(declared))
    if unknown:
        raise CaseBundleError(
            "run tags were supplied for beats the case does not declare: " + ", ".join(unknown)
        )

    document = bound.resolved.case.model_dump(mode="json")
    document["kind"] = CaseRuntime.model_fields["kind"].default
    # Several beats legitimately share one run tag: a `dialogue-scene` run binds
    # many scenarios so the cast is drawn once, so the tag locates the run and the
    # `scenario_id` locates the leaf inside it - keyed exactly as that run's own
    # manifest keys them. The id is derived from the beat's member rather than
    # supplied, so the two cannot disagree.
    document["beats"] = [
        {
            **beat,
            "run_tag": run_tags[str(beat["beat_id"])],
            **(
                {"scenario_id": declared[str(beat["beat_id"])].scenario_member_id}
                if beat["kind"] == "scenario"
                else {}
            ),
        }
        for beat in document["beats"]
    ]
    return CaseRuntime.model_validate(document)


def publish_case(
    root: Path,
    case_id: str,
    *,
    run_tags: Mapping[str, str],
    output: Path,
    runs_root: Path | None = None,
) -> PublishedCase:
    """Prove, bind, check the runs exist, then write `<output>/case.json`."""

    bound = bind_case(root, case_id)
    runtime = build_case_runtime(bound, run_tags)
    _require_runs_exist(runtime, runs_root if runs_root is not None else Path(output).parent)

    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        runtime.model_dump(mode="json", exclude_none=True),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    (destination / CASE_RUNTIME_NAME).write_bytes(payload)
    return PublishedCase(
        runtime=runtime,
        output=destination / CASE_RUNTIME_NAME,
        document_sha256=sha256_bytes(payload),
    )


def _require_runs_exist(runtime: CaseRuntime, runs_root: Path) -> None:
    """Refuse a missing run here, offline, rather than as a consumer's 500.

    Only existence is checked, and deliberately so: what a run must *contain* is
    each leaf recipe's own runtime manifest contract, and re-stating it here would
    be a second copy of a rule that already has an owner.
    """

    root = Path(runs_root)
    if not root.is_dir():
        raise CaseBundleError(f"case runs root {root} is not a directory")
    missing = [
        f"{beat.beat_id} -> {beat.run_tag}"
        for beat in runtime.beats
        if not (root / beat.run_tag).is_dir() or (root / beat.run_tag).is_symlink()
    ]
    if missing:
        raise CaseBundleError(
            f"beats name runs that are not directories under {runs_root}: " + ", ".join(missing)
        )


__all__ = [
    "CASE_RUNTIME_NAME",
    "CaseBundleError",
    "PublishedCase",
    "build_case_runtime",
    "publish_case",
]
