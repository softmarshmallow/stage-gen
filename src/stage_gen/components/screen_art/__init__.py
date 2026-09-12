"""Independent screen pictures, reserved-region geometry, and image admission."""

from .layouts import LOADING_SCREEN, OPENING_SHOT, TITLE_SCREEN, Rect
from .layouts import ShellLayout as ScreenLayout
from .models import ImagePlate, ImageReferenceBinding, Typeface, VideoPlate
from .plates import canonicalize_shell_plate as canonicalize_plate
from .plates import shell_plate_evidence as plate_evidence
from .plates import validate_shell_plate as validate_plate
from .service import ScreenPlateRequest

__all__ = [
    "Rect",
    "ScreenLayout",
    "TITLE_SCREEN",
    "LOADING_SCREEN",
    "OPENING_SHOT",
    "ImagePlate",
    "VideoPlate",
    "ImageReferenceBinding",
    "Typeface",
    "ScreenPlateRequest",
    "canonicalize_plate",
    "validate_plate",
    "plate_evidence",
]
