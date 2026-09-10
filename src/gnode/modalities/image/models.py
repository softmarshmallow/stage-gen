from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import ClassVar, Literal, Protocol, cast

from gnode.modalities._types import (
    ArtifactValidator,
    ProviderResponseMetadata,
    validate_optional_timeout,
)
from gnode.reliability import CancellationToken
from gnode.routes import ResolvedBindingV1

ImageQuality = Literal["auto", "low", "medium", "high", "xhigh", "max"]
ImageBackground = Literal["auto", "opaque", "transparent"]
ImageOutputFormat = Literal["png", "jpeg", "webp"]
ImageModeration = Literal["auto", "low"]
ImageResolution = Literal["512", "1K", "2K", "4K"]
ImageOperationVariant = Literal["generation", "edit"]
ImageQualityGoal = Literal["maximum_verified"]
ImageModerationGoal = Literal["low_when_supported"]
ImageReferenceDelivery = Literal["data_url", "hosted_url", "mixed"]

_REFERENCE_RE = re.compile(r"^(?:https?://|data:image/[^;,]+;base64,)", re.IGNORECASE)
_ASPECT_RE = re.compile(r"^[1-9]\d*:[1-9]\d*$")
_SIZE_RE = re.compile(r"^[1-9]\d*x[1-9]\d*$")


@dataclass(frozen=True, slots=True)
class ImageReference:
    url: str
    provenance_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.url.strip():
            raise ValueError("image reference url must be non-empty")
        if not _REFERENCE_RE.match(self.url):
            raise ValueError("image references must be HTTP(S) URLs or base64 image data URLs")


@dataclass(frozen=True, slots=True)
class PromptAnchor:
    """One exact clause appended to a prompt idempotently and recorded verbatim.

    The engine knows nothing about what the clause means - an application
    compiles its own vocabulary (a style anchor, a house rule) into the
    rendered ``clause``, a ``marker`` substring that identifies the clause
    family inside a prompt, and the ``provenance`` block recorded under
    ``provenance_key`` in the artifact's params. Key order in ``provenance``
    is preserved into the persisted bytes.
    """

    clause: str
    marker: str
    provenance_key: str
    provenance: Mapping[str, object]

    def __post_init__(self) -> None:
        if not self.clause.strip():
            raise ValueError("prompt anchor clause must be non-empty")
        if not self.marker.strip() or self.marker not in self.clause:
            raise ValueError("prompt anchor marker must be a substring of its clause")
        if not self.provenance_key.strip():
            raise ValueError("prompt anchor provenance_key must be non-empty")


def append_prompt_anchor_once(prompt: str, anchor: PromptAnchor) -> str:
    """Append the anchor clause idempotently and reject conflicting pre-anchors."""

    occurrences = prompt.count(anchor.marker)
    if occurrences == 0:
        return f"{prompt.rstrip()}\n\n{anchor.clause}"
    if occurrences == 1 and anchor.clause in prompt:
        return prompt
    raise ValueError("prompt already contains a different or malformed anchor")


