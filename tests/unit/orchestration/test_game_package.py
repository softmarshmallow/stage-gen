from __future__ import annotations

import hashlib
import re
import shutil
import zipfile
from pathlib import Path

import pytest

from stage_gen.orchestration.game_package import (
    GamePackageValidationError,
    invalid_game_package_report,
    resolve_game_package,
    validate_game_package,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SOURCE_PACKAGE = REPOSITORY_ROOT / "library" / "games" / "bellweather"


def _copy_package(tmp_path: Path) -> Path:
    target = tmp_path / "bellweather"
    shutil.copytree(SOURCE_PACKAGE, target)
    return target


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _replace_root_digest(package: Path, source: str, digest: str) -> None:
    root = package / "game.toml"
    text = root.read_text(encoding="utf-8")
    pattern = (
        rf'(source = "{re.escape(source)}"\nsource_sha256 = ")'
        r"[a-f0-9]{64}(\")"
    )
    updated, replacements = re.subn(pattern, rf"\g<1>{digest}\g<2>", text, count=1)
    assert replacements == 1
    root.write_text(updated, encoding="utf-8")


def _write_zip(package: Path, output: Path, *, wrapped: bool = True) -> None:
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(package.rglob("*")):
            if not source.is_file():
                continue
            relative = source.relative_to(package)
            archive_name = Path(package.name, relative) if wrapped else relative
            archive.write(source, archive_name.as_posix())


def test_resolve_bellweather_directory_captures_complete_exact_current_package() -> None:
    package = resolve_game_package(SOURCE_PACKAGE)

    assert package.game.game_id == "bellweather"
    assert package.package_sha256 == _sha256(SOURCE_PACKAGE / "game.toml")
    assert len(package.files) == 22
    assert [entry.map_id for entry in package.maps] == [
        "sunpetal-crossing",
        "crowncrag-road",
    ]
    assert [entry.mob_id for entry in package.mobs.mobs] == package.game.cast.mob_ids
    assert [entry.npc_id for entry in package.npcs.npcs] == package.game.cast.npc_ids
    assert package.sequence_catalog.sequences[0].sequence_id == "sunpetal-welcome"


@pytest.mark.parametrize("wrapped", [True, False])
def test_directory_and_zip_resolve_to_the_same_canonical_identity(
    tmp_path: Path, wrapped: bool
) -> None:
    package = _copy_package(tmp_path)
    archive = tmp_path / "bellweather.zip"
    _write_zip(package, archive, wrapped=wrapped)

    directory = resolve_game_package(package)
    zipped = resolve_game_package(archive)

    assert zipped.source_kind == "zip"
    assert zipped.package_sha256 == directory.package_sha256
    assert zipped.canonical_game_sha256 == directory.canonical_game_sha256
    assert [entry.identity() for entry in zipped.files] == [
        entry.identity() for entry in directory.files
    ]


def test_validate_repository_selector_resolves_bellweather() -> None:
    report = validate_game_package(REPOSITORY_ROOT)

    assert report["valid"] is True
    assert report["kind"] == "game-package-validation-v2"
    assert report["game_id"] == "bellweather"
    assert report["generated_status"] == "not_checked"
    assert report["file_count"] == 22


def test_rejects_stale_member_digest_before_returning_a_package(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    gameplay = package / "gameplay.toml"
    gameplay.write_text(
        gameplay.read_text(encoding="utf-8").replace(
            "starting_health = 10", "starting_health = 11"
        ),
        encoding="utf-8",
    )

    with pytest.raises(GamePackageValidationError) as caught:
        resolve_game_package(package)

    assert caught.value.code == "stale_source_digest"
    assert "gameplay.toml" in str(caught.value)


def test_rejects_unresolved_cross_contract_id_after_relocking(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    gameplay = package / "gameplay.toml"
    gameplay.write_text(
        gameplay.read_text(encoding="utf-8").replace(
            'mob_id = "petal_puff"', 'mob_id = "missing_mob"', 1
        ),
        encoding="utf-8",
    )
    _replace_root_digest(package, "gameplay.toml", _sha256(gameplay))

    with pytest.raises(GamePackageValidationError) as caught:
        resolve_game_package(package)

    assert caught.value.code == "unresolved_cross_reference"
    assert "missing_mob" in str(caught.value)


def test_rejects_orphaned_package_files(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    (package / "unused.toml").write_text("unused = true\n", encoding="utf-8")

    with pytest.raises(GamePackageValidationError) as caught:
        resolve_game_package(package)

    assert caught.value.code == "orphan_package_file"
    assert "unused.toml" in str(caught.value)


def test_rejects_directory_symlinks(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    (package / "references" / "linked.png").symlink_to(package / "references" / "cover.png")

    with pytest.raises(GamePackageValidationError) as caught:
        resolve_game_package(package)

    assert caught.value.code == "symlink_escape"


def test_rejects_zip_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "bellweather.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("bellweather/game.toml", "schema_version = 4\n")
        output.writestr("../outside.txt", "escape")

    with pytest.raises(GamePackageValidationError) as caught:
        resolve_game_package(archive)

    assert caught.value.code == "invalid_package"
    assert "parent segments" in str(caught.value)


def test_invalid_report_is_machine_readable(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    (package / "game.toml").unlink()

    with pytest.raises(GamePackageValidationError) as caught:
        resolve_game_package(package)

    report = invalid_game_package_report(caught.value)
    assert report["valid"] is False
    assert report["source_status"] == "invalid"
    assert report["errors"] == [
        {"code": "missing_package_file", "message": "prepared package is missing game.toml"}
    ]


def test_repository_gate_failure_keeps_source_truth_separate() -> None:
    report = invalid_game_package_report(
        GamePackageValidationError(
            "uncommitted_game_package", "package closure differs from Git HEAD"
        )
    )

    assert report["source_status"] == "current"
    assert report["disposition"] == "commit_before_publish"
