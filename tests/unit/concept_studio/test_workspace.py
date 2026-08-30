from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from gnode import BinaryArtifact, ProvenanceInput, SoftwareIdentity, write_artifact_with_provenance
from stage_gen.concept_studio import workspace as workspace_module
from stage_gen.concept_studio.workspace import (
    check_workspace,
    create_workspace,
    select_candidate,
)

_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xcf\xc0\x00"
    b"\x00\x03\x01\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_workspace_init_draft_check_and_duplicate_rejection(concept_repository: Path) -> None:
    created = create_workspace(
        concept_repository,
        concept_id="flooded-couriers",
        title=" Flooded Couriers ",
        brief=" Deliver medicine between rooftop settlements. ",
    )
    workspace = Path(str(created["workspace"]))

    assert workspace == concept_repository / "concept-studio/workspaces/flooded-couriers"
    assert (workspace / "concept.md").read_text() == (
        "# Flooded Couriers\n\n"
        "> Status: exploratory game concept only; not a game package or implementation plan.\n\n"
        "## Short brief\n\n"
        "Deliver medicine between rooftop settlements.\n"
    )
    assert (
        check_workspace(
            concept_repository,
            concept_id="flooded-couriers",
            draft=True,
        )["cover"]
        is None
    )
    with pytest.raises(ValueError, match="already exists"):
        create_workspace(
            concept_repository,
            concept_id="flooded-couriers",
            title="Duplicate",
            brief="Must not overwrite the first workspace.",
        )


def test_workspace_rejects_game_toml_at_any_depth(concept_repository: Path) -> None:
    created = create_workspace(
        concept_repository,
        concept_id="forbidden-runtime-contract",
        title="Concept Only",
        brief="This workspace must stay text and image only.",
    )
    workspace = Path(str(created["workspace"]))
    nested = workspace / "notes/runtime"
    nested.mkdir(parents=True)
    (nested / "game.toml").write_text('name = "forbidden"\n')

    with pytest.raises(ValueError, match=r"must not contain game.toml"):
        check_workspace(
            concept_repository,
            concept_id="forbidden-runtime-contract",
            draft=True,
        )


def test_select_candidate_copies_validated_pair_and_enables_full_check(
    concept_repository: Path,
) -> None:
    created = create_workspace(
        concept_repository,
        concept_id="selected-cover",
        title="Selected Cover",
        brief="Choose one reviewed concept candidate.",
    )
    workspace = Path(str(created["workspace"]))
    candidate = workspace / "images/candidate-01.png"
    candidate_sidecar = write_artifact_with_provenance(
        candidate,
        BinaryArtifact(data=_PNG, media_type="image/png"),
        ProvenanceInput(
            component=SoftwareIdentity(name="@stage-gen/core", version="0.0.0"),
            tool=SoftwareIdentity(name="stage-gen", version="0.0.0"),
            provider="fake",
            model="openai/gpt-image-2",
            prompt="Original concept cover",
            attempts=1,
        ),
    )

    selected = select_candidate(
        concept_repository,
        concept_id="selected-cover",
        candidate="candidate-01",
    )
    cover = workspace / "images/cover.png"
    cover_sidecar = Path(f"{cover}.meta.json")

    assert cover.read_bytes() == candidate.read_bytes()
    assert cover_sidecar.read_bytes() == candidate_sidecar.read_bytes()
    checked = check_workspace(
        concept_repository,
        concept_id="selected-cover",
    )
    checked_cover = cast(dict[str, object], checked["cover"])
    assert selected["sha256"] == checked_cover["sha256"]
    with pytest.raises(ValueError, match="exploratory image, not cover"):
        select_candidate(
            concept_repository,
            concept_id="selected-cover",
            candidate="cover",
            replace=True,
        )