@dataclass(frozen=True, slots=True)
class ImageGenerationRequest:
    prompt: str
    artifact_path: str | Path
    input_references: tuple[ImageReference, ...] = ()
    #: Optional inpainting mask. Transparent areas mark the editable region. Providers without a
    #: real masked-edit route must reject it rather than silently ignoring it.
    mask_reference: ImageReference | None = None
    aspect_ratio: str | None = None
    quality: ImageQuality | None = None
    background: ImageBackground | None = None
    output_format: ImageOutputFormat | None = None
    output_compression: int | None = None
    moderation: ImageModeration | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    timeout_seconds: float | None = None
    cancellation: CancellationToken | None = None
    validate: ArtifactValidator | None = None
    provenance_schema_version: Literal[2] = 2
    prompt_anchor: PromptAnchor | None = None
    resolution: ImageResolution | None = None
    size: str | None = None
    #: The exact route and effective option snapshot admitted by planning. Legacy
    #: standalone callers may omit it; a binding-driven runtime must require it.
    resolved_binding: ResolvedBindingV1 | None = None

    def __post_init__(self) -> None:
        if not self.prompt.strip():
            raise ValueError("image prompt must be non-empty")
        if not str(self.artifact_path).strip():
            raise ValueError("artifact_path must be non-empty")
        if self.aspect_ratio not in {None, "auto"} and not _ASPECT_RE.fullmatch(
            self.aspect_ratio or ""
        ):
            raise ValueError(
                "aspect_ratio must be auto or two positive integers separated by a colon"
            )
        if self.output_compression is not None and (
            isinstance(self.output_compression, bool)
            or not isinstance(self.output_compression, int)
            or not 0 <= self.output_compression <= 100
        ):
            raise ValueError("output_compression must be an integer from 0 to 100")
        if self.output_compression is not None and self.output_format not in {"jpeg", "webp"}:
            raise ValueError("output_compression requires explicit jpeg or webp output")
        if self.resolution not in (None, "512", "1K", "2K", "4K"):
            raise ValueError("resolution must be 512, 1K, 2K, or 4K")
        if self.quality not in {None, "auto", "low", "medium", "high", "xhigh", "max"}:
            raise ValueError("quality must be auto, low, medium, high, xhigh, or max")
        if self.background not in {None, "auto", "opaque", "transparent"}:
            raise ValueError("background must be auto, opaque, or transparent")
        if self.output_format not in {None, "png", "jpeg", "webp"}:
            raise ValueError("output_format must be png, jpeg, or webp")
        if self.background == "transparent" and self.output_format not in {None, "png", "webp"}:
            raise ValueError("transparent background requires png or webp output")
        if self.size not in {None, "auto"} and not _SIZE_RE.fullmatch(self.size or ""):
            raise ValueError("size must be auto or WIDTHxHEIGHT with positive integer edges")
        if self.moderation not in {None, "auto", "low"}:
            raise ValueError("moderation must be auto or low")
        validate_optional_timeout(self.timeout_seconds)
        if self.provenance_schema_version != 2:
            raise ValueError("provenance_schema_version must be 2")


