"""The semantic facing review that sits between generation and acceptance."""

from __future__ import annotations

import json
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from typing import Any, cast

import pytest
from PIL import Image

from stage_gen.components._types import ProviderResponseMetadata
from stage_gen.components.image_generation import ImageGenerationService
from stage_gen.components.structured_generation import (
    ProviderStructuredOutput,
    StructuredGenerationRequest,
    StructuredGenerationService,
)
from stage_gen.config import StageGenConfig, TransparencyMode
from stage_gen.recipes.base import StageContext
from stage_gen.recipes.scrolling_preview.executor import (
    _ACTOR_REVIEW_MAXIMUM_REGENERATIONS,
    ScrollingPreviewExecutor,
    _ImageSpec,
)
from stage_gen.recipes.scrolling_preview.review_criteria import (
    ACTOR_FACING_SCHEMA_NAME,
    ActorFacingError,
)
from stage_gen.recipes.scrolling_preview.scale_reference import (
    ACTOR_SCALE_REFERENCE_SCHEMA_NAME,
)


class _FacingBackend:
    """Returns a scripted facing verdict per call, so a run's sequence can be replayed."""

    provider = "fake-structured"
    model = "text-model"
    secrets: tuple[str, ...] = ()

    def __init__(self, facings: Sequence[str], *, confident: bool = True) -> None:
        self.facings = list(facings)
        self.confident = confident
        self.requests: list[StructuredGenerationRequest[object]] = []
        self.facing_requests: list[StructuredGenerationRequest[object]] = []
        self.scale_requests: list[StructuredGenerationRequest[object]] = []

    async def generate_once(
        self, request: StructuredGenerationRequest[object]
    ) -> ProviderStructuredOutput:
        self.requests.append(request)
        if request.schema.name == ACTOR_SCALE_REFERENCE_SCHEMA_NAME:
            # Every actor sheet is also measured for scale; that call is not a facing review.
            self.scale_requests.append(request)
            decoded: dict[str, object] = {
                "part": "head",
                "top": 0.1,
                "bottom": 0.4,
                "left": 0.3,
                "right": 0.6,
                "confident": True,
                "evidence": "head bounded above the shoulders",
            }
            return ProviderStructuredOutput(
                decoded=decoded,
                raw_text=json.dumps(decoded),
                response_metadata=ProviderResponseMetadata(
                    request_id=f"scale-{len(self.scale_requests)}"
                ),
            )
        self.facing_requests.append(request)
        index = min(len(self.facing_requests) - 1, len(self.facings) - 1)
        decoded = {
            "facing": self.facings[index],
            "confident": self.confident,
            "evidence": "the subject's eyes point that way",
        }
        return ProviderStructuredOutput(
            decoded=decoded,
            raw_text=json.dumps(decoded),
            response_metadata=ProviderResponseMetadata(request_id=f"review-{len(self.requests)}"),
        )

    async def aclose(self) -> None:
        return None


def _strip_png(path: Path, variant: int = 0) -> None:
    """A four-cell strip, only real enough for the reviewer to be handed a reference.

    `variant` shifts the fill so successive generations differ in bytes, which is what a real
    regeneration produces. Emitting identical art instead would let the digest-keyed verdict
    cache reuse the reading taken on the artwork that was just rejected.
    """

    image = Image.new("RGB", (256, 64), (255, 0, 255))
    for column in range(4):
        shade = (40 + variant * 17) % 200
        image.paste((shade, 90, 160), (column * 64 + 12, 12, column * 64 + 52, 52))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    path.write_bytes(buffer.getvalue())


