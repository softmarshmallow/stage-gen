from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from stage_gen.orchestration.game_package import (
    GamePackageValidationError,
    invalid_game_package_report,
    validate_game_package,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
GAME_ID = "whimsical-storybook-fantasy"


def _copy_game_package(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    game_parent = root / "library" / "games"
    request_parent = root / "examples" / "scrolling-preview"
    game_parent.mkdir(parents=True)
    request_parent.mkdir(parents=True)
    shutil.copytree(
        REPOSITORY_ROOT / "library" / "games" / GAME_ID,
        game_parent / GAME_ID,
    )
    shutil.copy2(REPOSITORY_ROOT / "library" / "games" / "main.toml", game_parent)
    shutil.copy2(
        REPOSITORY_ROOT / "examples" / "scrolling-preview" / "game-directed-village.toml",
        request_parent,
    )
    return root


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _replace_binding_digest(root: Path, section: str, digest: str) -> None:
    request_path = root / "examples" / "scrolling-preview" / "game-directed-village.toml"
    source = request_path.read_text(encoding="utf-8")
    pattern = rf'(\[{re.escape(section)}\][\s\S]*?source_sha256 = ")[a-f0-9]{{64}}(")'
    updated, replacements = re.subn(pattern, rf"\g<1>{digest}\g<2>", source, count=1)
    assert replacements == 1
    request_path.write_text(updated, encoding="utf-8")
    _relock_request(root)


def _relock_request(root: Path) -> None:
    request_path = root / "examples" / "scrolling-preview" / "game-directed-village.toml"
    selector_path = root / "library" / "games" / "main.toml"
    source = selector_path.read_text(encoding="utf-8")
    pattern = r'(request_sha256 = ")[a-f0-9]{64}(")'
    updated, replacements = re.subn(
        pattern,
        rf"\g<1>{_sha256(request_path)}\g<2>",
        source,
        count=1,
    )
    assert replacements == 1
    selector_path.write_text(updated, encoding="utf-8")


def _relock_game(root: Path) -> None:
    _replace_binding_digest(
        root,
        "game",
        _sha256(root / "library" / "games" / GAME_ID / "game.toml"),
    )


def _relock_soundtrack(root: Path) -> None:
    _replace_binding_digest(
        root,
        "soundtrack",
        _sha256(root / "library" / "games" / GAME_ID / "soundtrack.toml"),
    )


def _relock_map(root: Path, map_id: str) -> None:
    map_path = root / "library" / "games" / GAME_ID / "maps" / f"{map_id}.toml"
    index_path = root / "library" / "games" / GAME_ID / "maps" / "index.toml"
    source = index_path.read_text(encoding="utf-8")
    pattern = (
        rf'(\[\[maps\]\]\nmap_id = "{re.escape(map_id)}"\n'
        rf'source_sha256 = ")[a-f0-9]{{64}}(")'
    )
    updated, replacements = re.subn(pattern, rf"\g<1>{_sha256(map_path)}\g<2>", source)
    assert replacements == 1
    index_path.write_text(updated, encoding="utf-8")


def _relock_map_book(root: Path) -> None:
    _replace_binding_digest(
        root,
        "map_book",
        _sha256(root / "library" / "games" / GAME_ID / "maps" / "index.toml"),
    )


def test_validate_game_package_accepts_the_current_complete_closure(tmp_path: Path) -> None:
    root = _copy_game_package(tmp_path)

    report = validate_game_package(root)

    assert report["valid"] is True
    assert report["source_status"] == "current"
    assert report["generated_status"] == "not_checked"
    assert report["game_id"] == GAME_ID
    assert report["applied_defaults"] == []
    assert report["features"] == ["game", "soundtrack", "map_book", "village"]
    assert report["schema_versions"] == {
        "game_contract": 3,
        "game_soundtrack": 1,
        "game_map_book": 1,
        "game_map": 2,
    }
    assert report["repository"] == {
        "status": "not_git_checkout",
        "untracked_refs": [],
        "modified_refs": [],
    }


def test_validate_game_package_rejects_a_previous_selector_schema(tmp_path: Path) -> None:
    root = _copy_game_package(tmp_path)
    selector_path = root / "library" / "games" / "main.toml"
    selector_path.write_text(
        selector_path.read_text(encoding="utf-8").replace(
            "schema_version = 1",
            "schema_version = 0",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(GamePackageValidationError) as caught:
        validate_game_package(root)

    assert caught.value.code == "invalid_selector"


def test_validate_game_package_rejects_a_previous_game_schema(tmp_path: Path) -> None:
    root = _copy_game_package(tmp_path)
    game_path = root / "library" / "games" / GAME_ID / "game.toml"
    source = game_path.read_text(encoding="utf-8")
    source = source.replace("schema_version = 3", "schema_version = 2", 1)
    source = source.replace('kind = "game-contract-v3"', 'kind = "game-contract-v2"', 1)
    combat_start = source.index("[gameplay.combat_text]")
    population_start = source.index("[gameplay.mob_population]")
    game_path.write_text(source[:combat_start] + source[population_start:], encoding="utf-8")
    _relock_game(root)

    with pytest.raises(GamePackageValidationError) as caught:
        validate_game_package(root)

    assert caught.value.code == "unsupported_schema_version"
    assert "schema_version=3" in str(caught.value)


def test_validate_game_package_rejects_previous_map_sources(tmp_path: Path) -> None:
    root = _copy_game_package(tmp_path)
    maps_dir = root / "library" / "games" / GAME_ID / "maps"
    for map_path in sorted(maps_dir.glob("*.toml")):
        if map_path.name == "index.toml":
            continue
        source = map_path.read_text(encoding="utf-8")
        source = source.replace("schema_version = 2", "schema_version = 1", 1)
        source = source.replace('kind = "game-map-v2"', 'kind = "game-map-v1"', 1)
        map_path.write_text(source[: source.index("[level_profile]")], encoding="utf-8")
        _relock_map(root, map_path.stem)
    _relock_map_book(root)

    with pytest.raises(GamePackageValidationError) as caught:
        validate_game_package(root)

    assert caught.value.code == "unsupported_schema_version"
    assert "schema_version=2" in str(caught.value)


def test_validate_game_package_rejects_a_previous_soundtrack_schema(tmp_path: Path) -> None:
    root = _copy_game_package(tmp_path)
    soundtrack_path = root / "library" / "games" / GAME_ID / "soundtrack.toml"
    source = soundtrack_path.read_text(encoding="utf-8")
    source = source.replace("schema_version = 1", "schema_version = 0", 1)
    source = source.replace('kind = "game-soundtrack-v1"', 'kind = "game-soundtrack-v0"', 1)
    soundtrack_path.write_text(source, encoding="utf-8")
    _relock_soundtrack(root)

    with pytest.raises(GamePackageValidationError) as caught:
        validate_game_package(root)

    assert caught.value.code == "unsupported_schema_version"
    assert "schema_version=1" in str(caught.value)


def test_validate_game_package_rejects_a_previous_map_book_schema(tmp_path: Path) -> None:
    root = _copy_game_package(tmp_path)
    index_path = root / "library" / "games" / GAME_ID / "maps" / "index.toml"
    source = index_path.read_text(encoding="utf-8")
    source = source.replace("schema_version = 1", "schema_version = 0", 1)
    source = source.replace('kind = "game-map-book-v1"', 'kind = "game-map-book-v0"', 1)
    index_path.write_text(source, encoding="utf-8")
    _relock_map_book(root)

    with pytest.raises(GamePackageValidationError) as caught:
        validate_game_package(root)

    assert caught.value.code == "unsupported_schema_version"
    assert "schema_version=1" in str(caught.value)


def test_validate_game_package_rejects_a_stale_digest(tmp_path: Path) -> None:
    root = _copy_game_package(tmp_path)
    game_path = root / "library" / "games" / GAME_ID / "game.toml"
    game_path.write_text(
        game_path.read_text(encoding="utf-8").replace(
            'display_name = "Whimsical Storybook Fantasy"',
            'display_name = "Changed Without Relocking"',
        ),
        encoding="utf-8",
    )

    with pytest.raises(GamePackageValidationError) as caught:
        validate_game_package(root)

    assert caught.value.code == "invalid_game_contract"
    assert "source_sha256 mismatch" in str(caught.value)


def test_validate_game_package_rejects_unknown_request_fields(tmp_path: Path) -> None:
    root = _copy_game_package(tmp_path)
    request_path = root / "examples" / "scrolling-preview" / "game-directed-village.toml"
    source = request_path.read_text(encoding="utf-8")
    request_path.write_text(
        source.replace(
            'prompt = "whimsical storybook fantasy"',
            'prompt = "whimsical storybook fantasy"\nlegacy_mode = true',
        ),
        encoding="utf-8",
    )
    _relock_request(root)

    with pytest.raises(GamePackageValidationError) as caught:
        validate_game_package(root)

    assert caught.value.code == "unsupported_request_field"
    assert "legacy_mode" in str(caught.value)


def test_validate_game_package_rejects_general_recipe_fields_outside_its_closure(
    tmp_path: Path,
) -> None:
    root = _copy_game_package(tmp_path)
    request_path = root / "examples" / "scrolling-preview" / "game-directed-village.toml"
    source = request_path.read_text(encoding="utf-8")
    request_path.write_text(
        source.replace(
            'prompt = "whimsical storybook fantasy"',
            'prompt = "whimsical storybook fantasy"\ncharacter_heads_tall = 6',
        ),
        encoding="utf-8",
    )
    _relock_request(root)

    with pytest.raises(GamePackageValidationError) as caught:
        validate_game_package(root)

    assert caught.value.code == "unsupported_request_field"
    assert "character_heads_tall" in str(caught.value)


def test_validate_game_package_rejects_a_missing_required_feature(tmp_path: Path) -> None:
    root = _copy_game_package(tmp_path)
    request_path = root / "examples" / "scrolling-preview" / "game-directed-village.toml"
    source = request_path.read_text(encoding="utf-8")
    request_path.write_text(source[: source.index("[village]")], encoding="utf-8")
    _relock_request(root)

    with pytest.raises(GamePackageValidationError) as caught:
        validate_game_package(root)

    assert caught.value.code == "missing_required_feature"
    assert "village" in str(caught.value)


def test_validate_game_package_allows_undeclared_optional_systems_to_be_absent(
    tmp_path: Path,
) -> None:
    root = _copy_game_package(tmp_path)
    game_dir = root / "library" / "games" / GAME_ID
    game_path = game_dir / "game.toml"
    source = game_path.read_text(encoding="utf-8")
    gameplay_start = source.index("[gameplay.combat_text]")
    rights_start = source.index("[rights]")
    game_path.write_text(source[:gameplay_start] + source[rights_start:], encoding="utf-8")
    _relock_game(root)

    request_path = root / "examples" / "scrolling-preview" / "game-directed-village.toml"
    request_source = request_path.read_text(encoding="utf-8")
    request_path.write_text(
        request_source[: request_source.index("[soundtrack]")], encoding="utf-8"
    )
    _relock_request(root)
    (game_dir / "soundtrack.toml").unlink()
    shutil.rmtree(game_dir / "maps")

    selector_path = root / "library" / "games" / "main.toml"
    selector_path.write_text(
        selector_path.read_text(encoding="utf-8").replace(
            '["game", "soundtrack", "map_book", "village"]',
            '["game"]',
        ),
        encoding="utf-8",
    )

    report = validate_game_package(root)

    assert report["valid"] is True
    assert report["features"] == ["game"]
    assert report["required_features"] == ["game"]
    assert report["applied_defaults"] == ["gameplay.combat_text"]


def test_validate_game_package_rejects_unknown_map_track_ids(tmp_path: Path) -> None:
    root = _copy_game_package(tmp_path)
    map_id = "village-hub"
    map_path = root / "library" / "games" / GAME_ID / "maps" / f"{map_id}.toml"
    map_path.write_text(
        map_path.read_text(encoding="utf-8").replace(
            '["sunpetal_road", "village_lanterns"]',
            '["missing_track", "sunpetal_road"]',
        ),
        encoding="utf-8",
    )
    _relock_map(root, map_id)
    _relock_map_book(root)

    with pytest.raises(GamePackageValidationError) as caught:
        validate_game_package(root)

    assert caught.value.code == "unknown_soundtrack_track"
    assert "missing_track" in str(caught.value)


def test_validate_game_package_rejects_population_map_drift(tmp_path: Path) -> None:
    root = _copy_game_package(tmp_path)
    game_path = root / "library" / "games" / GAME_ID / "game.toml"
    source = game_path.read_text(encoding="utf-8")
    last_population_map = source.rindex("[[gameplay.mob_population.maps]]")
    rights_start = source.index("[rights]")
    game_path.write_text(source[:last_population_map] + source[rights_start:], encoding="utf-8")
    _relock_game(root)

    with pytest.raises(GamePackageValidationError) as caught:
        validate_game_package(root)

    assert caught.value.code == "population_map_mismatch"


def test_validate_game_package_rejects_orphan_toml_sources(tmp_path: Path) -> None:
    root = _copy_game_package(tmp_path)
    orphan = root / "library" / "games" / GAME_ID / "retired-map.toml"
    orphan.write_text('schema_version = 1\nkind = "retired"\n', encoding="utf-8")

    with pytest.raises(GamePackageValidationError) as caught:
        validate_game_package(root)

    assert caught.value.code == "orphan_game_source"
    assert "retired-map.toml" in str(caught.value)


def test_validate_game_package_rejects_symlinked_sources(tmp_path: Path) -> None:
    root = _copy_game_package(tmp_path)
    selector = root / "library" / "games" / "main.toml"
    replacement = root / "replacement.toml"
    replacement.write_bytes(selector.read_bytes())
    selector.unlink()
    selector.symlink_to(replacement)

    with pytest.raises(GamePackageValidationError) as caught:
        validate_game_package(root)

    assert caught.value.code == "invalid_selector"
    assert "symlink" in str(caught.value)


def test_validate_game_package_can_require_git_inclusion(tmp_path: Path) -> None:
    root = _copy_game_package(tmp_path)

    with pytest.raises(GamePackageValidationError) as caught:
        validate_game_package(root, require_tracked=True)

    assert caught.value.code == "untracked_game_package"
    assert "not a Git checkout" in str(caught.value)
    assert invalid_game_package_report(caught.value)["source_status"] == "current"
    assert invalid_game_package_report(caught.value)["disposition"] == "track_before_publish"


def test_validate_game_package_rejects_a_stale_request_lock(tmp_path: Path) -> None:
    root = _copy_game_package(tmp_path)
    request_path = root / "examples" / "scrolling-preview" / "game-directed-village.toml"
    request_path.write_text(
        request_path.read_text(encoding="utf-8").replace(
            'prompt = "whimsical storybook fantasy"',
            'prompt = "changed without promoting"',
        ),
        encoding="utf-8",
    )

    with pytest.raises(GamePackageValidationError) as caught:
        validate_game_package(root)

    assert caught.value.code == "request_digest_mismatch"


def test_validate_game_package_distinguishes_tracked_from_committed_bytes(
    tmp_path: Path,
) -> None:
    root = _copy_game_package(tmp_path)

    def git(*arguments: str) -> None:
        subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    git("init", "-q")
    git("config", "user.name", "game-package-test")
    git("config", "user.email", "game-package-test@example.invalid")
    git("config", "commit.gpgsign", "false")
    git("add", "library", "examples")
    git("commit", "-qm", "canonical game fixture")

    committed = validate_game_package(root, require_committed=True)
    assert committed["repository"] == {
        "status": "committed",
        "untracked_refs": [],
        "modified_refs": [],
    }

    selector_path = root / "library" / "games" / "main.toml"
    selector_path.write_text(
        selector_path.read_text(encoding="utf-8") + "\n# local modification\n",
        encoding="utf-8",
    )
    tracked = validate_game_package(root, require_tracked=True)
    repository = tracked["repository"]
    assert isinstance(repository, dict)
    assert repository["status"] == "modified"
    assert tracked["disposition"] == "commit_before_publish"

    with pytest.raises(GamePackageValidationError) as caught:
        validate_game_package(root, require_committed=True)

    assert caught.value.code == "uncommitted_game_package"
    assert invalid_game_package_report(caught.value)["source_status"] == "current"
    assert invalid_game_package_report(caught.value)["disposition"] == "commit_before_publish"


def test_require_committed_rejects_index_bytes_that_differ_from_head(tmp_path: Path) -> None:
    root = _copy_game_package(tmp_path)

    def git(*arguments: str) -> None:
        subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    git("init", "-q")
    git("config", "user.name", "game-package-test")
    git("config", "user.email", "game-package-test@example.invalid")
    git("config", "commit.gpgsign", "false")
    git("add", "library", "examples")
    git("commit", "-qm", "canonical game fixture")

    selector_path = root / "library" / "games" / "main.toml"
    committed_bytes = selector_path.read_bytes()
    selector_path.write_bytes(committed_bytes + b"\n# staged alternate\n")
    git("add", "library/games/main.toml")
    selector_path.write_bytes(committed_bytes)

    with pytest.raises(GamePackageValidationError) as caught:
        validate_game_package(root, require_committed=True)

    assert caught.value.code == "uncommitted_game_package"
    assert "library/games/main.toml" in str(caught.value)