@dataclass(frozen=True, slots=True)
class ImageRouteRequirementsV1:
    """Typed image intent normalized by a host policy before ring-0 resolution.

    Stable asset intent lives here; provider-native values do not. In
    particular, ``maximum_verified`` is resolved by the host to an exact value
    such as ``max`` and is then sealed into ``ResolvedBindingV1.output_options``.
    """

    operation_variant: ImageOperationVariant
    background: ImageBackground
    output_format: ImageOutputFormat
    size: str | None = None
    aspect_ratio: str | None = None
    resolution: ImageResolution | None = None
    output_compression: int | None = None
    reference_count: int = 0
    mask_present: bool = False
    reference_delivery: ImageReferenceDelivery | None = None
    quality_goal: ImageQualityGoal | None = "maximum_verified"
    moderation_goal: ImageModerationGoal | None = "low_when_supported"

    def __post_init__(self) -> None:
        # Reuse the public request's field validation without inventing a second
        # set of size/format rules. The placeholder is never dispatched.
        ImageGenerationRequest(
            prompt="route-requirement-validation",
            artifact_path="unused",
            aspect_ratio=self.aspect_ratio,
            resolution=self.resolution,
            background=self.background,
            output_format=self.output_format,
            output_compression=self.output_compression,
            size=self.size,
        )
        exact_size = self.size
        explicit_ratio = self.aspect_ratio
        if explicit_ratio is not None and explicit_ratio != "auto":
            ratio_width_text, ratio_height_text = explicit_ratio.split(":")
            ratio_width, ratio_height = int(ratio_width_text), int(ratio_height_text)
        if exact_size is not None and exact_size != "auto":
            if self.resolution is not None:
                raise ValueError("image resolution cannot be combined with an exact size")
            if explicit_ratio is not None and explicit_ratio != "auto":
                width_text, height_text = exact_size.split("x")
                width, height = int(width_text), int(height_text)
                if width * ratio_height != height * ratio_width:
                    raise ValueError("exact image size does not match aspect_ratio")
        if (
            isinstance(self.reference_count, bool)
            or not isinstance(self.reference_count, int)
            or self.reference_count < 0
        ):
            raise ValueError("image reference_count must be a non-negative integer")
        if self.operation_variant == "generation" and self.reference_count:
            raise ValueError("image generation requirements cannot declare references")
        if self.operation_variant == "edit" and self.reference_count < 1:
            raise ValueError("image edit requirements need at least one reference")
        if self.mask_present and self.operation_variant != "edit":
            raise ValueError("an image mask requires the edit operation variant")
        if self.reference_delivery not in {None, "data_url", "hosted_url", "mixed"}:
            raise ValueError("image reference_delivery must be data_url, hosted_url, or mixed")
        if self.reference_count == 0:
            if self.reference_delivery is not None:
                raise ValueError("image generation cannot declare reference delivery")
        elif self.reference_delivery is None:
            # Data URLs are the portable in-process default. Callers planning
            # concrete hosted inputs must declare that delivery shape; deriving
            # from a request classifies it exactly.
            object.__setattr__(self, "reference_delivery", "data_url")

    @property
    def required_features(self) -> frozenset[str]:
        features = {
            "authored_prompt_passthrough",
            f"{self.background}_background",
            f"{self.output_format}_output",
            "text_to_image" if self.operation_variant == "generation" else "reference_images",
        }
        if self.quality_goal == "maximum_verified":
            features.add("maximum_quality")
        if self.size not in {None, "auto"}:
            features.add("exact_size")
        else:
            features.add("flexible_size")
        if self.resolution is not None:
            features.add("resolution_ladder")
        if self.mask_present:
            features.add("masked_edit")
        if self.reference_delivery in {"data_url", "mixed"}:
            features.add("data_url_reference_input")
        if self.reference_delivery in {"hosted_url", "mixed"}:
            features.add("hosted_url_reference_input")
        return frozenset(features)

    def semantic_options(self) -> dict[str, object]:
        """Canonical provider-neutral values whose exact mapping must be sealed."""

        options: dict[str, object] = {
            "operation_variant": self.operation_variant,
            "background": self.background,
            "output_format": self.output_format,
            "reference_count": self.reference_count,
            "mask_present": self.mask_present,
            "prompt_policy": "authored_verbatim",
        }
        if self.quality_goal is not None:
            options["quality_goal"] = self.quality_goal
        if self.size is not None:
            options["size"] = self.size
        if self.aspect_ratio is not None:
            options["aspect_ratio"] = self.aspect_ratio
        if self.resolution is not None:
            options["resolution"] = self.resolution
        if self.output_compression is not None:
            options["output_compression"] = self.output_compression
        if self.moderation_goal is not None:
            options["moderation_goal"] = self.moderation_goal
        if self.reference_delivery is not None:
            options["reference_delivery"] = self.reference_delivery
        return options

    @classmethod
    def from_request(cls, request: ImageGenerationRequest) -> ImageRouteRequirementsV1:
        return cls(
            operation_variant="edit" if request.input_references else "generation",
            background=request.background or "auto",
            output_format=request.output_format or "png",
            size=request.size,
            aspect_ratio=request.aspect_ratio,
            resolution=request.resolution,
            output_compression=request.output_compression,
            reference_count=len(request.input_references),
            mask_present=request.mask_reference is not None,
            reference_delivery=classify_image_reference_delivery(
                (
                    *request.input_references,
                    *((request.mask_reference,) if request.mask_reference is not None else ()),
                )
            ),
            quality_goal="maximum_verified" if request.quality == "max" else None,
            moderation_goal=("low_when_supported" if request.moderation in {None, "low"} else None),
        )


