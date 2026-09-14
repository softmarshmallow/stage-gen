"""Explicit application binding and budgeted endpoint-video service for movie sprites."""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

import httpx

from gnode import (
    ArtifactRights,
    ArtifactValidator,
    Binding,
    BindingTable,
    ModelRef,
    NonRetryableError,
    ProviderVideo,
    RetryPolicy,
    VideoGenerationRequest,
    VideoGenerationResult,
    VideoGenerationService,
    VideoReference,
    VideoResolution,
    inspect_image,
    is_portable_artifact_reference,
)
from gnode.providers.fal import FAL_ENDPOINT_VIDEO_MODEL, FalEndpointVideoBackend
from stage_gen.components.character_3d.budget_pool import BudgetError, BudgetPool
from stage_gen.config import ConfigError, StageGenConfig
from stage_gen.identity import STAGE_GEN_TOOL, VIDEO_GENERATION_COMPONENT
from stage_gen.media.data_url import data_url

# Official endpoint schema and published pricing refreshed on 2026-09-15.
# https://fal.ai/models/google/gemini-omni-flash/v1.1/image-to-video/api
# https://fal.ai/models/google/gemini-omni-flash/v1.1/image-to-video
_PRICE_PER_SECOND = {"360p": "0.03", "720p": "0.10", "1080p": "0.15", "4k": "0.30"}
_OPERATION_ID = re.compile(r"[a-z][a-z0-9_-]{0,79}\Z")


def movie_sprite_video_binding(
    *, duration_seconds: int = 8, resolution: str = "720p", aspect_ratio: str = "9:16"
) -> Binding:
    """Admit the current endpoint contract offline and declare its per-attempt budget."""

    if type(duration_seconds) is not int or not 3 <= duration_seconds <= 10:
        raise ValueError("movie sprite duration_seconds must be an integer from 3 through 10")
    if resolution not in _PRICE_PER_SECOND:
        raise ValueError("movie sprite resolution must be 360p, 720p, 1080p or 4k")
    if aspect_ratio not in {"9:16", "16:9"}:
        raise ValueError("movie sprite aspect_ratio must be 9:16 or 16:9")
    estimate = Decimal(_PRICE_PER_SECOND[resolution]) * duration_seconds
    binding = Binding(
        "video_generation",
        ModelRef(FAL_ENDPOINT_VIDEO_MODEL, "fal"),
        "movie_sprite_video",
        600,
        float(estimate),
        float(estimate * Decimal("1.25")),
        features=frozenset(
            {
                "first_last_frame",
                *(f"resolution:{item}" for item in _PRICE_PER_SECOND),
                "aspect_ratio:9:16",
                "aspect_ratio:16:9",
            }
        ),
        limits=(
            ("clip_seconds_min", 3),
            ("clip_seconds_max", 10),
            ("clip_seconds_step", 1),
            ("prompt_chars_max", 20_000),
        ),
        max_in_flight=1,
        verified_on="2026-09-15",
    )
    BindingTable((binding,)).require(
        "video_generation",
        "first_last_frame",
        f"resolution:{resolution}",
        f"aspect_ratio:{aspect_ratio}",
    )
    return binding


def _reported_cost(result: ProviderVideo) -> Decimal | None:
    value = (result.response_metadata.usage or {}).get("cost")
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        return None
    try:
        cost = Decimal(str(value))
    except InvalidOperation:
        return None
    return cost if cost.is_finite() and cost >= 0 else None


