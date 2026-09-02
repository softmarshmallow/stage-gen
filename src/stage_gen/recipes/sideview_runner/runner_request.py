"""Resolve one prepared package's runner member into what the runner plan needs.

The container resolver has already done the heavy lifting - exact closure,
digest locking, image decoding, seam and gap admission - so this module only
refuses a package without a runner member and hands the plan a typed handle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from stage_gen.orchestration.game_package import (
    GamePackageValidationError,
    ResolvedPreparedPackage,
    ResolvedRunnerMember,
    resolve_prepared_package,
)

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class ResolvedRunnerPackage:
    """The container package plus its resolved runner member."""

    package: ResolvedPreparedPackage
    runner: ResolvedRunnerMember

    def identity(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "kind": "sideview-runner-identity-v1",
            "game_id": self.package.game.game_id,
            "track_id": self.runner.track.track_id,
            "package_sha256": self.package.package_sha256,
            "closure_sha256": self.package.closure_sha256,
            "segment_ids": [entry.segment_id for entry in self.runner.track.segments.chunks],
        }


def resolve_runner_package(input_path: Path) -> ResolvedRunnerPackage:
    package = resolve_prepared_package(input_path)
    runner = package.runner
    if runner is None:
        raise GamePackageValidationError(
            "missing_genre_member", "prepared package declares no runner genre member"
        )
    return ResolvedRunnerPackage(package=package, runner=runner)


__all__ = ["ResolvedRunnerPackage", "resolve_runner_package"]