def apply_resolved_image_binding(
    request: ImageGenerationRequest,
    binding: ResolvedBindingV1,
    *,
    allowed_extension_options: frozenset[str] = frozenset(),
) -> ImageGenerationRequest:
    """Apply only the exact image values sealed by planning and bind the route.

    The application service registry calls this immediately before handing a
    request to the retry-owning service. Unknown option keys or a semantic
    action mismatch are refusals, never silently ignored provider defaults.
    """

    options = dict(binding.request.output_options)
    requirements = ImageRouteRequirementsV1.from_request(request)
    for name, value in requirements.semantic_options().items():
        if options.get(name) != value:
            raise ValueError(f"resolved image semantic option {name} does not match the request")
    allowed = {
        "operation_variant",
        "quality",
        "quality_goal",
        "background",
        "output_format",
        "output_compression",
        "moderation",
        "moderation_goal",
        "aspect_ratio",
        "resolution",
        "size",
        "reference_count",
        "reference_delivery",
        "mask_present",
        "prompt_policy",
    } | allowed_extension_options
    unknown = sorted(set(options) - allowed)
    if unknown:
        raise ValueError("resolved image binding carries unknown options: " + ", ".join(unknown))
    actual_variant = "edit" if request.input_references else "generation"
    if options.get("operation_variant") != actual_variant:
        raise ValueError("resolved image operation variant does not match the request")
    if options.get("reference_count") != len(request.input_references):
        raise ValueError("resolved image reference count does not match the request")
    if options.get("mask_present") != (request.mask_reference is not None):
        raise ValueError("resolved image mask presence does not match the request")
    if options.get("prompt_policy") != "authored_verbatim":
        raise ValueError("resolved image route must preserve the authored prompt")

    def optional(name: str, allowed_values: set[str]) -> str | None:
        value = options.get(name)
        if value is None:
            return None
        if not isinstance(value, str) or value not in allowed_values:
            raise ValueError(f"resolved image {name} is invalid")
        return value

    compression = options.get("output_compression")
    if compression is not None and (
        isinstance(compression, bool)
        or not isinstance(compression, int)
        or not 0 <= compression <= 100
    ):
        raise ValueError("resolved image output_compression is invalid")
    size = options.get("size")
    aspect_ratio = options.get("aspect_ratio")
    resolution = options.get("resolution")
    for name, value in (("size", size), ("aspect_ratio", aspect_ratio), ("resolution", resolution)):
        if value is not None and not isinstance(value, str):
            raise ValueError(f"resolved image {name} is invalid")

    return replace(
        request,
        quality=cast(
            ImageQuality | None,
            optional("quality", {"auto", "low", "medium", "high", "xhigh", "max"}),
        ),
        background=cast(
            ImageBackground | None,
            optional("background", {"auto", "opaque", "transparent"}),
        ),
        output_format=cast(
            ImageOutputFormat | None,
            optional("output_format", {"png", "jpeg", "webp"}),
        ),
        output_compression=compression,
        moderation=cast(
            ImageModeration | None,
            optional("moderation", {"auto", "low"}),
        ),
        aspect_ratio=cast(str | None, aspect_ratio),
        resolution=cast(ImageResolution | None, resolution),
        size=cast(str | None, size),
        resolved_binding=binding,
    )


def classify_image_reference_delivery(
    references: tuple[ImageReference, ...],
) -> ImageReferenceDelivery | None:
    """Classify every provider-visible image or mask reference by delivery shape."""

    if not references:
        return None
    kinds = {
        "data_url" if reference.url.lower().startswith("data:image/") else "hosted_url"
        for reference in references
    }
    if len(kinds) == 1:
        return cast(ImageReferenceDelivery, next(iter(kinds)))
    return "mixed"


@dataclass(frozen=True, slots=True)
class ProviderImage:
    data: bytes
    media_type: str
    response_metadata: ProviderResponseMetadata
    applied_params: Mapping[str, object] | None = None


class ImageModelV1(Protocol):
    """The v1 image model spec: one attempt, no loop, injected credentials."""

    spec_version: ClassVar[Literal[1]]
    provider: str
    model: str
    adapter_id: str
    adapter_behavior_version: str
    secrets: tuple[str, ...]
    supports_native_alpha: bool

    def endpoint_for(self, request: ImageGenerationRequest) -> str: ...

    async def generate_once(self, request: ImageGenerationRequest) -> ProviderImage: ...

    async def aclose(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ImageGenerationResult:
    data: bytes
    media_type: str
    provider: str
    model: str
    attempts: int
    provenance_path: str
    response_metadata: ProviderResponseMetadata

    @property
    def bytes(self) -> bytes:
        return self.data