class _Harness:
    """Stands in for image generation so the test exercises the review loop, not the pipeline."""

    def __init__(self, executor: ScrollingPreviewExecutor, output: Path) -> None:
        self.executor = executor
        self.output = output
        self.generations = 0
        self.forced = 0

    def install(self) -> None:
        async def fake_generate(
            _context: StageContext,
            _spec: _ImageSpec,
            *,
            force: bool = False,
        ) -> Sequence[str]:
            self.generations += 1
            if force:
                self.forced += 1
            # Only a forced call produces new artwork. An unforced call models the pipeline's
            # own cache handing back the same bytes, which is what a resumed run sees.
            _strip_png(self.output, variant=self.forced)
            return (str(self.output),)

        # Replaces only the provider-facing half; the review loop under test is untouched.
        # setattr, not assignment: rebinding a method is what this needs to do.
        setattr(self.executor, "_generate_image_asset", fake_generate)  # noqa: B010


def _context(tmp_path: Path) -> StageContext:
    return StageContext(
        input={"prompt": "original lantern forest"},
        tag="review-v1",
        run_dir=tmp_path,
        config=StageGenConfig(out_dir=tmp_path, transparency_mode=TransparencyMode.CHROMA),
    )


def _spec(tmp_path: Path, stage: str) -> _ImageSpec:
    return _ImageSpec(
        stage=stage,
        prompt="four-frame side view",
        output=tmp_path / "strip.png",
        width=256,
        height=64,
    )


def _build(tmp_path: Path, backend: _FacingBackend) -> tuple[ScrollingPreviewExecutor, _Harness]:
    executor = ScrollingPreviewExecutor(
        image_service=cast(ImageGenerationService, object()),
        structured_service=StructuredGenerationService[object](backend),
    )
    harness = _Harness(executor, tmp_path / "strip.png")
    harness.install()
    return executor, harness


async def test_a_right_facing_strip_is_accepted_after_one_review(tmp_path: Path) -> None:
    backend = _FacingBackend(["right"])
    executor, harness = _build(tmp_path, backend)

    artifacts = await executor._generate_reviewed_image_asset(
        _context(tmp_path), _spec(tmp_path, "mob-idle-0")
    )

    assert artifacts == (str(tmp_path / "strip.png"),)
    assert harness.generations == 1
    assert harness.forced == 0
    assert len(backend.facing_requests) == 1
    assert backend.facing_requests[0].schema.name == ACTOR_FACING_SCHEMA_NAME


async def test_a_left_facing_strip_is_regenerated_until_it_faces_right(tmp_path: Path) -> None:
    # The reported defect: the player walked right while facing left. One regeneration clears it.
    backend = _FacingBackend(["left", "right"])
    executor, harness = _build(tmp_path, backend)

    await executor._generate_reviewed_image_asset(
        _context(tmp_path), _spec(tmp_path, "character-master-strip-idle")
    )

    assert harness.generations == 2
    # Without force the rejected art is still on disk and passes every deterministic contract,
    # so the second call would hand back exactly what the reviewer just turned down.
    assert harness.forced == 1
    assert len(backend.facing_requests) == 2


async def test_a_strip_that_stays_wrong_fails_the_stage_with_its_history(tmp_path: Path) -> None:
    backend = _FacingBackend(["left"])
    executor, harness = _build(tmp_path, backend)

    with pytest.raises(ActorFacingError) as caught:
        await executor._generate_reviewed_image_asset(
            _context(tmp_path), _spec(tmp_path, "mob-hurt-2")
        )

    assert f"{_ACTOR_REVIEW_MAXIMUM_REGENERATIONS} semantic regenerations" in str(caught.value)
    assert caught.value.facing == "left"
    assert harness.generations == _ACTOR_REVIEW_MAXIMUM_REGENERATIONS + 1
    assert len(backend.facing_requests) == _ACTOR_REVIEW_MAXIMUM_REGENERATIONS + 1


async def test_an_unconfident_left_reading_never_burns_a_regeneration(tmp_path: Path) -> None:
    # A flower or a featureless golem has no locatable front. Rejecting those would spend a full
    # image generation per attempt and still never resolve.
    backend = _FacingBackend(["left"], confident=False)
    executor, harness = _build(tmp_path, backend)

    await executor._generate_reviewed_image_asset(_context(tmp_path), _spec(tmp_path, "mob-idle-5"))

    assert harness.generations == 1
    assert harness.forced == 0


