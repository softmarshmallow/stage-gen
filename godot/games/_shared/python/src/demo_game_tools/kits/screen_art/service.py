"""A screen-image request with explicit geometry and an injected image service."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from gnode import ImageGenerationRequest, ImageReference

from .layouts import ShellLayout
from .models import ImagePlate
from .plates import validate_shell_plate


@dataclass(frozen=True, slots=True)
class ScreenPlateRequest:
    """One picture and the optional regions a consumer needs kept quiet."""

    plate: ImagePlate
    layout: ShellLayout
    measured_regions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        unknown = set(self.measured_regions) - set(self.layout.region_names())
        if unknown:
            raise ValueError(
                "screen image names unknown reserved regions: " + ", ".join(sorted(unknown))
            )

    def validate(self, data: bytes) -> dict[str, object]:
        return validate_shell_plate(
            data,
            layout=self.layout,
            alpha_policy=self.plate.alpha_policy,
            measured_regions=self.measured_regions,
        )

    def image_request(
        self, *, artifact_path: Path, references: Sequence[ImageReference]
    ) -> ImageGenerationRequest:
        """Build the provider request; the caller injects the service and retry owner."""

        if len(references) != len(self.plate.reference_ids):
            raise ValueError("screen image requires one bound image per declared reference ID")
        width, height = self.layout.canvas
        regions = [self.layout.drift_union(name).record() for name in self.measured_regions]
        prompt = (
            self.plate.prompt + "\nDraw one image without text, lettering, logos, or watermarks."
        )
        if regions:
            prompt += (
                f" Keep these canvas-pixel regions visually quiet for later composition: {regions}."
            )
        return ImageGenerationRequest(
            prompt=prompt,
            artifact_path=artifact_path,
            input_references=tuple(references),
            size=f"{width}x{height}",
            output_format="png",
            quality="max",
            background="opaque" if self.plate.alpha_policy == "fully_opaque_v1" else "transparent",
            validate=lambda artifact: self.validate(artifact.data),
        )


__all__ = ["ScreenPlateRequest"]
