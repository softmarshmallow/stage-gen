"""Resolving one authored scenario package: confinement, digests, and the real one."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from stage_gen.components._secure_fs import SecurePathError
from stage_gen.components.scenario import resolve_scenario, script_digest
from stage_gen.components.scenario.resolve import read_scenario_declarations

from .package import DEFAULT_SCRIPT, write_scenario_package

REPOSITORY_ROOT = Path(__file__).parents[4]
LARKFIELD = REPOSITORY_ROOT / "library/games/larkfield"


def test_the_shipped_scenario_is_admitted_and_both_endings_are_reachable() -> None:
    """The package in the tree is the happy path; a fixture cannot stand in for it."""

    resolved = resolve_scenario(LARKFIELD, "last_class")
    assert resolved.declarations.scenario_id == "last_class"
    assert resolved.program.entry == "arrival"
    labels = [block.label for block in resolved.program.blocks]
    assert labels[:3] == ["arrival", "listening", "asking"]
    assert len(labels) == 20
    witnesses = {witness.outcome_id: witness.path for witness in resolved.admission.witnesses}
    # Four endings, each with one shortest route as evidence.
    assert set(witnesses) == {"broadcast", "talked", "listened", "locked_out"}
    assert witnesses["broadcast"][:3] == ["arrival", "listening", "the_playback"]
    assert witnesses["broadcast"][-1] == "ending_broadcast"


def test_the_shipped_scenario_declares_the_digest_of_its_own_script() -> None:
    declarations = read_scenario_declarations(LARKFIELD, "last_class")
    assert script_digest(LARKFIELD, declarations) == declarations.script_sha256


def test_a_script_that_no_longer_matches_its_digest_is_refused(tmp_path: Path) -> None:
    write_scenario_package(tmp_path, declared_sha256="0" * 64)
    with pytest.raises(ValueError, match="does not match its authored digest"):
        resolve_scenario(tmp_path, "last_class")


def test_the_digest_helper_reports_what_edited_prose_would_need(tmp_path: Path) -> None:
    """Authoring against a hand-copied hash is only tolerable if a tool repairs it."""

    edited = DEFAULT_SCRIPT.replace("The room is empty.", "The room is very empty.")
    write_scenario_package(tmp_path, script=edited, declared_sha256="0" * 64)
    declarations = read_scenario_declarations(tmp_path, "last_class")
    assert (
        script_digest(tmp_path, declarations) == hashlib.sha256(edited.encode("utf-8")).hexdigest()
    )


def test_a_script_reached_through_a_symlinked_directory_is_refused(tmp_path: Path) -> None:
    """The old per-recipe reader only inspected the final path component."""

    package = tmp_path / "package"
    package.mkdir()
    write_scenario_package(package)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "last_class.scenario").write_text(DEFAULT_SCRIPT, encoding="utf-8")
    real = package / "scenarios"
    for child in real.iterdir():
        child.unlink()
    real.rmdir()
    real.symlink_to(outside, target_is_directory=True)
    with pytest.raises(SecurePathError, match="must not traverse a symlink"):
        resolve_scenario(package, "last_class")


def test_a_symlinked_script_file_is_refused(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    write_scenario_package(package)
    outside = tmp_path / "elsewhere.scenario"
    outside.write_text(DEFAULT_SCRIPT, encoding="utf-8")
    script = package / "scenarios/last_class.scenario"
    script.unlink()
    script.symlink_to(outside)
    with pytest.raises(SecurePathError, match="regular non-symlink file"):
        resolve_scenario(package, "last_class")


def test_a_script_path_that_escapes_the_package_is_refused(tmp_path: Path) -> None:
    write_scenario_package(tmp_path, script_path_override=True)
    with pytest.raises(ValueError, match=re.escape("must equal scenarios/last_class.scenario")):
        resolve_scenario(tmp_path, "last_class")


def test_the_identity_names_the_exact_prose_the_program_was_compiled_from(
    tmp_path: Path,
) -> None:
    write_scenario_package(tmp_path)
    resolved = resolve_scenario(tmp_path, "last_class")
    identity = resolved.identity()
    assert identity["kind"] == "scenario-identity-v1"
    assert identity["script_sha256"] == resolved.declarations.script_sha256
    assert identity["reachable_states"] == resolved.admission.reachable_states


def test_the_compiled_program_is_canonical_and_stable(tmp_path: Path) -> None:
    write_scenario_package(tmp_path)
    first = resolve_scenario(tmp_path, "last_class")
    second = resolve_scenario(tmp_path, "last_class")
    assert first.program_bytes == second.program_bytes
    assert first.program_sha256 == hashlib.sha256(first.program_bytes).hexdigest()