@pytest.mark.parametrize("stage", ["character-climb", "items", "ladder"])
async def test_stages_without_a_facing_contract_are_never_reviewed(
    tmp_path: Path, stage: str
) -> None:
    # The climb strip is authored rear-facing; reviewing it would reject correct art.
    backend = _FacingBackend(["left"])
    executor, harness = _build(tmp_path, backend)

    await executor._generate_reviewed_image_asset(_context(tmp_path), _spec(tmp_path, stage))

    assert harness.generations == 1
    assert backend.facing_requests == []


async def test_the_reviewer_is_handed_the_strip_and_nothing_about_the_answer(
    tmp_path: Path,
) -> None:
    backend = _FacingBackend(["right"])
    executor, _ = _build(tmp_path, backend)

    await executor._generate_reviewed_image_asset(_context(tmp_path), _spec(tmp_path, "mob-idle-0"))

    request: Any = backend.facing_requests[0]
    assert len(request.references) == 1
    # The generated strip itself, not a description of it.
    assert request.references[0].url.startswith("data:image/png;base64,")
    assert request.references[0].provenance_ref == str(tmp_path / "strip.png")
    # Both sides are offered as plain options. A reviewer told which one is wanted stops
    # producing evidence and starts agreeing.
    prompt = request.prompt.lower()
    assert "'right' when the subject faces the right edge" in prompt
    assert "'left' when it faces the left edge" in prompt
    assert request.schema.strict is True


async def test_a_verdict_is_reused_for_the_bytes_it_was_taken_on(tmp_path: Path) -> None:
    # A resumed run reuses most artwork from cache. Without this it pays a provider call per
    # actor to re-ask a question whose answer cannot have changed.
    backend = _FacingBackend(["right"])
    executor, harness = _build(tmp_path, backend)
    context, spec = _context(tmp_path), _spec(tmp_path, "mob-idle-0")

    await executor._generate_reviewed_image_asset(context, spec)
    assert len(backend.facing_requests) == 1

    await executor._generate_reviewed_image_asset(context, spec)
    assert len(backend.facing_requests) == 1, "identical bytes must not be re-reviewed"
    assert harness.generations == 2


async def test_regenerated_art_never_inherits_the_previous_verdict(tmp_path: Path) -> None:
    backend = _FacingBackend(["right"])
    executor, _ = _build(tmp_path, backend)
    context, spec = _context(tmp_path), _spec(tmp_path, "mob-idle-0")

    await executor._generate_reviewed_image_asset(context, spec)
    assert len(backend.facing_requests) == 1

    # Different artwork at the same path: the digest moves, so the cache must fall through.
    image = Image.new("RGB", (256, 64), (0, 255, 0))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    (tmp_path / "strip.png").write_bytes(buffer.getvalue())
    setattr(executor, "_generate_image_asset", _noop_generate(tmp_path))  # noqa: B010

    await executor._generate_reviewed_image_asset(context, spec)
    assert len(backend.facing_requests) == 2, "new bytes must be reviewed afresh"


def _noop_generate(tmp_path: Path):  # type: ignore[no-untyped-def]
    async def generate(
        _context: StageContext, _spec: _ImageSpec, *, force: bool = False
    ) -> Sequence[str]:
        return (str(tmp_path / "strip.png"),)

    return generate


async def test_an_unreadable_verdict_pair_falls_back_to_a_fresh_review(tmp_path: Path) -> None:
    backend = _FacingBackend(["right"])
    executor, _ = _build(tmp_path, backend)
    context, spec = _context(tmp_path), _spec(tmp_path, "mob-idle-0")

    await executor._generate_reviewed_image_asset(context, spec)
    review = tmp_path / "strip.facing-review.json"
    review.write_text("{ not json", encoding="utf-8")

    await executor._generate_reviewed_image_asset(context, spec)
    assert len(backend.facing_requests) == 2, "a damaged verdict must fail closed, not be trusted"
