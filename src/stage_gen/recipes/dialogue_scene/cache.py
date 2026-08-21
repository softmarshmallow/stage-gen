"""Digest-bound resume cache for dialogue recipe stages."""

from __future__ import annotations

import json
from pathlib import Path

from stage_gen.recipes.dialogue_scene.identity import canonical_sha256, content_sha256
from stage_gen.reliability import atomic_write_json, resolve_relative_path_within_root


class DialogueStageCache:
    def __init__(self, run_dir: Path) -> None:
        self._run_dir = run_dir
        self._root = run_dir / ".dialogue-cache"

    def dependency_digests(self, paths: tuple[str, ...]) -> dict[str, str]:
        result: dict[str, str] = {}
        for relative in paths:
            path = resolve_relative_path_within_root(self._run_dir, relative, "cache artifact")
            if not path.is_file():
                raise ValueError(f"dialogue dependency is missing: {relative}")
            result[relative] = content_sha256(path.read_bytes())
        return result

    def key(
        self,
        stage: str,
        *,
        inputs: object,
        dependencies: dict[str, str],
        recipe_version: str = "dialogue-scene-v3",
        contract_schema_version: int = 2,
    ) -> str:
        return canonical_sha256(
            {
                "recipe": recipe_version,
                "contract_schema_version": contract_schema_version,
                "stage": stage,
                "inputs": inputs,
                "dependencies": dependencies,
            }
        )

    def load(self, stage: str, key: str, *, force: bool = False) -> tuple[str, ...] | None:
        if force:
            return None
        try:
            value = json.loads(self._path(stage).read_text(encoding="utf-8"))
            if (
                value.get("schema_version") != 2
                or value.get("kind") != "dialogue_stage_cache_v2"
                or value.get("key") != key
            ):
                return None
            artifacts = tuple(value["artifacts"])
            for relative in artifacts:
                path = resolve_relative_path_within_root(self._run_dir, relative, "cache artifact")
                if content_sha256(path.read_bytes()) != value["digests"][relative]:
                    return None
            return artifacts
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def store(self, stage: str, key: str, artifacts: tuple[str, ...]) -> None:
        digests = self.dependency_digests(artifacts)
        self._root.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            self._path(stage),
            {
                "schema_version": 2,
                "kind": "dialogue_stage_cache_v2",
                "key": key,
                "artifacts": list(artifacts),
                "digests": digests,
            },
        )

    def _path(self, stage: str) -> Path:
        if not stage or any(character not in "abcdefghijklmnopqrstuvwxyz-" for character in stage):
            raise ValueError("invalid dialogue stage cache id")
        return self._root / f"{stage}.json"