class _BudgetedEndpoint(FalEndpointVideoBackend):
    """One reservation per dispatch; VideoGenerationService alone owns retries."""

    def __init__(self, owner: MovieSpriteVideoService, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.owner = owner
        self.attempt = 0
        self.identity = ""
        self.amount = Decimal(0)
        self.uncertain = False

    async def generate_once(self, request: VideoGenerationRequest) -> ProviderVideo:
        if self.uncertain:
            raise NonRetryableError(
                "Video submission was interrupted; inspect its result before another dispatch",
                code="video_submission_uncertain",
            )
        self.attempt += 1
        reservation_id = f"{self.owner.operation_id}-attempt-{self.attempt}"
        try:
            record = self.owner.budget.reserve(reservation_id, self.identity, self.amount)
            if record["dispatch_started"] or record["status"] != "reserved":
                raise NonRetryableError(
                    "This video candidate was already dispatched; "
                    "inspect existing output or use a new candidate",
                    code="video_candidate_already_dispatched",
                )
            self.owner.budget.mark_started(reservation_id, self.identity)
        except BudgetError as error:
            raise NonRetryableError(str(error), code="video_budget_refused") from None
        self.owner._provider_operations += 1
        try:
            result = await super().generate_once(request)
        except BaseException as error:
            self.owner.budget.settle(
                reservation_id,
                self.identity,
                known_actual_usd="0",
                unresolved_liability_usd=self.amount,
                outcome="interrupted",
            )
            if isinstance(error, asyncio.CancelledError):
                self.uncertain = True
            if isinstance(
                error, (httpx.ReadTimeout, httpx.ReadError, httpx.WriteTimeout, httpx.WriteError)
            ):
                self.uncertain = True
                raise NonRetryableError(
                    "Video submission transport ended without a confirmed result",
                    code="video_submission_uncertain",
                ) from None
            raise
        cost = _reported_cost(result)
        self.owner.budget.settle(
            reservation_id,
            self.identity,
            known_actual_usd=cost if cost is not None else "0",
            unresolved_liability_usd="0" if cost is not None else self.amount,
            outcome="completed",
        )
        if cost is not None:
            self.owner._known_cost += cost
            self.owner._has_reported_cost = True
        return result


class MovieSpriteVideoService:
    """Caller-owned live host; configuration comes from the existing allowlisted loader.

    Each instance represents one deliberately named candidate. Reusing a dispatched
    candidate is refused, including after a process restart. Unknown charges retain
    their reservation; published pricing is never presented as a reported invoice.
    """

    def __init__(
        self,
        config: StageGenConfig,
        budget: BudgetPool,
        *,
        live: bool,
        operation_id: str = "movie-sprite-video",
        client: httpx.AsyncClient | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        if not live:
            raise ValueError("movie sprite provider execution requires explicit live opt-in")
        if not config.fal_key:
            raise ConfigError(("FAL_KEY",))
        if not _OPERATION_ID.fullmatch(operation_id):
            raise ValueError("operation_id must be a lowercase non-path candidate identifier")
        self.operation_id = operation_id
        self.budget = budget
        self._provider_operations = 0
        self._known_cost = Decimal(0)
        self._has_reported_cost = False
        self._lock = asyncio.Lock()
        self._timeout = config.capability_timeout_s
        self._backend = _BudgetedEndpoint(
            self,
            api_key=config.fal_key,
            model=FAL_ENDPOINT_VIDEO_MODEL,
            base_url=config.fal_base_url or "https://fal.run",
            client=client,
        )
        self._service = VideoGenerationService(
            self._backend,
            component=VIDEO_GENERATION_COMPONENT,
            tool=STAGE_GEN_TOOL,
            retry_policy=retry_policy,
        )

    @property
    def provider_operations(self) -> int:
        return self._provider_operations

    @property
    def known_cost_usd(self) -> float | None:
        return float(self._known_cost) if self._has_reported_cost else None

    def budget_snapshot(self) -> dict[str, Any]:
        return self.budget.snapshot()

    @contextmanager
    def _candidate_lock(self) -> Iterator[None]:
        """Reserve/start must not race with another host using the same candidate."""

        if any(path.is_symlink() for path in (self.budget.root, *self.budget.root.parents)):
            raise ValueError("movie sprite budget root cannot contain symlinks")
        descriptor = os.open(
            self.budget.root / f"{self.operation_id}.video.lock",
            os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
            0o600,
        )
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise NonRetryableError(
                    "This video candidate is already running", code="video_candidate_running"
                ) from None
            yield
        finally:
            os.close(descriptor)

    async def generate(
        self,
        prompt: str,
        endpoint: bytes,
        *,
        duration_seconds: int,
        resolution: str,
        aspect_ratio: str,
        artifact_path: Path,
        rights: ArtifactRights | None = None,
        endpoint_ref: str = "body/endpoint.png",
        validate: ArtifactValidator | None = None,
    ) -> VideoGenerationResult:
        binding = movie_sprite_video_binding(
            duration_seconds=duration_seconds,
            resolution=resolution,
            aspect_ratio=aspect_ratio,
        )
        if not prompt.strip():
            raise ValueError("movie sprite prompt must be non-empty")
        binding.within("prompt_chars_max", len(prompt), subject="video prompt")
        if not is_portable_artifact_reference(endpoint_ref):
            raise ValueError("endpoint_ref must be a portable artifact reference")
        if not endpoint or len(endpoint) > 32 * 1024 * 1024:
            raise ValueError("prepared endpoint must contain between 1 byte and 32 MiB")
        facts = inspect_image(endpoint)
        reference = VideoReference(
            url=data_url(endpoint, facts.media_type), provenance_ref=endpoint_ref
        )
        identity = hashlib.sha256(
            json.dumps(
                {
                    "prompt": prompt,
                    "endpoint_sha256": hashlib.sha256(endpoint).hexdigest(),
                    "duration_seconds": duration_seconds,
                    "resolution": resolution,
                    "aspect_ratio": aspect_ratio,
                    "model": str(binding.model),
                    "reference_roles": ["start_frame", "end_frame"],
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        async with self._lock:
            with self._candidate_lock():
                self._backend.attempt = 0
                self._backend.identity = identity
                self._backend.amount = (
                    Decimal(_PRICE_PER_SECOND[resolution]) * duration_seconds * Decimal("1.25")
                )
                return await self._service.generate(
                    VideoGenerationRequest(
                        prompt=prompt,
                        artifact_path=artifact_path,
                        start_frame=reference,
                        end_frame=reference,
                        duration_seconds=duration_seconds,
                        resolution=cast(VideoResolution, resolution),
                        aspect_ratio=aspect_ratio,
                        rights=rights,
                        timeout_seconds=self._timeout,
                        validate=validate,
                        metadata={"candidate_id": self.operation_id},
                    )
                )

    async def aclose(self) -> None:
        await self._service.aclose()