def test_select_candidate_publishes_the_validated_snapshot_without_rereading_paths(
    concept_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = create_workspace(
        concept_repository,
        concept_id="snapshot-cover",
        title="Snapshot Cover",
        brief="Copy exactly the bytes that passed validation.",
    )
    workspace = Path(str(created["workspace"]))
    candidate = workspace / "images/candidate-01.png"
    write_artifact_with_provenance(
        candidate,
        BinaryArtifact(data=_PNG, media_type="image/png"),
        ProvenanceInput(
            component=SoftwareIdentity(name="@stage-gen/core", version="0.0.0"),
            tool=SoftwareIdentity(name="stage-gen", version="0.0.0"),
            provider="fake",
            model="openai/gpt-image-2",
            prompt="Original snapshot",
            attempts=1,
        ),
    )
    original_publish = workspace_module._publish_files_at

    def mutate_source_then_publish(
        directory_fd: int,
        entries: tuple[tuple[str, bytes], ...],
        *,
        replace: bool,
        conflict_message: str,
        check_location: Callable[[], None],
    ) -> None:
        candidate.write_bytes(b"changed after validation")
        original_publish(
            directory_fd,
            entries,
            replace=replace,
            conflict_message=conflict_message,
            check_location=check_location,
        )

    monkeypatch.setattr(workspace_module, "_publish_files_at", mutate_source_then_publish)

    selected = select_candidate(
        concept_repository,
        concept_id="snapshot-cover",
        candidate="candidate-01",
    )

    cover = workspace / "images/cover.png"
    assert cover.read_bytes() == _PNG
    assert selected["sha256"] == hashlib.sha256(_PNG).hexdigest()


def test_select_candidate_never_overwrites_a_racing_cover_without_replace(
    concept_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = create_workspace(
        concept_repository,
        concept_id="cover-race",
        title="Cover Race",
        brief="Preserve a concurrent cover publication.",
    )
    workspace = Path(str(created["workspace"]))
    candidate = workspace / "images/candidate-01.png"
    write_artifact_with_provenance(
        candidate,
        BinaryArtifact(data=_PNG, media_type="image/png"),
        ProvenanceInput(
            component=SoftwareIdentity(name="@stage-gen/core", version="0.0.0"),
            tool=SoftwareIdentity(name="stage-gen", version="0.0.0"),
            provider="fake",
            model="openai/gpt-image-2",
            prompt="Candidate",
            attempts=1,
        ),
    )
    original_read = workspace_module._read_artifact_pair_at
    competing_artifact = b"concurrent cover"
    competing_sidecar = b"concurrent provenance"

    def read_then_publish_competing_cover(
        directory_fd: int,
        artifact_name: str,
        sidecar_name: str,
    ) -> workspace_module._ArtifactSnapshot:
        snapshot = original_read(directory_fd, artifact_name, sidecar_name)
        (workspace / "images/cover.png").write_bytes(competing_artifact)
        (workspace / "images/cover.png.meta.json").write_bytes(competing_sidecar)
        return snapshot

    monkeypatch.setattr(
        workspace_module,
        "_read_artifact_pair_at",
        read_then_publish_competing_cover,
    )

    with pytest.raises(ValueError, match="concept image already exists: cover"):
        select_candidate(
            concept_repository,
            concept_id="cover-race",
            candidate="candidate-01",
        )

    assert (workspace / "images/cover.png").read_bytes() == competing_artifact
    assert (workspace / "images/cover.png.meta.json").read_bytes() == competing_sidecar


def test_workspace_check_rejects_symlinked_content(concept_repository: Path) -> None:
    created = create_workspace(
        concept_repository,
        concept_id="symlinked-content",
        title="Symlinked Content",
        brief="Workspace checks fail closed on links.",
    )
    workspace = Path(str(created["workspace"]))
    outside = concept_repository / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    (workspace / "notes-link").symlink_to(outside)

    with pytest.raises(ValueError, match="must not contain symlinks"):
        check_workspace(
            concept_repository,
            concept_id="symlinked-content",
            draft=True,
        )
