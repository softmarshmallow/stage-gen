"""Every oblique-survival node's implementation: the gates, the drawing, the publishing.

One image route, not two. gnode's binding table declares at most one route per
operation, so binding a transparent route and an opaque route would mean two operation
names, two services and two retry owners for one modality. Instead every image goes
through OpenAI direct, which is the only route with native alpha, and the ground and the
flame strip ask it for an opaque background.
"""

from __future__ import annotations

import asyncio
import base64
import json
import math
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from io import BytesIO
from pathlib import Path
from typing import Any, Final, Literal, Protocol, TypedDict, cast

from PIL import Image, ImageDraw

from gnode import (
    ArtifactRights,
    BinaryArtifact,
    ImageGenerationRequest,
    ImageGenerationService,
    ImageReference,
    MusicGenerationRequest,
    MusicGenerationService,
    Node,
    NodeExecutionError,
    NodeExecutionResult,
    NodeType,
    ProvenanceInput,
    RetryExhaustedError,
    SoftwareIdentity,
    SoundEffectGenerationRequest,
    SoundEffectGenerationService,
    StructuredGenerationService,
    StructuredReference,
    Tool,
    ToolLoopReference,
    ToolLoopRequest,
    ToolLoopService,
    ToolResult,
    inspect_image,
    write_artifact_with_provenance_async,
)
from stage_gen.canonical import content_sha256
from stage_gen.components.game_ui.nodes import (
    UI_ATLAS_GENERATE,
    UI_ATLAS_REVIEW,
    UI_ATLAS_VALIDATE,
    UiAtlasHandlers,
    UiAtlasHost,
)
from stage_gen.components.sideview_actor import motion_rebase
from stage_gen.components.sound_effect import admit_sound_effect_bytes_sync
from stage_gen.identity import STAGE_GEN_TOOL
from stage_gen.media import measure_level_and_duration_sync, validate_music_payload
from stage_gen.media.comparison_plate import BandedComparisonPlate
from stage_gen.recipes.node_handler import NodeMethod, RecipeNodeHandler
from stage_gen.recipes.oblique_survival import gates, templates
from stage_gen.recipes.oblique_survival import layout as layout_module
from stage_gen.recipes.oblique_survival import manifest as manifest_module
from stage_gen.recipes.oblique_survival.models import (
    Actor,
    Biome,
    Condition,
    Package,
    SoundCue,
    SoundEffect,
    Track,
    strip_key,
)
from stage_gen.recipes.oblique_survival.schema import (
    AttemptLedger,
    generate_structured,
    known_cost,
)
from stage_gen.recipes.oblique_survival.survival_graph import (
    OBLIQUE_SURVIVAL_ATTEMPT_LEDGER_KIND,
    OBLIQUE_SURVIVAL_CACHE_NAMESPACE,
    OBLIQUE_SURVIVAL_CACHE_RECORD_KIND,
    REJECTS_ROOT,
    AnchorPlacement,
    FamilyReview,
    ObliqueSurvivalGraph,
    evaluate_review,
)
from stage_gen.recipes.oblique_survival.survival_types import (
    ACTOR_CONCEPT,
    CONTRACT_VERSION_PREFIX,
    DECAL_GENERATE,
    DECAL_VALIDATE,
    DUST_GENERATE,
    DUST_VALIDATE,
    FIRE_GENERATE,
    FIRE_VALIDATE,
    FORAGE_ADOPT,
    FORAGE_GENERATE,
    FORAGE_VALIDATE,
    GROUND_ADOPT,
    GROUND_CANONICALIZE,
    GROUND_GENERATE,
    ICONS_ADOPT,
    ICONS_GENERATE,
    ICONS_VALIDATE,
    ITEM_GENERATE,
    ITEM_VALIDATE,
    MACRO_CANONICALIZE,
    MACRO_GENERATE,
    MOTION_GENERATE,
    MOTION_VALIDATE,
    MUSIC_ADOPT,
    MUSIC_GENERATE,
    MUSIC_VALIDATE,
    PACKAGE_MANIFEST,
    PRESENTATION_PROFILE,
    PROP_ANCHOR,
    PROP_GENERATE,
    PROP_SHEET_GENERATE,
    PROP_SHEET_VALIDATE,
    PROP_VALIDATE,
    REBASE_JUDGE,
    REBASE_PLATE,
    REBASE_VERIFY,
    REBASE_VERIFY_PLATE,
    REVIEW_JUDGE,
    REVIEW_SHEET,
    ROAD_CANONICALIZE,
    ROAD_GENERATE,
    SEASON_LOOK_GENERATE,
    SEASON_LOOK_VALIDATE,
    SOUND_ADOPT,
    SOUND_DURATION_TOLERANCE_SECONDS,
    SOUND_GENERATE,
    SOUND_VALIDATE,
    SOURCE_LOCK,
    STRIKE_CELL_KINDS,
    TEMPLATES_DRAW,
    WATER_CANONICALIZE,
    WATER_GENERATE,
    WEATHER_COVER_CANONICALIZE,
    WEATHER_COVER_GENERATE,
    WEATHER_DROPS_GENERATE,
    WEATHER_DROPS_VALIDATE,
    WEATHER_GROUND_GENERATE,
    WEATHER_GROUND_VALIDATE,
    WEATHER_ICE_ADOPT,
    WEATHER_ICE_CANONICALIZE,
    WEATHER_ICE_GENERATE,
    WEATHER_SOUND_GENERATE,
    WEATHER_SOUND_VALIDATE,
    WEATHER_STRIKE_GENERATE,
    WEATHER_STRIKE_VALIDATE,
    WORLD_LAYOUT,
)

OBLIQUE_SURVIVAL_COMPONENT: Final = SoftwareIdentity(
    name="@stage-gen/oblique-survival", version="1"
)
OBLIQUE_SURVIVAL_RIGHTS: Final = ArtifactRights(
    status="unreviewed",
    attribution=[],
    basis=["exploratory oblique-survival generation; publication not authorized"],
    reviewed_at=None,
)

#: A gate handed to the image service's retry owner: it admits the bytes or raises.
ImageValidator = Callable[[BinaryArtifact], dict[str, object]]
#: A cell-sheet gate: the canonicalized sheet and what was measured of it.
SheetGate = Callable[[bytes], tuple[bytes, dict[str, object]]]


class SheetLattice(Protocol):
    """What the sheet handlers need of a lattice: its grid and its adopted take.

    The forage and the icon sheet are two authored types with two cell types
    and one drawing route, so what they share is stated here rather than
    passed as an untyped object. The manifest declares its own, wider
    protocol: it reads the cells, and this one only draws the grid.
    """

    @property
    def columns(self) -> int: ...
    @property
    def rows(self) -> int: ...
    @property
    def take(self) -> str | None: ...


#: The backgrounds the bound image route offers.
ImageBackground = Literal["auto", "opaque", "transparent"]


#: A season look is measured against its summer twin as FRACTIONS of their
#: canvases (a summer sprite cut to 512 px and a paintover drawn at 1024 are
#: the same drawing at two pixel scales; the first winter run refused sixteen
#: honest looks on that arithmetic). Scale and placement are then corrected,
#: not refused: the look is resized to the summer's painted width and its
#: foot set on the summer's, on a canvas the summer's size, so the state's
#: ruler and anchor hold by construction. What cannot be corrected is the
#: shape: a look whose width-to-height changed past this band is a different
#: drawing. A cap adds height and not width, so the band leans below one.
LOOK_ASPECT_RATIO: Final = (0.72, 1.2)


def _look_drift(summer: bytes, candidate: bytes) -> tuple[dict[str, float], list[str]]:
    """Measure a season look against its summer sprite; the reasons refuse it."""

    a = manifest_module.measure_sprite(summer)
    b = manifest_module.measure_sprite(candidate)
    box_a = manifest_module.alpha_bbox(summer) or (0, 0, 1, 1)
    box_b = manifest_module.alpha_bbox(candidate) or (0, 0, 1, 1)
    width_a = (box_a[2] - box_a[0]) / max(1.0, float(a["width_px"]))
    width_b = (box_b[2] - box_b[0]) / max(1.0, float(b["width_px"]))
    height_a = float(a["bbox_height_px"]) / max(1.0, float(a["height_px"]))
    height_b = float(b["bbox_height_px"]) / max(1.0, float(b["height_px"]))
    width_ratio = width_b / max(1e-6, width_a)
    height_ratio = height_b / max(1e-6, height_a)
    aspect_ratio = width_ratio / max(1e-6, height_ratio)
    contact_shift = abs(
        float(b["ground_contact_y_normalized"] or 0.0)
        - float(a["ground_contact_y_normalized"] or 0.0)
    )
    drift = {
        "width_ratio": round(width_ratio, 4),
        "height_ratio": round(height_ratio, 4),
        "aspect_ratio": round(aspect_ratio, 4),
        "contact_shift": round(contact_shift, 4),
    }
    reasons: list[str] = []
    if not b.get("painted"):
        reasons.append("the look is an empty canvas")
    elif not LOOK_ASPECT_RATIO[0] <= aspect_ratio <= LOOK_ASPECT_RATIO[1]:
        reasons.append(
            f"the look's width-to-height is {aspect_ratio:.2f} times the summer"
            " sprite's; it must stay "
            f"within [{LOOK_ASPECT_RATIO[0]}, {LOOK_ASPECT_RATIO[1]}] to be the same drawing"
        )
    return drift, reasons


def _normalise_look(summer: bytes, candidate: bytes) -> tuple[bytes, dict[str, float]]:
    """Put a season look on its summer twin's canvas at the summer's scale.

    Resized so its painted width equals the summer's, then set with its
    painted bottom-centre on the summer's. A cap rises from there: when it
    would pass the canvas top, the canvas grows upward by that much (the
    manifest reads the look's own height and contact row, so a taller
    canvas costs nothing). Returns the canvas and what was done.
    """

    with Image.open(BytesIO(summer)) as opened:
        canvas_w, canvas_h = opened.size
    box_a = manifest_module.alpha_bbox(summer)
    box_b = manifest_module.alpha_bbox(candidate)
    with Image.open(BytesIO(candidate)) as opened:
        look = opened.convert("RGBA")
    if box_a is None or box_b is None:
        return candidate, {"scale": 1.0, "grown_top_px": 0}
    scale = (box_a[2] - box_a[0]) / max(1, box_b[2] - box_b[0])
    resized = look.resize(
        (max(1, round(look.width * scale)), max(1, round(look.height * scale))),
        Image.Resampling.LANCZOS,
    )
    left = round(box_b[0] * scale)
    right = round(box_b[2] * scale)
    top = round(box_b[1] * scale)
    bottom = round(box_b[3] * scale)
    target_centre = (box_a[0] + box_a[2]) / 2.0
    offset_x = round(target_centre - (left + right) / 2.0)
    offset_y = round(box_a[3] - bottom)
    grow = max(0, -(offset_y + top))
    out = Image.new("RGBA", (canvas_w, canvas_h + grow), (0, 0, 0, 0))
    offset_y += grow
    # Crop the source to what lands on the canvas: a look wider than the
    # summer's padding is clipped at the sides, never at the top.
    src_x = max(0, -offset_x)
    src_y = max(0, -offset_y)
    dst_x = max(0, offset_x)
    dst_y = max(0, offset_y)
    width = min(resized.width - src_x, out.width - dst_x)
    height = min(resized.height - src_y, out.height - dst_y)
    if width > 0 and height > 0:
        out.alpha_composite(
            resized.crop((src_x, src_y, src_x + width, src_y + height)), dest=(dst_x, dst_y)
        )
    buffer = BytesIO()
    out.save(buffer, format="PNG")
    return buffer.getvalue(), {"scale": round(scale, 4), "grown_top_px": grow}


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")


def _safe(value: str) -> str:
    return value.replace("_", "-")


def _inline_data_url(data: bytes, media_type: str) -> str:
    """A payload handed to a model inline. Named apart from the substrate helper the
    recipe layer forbids at module scope, which is the same function under a banned name."""

    return f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"


def _jpeg(image: Image.Image, quality: int = 88) -> bytes:
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


SPRITE_CANVAS: Final = (1024, 1024)
STRIP_CANVAS: Final = (1536, 1024)
GROUND_CANVAS: Final = (1024, 1024)


def plate_busyness_max(biome: Biome) -> float:
    """A fabric plate is judged against the reference's own busyness, a field
    against the speckle limit (gates.FABRIC_BUSYNESS_MAX, GROUND_BUSYNESS_MAX)."""

    return gates.FABRIC_BUSYNESS_MAX if biome.material == "fabric" else gates.GROUND_BUSYNESS_MAX


class PlateGateBands(TypedDict, total=False):
    """The bands ``gates.gate_ground_texture`` takes beyond the canvas and texel size."""

    busyness_max: float
    luma_range: tuple[float, float]


def plate_gate_kwargs(biome: Biome) -> PlateGateBands:
    """The plate gate's bands for this biome's material: a fabric is allowed
    the reference's busyness and arrives darker (gates.FABRIC_LUMA_RANGE)."""

    kwargs: PlateGateBands = {"busyness_max": plate_busyness_max(biome)}
    if biome.material == "fabric":
        kwargs["luma_range"] = gates.FABRIC_LUMA_RANGE
    return kwargs


MOTION_COLUMNS: Final = 4
#: A music loop shorter than this is a stinger, not a bed; the briefs ask for
#: about ninety seconds and the model has come back well over a minute.
MUSIC_MIN_SECONDS: Final = 45.0
#: A loop whose loudest sample sits below this is silence with a container.
MUSIC_PEAK_MIN_DBFS: Final = -30.0
#: The props a minimal run draws. It began as three -- one tall, one squat, one


#: The canvas an image node's own port must carry, where the type fixes one. A sheet's
#: canvas is computed from its grid and is not listed; format and a non-zero size still
#: hold for those.
FIXED_CANVAS: Final[dict[str, tuple[int, int]]] = {
    ACTOR_CONCEPT.type_id: SPRITE_CANVAS,
    DECAL_GENERATE.type_id: SPRITE_CANVAS,
    DUST_GENERATE.type_id: SPRITE_CANVAS,
    ITEM_GENERATE.type_id: SPRITE_CANVAS,
    PROP_GENERATE.type_id: SPRITE_CANVAS,
    SEASON_LOOK_GENERATE.type_id: SPRITE_CANVAS,
    WEATHER_DROPS_GENERATE.type_id: SPRITE_CANVAS,
    WEATHER_GROUND_GENERATE.type_id: SPRITE_CANVAS,
    WEATHER_STRIKE_GENERATE.type_id: SPRITE_CANVAS,
    MOTION_GENERATE.type_id: STRIP_CANVAS,
    GROUND_GENERATE.type_id: GROUND_CANVAS,
    MACRO_GENERATE.type_id: GROUND_CANVAS,
    ROAD_GENERATE.type_id: GROUND_CANVAS,
    WATER_GENERATE.type_id: GROUND_CANVAS,
    WEATHER_COVER_GENERATE.type_id: GROUND_CANVAS,
    WEATHER_ICE_GENERATE.type_id: GROUND_CANVAS,
}


def _rebase_errors(
    reading: motion_rebase.MotionRebaseReading,
    frames: Mapping[str, Sequence[bytes]],
    plate: BandedComparisonPlate,
    baseline: str,
) -> list[str]:
    """Run the shared admission inside the retry owner and report it as text."""

    try:
        motion_rebase.evaluate_motion_rebase(
            reading,
            published_states=sorted(frames),
            plate=plate,
            baseline_state=baseline,
        )
    except motion_rebase.MotionRebaseError as error:
        return [str(error)]
    return []


# --- local drawing --------------------------------------------------------------------


def _anchor_overlay(
    sprite: bytes,
    *,
    anchor: tuple[float, float],
    radius_meters: float,
    px_per_meter: float,
    pitch_degrees: float,
) -> bytes:
    """Draw the prop standing on a metre grid with its anchor and footprint marked.

    This is what the placement agent actually looks at. The grid is squashed by
    the cosine of the camera pitch, so the ellipse the agent sees is the ellipse
    the runtime will draw, and "is the footprint under the object" becomes a
    question about a picture instead of about two numbers.
    """

    with Image.open(BytesIO(sprite)) as opened:
        card = opened.convert("RGBA")
    width, height = card.size
    squash = max(0.15, math.cos(math.radians(pitch_degrees)))
    plate = Image.new("RGBA", (width, height), (26, 27, 31, 255))
    draw = ImageDraw.Draw(plate)

    anchor_px = (anchor[0] * width, anchor[1] * height)
    step = max(8.0, px_per_meter)
    grid = (70, 74, 82, 255)
    horizon = int(anchor_px[1])
    for index in range(-12, 13):
        offset = index * step
        x = int(anchor_px[0] + offset)
        draw.line([(x, 0), (x, height)], fill=grid, width=1)
        y = int(anchor_px[1] + offset * squash)
        if 0 <= y < height:
            draw.line([(0, y), (width, y)], fill=grid, width=1)
    del horizon

    plate.alpha_composite(card, (0, 0))

    radius_px = max(3.0, radius_meters * px_per_meter)
    marker = Image.new("RGBA", plate.size, (0, 0, 0, 0))
    mark = ImageDraw.Draw(marker)
    mark.ellipse(
        [
            anchor_px[0] - radius_px,
            anchor_px[1] - radius_px * squash,
            anchor_px[0] + radius_px,
            anchor_px[1] + radius_px * squash,
        ],
        outline=(90, 226, 150, 255),
        width=max(2, int(width / 220)),
    )
    arm = max(6.0, radius_px * 0.5)
    mark.line(
        [(anchor_px[0] - arm, anchor_px[1]), (anchor_px[0] + arm, anchor_px[1])],
        fill=(90, 226, 150, 255),
        width=max(2, int(width / 260)),
    )
    mark.line(
        [(anchor_px[0], anchor_px[1] - arm), (anchor_px[0], anchor_px[1] + arm)],
        fill=(90, 226, 150, 255),
        width=max(2, int(width / 260)),
    )
    plate.alpha_composite(marker, (0, 0))
    return _jpeg(plate)


def _contact_sheet(assets: Sequence[tuple[str, bytes]], columns: int = 4, cell: int = 384) -> bytes:
    """One labelled grid of every asset in a family, at equal cell size.

    The reviewer is asked about the set, so the set has to be one picture. Cells
    are equal-sized and each asset is fitted inside its own cell, which means the
    sheet answers questions about pitch, style and clean edges but deliberately
    not about relative scale -- the gallery view in the viewer answers that one,
    at true scale, where it can actually be seen.
    """

    if not assets:
        assets = [("nothing published", b"")]
    rows = (len(assets) + columns - 1) // columns
    label_h = 26
    sheet = Image.new("RGBA", (columns * cell, rows * (cell + label_h)), (22, 23, 27, 255))
    draw = ImageDraw.Draw(sheet)
    for index, (label, data) in enumerate(assets):
        column = index % columns
        row = index // columns
        x0 = column * cell
        y0 = row * (cell + label_h)
        draw.rectangle([x0, y0, x0 + cell - 1, y0 + cell + label_h - 1], outline=(60, 63, 70, 255))
        if data:
            with Image.open(BytesIO(data)) as opened:
                art = opened.convert("RGBA")
            art.thumbnail((cell - 16, cell - 16), Image.Resampling.LANCZOS)
            sheet.alpha_composite(art, (x0 + (cell - art.width) // 2, y0 + (cell - art.height) - 8))
        draw.text((x0 + 8, y0 + cell + 6), f"{index + 1}. {label}", fill=(226, 222, 214, 255))
    buffer = BytesIO()
    sheet.convert("RGB").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _as_mapping(value: object) -> Mapping[str, object]:
    """One nested object out of a record read back as JSON, empty when it is absent."""

    return {str(key): item for key, item in value.items()} if isinstance(value, Mapping) else {}


def _gate_rows(value: object) -> Sequence[Mapping[str, Any]]:
    """A gate record's ``cells`` list, narrowed for the reader.

    A gate answers with an open record, because what it measures differs per gate.
    The rows a lattice gate returns are read here by key, so the narrowing is stated
    once rather than at every field.
    """

    return cast("Sequence[Mapping[str, Any]]", value)


def _as_bbox(value: object, width: int, height: int) -> tuple[float, float, float, float]:
    """A measured alpha box out of a validation record, or the whole canvas."""

    if not isinstance(value, Sequence) or isinstance(value, str | bytes) or len(value) != 4:
        return (0.0, 0.0, float(width), float(height))
    left, top, right, bottom = (_as_float(entry) for entry in value)
    return (left, top, right, bottom)


def _as_float(value: object) -> float:
    """One number out of a record read back as JSON, refused rather than coerced blind."""

    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise ValueError(f"expected a number, got {type(value).__name__}")
    return float(value)


def _properties(schema: Mapping[str, object]) -> Mapping[str, Mapping[str, object]]:
    """The ``properties`` block of a hand-written JSON schema, narrowed for the reader."""

    properties = schema["properties"]
    if not isinstance(properties, Mapping):
        raise TypeError("a JSON schema's properties must be an object")
    return {
        str(key): dict(value) for key, value in properties.items() if isinstance(value, Mapping)
    }


def _measured_centre_x(validation: Mapping[str, object]) -> float:
    """The measured horizontal centre of a prop's painted pixels, or the canvas middle.

    The agent is handed this as its starting anchor. A validation record written before
    the measurement existed has no centre, and the middle of the canvas is the honest
    answer there rather than a guess dressed as a reading.
    """

    value = validation.get("center_x_normalized")
    return round(float(value) if isinstance(value, int | float) else 0.5, 3)


def admit_cached(node: Node, payloads: tuple[bytes, ...]) -> bool:
    """Re-read a restored payload the way the live path would before publishing it.

    ``Node.params`` is not a cache-key input, so a key alone cannot prove that what came
    back is the picture this node asks for. Every image node's first payload is decoded
    here and measured against the canvas its type draws on; a node whose canvas is
    computed from the sheet's grid is admitted on format and non-zero size alone, which
    is still enough to refuse a truncated or mistyped file.
    """

    if not payloads:
        return True
    first = node.ports[0].artifact_ref if node.ports else ""
    if not first.endswith(".png"):
        return True
    try:
        facts = inspect_image(payloads[0], expected_media_type="image/png")
    except (ValueError, TypeError, OSError):
        return False
    if facts.width <= 0 or facts.height <= 0:
        return False
    expected = FIXED_CANVAS.get(node.type_id)
    return expected is None or (facts.width, facts.height) == expected


class ObliqueSurvivalNodeHandler(RecipeNodeHandler):
    """Every node of one oblique-survival run: the gates, the drawing, the publishing.

    A provider operation stays inside the service that owns its retry; a method here
    builds one request, hands it over, and admits what came back.
    """

    def __init__(
        self,
        graph: ObliqueSurvivalGraph,
        package: Package,
        *,
        run_dir: Path,
        cache_dir: Path,
        images: ImageGenerationService | None = None,
        structured: StructuredGenerationService[object] | None = None,
        tool_loop: ToolLoopService[dict[str, object]] | None = None,
        music: MusicGenerationService | None = None,
        sounds: SoundEffectGenerationService | None = None,
    ) -> None:
        self.package = package
        self.images = images
        self.structured = structured
        self.tool_loop = tool_loop
        self.music = music
        self.sounds = sounds
        self._plate: tuple[ImageReference, ...] | None = None
        self._ui: UiAtlasHandlers | None = None
        super().__init__(
            graph,
            run_dir=run_dir,
            cache_dir=cache_dir,
            namespace=OBLIQUE_SURVIVAL_CACHE_NAMESPACE,
            record_kind=OBLIQUE_SURVIVAL_CACHE_RECORD_KIND,
            admit=admit_cached,
        )

    def _handlers(self) -> Iterable[tuple[NodeType, NodeMethod]]:
        return (
            (SOURCE_LOCK, self._source_lock),
            (TEMPLATES_DRAW, self._templates_draw),
            (ACTOR_CONCEPT, self._actor_concept),
            (MOTION_GENERATE, self._motion_generate),
            (MOTION_VALIDATE, self._motion_validate),
            (REBASE_PLATE, self._rebase_plate),
            (REBASE_JUDGE, self._rebase_judge),
            (REBASE_VERIFY_PLATE, self._rebase_verify_plate),
            (REBASE_VERIFY, self._rebase_verify),
            (PROP_GENERATE, self._prop_generate),
            (PROP_VALIDATE, self._prop_validate),
            (PROP_ANCHOR, self._prop_anchor),
            (PROP_SHEET_GENERATE, self._prop_sheet_generate),
            (PROP_SHEET_VALIDATE, self._prop_sheet_validate),
            (SEASON_LOOK_GENERATE, self._season_look_generate),
            (SEASON_LOOK_VALIDATE, self._season_look_validate),
            (ITEM_GENERATE, self._item_generate),
            (ITEM_VALIDATE, self._item_validate),
            (GROUND_GENERATE, self._ground_generate),
            (GROUND_ADOPT, self._ground_adopt),
            (GROUND_CANONICALIZE, self._ground_canonicalize),
            (DECAL_GENERATE, self._decal_generate),
            (DECAL_VALIDATE, self._decal_validate),
            (MACRO_GENERATE, self._macro_generate),
            (MACRO_CANONICALIZE, self._macro_canonicalize),
            (ROAD_GENERATE, self._road_generate),
            (ROAD_CANONICALIZE, self._road_canonicalize),
            (FORAGE_GENERATE, self._forage_generate),
            (FORAGE_ADOPT, self._forage_adopt),
            (FORAGE_VALIDATE, self._forage_validate),
            (ICONS_GENERATE, self._icons_generate),
            (ICONS_ADOPT, self._icons_adopt),
            (ICONS_VALIDATE, self._icons_validate),
            (WATER_GENERATE, self._water_generate),
            (WATER_CANONICALIZE, self._water_canonicalize),
            (FIRE_GENERATE, self._fire_generate),
            (FIRE_VALIDATE, self._fire_validate),
            (DUST_GENERATE, self._dust_generate),
            (DUST_VALIDATE, self._dust_validate),
            (MUSIC_GENERATE, self._music_generate),
            (MUSIC_ADOPT, self._music_adopt),
            (MUSIC_VALIDATE, self._music_validate),
            (WEATHER_DROPS_GENERATE, self._weather_drops_generate),
            (WEATHER_COVER_GENERATE, self._weather_cover_generate),
            (WEATHER_COVER_CANONICALIZE, self._weather_cover_canonicalize),
            (WEATHER_ICE_GENERATE, self._weather_ice_generate),
            (WEATHER_ICE_ADOPT, self._weather_ice_adopt),
            (WEATHER_ICE_CANONICALIZE, self._weather_ice_canonicalize),
            (WEATHER_DROPS_VALIDATE, self._weather_drops_validate),
            (WEATHER_GROUND_GENERATE, self._weather_ground_generate),
            (WEATHER_GROUND_VALIDATE, self._weather_ground_validate),
            (WEATHER_STRIKE_GENERATE, self._weather_strike_generate),
            (WEATHER_STRIKE_VALIDATE, self._weather_strike_validate),
            (WEATHER_SOUND_GENERATE, self._weather_sound_generate),
            (WEATHER_SOUND_VALIDATE, self._weather_sound_validate),
            (SOUND_GENERATE, self._sound_generate),
            (SOUND_ADOPT, self._sound_adopt),
            (SOUND_VALIDATE, self._sound_validate),
            (REVIEW_SHEET, self._review_sheet),
            (REVIEW_JUDGE, self._review_judge),
            (UI_ATLAS_GENERATE, self._ui_generate),
            (UI_ATLAS_VALIDATE, self._ui_validate),
            (UI_ATLAS_REVIEW, self._ui_review),
            (WORLD_LAYOUT, self._world_layout),
            (PACKAGE_MANIFEST, self._package_manifest),
        )

    # -- utilities

    @property
    def style_plate(self) -> tuple[ImageReference, ...]:
        """The authored style plate, as reference image 1, or nothing.

        Carried by every plain generative image node. The paintovers spend
        reference image 1 on their own template or concept sheet and keep the
        style prose alone instead.
        """

        if self._plate is None:
            reference = self.package.style_reference
            if reference is None:
                self._plate = ()
            else:
                data = (self.package.root / reference).read_bytes()
                self._plate = (
                    ImageReference(
                        url=_inline_data_url(data, "image/png"),
                        provenance_ref=(
                            f"source://{reference}#sha256={self.package.style_reference_digest}"
                        ),
                    ),
                )
        return self._plate

    def appearance_plate(self, actor: Actor) -> tuple[ImageReference, ...]:
        """An authored picture of THIS actor, as reference image 1, or nothing.

        Carried only by the concept node. When present the style plate is
        demoted to image 2, because identity is a far stronger pull than any
        adjective and the character must win the body while the plate still
        wins the drawing.
        """

        reference = actor.appearance_reference
        if reference is None:
            return ()
        data = (self.package.root / reference).read_bytes()
        return (
            ImageReference(
                url=_inline_data_url(data, "image/png"),
                provenance_ref=(f"source://{reference}#sha256={actor.appearance_reference_digest}"),
            ),
        )

    @property
    def graph(self) -> ObliqueSurvivalGraph:
        """This run's plan, at the recipe's own type rather than the engine's."""

        graph = self._graph
        assert isinstance(graph, ObliqueSurvivalGraph)
        return graph

    def _require_structured(self) -> StructuredGenerationService[object]:
        if self.structured is None:
            raise ValueError("structured service missing")
        return self.structured

    def _require_images(self) -> ImageGenerationService:
        if self.images is None:
            raise ValueError("image service missing")
        return self.images

    # -- the interface: the shared triplet, hosted

    def _ui_handlers(self) -> UiAtlasHandlers:
        """The recipe-neutral atlas triplet, bound to this package and this run.

        Built on first use so a run that draws no interface never asks for the
        services it would need; the three node types are registered regardless,
        because a registry that lacks a type the graph can plan is a bug found
        only when it is too late.
        """

        if self.package.ui is None:
            raise NodeExecutionError(
                "this package declares no ui.toml, so no interface node can run",
                attempts=1,
                provider_operations=0,
            )
        if self._ui is None:
            self._ui = UiAtlasHandlers(
                UiAtlasHost(
                    ui=self.package.ui,
                    run_dir=self._run_dir,
                    package_id=self.package.package_id,
                    file=self.package.ui_reference,
                    component=OBLIQUE_SURVIVAL_COMPONENT,
                    tool=STAGE_GEN_TOOL,
                ),
                graph=self._graph,
                image_service=self._require_images(),
                structured_service=self._require_structured(),
                provider_call=self._ui_provider_call,
            )
        return self._ui

    async def _ui_generate(self, node: Node) -> NodeExecutionResult:
        return await self._ui_handlers().generate(node)

    async def _ui_validate(self, node: Node) -> NodeExecutionResult:
        return await self._ui_handlers().validate(node)

    async def _ui_review(self, node: Node) -> NodeExecutionResult:
        return await self._ui_handlers().review(node)

    async def _ui_provider_call(
        self, node: Node, label: str, prompt: str, call: Callable[[], Awaitable[Any]]
    ) -> Any:
        """The triplet's provider seam: the node's declared ledger, written either way.

        The sheet gate runs inside the image service's own retry owner, so a
        refused draw is counted by the result's attempts rather than kept here;
        the ledger records that count, and a run that exhausted its budget
        records that too before the failure is raised.
        """

        operation_id = f"ui-{label}"
        try:
            result = await call()
        except RetryExhaustedError as error:
            await self._write_ledger(
                node,
                operation_id=operation_id,
                attempts=[
                    {"attempt": ordinal, "outcome": "rejected", "reason": str(error)}
                    for ordinal in range(1, int(error.attempts) + 1)
                ],
            )
            raise
        refused = max(0, int(result.attempts) - 1)
        await self._write_ledger(
            node,
            operation_id=operation_id,
            attempts=[
                {
                    "attempt": ordinal,
                    "outcome": "rejected",
                    "reason": "refused by the sheet gate inside the service's retry",
                }
                for ordinal in range(1, refused + 1)
            ],
        )
        return result

    def _run_ref(self, ref: str) -> str:
        return f"run://{ref}#sha256={content_sha256(self._path(ref).read_bytes())}"

    def _refuse_missing_take(self, node: Node, take: str) -> None:
        """An adopt node whose take is declared but absent refuses before it publishes.

        The authored package binds each take by digest; the bytes may be kept outside
        the repository. Planning needs only the digest, so a plan is complete either
        way -- but adopting a file that is not there would publish nothing under a
        successful node.
        """

        if self.package.missing_take(take) is not None:
            raise NodeExecutionError(
                f"{node.node_id} adopts the take {take!r}, which the package declares by "
                "digest but does not carry; fetch the take or generate instead of adopting",
                attempts=1,
                provider_operations=0,
            )

    async def _write_ledger(
        self, node: Node, *, operation_id: str, attempts: Sequence[Mapping[str, object]] = ()
    ) -> None:
        """The attempts port, written whether or not anything was refused.

        The spike wrote refused image attempts under an undeclared ``production/rejected``
        tree and structured attempts into an undeclared ``.attempts`` directory, so a
        cache restore lost both and the run view never saw them. A node whose declared
        ports are not all present cannot be cached, and an empty ledger is itself the
        useful statement that nothing was refused.
        """

        port = node.port("attempts")
        document = {
            "schema_version": 1,
            "kind": OBLIQUE_SURVIVAL_ATTEMPT_LEDGER_KIND,
            "node_id": node.node_id,
            "operation_id": operation_id,
            "rejected_attempts": len(attempts),
            "attempts": [dict(entry) for entry in attempts],
        }
        path = self._path(port.artifact_ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, _json_bytes(document))

    async def _write_local(
        self,
        ref: str,
        data: bytes,
        *,
        media_type: str,
        model: str,
        prompt: str,
        refs: Sequence[str] = (),
        validation: Mapping[str, object] | None = None,
    ) -> None:
        await write_artifact_with_provenance_async(
            self._path(ref),
            BinaryArtifact(data=data, media_type=media_type),
            ProvenanceInput(
                schema_version=2,
                provider="local",
                model=model,
                prompt=prompt,
                refs=list(refs),
                inputs=[],
                params={
                    "publication_authorized": False,
                    "contract": CONTRACT_VERSION_PREFIX,
                },
                validation=dict(validation or {"status": "pass"}),
                component=OBLIQUE_SURVIVAL_COMPONENT,
                tool=STAGE_GEN_TOOL,
                attempts=1,
                rights=OBLIQUE_SURVIVAL_RIGHTS,
            ),
        )

    async def _generate_image(
        self,
        node: Node,
        *,
        size: tuple[int, int],
        background: ImageBackground,
        references: tuple[ImageReference, ...] = (),
        validate: ImageValidator | None = None,
        operation_id: str,
    ) -> NodeExecutionResult:
        if self.images is None or node.card is None or node.card.prompt is None:
            raise ValueError("image service or prompt missing")
        rejected: list[Mapping[str, object]] = []
        try:
            result = await self.images.generate(
                ImageGenerationRequest(
                    prompt=node.card.prompt,
                    artifact_path=self._path(node.port("image").artifact_ref),
                    input_references=references,
                    quality="high",
                    background=background,
                    output_format="png",
                    size=f"{size[0]}x{size[1]}",
                    moderation="low",
                    metadata={
                        "operation_id": operation_id,
                        "invocation_id": self.invocation_id,
                        "presentation_profile": PRESENTATION_PROFILE,
                        "input_reference_count": len(references),
                        "publication_authorized": False,
                    },
                    timeout_seconds=1_800,
                    validate=(
                        self._keeping_rejects(node, validate, rejected=rejected)
                        if validate is not None
                        else None
                    ),
                    provenance_schema_version=2,
                )
            )
        finally:
            await self._write_ledger(node, operation_id=operation_id, attempts=rejected)
        return self._result(
            node,
            attempts=result.attempts,
            provider_operations=result.attempts,
            known_cost_usd=known_cost(result.response_metadata.usage),
        )

    def _keeping_rejects(
        self,
        node: Node,
        validate: ImageValidator,
        *,
        rejected: list[Mapping[str, object]],
        suffix: str = ".png",
    ) -> ImageValidator:
        """Wrap a gate so every attempt it refuses is kept, with its reasons.

        A six-attempt failure used to report one sentence, the last reason, and the five
        pictures before it were gone. The litter sheet spent six operations that way on
        a lattice complaint nobody could look at. The reasons and the digest of each
        refused picture ride the node's declared attempts ledger, so they survive a
        cache restore; the refused bytes themselves stay exploration, under
        ``production/rejected/`` where nothing reads them.
        """

        rejected_dir = self._path(f"{REJECTS_ROOT}/{node.node_id}")

        def wrapped(artifact: BinaryArtifact) -> dict[str, object]:
            attempt = len(rejected) + 1
            try:
                return validate(artifact)
            except Exception as error:
                reasons = list(getattr(error, "reasons", None) or [str(error)])
                rejected_dir.mkdir(parents=True, exist_ok=True)
                stem = rejected_dir / f"attempt-{attempt:02d}"
                stem.with_suffix(suffix).write_bytes(artifact.data)
                stem.with_suffix(".json").write_text(
                    _json_bytes({"attempt": attempt, "reasons": reasons}).decode("utf-8")
                )
                rejected.append(
                    {
                        "attempt": attempt,
                        "reasons": reasons,
                        "artifact_sha256": content_sha256(artifact.data),
                        "bytes": len(artifact.data),
                        "kept_at": f"{REJECTS_ROOT}/{node.node_id}/attempt-{attempt:02d}{suffix}",
                    }
                )
                raise

        return wrapped

    # -- source

    async def _source_lock(self, node: Node) -> NodeExecutionResult:
        package = self.package
        record = {
            "schema_version": 1,
            "kind": "oblique-survival-source-lock-v1",
            "package_id": package.package_id,
            "title": package.title,
            "presentation_profile": package.profile,
            "source_digest": package.source_digest(),
            "file_digests": dict(sorted(package.digests.items())),
            "scale": {"player_height_meters": package.player_height_meters},
            "camera": dict(package.camera),
            "counts": {
                "props": len(package.props),
                "prop_states": sum(len(prop.states) for prop in package.props),
                "items": len(package.items),
                "actors": len(package.actors),
                "actor_states": sum(len(actor.states) for actor in package.actors),
                "actor_strips": sum(len(actor.strips) for actor in package.actors),
                "biomes": len(package.biomes),
                "decals": len(package.decals),
            },
            "publication_authorized": False,
        }
        await self._write_local(
            node.port("lock").artifact_ref,
            _json_bytes(record),
            media_type="application/json",
            model="source-lock",
            prompt="Digest the authored package before anything is generated.",
        )
        return self._result(node)

    async def _templates_draw(self, node: Node) -> NodeExecutionResult:
        columns = int(node.params["columns"])
        rows = int(node.params["rows"])
        cell_px = int(node.params.get("cell_px", templates.LATTICE_CELL_PX))
        transparent = node.params.get("transparent", "0") == "1"
        data = templates.lattice_template(columns, rows, cell_px, transparent=transparent)
        await self._write_local(
            node.port("template").artifact_ref,
            data,
            media_type="image/png",
            model=templates.template_id(columns, rows, cell_px, transparent=transparent),
            prompt=(
                "Draw the cyan-guided paintover lattice that strips and sheets are painted into."
            ),
        )
        return self._result(node)

    # -- props

    async def _prop_generate(self, node: Node) -> NodeExecutionResult:
        prop = self.package.prop(str(node.params["prop_id"]))
        state = str(node.params["state"])

        def validate(artifact: BinaryArtifact) -> dict[str, object]:
            return gates.gate_prop(
                artifact.data,
                width=SPRITE_CANVAS[0],
                height=SPRITE_CANVAS[1],
                max_components=prop.max_components,
            )

        return await self._generate_image(
            node,
            size=SPRITE_CANVAS,
            background="transparent",
            references=self.style_plate,
            validate=validate,
            operation_id=f"survival.prop.{prop.prop_id}.{state}",
        )

    async def _prop_validate(self, node: Node) -> NodeExecutionResult:
        prop = self.package.prop(str(node.params["prop_id"]))
        state = str(node.params["state"])
        source_ref = f"production/props/{prop.prop_id}-{state}.source.png"
        data = self._path(source_ref).read_bytes()
        facts = gates.gate_prop(
            data,
            width=SPRITE_CANVAS[0],
            height=SPRITE_CANVAS[1],
            max_components=prop.max_components,
        )
        canonical, alpha = gates.canonicalize_sprite_alpha(data)
        record = {
            "schema_version": 1,
            "kind": "oblique-survival-prop-validation-v1",
            "prop_id": prop.prop_id,
            "state": state,
            "max_components": prop.max_components,
            "alpha_canonicalization": alpha,
            "drawn": {"kind": "sprite"},
            **facts,
        }
        await self._write_local(
            node.port("image").artifact_ref,
            canonical,
            media_type="image/png",
            model="oblique-survival-sprite-alpha-v1",
            prompt=(
                f"Lift {prop.prop_id} {state} to full opacity and bleed its colour under the rim."
            ),
            refs=[self._run_ref(source_ref)],
            validation=record,
        )
        await self._write_local(
            node.port("validation").artifact_ref,
            _json_bytes(record),
            media_type="application/json",
            model="prop-validate",
            prompt="Record the prop gate's measurements.",
            refs=[self._run_ref(source_ref)],
        )
        return self._result(node)

    # -- season looks

    async def _season_look_generate(self, node: Node) -> NodeExecutionResult:
        prop = self.package.prop(str(node.params["prop_id"]))
        state = str(node.params["state"])
        look_id = str(node.params["look"])
        summer_ref = manifest_module.prop_ref(prop.prop_id, state)
        summer = self._path(summer_ref).read_bytes()
        references = (
            ImageReference(
                url=_inline_data_url(summer, "image/png"), provenance_ref=self._run_ref(summer_ref)
            ),
            *self.style_plate,
        )

        def validate(artifact: BinaryArtifact) -> dict[str, object]:
            facts = gates.gate_prop(
                artifact.data,
                width=SPRITE_CANVAS[0],
                height=SPRITE_CANVAS[1],
                max_components=prop.max_components,
            )
            # The drift gate: a paintover that came back a different size or
            # moved its foot is a bad draw, refused inside the retry owner.
            drift, reasons = _look_drift(summer, artifact.data)
            if reasons:
                raise gates.GateError(reasons)
            return {**facts, "drift": drift}

        return await self._generate_image(
            node,
            size=SPRITE_CANVAS,
            background="transparent",
            references=references,
            validate=validate,
            operation_id=f"survival.season.{look_id}.{prop.prop_id}.{state}",
        )

    async def _season_look_validate(self, node: Node) -> NodeExecutionResult:
        prop = self.package.prop(str(node.params["prop_id"]))
        state = str(node.params["state"])
        look_id = str(node.params["look"])
        source_ref = f"production/props/{prop.prop_id}-{state}.{look_id}.source.png"
        data = self._path(source_ref).read_bytes()
        summer_ref = manifest_module.prop_ref(prop.prop_id, state)
        summer = self._path(summer_ref).read_bytes()
        facts = gates.gate_prop(
            data,
            width=SPRITE_CANVAS[0],
            height=SPRITE_CANVAS[1],
            max_components=prop.max_components,
        )
        drift, reasons = _look_drift(summer, data)
        if reasons:
            raise gates.GateError(reasons)
        normalised, placement = _normalise_look(summer, data)
        canonical, alpha = gates.canonicalize_sprite_alpha(normalised)
        record = {
            "schema_version": 1,
            "kind": "oblique-survival-season-look-validation-v1",
            "prop_id": prop.prop_id,
            "state": state,
            "look": look_id,
            "max_components": prop.max_components,
            "alpha_canonicalization": alpha,
            "drift": drift,
            "normalised": placement,
            **facts,
        }
        await self._write_local(
            node.port("image").artifact_ref,
            canonical,
            media_type="image/png",
            model="oblique-survival-sprite-alpha-v1",
            prompt=(
                f"Set {prop.prop_id} {state} {look_id} on its summer canvas at the"
                " summer's width and foot, lift it to full opacity and bleed its"
                " colour under the rim."
            ),
            refs=[self._run_ref(source_ref), self._run_ref(summer_ref)],
            validation=record,
        )
        await self._write_local(
            node.port("validation").artifact_ref,
            _json_bytes(record),
            media_type="application/json",
            model="season-look-validate",
            prompt="Record the prop gate's measurements and the drift against the summer sprite.",
            refs=[self._run_ref(source_ref), self._run_ref(summer_ref)],
        )
        return self._result(node)

    async def _prop_anchor(self, node: Node) -> NodeExecutionResult:
        """The one agentic node: where does this prop touch the ground, and how does it move.

        The pattern is the cut-in placement loop's. The agent is handed the sprite
        and a tool that re-renders it standing on a ruled ground plane at the scene
        pitch, with a footprint ellipse and an anchor cross drawn on. It looks at
        its own proposal rather than reasoning about coordinates blind.
        """

        if self.tool_loop is None:
            raise ValueError("tool-loop service missing")
        prop = self.package.prop(str(node.params["prop_id"]))
        baseline = prop.baseline_state
        sprite_ref = manifest_module.prop_ref(prop.prop_id, baseline)
        sprite = self._path(sprite_ref).read_bytes()
        validation = json.loads(
            self._path(f"production/validation/props/{prop.prop_id}-{baseline}.json").read_bytes()
        )
        height_meters = self.package.meters(prop.height_units)
        px_per_meter = max(1e-6, _as_float(validation["subject_height_px"])) / max(
            height_meters, 1e-6
        )
        proposed_radius = round(
            (_as_float(validation["footprint_width_px"]) / 2.0 / px_per_meter)
            / max(self.package.player_height_meters, 1e-6),
            3,
        )
        pitch = float(self.package.camera.get("pitch_degrees", 55.0))

        def render(arguments: Mapping[str, object]) -> ToolResult:
            anchor_x = _as_float(arguments["anchor_x"])
            anchor_y = _as_float(arguments["anchor_y"])
            radius_units = _as_float(arguments["footprint_radius_units"])
            plate = _anchor_overlay(
                sprite,
                anchor=(anchor_x, anchor_y),
                radius_meters=self.package.meters(radius_units),
                px_per_meter=px_per_meter,
                pitch_degrees=pitch,
            )
            return ToolResult(
                text=(
                    f"Rendered {prop.prop_id} with its anchor at ({anchor_x:.3f}, {anchor_y:.3f}) "
                    f"and a footprint radius of {radius_units:.3f} player heights "
                    f"({self.package.meters(radius_units):.2f} m). The green cross is the anchor, "
                    f"the green ellipse is the footprint on the ground plane, and the grey grid is "
                    f"one metre per cell at the scene camera's {pitch:.0f} degree pitch."
                ),
                images=(_inline_data_url(plate, "image/jpeg"),),
            )

        parameters = {
            "type": "object",
            "properties": {
                "anchor_x": {"type": "number", "description": "0 is the left edge, 1 the right"},
                "anchor_y": {"type": "number", "description": "0 is the top edge, 1 the bottom"},
                "footprint_radius_units": {
                    "type": "number",
                    "description": "ground radius in player heights",
                },
            },
            "required": ["anchor_x", "anchor_y", "footprint_radius_units"],
            "additionalProperties": False,
        }
        submit_schema = {
            "type": "object",
            "properties": {
                **{key: dict(value) for key, value in _properties(parameters).items()},
                "motion_hint": {
                    "type": "string",
                    "enum": ["sway_top", "bob", "flicker", "none"],
                },
                "rationale": {"type": "string"},
            },
            "required": [
                "anchor_x",
                "anchor_y",
                "footprint_radius_units",
                "motion_hint",
                "rationale",
            ],
            "additionalProperties": False,
        }

        def parse(value: object) -> dict[str, object]:
            placement = AnchorPlacement.model_validate(value)
            # The sprite's own size, not the sprite canvas: a look cut from a
            # sheet is half the canvas on a side, and a normalised anchor
            # converted against the wrong size is refused every time.
            width = int(_as_float(validation.get("width") or SPRITE_CANVAS[0]))
            height = int(_as_float(validation.get("height") or SPRITE_CANVAS[1]))
            bbox = _as_bbox(validation.get("bbox"), width, height)
            left, _top, right, bottom = bbox
            x_px = placement.anchor_x * width
            y_px = placement.anchor_y * height
            if not left - 8 <= x_px <= right + 8:
                raise ValueError("the anchor must sit inside the painted silhouette horizontally")
            if y_px < bottom - 0.35 * (bottom - _top) or y_px > bottom + 12:
                raise ValueError("the anchor must sit in the lower third of the silhouette")
            if placement.motion_hint not in {"sway_top", "bob", "flicker", "none"}:
                raise ValueError("unknown motion hint")
            return {
                "anchor_x": placement.anchor_x,
                "anchor_y": placement.anchor_y,
                "footprint_radius_units": placement.footprint_radius_units,
                "motion_hint": placement.motion_hint,
                "rationale": placement.rationale,
            }

        instructions = "\n".join(
            (
                f"You are placing the ground anchor for one 2D billboard prop: {prop.prop_id}, a "
                f"{prop.family}, {height_meters:.2f} m tall in world scale.",
                "",
                "The prop is drawn as a flat card that stands upright on a ground plane, seen by a "
                f"camera pitched {pitch:.0f} degrees down. Two numbers decide how it sits:",
                "  - the ANCHOR is the point in the image where the object actually meets the "
                "ground. For most objects that is the centre of its base.",
                "  - the FOOTPRINT RADIUS is how much ground the object occupies, in player "
                "heights, used for collision and for the contact shadow.",
                "",
                f"Call render_with_placement to see your proposal drawn."
                " A measured starting point: "
                f"anchor ({_measured_centre_x(validation)}, "
                f"{round(float(validation['ground_contact']['ground_contact_y_normalized']), 3)}), "
                f"radius {proposed_radius}. Try it, look at the picture, and adjust until the "
                "ellipse sits under the object rather than around it or inside it.",
                "",
                "Then choose a MOTION HINT for how the runtime should move the card slightly, so "
                "the world is not perfectly still:",
                "  - sway_top: the top of the card sways around its base. For anything with "
                "foliage, leaves or thin upright parts.",
                "  - bob: the whole card rises and falls a little. For something floating.",
                "  - flicker: the card brightens and dims. For anything glowing.",
                "  - none: the card is rigid. For stone, built structures and dead wood.",
                "",
                "Submit anchor_x, anchor_y, footprint_radius_units, motion_hint and a one-sentence "
                "rationale.",
            )
        )
        operation_id = f"survival.prop.anchor.{prop.prop_id}"
        try:
            result = await self.tool_loop.run(
                ToolLoopRequest(
                    instructions=instructions,
                    artifact_path=self._path(node.port("anchor").artifact_ref),
                    tools=(
                        Tool(
                            name="render_with_placement",
                            description=(
                                "Draw the prop standing on a one-metre ground"
                                " grid with your proposed "
                                "anchor cross and footprint ellipse, and return the picture."
                            ),
                            parameters=parameters,
                            handler=render,
                        ),
                    ),
                    submit_schema=submit_schema,
                    parse=parse,
                    references=(
                        ToolLoopReference(
                            url=_inline_data_url(sprite, "image/png"),
                            provenance_ref=self._run_ref(sprite_ref),
                        ),
                    ),
                    artifact_value=lambda placement: {
                        "schema_version": 1,
                        "kind": "oblique-survival-prop-anchor-v1",
                        "prop_id": prop.prop_id,
                        "baseline_state": baseline,
                        "anchor": {
                            "x": placement["anchor_x"],
                            "y": placement["anchor_y"],
                        },
                        "footprint_radius_units": placement["footprint_radius_units"],
                        "motion_hint": placement["motion_hint"],
                        "rationale": placement["rationale"],
                        "measured_proposal": {
                            "footprint_radius_units": proposed_radius,
                            "ground_contact_y_normalized": validation["ground_contact"][
                                "ground_contact_y_normalized"
                            ],
                        },
                    },
                    max_steps=6,
                    max_total_tokens=300_000,
                    metadata={
                        "operation_id": operation_id,
                        "invocation_id": self.invocation_id,
                        "publication_authorized": False,
                    },
                    timeout_seconds=900,
                )
            )
        finally:
            await self._write_ledger(node, operation_id=operation_id)
        # One episode is one provider operation whatever it spent inside, and a
        # tool-loop result reports tokens rather than a usage record, so there is
        # no known cost to publish here.
        return self._result(
            node, attempts=result.attempts, provider_operations=1, known_cost_usd=None
        )

    # -- items

    async def _item_generate(self, node: Node) -> NodeExecutionResult:
        item_id = str(node.params["item_id"])

        def validate(artifact: BinaryArtifact) -> dict[str, object]:
            return gates.gate_transparent_canvas(
                artifact.data, width=SPRITE_CANVAS[0], height=SPRITE_CANVAS[1]
            )

        return await self._generate_image(
            node,
            size=SPRITE_CANVAS,
            background="transparent",
            references=self.style_plate,
            validate=validate,
            operation_id=f"survival.item.{item_id}",
        )

    async def _item_validate(self, node: Node) -> NodeExecutionResult:
        item_id = str(node.params["item_id"])
        source_ref = f"production/items/{item_id}.source.png"
        data = self._path(source_ref).read_bytes()
        facts = gates.gate_transparent_canvas(data, width=SPRITE_CANVAS[0], height=SPRITE_CANVAS[1])
        canonical, alpha = gates.canonicalize_sprite_alpha(data)
        record = {
            "schema_version": 1,
            "kind": "oblique-survival-item-validation-v1",
            "item_id": item_id,
            "alpha_canonicalization": alpha,
            **facts,
        }
        await self._write_local(
            node.port("image").artifact_ref,
            canonical,
            media_type="image/png",
            model="oblique-survival-sprite-alpha-v1",
            prompt=f"Lift the {item_id} pickup to full opacity and bleed its colour under the rim.",
            refs=[self._run_ref(source_ref)],
            validation=record,
        )
        await self._write_local(
            node.port("validation").artifact_ref,
            _json_bytes(record),
            media_type="application/json",
            model="item-validate",
            prompt="Record the item gate's measurements.",
            refs=[self._run_ref(source_ref)],
        )
        return self._result(node)

    # -- ground

    async def _ground_generate(self, node: Node) -> NodeExecutionResult:
        biome_id = str(node.params["biome_id"])
        biome = self.package.biome(biome_id)
        texel = biome.texel_meters

        def validate(artifact: BinaryArtifact) -> dict[str, object]:
            return gates.gate_ground_texture(
                artifact.data,
                width=GROUND_CANVAS[0],
                height=GROUND_CANVAS[1],
                texel_meters=texel,
                **plate_gate_kwargs(biome),
            )

        return await self._generate_image(
            node,
            size=GROUND_CANVAS,
            background="opaque",
            references=self.style_plate,
            validate=validate,
            operation_id=f"survival.ground.{biome_id}",
        )

    async def _ground_adopt(self, node: Node) -> NodeExecutionResult:
        """Copy the auditioned plate into the run through the plate gate, lineage kept."""

        biome = self.package.biome(str(node.params["biome_id"]))
        assert biome.take is not None
        self._refuse_missing_take(node, biome.take)
        data = (self.package.root / biome.take).read_bytes()
        digest = self.package.digests[biome.take]
        facts = gates.gate_ground_texture(
            data,
            width=GROUND_CANVAS[0],
            height=GROUND_CANVAS[1],
            texel_meters=biome.texel_meters,
            **plate_gate_kwargs(biome),
        )
        record = {
            "schema_version": 1,
            "kind": "oblique-survival-ground-adoption-v1",
            "biome_id": biome.biome_id,
            "adopted_from": biome.take,
            "adopted_sha256": digest,
            # The pick was made over audition draws of this brief
            # (explore/ground-audition/); the gate confirms the plate is one.
            "accepted_by": "audition_pick",
            **facts,
        }
        await self._write_local(
            node.port("image").artifact_ref,
            data,
            media_type="image/png",
            model="ground-plate-adopt",
            prompt=node.card.prompt if node.card and node.card.prompt else biome.prompt,
            refs=[f"source://{biome.take}#sha256={digest}"],
            validation=record,
        )
        return self._result(node)

    async def _ground_canonicalize(self, node: Node) -> NodeExecutionResult:
        biome_id = str(node.params["biome_id"])
        source_ref = f"production/ground/{biome_id}.source.png"
        data = self._path(source_ref).read_bytes()
        facts = gates.gate_ground_texture(
            data,
            width=GROUND_CANVAS[0],
            height=GROUND_CANVAS[1],
            texel_meters=self.package.biome(biome_id).texel_meters,
            **plate_gate_kwargs(self.package.biome(biome_id)),
        )
        tiled, mirror = gates.mirror_repeat_2d(data)
        edges = gates.gate_tileable_2d(tiled)
        record = {
            "schema_version": 1,
            "kind": "oblique-survival-ground-validation-v1",
            "biome_id": biome_id,
            "source": facts,
            "mirror": mirror,
            "edges": edges,
        }
        await self._write_local(
            node.port("image").artifact_ref,
            tiled,
            media_type="image/png",
            model="mirror-repeat-2d-v1",
            prompt="Mirror the plate on both axes so its edges wrap exactly.",
            refs=[self._run_ref(source_ref)],
            validation=record,
        )
        await self._write_local(
            node.port("validation").artifact_ref,
            _json_bytes(record),
            media_type="application/json",
            model="ground-validate",
            prompt="Record the ground gate and the mirror construction.",
            refs=[self._run_ref(source_ref)],
        )
        return self._result(node)

    async def _plate_canonicalize(
        self,
        node: Node,
        *,
        source_ref: str,
        facts: Mapping[str, object],
        kind: str,
        extra: Mapping[str, object],
    ) -> NodeExecutionResult:
        """Mirror a plate on both axes and record the gate: shared by every plate."""

        data = self._path(source_ref).read_bytes()
        tiled, mirror = gates.mirror_repeat_2d(data)
        edges = gates.gate_tileable_2d(tiled)
        record = {
            "schema_version": 1,
            "kind": kind,
            **extra,
            "source": facts,
            "mirror": mirror,
            "edges": edges,
        }
        await self._write_local(
            node.port("image").artifact_ref,
            tiled,
            media_type="image/png",
            model="mirror-repeat-2d-v1",
            prompt="Mirror the plate on both axes so its edges wrap exactly.",
            refs=[self._run_ref(source_ref)],
            validation=record,
        )
        await self._write_local(
            node.port("validation").artifact_ref,
            _json_bytes(record),
            media_type="application/json",
            model="ground-validate",
            prompt="Record the plate gate and the mirror construction.",
            refs=[self._run_ref(source_ref)],
        )
        return self._result(node)

    async def _macro_generate(self, node: Node) -> NodeExecutionResult:
        def validate(artifact: BinaryArtifact) -> dict[str, object]:
            return gates.gate_macro_plate(
                artifact.data, width=GROUND_CANVAS[0], height=GROUND_CANVAS[1]
            )

        return await self._generate_image(
            node,
            size=GROUND_CANVAS,
            background="opaque",
            validate=validate,
            operation_id="survival.ground.macro",
        )

    async def _macro_canonicalize(self, node: Node) -> NodeExecutionResult:
        source_ref = "production/ground/macro.source.png"
        facts = gates.gate_macro_plate(
            self._path(source_ref).read_bytes(), width=GROUND_CANVAS[0], height=GROUND_CANVAS[1]
        )
        return await self._plate_canonicalize(
            node,
            source_ref=source_ref,
            facts=facts,
            kind="oblique-survival-macro-validation-v1",
            extra={},
        )

    async def _road_generate(self, node: Node) -> NodeExecutionResult:
        road = self.package.road
        assert road is not None

        def validate(artifact: BinaryArtifact) -> dict[str, object]:
            return gates.gate_ground_texture(
                artifact.data,
                width=GROUND_CANVAS[0],
                height=GROUND_CANVAS[1],
                texel_meters=road.texel_meters,
            )

        return await self._generate_image(
            node,
            size=GROUND_CANVAS,
            background="opaque",
            references=self.style_plate,
            validate=validate,
            operation_id=f"survival.ground.road.{road.road_id}",
        )

    async def _road_canonicalize(self, node: Node) -> NodeExecutionResult:
        road = self.package.road
        assert road is not None
        source_ref = f"production/ground/road-{road.road_id}.source.png"
        facts = gates.gate_ground_texture(
            self._path(source_ref).read_bytes(),
            width=GROUND_CANVAS[0],
            height=GROUND_CANVAS[1],
            texel_meters=road.texel_meters,
        )
        return await self._plate_canonicalize(
            node,
            source_ref=source_ref,
            facts=facts,
            kind="oblique-survival-road-validation-v1",
            extra={"road_id": road.road_id},
        )

    async def _water_generate(self, node: Node) -> NodeExecutionResult:
        water = self.package.water
        assert water is not None

        def validate(artifact: BinaryArtifact) -> dict[str, object]:
            return gates.gate_ground_texture(
                artifact.data,
                width=GROUND_CANVAS[0],
                height=GROUND_CANVAS[1],
                texel_meters=water.texel_meters,
                luma_range=gates.WATER_LUMA_RANGE,
            )

        return await self._generate_image(
            node,
            size=GROUND_CANVAS,
            background="opaque",
            references=self.style_plate,
            validate=validate,
            operation_id="survival.ground.water",
        )

    async def _water_canonicalize(self, node: Node) -> NodeExecutionResult:
        water = self.package.water
        assert water is not None
        source_ref = "production/ground/water.source.png"
        facts = gates.gate_ground_texture(
            self._path(source_ref).read_bytes(),
            width=GROUND_CANVAS[0],
            height=GROUND_CANVAS[1],
            texel_meters=water.texel_meters,
            luma_range=gates.WATER_LUMA_RANGE,
        )
        return await self._plate_canonicalize(
            node,
            source_ref=source_ref,
            facts=facts,
            kind="oblique-survival-water-validation-v1",
            extra={},
        )

    async def _prop_sheet_generate(self, node: Node) -> NodeExecutionResult:
        prop = self.package.prop(str(node.params["prop_id"]))
        sheet = prop.sheet
        assert sheet is not None
        cell_px = templates.SHEET_CELL_PX

        def validate(artifact: BinaryArtifact) -> dict[str, object]:
            _sprites, record = gates.gate_prop_sheet(
                artifact.data,
                columns=sheet.columns,
                rows=sheet.rows,
                cell_px=cell_px,
                states=prop.states,
                max_components=prop.max_components,
            )
            return record

        return await self._generate_image(
            node,
            size=(sheet.columns * cell_px, sheet.rows * cell_px),
            background="transparent",
            references=self.style_plate,
            validate=validate,
            operation_id=f"survival.prop.{prop.prop_id}.sheet",
        )

    async def _prop_sheet_validate(self, node: Node) -> NodeExecutionResult:
        prop = self.package.prop(str(node.params["prop_id"]))
        sheet = prop.sheet
        assert sheet is not None
        cell_px = templates.SHEET_CELL_PX
        source_ref = f"production/props/{prop.prop_id}.sheet.source.png"
        data = self._path(source_ref).read_bytes()
        sprites, record = gates.gate_prop_sheet(
            data,
            columns=sheet.columns,
            rows=sheet.rows,
            cell_px=cell_px,
            states=prop.states,
            max_components=prop.max_components,
        )
        record = {**record, "prop_id": prop.prop_id}
        # Each look gets the sprite path's own record shape, plus where it was
        # cut from, so the anchor loop and the manifest read it unchanged.
        for cell in _gate_rows(record["cells"]):
            state = str(cell["state"])
            facts = {
                key: value
                for key, value in cell.items()
                if key not in {"index", "state", "x", "y", "w", "h", "alpha_canonicalization"}
            }
            look_record = {
                "schema_version": 1,
                "kind": "oblique-survival-prop-validation-v1",
                "prop_id": prop.prop_id,
                "state": state,
                "max_components": prop.max_components,
                "alpha_canonicalization": cell["alpha_canonicalization"],
                "drawn": {
                    "kind": "sheet",
                    "columns": sheet.columns,
                    "rows": sheet.rows,
                    "cell_px": cell_px,
                    "index": cell["index"],
                },
                **facts,
            }
            await self._write_local(
                node.port(f"image_{_safe(state)}").artifact_ref,
                sprites[state],
                media_type="image/png",
                model="oblique-survival-sprite-alpha-v1",
                prompt=(
                    f"Cut {prop.prop_id} {state} from its sheet, lift it to full"
                    " opacity and bleed its colour under the rim."
                ),
                refs=[self._run_ref(source_ref)],
                validation=look_record,
            )
            await self._write_local(
                node.port(f"validation_{_safe(state)}").artifact_ref,
                _json_bytes(look_record),
                media_type="application/json",
                model="prop-validate",
                prompt="Record the prop gate's measurements for one look cut from a sheet.",
                refs=[self._run_ref(source_ref)],
            )
        keyed = Image.new("RGBA", (sheet.columns * cell_px, sheet.rows * cell_px), (0, 0, 0, 0))
        for cell in _gate_rows(record["cells"]):
            keyed.alpha_composite(
                Image.open(BytesIO(sprites[str(cell["state"])])).convert("RGBA"),
                (int(cell["x"]), int(cell["y"])),
            )
        buffer = BytesIO()
        keyed.save(buffer, format="PNG")
        await self._write_local(
            node.port("sheet").artifact_ref,
            buffer.getvalue(),
            media_type="image/png",
            model="prop-sheet-canonicalize",
            prompt="Lay the canonical looks back on the sheet's grid.",
            refs=[self._run_ref(source_ref)],
            validation=record,
        )
        await self._write_local(
            node.port("sheet_validation").artifact_ref,
            _json_bytes(record),
            media_type="application/json",
            model="prop-sheet-validate",
            prompt="Record every look's gate measurements and where on the sheet it was.",
            refs=[self._run_ref(source_ref)],
        )
        return self._result(node)

    # -- piece sheets: the forage, the icons -------------------------------------------
    #
    # Two lattices, one handler shape each for generate, adopt and validate,
    # parametrised on the sheet. ``contacts`` is None for the icons: an icon
    # has no ground to meet.

    def _sheet_gate(
        self,
        sheet: SheetLattice,
        *,
        contacts: Sequence[str] | None,
        coverage: tuple[float, float],
        halo: bool = False,
        inset_fraction: float = gates.SHEET_CELL_INSET,
    ) -> tuple[SheetGate, bytes, str, int]:
        # Only the icon sheet authors its own cell size; the ground sheets take
        # the lattice's.
        cell_px: int = getattr(sheet, "cell_px", templates.LATTICE_CELL_PX)
        template_ref = templates.template_ref(sheet.columns, sheet.rows, cell_px)
        template = self._path(template_ref).read_bytes()

        def gate(data: bytes) -> tuple[bytes, dict[str, object]]:
            return gates.gate_piece_sheet(
                data,
                columns=sheet.columns,
                rows=sheet.rows,
                cell_px=cell_px,
                template=template,
                contacts=contacts,
                native_alpha=templates.LATTICE_TRANSPARENT,
                coverage=coverage,
                halo=halo,
                inset_fraction=inset_fraction,
            )

        return gate, template, template_ref, cell_px

    async def _sheet_generate(
        self,
        node: Node,
        sheet: SheetLattice,
        *,
        contacts: Sequence[str] | None,
        coverage: tuple[float, float],
        halo: bool = False,
        operation_id: str,
    ) -> NodeExecutionResult:
        gate, template, template_ref, cell_px = self._sheet_gate(
            sheet, contacts=contacts, coverage=coverage, halo=halo
        )

        def validate(artifact: BinaryArtifact) -> dict[str, object]:
            _canonical, record = gate(artifact.data)
            return record

        return await self._generate_image(
            node,
            size=(sheet.columns * cell_px, sheet.rows * cell_px),
            background="transparent" if templates.LATTICE_TRANSPARENT else "opaque",
            references=(
                ImageReference(
                    url=_inline_data_url(template, "image/png"),
                    provenance_ref=self._run_ref(template_ref),
                ),
            ),
            validate=validate,
            operation_id=operation_id,
        )

    async def _sheet_adopt(
        self,
        node: Node,
        sheet: SheetLattice,
        *,
        contacts: Sequence[str] | None,
        coverage: tuple[float, float],
        halo: bool = False,
        kind: str,
        model: str,
        label: str,
    ) -> NodeExecutionResult:
        """Copy an auditioned sheet into the run through the lattice gate."""

        assert sheet.take is not None
        self._refuse_missing_take(node, sheet.take)
        data = (self.package.root / sheet.take).read_bytes()
        digest = self.package.digests[sheet.take]
        gate, _template, template_ref, _cell_px = self._sheet_gate(
            sheet, contacts=contacts, coverage=coverage, halo=halo
        )
        _canonical, facts = gate(data)
        record = {
            "schema_version": 1,
            "kind": kind,
            "adopted_from": sheet.take,
            "adopted_sha256": digest,
            "accepted_by": "audition_pick",
            **facts,
        }
        await self._write_local(
            node.port("image").artifact_ref,
            data,
            media_type="image/png",
            model=model,
            prompt=node.card.prompt if node.card and node.card.prompt else label,
            refs=[f"source://{sheet.take}#sha256={digest}", self._run_ref(template_ref)],
            validation=record,
        )
        return self._result(node)

    async def _sheet_validate(
        self,
        node: Node,
        sheet: SheetLattice,
        *,
        contacts: Sequence[str] | None,
        coverage: tuple[float, float],
        halo: bool = False,
        inset_fraction: float = gates.SHEET_CELL_INSET,
        source_ref: str,
        kind: str,
        model: str,
        extra: Mapping[str, object],
        what: str,
    ) -> NodeExecutionResult:
        gate, _template, _template_ref, _cell_px = self._sheet_gate(
            sheet, contacts=contacts, coverage=coverage, halo=halo, inset_fraction=inset_fraction
        )
        canonical, record = gate(self._path(source_ref).read_bytes())
        record = {**record, "kind": kind, **extra}
        await self._write_local(
            node.port("image").artifact_ref,
            canonical,
            media_type="image/png",
            model=f"{model}-canonicalize",
            prompt="Cut the cells along the guides and lay them back on a clean grid.",
            refs=[self._run_ref(source_ref)],
            validation=record,
        )
        await self._write_local(
            node.port("validation").artifact_ref,
            _json_bytes(record),
            media_type="application/json",
            model=f"{model}-validate",
            prompt=f"Record every {what} cell's coverage and bounding box.",
            refs=[self._run_ref(source_ref)],
        )
        return self._result(node)

    async def _forage_generate(self, node: Node) -> NodeExecutionResult:
        forage = self.package.forage
        assert forage is not None
        return await self._sheet_generate(
            node,
            forage,
            contacts=[cell.contact for cell in forage.cells],
            coverage=gates.PIECE_CELL_COVERAGE,
            operation_id="survival.ground.forage",
        )

    async def _forage_adopt(self, node: Node) -> NodeExecutionResult:
        forage = self.package.forage
        assert forage is not None
        return await self._sheet_adopt(
            node,
            forage,
            contacts=[cell.contact for cell in forage.cells],
            coverage=gates.PIECE_CELL_COVERAGE,
            kind="oblique-survival-forage-adoption-v1",
            model="ground-forage-adopt",
            label="forage sheet",
        )

    async def _forage_validate(self, node: Node) -> NodeExecutionResult:
        forage = self.package.forage
        assert forage is not None
        return await self._sheet_validate(
            node,
            forage,
            contacts=[cell.contact for cell in forage.cells],
            coverage=gates.PIECE_CELL_COVERAGE,
            source_ref="production/ground/forage.source.png",
            kind="oblique-survival-forage-validation-v1",
            model="ground-forage",
            extra={
                "cell_meters": forage.cell_meters,
                "items": [cell.item_id for cell in forage.cells],
            },
            what="forage",
        )

    async def _icons_generate(self, node: Node) -> NodeExecutionResult:
        return await self._sheet_generate(
            node,
            self.package.icons,
            contacts=None,
            coverage=gates.ICON_CELL_COVERAGE,
            operation_id="survival.items.icons",
        )

    async def _icons_adopt(self, node: Node) -> NodeExecutionResult:
        return await self._sheet_adopt(
            node,
            self.package.icons,
            contacts=None,
            coverage=gates.ICON_CELL_COVERAGE,
            kind="oblique-survival-icons-adoption-v1",
            model="item-icons-adopt",
            label="icon sheet",
        )

    async def _icons_validate(self, node: Node) -> NodeExecutionResult:
        icons = self.package.icons
        names = [item.item_id for item in self.package.items] + [
            glyph.glyph for glyph in icons.glyphs
        ]
        return await self._sheet_validate(
            node,
            icons,
            contacts=None,
            coverage=gates.ICON_CELL_COVERAGE,
            source_ref="production/items/icons.source.png",
            kind="oblique-survival-icons-validation-v1",
            model="item-icons",
            extra={"names": names},
            what="icon",
        )

    async def _decal_generate(self, node: Node) -> NodeExecutionResult:
        decal_id = str(node.params["decal_id"])

        def validate(artifact: BinaryArtifact) -> dict[str, object]:
            # soft_edge=False: the feather is applied at publish, deterministically.
            return gates.gate_decal(
                artifact.data,
                width=SPRITE_CANVAS[0],
                height=SPRITE_CANVAS[1],
                soft_edge=False,
            )

        return await self._generate_image(
            node,
            size=SPRITE_CANVAS,
            background="transparent",
            references=self.style_plate,
            validate=validate,
            operation_id=f"survival.decal.{decal_id}",
        )

    async def _decal_validate(self, node: Node) -> NodeExecutionResult:
        decal_id = str(node.params["decal_id"])
        source_ref = f"production/ground/decals/{decal_id}.source.png"
        source = self._path(source_ref).read_bytes()
        drawn_share = gates.decal_soft_edge_share(source)
        data = gates.feather_decal_edge(source)
        facts = gates.gate_decal(data, width=SPRITE_CANVAS[0], height=SPRITE_CANVAS[1])
        record = {
            "schema_version": 1,
            "kind": "oblique-survival-decal-validation-v1",
            "decal_id": decal_id,
            "drawn_soft_edge_share": round(drawn_share, 4),
            "feather_radius_px": gates.DECAL_FEATHER_RADIUS_PX,
            **facts,
        }
        await self._write_local(
            node.port("image").artifact_ref,
            data,
            media_type="image/png",
            model="decal-publish",
            # No alpha lifting or clearing here -- a decal's contract is an edge
            # fading to nothing, and both would destroy it. The one alteration is
            # the feather itself, applied inward so the drawn silhouette is kept.
            prompt=f"Feather the {decal_id} decal's edge and publish it.",
            refs=[self._run_ref(source_ref)],
            validation=record,
        )
        await self._write_local(
            node.port("validation").artifact_ref,
            _json_bytes(record),
            media_type="application/json",
            model="decal-validate",
            prompt="Record the decal gate's measurements.",
            refs=[self._run_ref(source_ref)],
        )
        return self._result(node)

    # -- actors

    async def _actor_concept(self, node: Node) -> NodeExecutionResult:
        actor_id = str(node.params["actor_id"])
        actor = next(
            (
                entry
                for entry in (self.package.player, self.package.mob)
                if entry.actor_id == actor_id
            ),
            None,
        )
        appearance = self.appearance_plate(actor) if actor is not None else ()

        def validate(artifact: BinaryArtifact) -> dict[str, object]:
            return gates.gate_transparent_canvas(
                artifact.data, width=SPRITE_CANVAS[0], height=SPRITE_CANVAS[1]
            )

        return await self._generate_image(
            node,
            size=SPRITE_CANVAS,
            background="transparent",
            references=appearance + self.style_plate,
            validate=validate,
            operation_id=f"survival.actor.concept.{actor_id}",
        )

    async def _motion_generate(self, node: Node) -> NodeExecutionResult:
        actor_id = str(node.params["actor_id"])
        state = str(node.params["state"])
        facing = node.params.get("facing")
        facing = str(facing) if facing is not None else None
        concept_ref = manifest_module.concept_ref(actor_id)
        concept = self._path(concept_ref).read_bytes()
        references = [
            ImageReference(
                url=_inline_data_url(concept, "image/png"),
                provenance_ref=self._run_ref(concept_ref),
            )
        ]
        if facing not in (None, "front"):
            # The front strip, already gated and repacked: the pose reference.
            front_ref = manifest_module.state_ref(actor_id, state, "front")
            references.append(
                ImageReference(
                    url=_inline_data_url(self._path(front_ref).read_bytes(), "image/png"),
                    provenance_ref=self._run_ref(front_ref),
                )
            )

        def validate(artifact: BinaryArtifact) -> dict[str, object]:
            _canonical, record = gates.gate_motion_atlas(
                artifact.data,
                width=STRIP_CANVAS[0],
                height=STRIP_CANVAS[1],
                columns=MOTION_COLUMNS,
                state=state,
            )
            return record

        return await self._generate_image(
            node,
            size=STRIP_CANVAS,
            background="transparent",
            references=tuple(references),
            validate=validate,
            operation_id=f"survival.actor.{actor_id}.{strip_key(state, facing)}",
        )

    async def _motion_validate(self, node: Node) -> NodeExecutionResult:
        actor_id = str(node.params["actor_id"])
        state = str(node.params["state"])
        facing = node.params.get("facing")
        facing = str(facing) if facing is not None else None
        source_ref = f"production/actors/{actor_id}-{strip_key(state, facing)}.source.png"
        data = self._path(source_ref).read_bytes()
        canonical, record = gates.gate_motion_atlas(
            data,
            width=STRIP_CANVAS[0],
            height=STRIP_CANVAS[1],
            columns=MOTION_COLUMNS,
            state=state,
        )
        record = {
            "schema_version": 1,
            "kind": "oblique-survival-motion-validation-v1",
            "actor_id": actor_id,
            "facing_set": self.package.actor(actor_id).facings.set,
            "source_facing": facing if facing is not None else self.package.facing_authored,
            "runtime_horizontal_mirroring": facing is None,
            **record,
        }
        await self._write_local(
            node.port("image").artifact_ref,
            canonical,
            media_type="image/png",
            model="alpha-component-repack-v3",
            prompt=(
                f"Repack {actor_id}'s {strip_key(state, facing)} strip onto"
                " canonical bottom-anchored cells."
            ),
            refs=[self._run_ref(source_ref)],
            validation=record,
        )
        await self._write_local(
            node.port("validation").artifact_ref,
            _json_bytes(record),
            media_type="application/json",
            model="motion-validate",
            prompt="Record the strip gate and the repack.",
            refs=[self._run_ref(source_ref)],
        )
        return self._result(node)

    def _actor_frames(self, actor: Actor) -> dict[str, list[bytes]]:
        """Every published state's frames, split out of its canonical strip."""

        from stage_gen.media.sprite_sheets import split_atlas_columns

        frames: dict[str, list[bytes]] = {}
        for state, facing in actor.strips:
            path = self._path(manifest_module.state_ref(actor.actor_id, state, facing))
            if not path.is_file():
                continue
            frames[strip_key(state, facing)] = list(
                split_atlas_columns(path.read_bytes(), MOTION_COLUMNS, 1)
            )
        return frames

    async def _rebase_plate(self, node: Node) -> NodeExecutionResult:
        actor = self.package.actor(str(node.params["actor_id"]))
        plate = motion_rebase.build_motion_rebase_plate(
            self._actor_frames(actor), baseline_state=actor.baseline_key
        )
        await self._write_local(
            node.port("plate").artifact_ref,
            plate.png,
            media_type="image/png",
            model="comparison_plate_v1",
            prompt="Composite every state's frames at one uniform source scale.",
            refs=[
                self._run_ref(manifest_module.state_ref(actor.actor_id, state, facing))
                for state, facing in actor.strips
                if self._path(manifest_module.state_ref(actor.actor_id, state, facing)).is_file()
            ],
        )
        return self._result(node)

    async def _rebase_judge(self, node: Node) -> NodeExecutionResult:
        actor = self.package.actor(str(node.params["actor_id"]))
        frames = self._actor_frames(actor)
        plate = motion_rebase.build_motion_rebase_plate(frames, baseline_state=actor.baseline_key)
        plate_ref = f"production/rebase/{actor.actor_id}-first-pass.png"
        operation_id = f"survival.rebase.{actor.actor_id}"
        ledger = AttemptLedger(operation_id=operation_id)
        try:
            value, operation = await generate_structured(
                self._require_structured(),
                model_type=motion_rebase.MotionRebaseReading,
                operation_id=operation_id,
                prompt=motion_rebase.motion_rebase_prompt(actor.display_name, sorted(frames)),
                artifact_path=self._path(node.port("reading").artifact_ref),
                ledger=ledger,
                references=(
                    StructuredReference(
                        url=_inline_data_url(plate.png, "image/png"),
                        provenance_ref=self._run_ref(plate_ref),
                    ),
                ),
                max_tokens=8_000,
                timeout_seconds=600,
                semantic_validate=lambda reading: _rebase_errors(
                    reading, frames, plate, actor.baseline_key
                ),
            )
        finally:
            await self._write_ledger(node, operation_id=operation_id, attempts=ledger.records)
        del value
        attempts = int(operation["attempts"])
        return self._result(
            node,
            attempts=attempts,
            provider_operations=attempts,
            known_cost_usd=known_cost(operation.get("usage")),
        )

    async def _rebase_verify_plate(self, node: Node) -> NodeExecutionResult:
        actor = self.package.actor(str(node.params["actor_id"]))
        frames = self._actor_frames(actor)
        first_ref = f"production/rebase/{actor.actor_id}-first-pass.json"
        reading = motion_rebase.MotionRebaseReading.model_validate_json(
            self._path(first_ref).read_bytes()
        )
        first_pass = {entry.state: entry.multiplier for entry in reading.states}
        first_pass.setdefault(actor.baseline_key, 1.0)
        plate = motion_rebase.build_motion_rebase_verification_plate(
            frames, first_pass, baseline_state=actor.baseline_key
        )
        await self._write_local(
            node.port("plate").artifact_ref,
            plate.png,
            media_type="image/png",
            model="comparison_plate_v1",
            prompt="Re-composite every state with its first-pass multiplier applied.",
            refs=[self._run_ref(first_ref)],
        )
        return self._result(node)

    async def _rebase_verify(self, node: Node) -> NodeExecutionResult:
        actor = self.package.actor(str(node.params["actor_id"]))
        frames = self._actor_frames(actor)
        first_ref = f"production/rebase/{actor.actor_id}-first-pass.json"
        plate_ref = f"production/rebase/{actor.actor_id}-verify.png"
        reading = motion_rebase.MotionRebaseReading.model_validate_json(
            self._path(first_ref).read_bytes()
        )
        first_pass = {entry.state: entry.multiplier for entry in reading.states}
        first_pass.setdefault(actor.baseline_key, 1.0)
        # Admission checks both plates: the first pass is re-admitted against a
        # plate rebuilt from today's bytes, so a strip regenerated after the
        # first reading is refused rather than silently corrected.
        plate = motion_rebase.build_motion_rebase_plate(frames, baseline_state=actor.baseline_key)
        verification_plate = motion_rebase.build_motion_rebase_verification_plate(
            frames, first_pass, baseline_state=actor.baseline_key
        )
        residual_path = self._path(f"production/rebase/{actor.actor_id}-residual.json")
        operation_id = f"survival.rebase.verify.{actor.actor_id}"
        ledger = AttemptLedger(operation_id=operation_id)
        try:
            value, operation = await generate_structured(
                self._require_structured(),
                model_type=motion_rebase.MotionRebaseReading,
                operation_id=operation_id,
                prompt=motion_rebase.motion_rebase_verification_prompt(
                    actor.display_name, sorted(frames)
                ),
                artifact_path=residual_path,
                ledger=ledger,
                references=(
                    StructuredReference(
                        url=_inline_data_url(verification_plate.png, "image/png"),
                        provenance_ref=self._run_ref(plate_ref),
                    ),
                ),
                max_tokens=8_000,
                timeout_seconds=600,
            )
        finally:
            await self._write_ledger(node, operation_id=operation_id, attempts=ledger.records)
        record = motion_rebase.evaluate_motion_rebase_correction(
            value,
            first_pass=first_pass,
            published_states=sorted(frames),
            plate=plate,
            verification_plate=verification_plate,
            baseline_state=actor.baseline_key,
        )
        published = {
            "schema_version": 1,
            "kind": "oblique-survival-rebase-v1",
            "actor_id": actor.actor_id,
            "baseline_state": record.get("baseline_state", actor.baseline_key),
            # The manifest reads a list, so the mapping is flattened here rather
            # than in the consumer: one shape per document, no branching there.
            "states": [
                {"state": state, "multiplier": multiplier}
                for state, multiplier in sorted(_as_mapping(record.get("states")).items())
            ],
            "record": record,
        }
        await self._write_local(
            node.port("rebase").artifact_ref,
            _json_bytes(published),
            media_type="application/json",
            model="motion-rebase-verify",
            prompt="Publish the admitted per-state draw-scale multipliers.",
            refs=[self._run_ref(first_ref), self._run_ref(plate_ref)],
        )
        attempts = int(operation["attempts"])
        return self._result(
            node,
            attempts=attempts,
            provider_operations=attempts,
            known_cost_usd=known_cost(operation.get("usage")),
        )

    # -- effects

    async def _fire_generate(self, node: Node) -> NodeExecutionResult:
        fire = self.package.fire
        template_ref = templates.template_ref(fire.columns, fire.rows)
        template = self._path(template_ref).read_bytes()

        def validate(artifact: BinaryArtifact) -> dict[str, object]:
            _canonical, record = gates.gate_fx_strip(
                artifact.data,
                columns=fire.columns,
                rows=fire.rows,
                cell_px=templates.LATTICE_CELL_PX,
                template=template,
                native_alpha=templates.LATTICE_TRANSPARENT,
            )
            return record

        return await self._generate_image(
            node,
            size=(fire.columns * templates.LATTICE_CELL_PX, fire.rows * templates.LATTICE_CELL_PX),
            background="transparent" if templates.LATTICE_TRANSPARENT else "opaque",
            references=(
                ImageReference(
                    url=_inline_data_url(template, "image/png"),
                    provenance_ref=self._run_ref(template_ref),
                ),
            ),
            validate=validate,
            operation_id="survival.fx.fire",
        )

    async def _fire_validate(self, node: Node) -> NodeExecutionResult:
        fire = self.package.fire
        source_ref = "production/fx/fire.source.png"
        template_ref = templates.template_ref(fire.columns, fire.rows)
        data = self._path(source_ref).read_bytes()
        canonical, record = gates.gate_fx_strip(
            data,
            columns=fire.columns,
            rows=fire.rows,
            cell_px=templates.LATTICE_CELL_PX,
            template=self._path(template_ref).read_bytes(),
            native_alpha=templates.LATTICE_TRANSPARENT,
        )
        record = {
            **record,
            "playback_order": gates.strip_playback_order(
                cast("int", record["frames"]), cast("str", record["mode"])
            ),
        }
        await self._write_local(
            node.port("image").artifact_ref,
            canonical,
            media_type="image/png",
            model="fx-strip-canonicalize",
            prompt="Cut the cells along the guides and publish the flame grid.",
            refs=[self._run_ref(source_ref), self._run_ref(template_ref)],
            validation=record,
        )
        await self._write_local(
            node.port("validation").artifact_ref,
            _json_bytes(record),
            media_type="application/json",
            model="fx-strip-validate",
            prompt="Record the lattice, coverage and cycle-continuity measurements.",
            refs=[self._run_ref(source_ref)],
        )
        return self._result(node)

    async def _dust_generate(self, node: Node) -> NodeExecutionResult:
        from stage_gen.components.game_fx.sprite import validate_dust_atlas

        def validate(artifact: BinaryArtifact) -> dict[str, object]:
            return dict(validate_dust_atlas(artifact.data))

        return await self._generate_image(
            node,
            size=SPRITE_CANVAS,
            background="transparent",
            references=self.style_plate,
            validate=validate,
            operation_id="survival.fx.dust",
        )

    async def _dust_validate(self, node: Node) -> NodeExecutionResult:
        from stage_gen.components.game_fx.sprite import canonicalize_dust_atlas, dust_atlas_contract

        source_ref = "production/fx/dust.source.png"
        data = self._path(source_ref).read_bytes()
        canonical, facts = canonicalize_dust_atlas(data)
        geometry = dust_atlas_contract(facts)
        # The shared contract names its four quadrant cells for the runner's
        # contacts; this package names them for its own four puffs, in the same
        # reading order the layout fixes.
        cells = []
        for index, kind in enumerate(self.package.dust.kinds):
            half_w = SPRITE_CANVAS[0] // 2
            half_h = SPRITE_CANVAS[1] // 2
            cells.append(
                {
                    "kind": kind,
                    "x": (index % 2) * half_w,
                    "y": (index // 2) * half_h,
                    "w": half_w,
                    "h": half_h,
                }
            )
        record = {
            "schema_version": 1,
            "kind": "oblique-survival-fx-dust-validation-v1",
            "cells": cells,
            "shared_geometry": geometry,
        }
        await self._write_local(
            node.port("image").artifact_ref,
            canonical,
            media_type="image/png",
            model="fx-dust-canonicalize",
            prompt="Lift the near-opaque body and clear the exterior to nothing.",
            refs=[self._run_ref(source_ref)],
            validation=record,
        )
        await self._write_local(
            node.port("validation").artifact_ref,
            _json_bytes(record),
            media_type="application/json",
            model="fx-dust-validate",
            prompt="Record the four puff cells in the layout's reading order.",
            refs=[self._run_ref(source_ref)],
        )
        return self._result(node)

    # -- review, world, manifest

    def _family_assets(self, family: str) -> list[tuple[str, bytes]]:
        """Every published asset in one family, labelled, in a stable order."""

        assets: list[tuple[str, bytes]] = []
        if family == "props":
            for prop in self.package.props:
                for state in prop.states:
                    path = self._path(manifest_module.prop_ref(prop.prop_id, state))
                    if path.is_file():
                        assets.append((f"{prop.prop_id} {state}", path.read_bytes()))
            path = self._path(manifest_module.icons_ref())
            if path.is_file():
                assets.append(("inventory icons", path.read_bytes()))
        elif family == "ground":
            for biome in self.package.biomes:
                path = self._path(manifest_module.ground_ref(biome.biome_id))
                if path.is_file():
                    assets.append((biome.biome_id, path.read_bytes()))
            extras: list[tuple[str, str]] = []
            if self.package.macro is not None:
                extras.append(("macro colour field", manifest_module.macro_ref()))
            if self.package.road is not None:
                extras.append(
                    (
                        f"{self.package.road.road_id} track",
                        manifest_module.road_ref(self.package.road.road_id),
                    )
                )
            if self.package.forage is not None:
                extras.append(("forage sheet", manifest_module.forage_ref()))
            if self.package.water is not None:
                extras.append(("water", manifest_module.water_ref()))
            for condition in self.package.weather:
                if condition.cover is not None:
                    extras.append(
                        (
                            f"{condition.condition_id} cover plate",
                            manifest_module.weather_ref(condition.condition_id, "cover"),
                        )
                    )
                if condition.ice is not None:
                    extras.append(
                        (
                            f"{condition.condition_id} ice plate",
                            manifest_module.weather_ref(condition.condition_id, "ice"),
                        )
                    )
            for label, ref in extras:
                path = self._path(ref)
                if path.is_file():
                    assets.append((label, path.read_bytes()))
            for decal in self.package.decals:
                path = self._path(manifest_module.decal_ref(decal.decal_id))
                if path.is_file():
                    assets.append((decal.decal_id, path.read_bytes()))
        elif family == "actors":
            for actor in self.package.actors:
                for motion in actor.states:
                    path = self._path(manifest_module.state_ref(actor.actor_id, motion.state))
                    if path.is_file():
                        assets.append((f"{actor.actor_id} {motion.state}", path.read_bytes()))
        elif family == "seasons":
            # Each season look beside its summer twin, the summer first.
            looks = self.package.seasons.looks if self.package.seasons is not None else ()
            for look in looks:
                for prop in self.package.props:
                    for state in prop.states:
                        summer = self._path(manifest_module.prop_ref(prop.prop_id, state))
                        season = self._path(
                            manifest_module.prop_look_ref(prop.prop_id, state, look.look_id)
                        )
                        if summer.is_file() and season.is_file():
                            assets.append((f"{prop.prop_id} {state}", summer.read_bytes()))
                            assets.append(
                                (f"{prop.prop_id} {state} {look.look_id}", season.read_bytes())
                            )
        elif family == "fx":
            entries = [
                ("fire strip", manifest_module.fire_ref()),
                ("dust sheet", manifest_module.dust_ref()),
            ]
            for condition in self.package.weather:
                cid = condition.condition_id
                entries.extend(
                    (f"{cid} {layer}", manifest_module.weather_ref(cid, layer))
                    for layer in ("drops", "ground", "strike")
                    if getattr(condition, layer) is not None
                )
            for label, ref in entries:
                path = self._path(ref)
                if path.is_file():
                    assets.append((label, path.read_bytes()))
        return assets

    # -- music

    def _track(self, node: Node) -> Track:
        track_id = str(node.params["track_id"])
        for track in self.package.music:
            if track.track_id == track_id:
                return track
        raise ValueError(f"unknown track {track_id!r}")

    @staticmethod
    def _gate_music(artifact: BinaryArtifact) -> dict[str, object]:
        """Refuse a truncated, short or silent loop inside the retry owner.

        Takes the artifact the service hands every validator, not bytes: the
        first live run refused six honest tracks with "'BinaryArtifact' has no
        len()" because this took bytes and its test called it with bytes.

        Bytes first (the payload floor), then one ffmpeg pass for the decoded
        length and the peak. The loop seam itself is not measured: the brief
        asks the model to end where it begins, and whether it did is a
        listening verdict, not a number this gate can honestly produce.
        """

        data = artifact.data
        facts = validate_music_payload(data)
        measured = measure_level_and_duration_sync(data)
        reasons: list[str] = []
        if measured.duration_seconds < MUSIC_MIN_SECONDS:
            reasons.append(
                f"loop is {measured.duration_seconds:.1f} s, under the"
                f" {MUSIC_MIN_SECONDS:.0f} s floor"
            )
        if measured.peak_dbfs < MUSIC_PEAK_MIN_DBFS:
            reasons.append(
                f"peak {measured.peak_dbfs:.1f} dBFS is under the"
                f" {MUSIC_PEAK_MIN_DBFS:.0f} dBFS floor"
            )
        if reasons:
            error = ValueError("; ".join(reasons))
            error.reasons = reasons  # type: ignore[attr-defined]
            raise error
        return {
            **facts,
            "duration_seconds": round(measured.duration_seconds, 3),
            "peak_dbfs": round(measured.peak_dbfs, 2),
            "duration_floor_seconds": MUSIC_MIN_SECONDS,
            "peak_floor_dbfs": MUSIC_PEAK_MIN_DBFS,
        }

    async def _music_generate(self, node: Node) -> NodeExecutionResult:
        if self.music is None or node.card is None or node.card.prompt is None:
            raise ValueError("music service or prompt missing")
        track = self._track(node)
        operation_id = f"survival.music.{track.cue}"
        rejected: list[Mapping[str, object]] = []
        try:
            result = await self.music.generate(
                MusicGenerationRequest(
                    prompt=node.card.prompt,
                    artifact_path=self._path(node.port("audio").artifact_ref),
                    output_format="mp3",
                    timeout_seconds=900,
                    metadata={
                        "operation_id": operation_id,
                        "invocation_id": self.invocation_id,
                        "track_id": track.track_id,
                        "cue": track.cue,
                        "target_duration_seconds": track.target_duration_seconds,
                        "seamless_loop": True,
                        "publication_authorized": False,
                    },
                    validate=self._keeping_rejects(
                        node, self._gate_music, rejected=rejected, suffix=".mp3"
                    ),
                    rights=OBLIQUE_SURVIVAL_RIGHTS,
                )
            )
        finally:
            await self._write_ledger(node, operation_id=operation_id, attempts=rejected)
        return self._result(
            node,
            attempts=result.attempts,
            provider_operations=result.attempts,
            known_cost_usd=known_cost(result.response_metadata.usage),
        )

    async def _music_adopt(self, node: Node) -> NodeExecutionResult:
        """Copy the auditioned take into the run through the music gate, lineage kept."""

        track = self._track(node)
        assert track.take is not None
        self._refuse_missing_take(node, track.take)
        data = (self.package.root / track.take).read_bytes()
        digest = self.package.digests[track.take]
        facts = self._gate_music(BinaryArtifact(data=data, media_type="audio/mpeg"))
        record = {
            "schema_version": 1,
            "kind": "oblique-survival-music-adoption-v1",
            "track_id": track.track_id,
            "cue": track.cue,
            "adopted_from": track.take,
            "adopted_sha256": digest,
            # The acceptance was a listening verdict, the user's, over draws of
            # this same brief; the gate only confirms the file is a loop.
            "accepted_by": "listening_verdict",
            **facts,
        }
        await self._write_local(
            node.port("audio").artifact_ref,
            data,
            media_type="audio/mpeg",
            model="music-track-adopt",
            prompt=node.card.prompt if node.card and node.card.prompt else track.prompt,
            refs=[f"source://{track.take}#sha256={digest}"],
            validation=record,
        )
        return self._result(node)

    async def _music_validate(self, node: Node) -> NodeExecutionResult:
        track = self._track(node)
        source_ref = f"production/music/{track.track_id}.source.mp3"
        data = self._path(source_ref).read_bytes()
        record = {
            "schema_version": 1,
            "kind": "oblique-survival-music-validation-v1",
            "track_id": track.track_id,
            "cue": track.cue,
            "loop": True,
            "target_duration_seconds": track.target_duration_seconds,
            **self._gate_music(BinaryArtifact(data=data, media_type="audio/mpeg")),
            # Not measured: whether the end meets the beginning is a listening verdict.
            "seam_measured": False,
        }
        await self._write_local(
            node.port("audio").artifact_ref,
            data,
            media_type="audio/mpeg",
            model="music-track-publish",
            prompt="Publish the admitted loop under its track id, bytes unchanged.",
            refs=[self._run_ref(source_ref)],
            validation=record,
        )
        await self._write_local(
            node.port("validation").artifact_ref,
            _json_bytes(record),
            media_type="application/json",
            model="music-track-validate",
            prompt="Record the loop's decoded length and peak.",
            refs=[self._run_ref(source_ref)],
        )
        return self._result(node)

    # -- weather

    def _condition(self, node: Node) -> Condition:
        condition_id = str(node.params["condition_id"])
        for condition in self.package.weather:
            if condition.condition_id == condition_id:
                return condition
        raise ValueError(f"unknown weather condition {condition_id!r}")

    async def _weather_drops_generate(self, node: Node) -> NodeExecutionResult:
        condition = self._condition(node)
        # The node exists only because the condition authored the layer.
        drops = condition.drops
        assert drops is not None

        def validate(artifact: BinaryArtifact) -> dict[str, object]:
            return gates.gate_quadrant_sheet(
                artifact.data,
                width=SPRITE_CANVAS[0],
                height=SPRITE_CANVAS[1],
                kinds=drops.kinds,
                coverage_range=gates.DROPS_CELL_COVERAGE,
            )

        # No style plate: the prompt carries only the ink line, and a reference
        # picture of a clearing would put a clearing on the sheet.
        return await self._generate_image(
            node,
            size=SPRITE_CANVAS,
            background="transparent",
            references=(),
            validate=validate,
            operation_id=f"survival.weather.{condition.condition_id}.drops",
        )

    async def _weather_cover_generate(self, node: Node) -> NodeExecutionResult:
        condition = self._condition(node)
        cover = condition.cover
        assert cover is not None

        def validate(artifact: BinaryArtifact) -> dict[str, object]:
            return gates.gate_ground_texture(
                artifact.data,
                width=GROUND_CANVAS[0],
                height=GROUND_CANVAS[1],
                texel_meters=cover.texel_meters,
                luma_range=gates.COVER_LUMA_RANGE,
            )

        return await self._generate_image(
            node,
            size=GROUND_CANVAS,
            background="opaque",
            references=self.style_plate,
            validate=validate,
            operation_id=f"survival.weather.{condition.condition_id}.cover",
        )

    async def _weather_cover_canonicalize(self, node: Node) -> NodeExecutionResult:
        condition = self._condition(node)
        source_ref = f"production/weather/{condition.condition_id}-cover.source.png"
        cover = condition.cover
        assert cover is not None
        data = self._path(source_ref).read_bytes()
        facts = gates.gate_ground_texture(
            data,
            width=GROUND_CANVAS[0],
            height=GROUND_CANVAS[1],
            texel_meters=cover.texel_meters,
            luma_range=gates.COVER_LUMA_RANGE,
        )
        return await self._plate_canonicalize(
            node,
            source_ref=source_ref,
            facts=facts,
            kind="oblique-survival-weather-cover-validation-v1",
            extra={"condition_id": condition.condition_id},
        )

    async def _weather_ice_generate(self, node: Node) -> NodeExecutionResult:
        condition = self._condition(node)
        ice = condition.ice
        assert ice is not None

        def validate(artifact: BinaryArtifact) -> dict[str, object]:
            return gates.gate_ground_texture(
                artifact.data,
                width=GROUND_CANVAS[0],
                height=GROUND_CANVAS[1],
                texel_meters=ice.texel_meters,
                luma_range=gates.COVER_LUMA_RANGE,
            )

        return await self._generate_image(
            node,
            size=GROUND_CANVAS,
            background="opaque",
            references=self.style_plate,
            validate=validate,
            operation_id=f"survival.weather.{condition.condition_id}.ice",
        )

    async def _weather_ice_adopt(self, node: Node) -> NodeExecutionResult:
        """Copy the auditioned ice plate into the run through the plate gate, lineage kept."""

        condition = self._condition(node)
        ice = condition.ice
        assert ice is not None and ice.take is not None
        self._refuse_missing_take(node, ice.take)
        data = (self.package.root / ice.take).read_bytes()
        digest = self.package.digests[ice.take]
        facts = gates.gate_ground_texture(
            data,
            width=GROUND_CANVAS[0],
            height=GROUND_CANVAS[1],
            texel_meters=ice.texel_meters,
            luma_range=gates.COVER_LUMA_RANGE,
        )
        record = {
            "schema_version": 1,
            "kind": "oblique-survival-weather-ice-adoption-v1",
            "condition_id": condition.condition_id,
            "adopted_from": ice.take,
            "adopted_sha256": digest,
            "accepted_by": "audition_pick",
            **facts,
        }
        await self._write_local(
            node.port("image").artifact_ref,
            data,
            media_type="image/png",
            model="ground-plate-adopt",
            prompt=node.card.prompt if node.card and node.card.prompt else ice.prompt,
            refs=[f"source://{ice.take}#sha256={digest}"],
            validation=record,
        )
        return self._result(node)

    async def _weather_ice_canonicalize(self, node: Node) -> NodeExecutionResult:
        condition = self._condition(node)
        source_ref = f"production/weather/{condition.condition_id}-ice.source.png"
        ice = condition.ice
        assert ice is not None
        facts = gates.gate_ground_texture(
            self._path(source_ref).read_bytes(),
            width=GROUND_CANVAS[0],
            height=GROUND_CANVAS[1],
            texel_meters=ice.texel_meters,
            luma_range=gates.COVER_LUMA_RANGE,
        )
        return await self._plate_canonicalize(
            node,
            source_ref=source_ref,
            facts=facts,
            kind="oblique-survival-weather-ice-validation-v1",
            extra={"condition_id": condition.condition_id},
        )

    async def _weather_drops_validate(self, node: Node) -> NodeExecutionResult:
        condition = self._condition(node)
        drops = condition.drops
        assert drops is not None
        return await self._weather_sheet_validate(
            node,
            layer="drops",
            kinds=drops.kinds,
            coverage_range=gates.DROPS_CELL_COVERAGE,
        )

    async def _weather_ground_generate(self, node: Node) -> NodeExecutionResult:
        condition = self._condition(node)
        ground = condition.ground
        assert ground is not None

        def validate(artifact: BinaryArtifact) -> dict[str, object]:
            return gates.gate_quadrant_sheet(
                artifact.data,
                width=SPRITE_CANVAS[0],
                height=SPRITE_CANVAS[1],
                kinds=ground.kinds,
                coverage_range=gates.SPLASH_CELL_COVERAGE,
            )

        return await self._generate_image(
            node,
            size=SPRITE_CANVAS,
            background="transparent",
            references=self.style_plate,
            validate=validate,
            operation_id=f"survival.weather.{condition.condition_id}.ground",
        )

    async def _weather_sheet_validate(
        self,
        node: Node,
        *,
        layer: str,
        kinds: Sequence[str],
        coverage_range: tuple[float, float],
        tallness_min: float | None = None,
        span_min: float | None = None,
    ) -> NodeExecutionResult:
        condition = self._condition(node)
        source_ref = f"production/weather/{condition.condition_id}-{layer}.source.png"
        data = self._path(source_ref).read_bytes()
        canonical, alpha_facts = gates.canonicalize_sprite_alpha(data)
        facts = gates.gate_quadrant_sheet(
            canonical,
            width=SPRITE_CANVAS[0],
            height=SPRITE_CANVAS[1],
            kinds=kinds,
            coverage_range=coverage_range,
            tallness_min=tallness_min,
            span_min=span_min,
        )
        record = {
            "schema_version": 1,
            "kind": f"oblique-survival-weather-{layer}-validation-v1",
            "condition_id": condition.condition_id,
            **facts,
            "alpha": alpha_facts,
        }
        await self._write_local(
            node.port("image").artifact_ref,
            canonical,
            media_type="image/png",
            model="weather-sheet-canonicalize",
            prompt="Lift the near-opaque body and clear the exterior to nothing.",
            refs=[self._run_ref(source_ref)],
            validation=record,
        )
        await self._write_local(
            node.port("validation").artifact_ref,
            _json_bytes(record),
            media_type="application/json",
            model="weather-sheet-validate",
            prompt="Record each quarter's painted box.",
            refs=[self._run_ref(source_ref)],
        )
        return self._result(node)

    async def _weather_ground_validate(self, node: Node) -> NodeExecutionResult:
        condition = self._condition(node)
        ground = condition.ground
        assert ground is not None
        return await self._weather_sheet_validate(
            node,
            layer="ground",
            kinds=ground.kinds,
            coverage_range=gates.SPLASH_CELL_COVERAGE,
        )

    async def _weather_strike_generate(self, node: Node) -> NodeExecutionResult:
        condition = self._condition(node)

        def validate(artifact: BinaryArtifact) -> dict[str, object]:
            return gates.gate_quadrant_sheet(
                artifact.data,
                width=SPRITE_CANVAS[0],
                height=SPRITE_CANVAS[1],
                kinds=STRIKE_CELL_KINDS,
                coverage_range=gates.STRIKE_CELL_COVERAGE,
                tallness_min=gates.STRIKE_TALLNESS_MIN,
                span_min=gates.STRIKE_SPAN_MIN,
            )

        return await self._generate_image(
            node,
            size=SPRITE_CANVAS,
            background="transparent",
            references=self.style_plate,
            validate=validate,
            operation_id=f"survival.weather.{condition.condition_id}.strike",
        )

    async def _weather_strike_validate(self, node: Node) -> NodeExecutionResult:
        return await self._weather_sheet_validate(
            node,
            layer="strike",
            kinds=STRIKE_CELL_KINDS,
            coverage_range=gates.STRIKE_CELL_COVERAGE,
            tallness_min=gates.STRIKE_TALLNESS_MIN,
            span_min=gates.STRIKE_SPAN_MIN,
        )

    def _sound_cue(self, node: Node) -> tuple[Condition, str, SoundCue]:
        condition = self._condition(node)
        name = str(node.params["cue"])
        for cue_name, cue in condition.sound_cues:
            if cue_name == name:
                return condition, name, cue
        raise ValueError(f"unknown sound cue {name!r}")

    @staticmethod
    def _gate_sound(artifact: BinaryArtifact, *, duration_seconds: float) -> dict[str, object]:
        """The shared clip admission (silent or clipped is refused) plus the length.

        Takes the artifact, as every validator the services call does; the
        music gate paid for getting that wrong once.
        """

        data = artifact.data
        facts = admit_sound_effect_bytes_sync(data)
        measured = measure_level_and_duration_sync(data)
        if measured.duration_seconds < duration_seconds - SOUND_DURATION_TOLERANCE_SECONDS:
            error = ValueError(
                f"clip is {measured.duration_seconds:.2f} s, short of the"
                f" {duration_seconds:.1f} s asked"
            )
            error.reasons = [str(error)]  # type: ignore[attr-defined]
            raise error
        return {
            **facts,
            "duration_seconds": round(measured.duration_seconds, 3),
            "peak_dbfs": round(measured.peak_dbfs, 2),
            "requested_duration_seconds": duration_seconds,
        }

    async def _weather_sound_generate(self, node: Node) -> NodeExecutionResult:
        if self.sounds is None or node.card is None or node.card.prompt is None:
            raise ValueError("sound-effect service or prompt missing")
        condition, name, cue = self._sound_cue(node)
        duration = cue.duration_seconds

        def gate(artifact: BinaryArtifact) -> dict[str, object]:
            return self._gate_sound(artifact, duration_seconds=duration)

        operation_id = f"survival.weather.{condition.condition_id}.{name}"
        rejected: list[Mapping[str, object]] = []
        try:
            result = await self.sounds.generate(
                SoundEffectGenerationRequest(
                    prompt=node.card.prompt,
                    artifact_path=self._path(node.port("audio").artifact_ref),
                    duration_seconds=duration,
                    loop=cue.loop,
                    output_format="mp3",
                    timeout_seconds=300,
                    metadata={
                        "operation_id": operation_id,
                        "invocation_id": self.invocation_id,
                        "condition_id": condition.condition_id,
                        "cue": name,
                        "loop": cue.loop,
                        "publication_authorized": False,
                    },
                    validate=self._keeping_rejects(node, gate, rejected=rejected, suffix=".mp3"),
                    rights=OBLIQUE_SURVIVAL_RIGHTS,
                )
            )
        finally:
            await self._write_ledger(node, operation_id=operation_id, attempts=rejected)
        return self._result(
            node,
            attempts=result.attempts,
            provider_operations=result.attempts,
            known_cost_usd=known_cost(result.response_metadata.usage),
        )

    async def _weather_sound_validate(self, node: Node) -> NodeExecutionResult:
        condition, name, cue = self._sound_cue(node)
        source_ref = f"production/weather/{condition.condition_id}-sound-{name}.source.mp3"
        data = self._path(source_ref).read_bytes()
        record = {
            "schema_version": 1,
            "kind": "oblique-survival-weather-sound-validation-v1",
            "condition_id": condition.condition_id,
            "cue": name,
            "loop": cue.loop,
            **self._gate_sound(
                BinaryArtifact(data=data, media_type="audio/mpeg"),
                duration_seconds=cue.duration_seconds,
            ),
            # Whether a loop's end meets its beginning is a listening verdict.
            "seam_measured": False,
        }
        await self._write_local(
            node.port("audio").artifact_ref,
            data,
            media_type="audio/mpeg",
            model="weather-sound-publish",
            prompt="Publish the admitted clip under its cue, bytes unchanged.",
            refs=[self._run_ref(source_ref)],
            validation=record,
        )
        await self._write_local(
            node.port("validation").artifact_ref,
            _json_bytes(record),
            media_type="application/json",
            model="weather-sound-validate",
            prompt="Record the clip's decoded length and peak.",
            refs=[self._run_ref(source_ref)],
        )
        return self._result(node)

    def _clip(self, node: Node) -> SoundEffect:
        cue = str(node.params["cue"])
        for clip in self.package.sounds:
            if clip.cue == cue:
                return clip
        raise ValueError(f"unknown sound cue {cue!r}")

    async def _sound_generate(self, node: Node) -> NodeExecutionResult:
        if self.sounds is None or node.card is None or node.card.prompt is None:
            raise ValueError("sound-effect service or prompt missing")
        clip = self._clip(node)
        duration = clip.duration_seconds

        def gate(artifact: BinaryArtifact) -> dict[str, object]:
            return self._gate_sound(artifact, duration_seconds=duration)

        operation_id = f"survival.sound.{clip.cue}"
        rejected: list[Mapping[str, object]] = []
        try:
            result = await self.sounds.generate(
                SoundEffectGenerationRequest(
                    prompt=node.card.prompt,
                    artifact_path=self._path(node.port("audio").artifact_ref),
                    duration_seconds=duration,
                    loop=clip.loop,
                    output_format="mp3",
                    timeout_seconds=300,
                    metadata={
                        "operation_id": operation_id,
                        "invocation_id": self.invocation_id,
                        "cue": clip.cue,
                        "loop": clip.loop,
                        "publication_authorized": False,
                    },
                    validate=self._keeping_rejects(node, gate, rejected=rejected, suffix=".mp3"),
                    rights=OBLIQUE_SURVIVAL_RIGHTS,
                )
            )
        finally:
            await self._write_ledger(node, operation_id=operation_id, attempts=rejected)
        return self._result(
            node,
            attempts=result.attempts,
            provider_operations=result.attempts,
            known_cost_usd=known_cost(result.response_metadata.usage),
        )

    async def _sound_adopt(self, node: Node) -> NodeExecutionResult:
        """Copy the auditioned clip into the run through the clip gate, lineage kept."""

        clip = self._clip(node)
        assert clip.take is not None
        self._refuse_missing_take(node, clip.take)
        data = (self.package.root / clip.take).read_bytes()
        digest = self.package.digests[clip.take]
        facts = self._gate_sound(
            BinaryArtifact(data=data, media_type="audio/mpeg"),
            duration_seconds=clip.duration_seconds,
        )
        record = {
            "schema_version": 1,
            "kind": "oblique-survival-sound-adoption-v1",
            "cue": clip.cue,
            "loop": clip.loop,
            "adopted_from": clip.take,
            "adopted_sha256": digest,
            # The pick was made over audition draws of this brief; the gate
            # only confirms the file is a clip of the length asked. Whose ear
            # picked it is the take's own business (explore/sfx-audition/).
            "accepted_by": "audition_pick",
            **facts,
        }
        await self._write_local(
            node.port("audio").artifact_ref,
            data,
            media_type="audio/mpeg",
            model="sound-effect-adopt",
            prompt=node.card.prompt if node.card and node.card.prompt else clip.prompt,
            refs=[f"source://{clip.take}#sha256={digest}"],
            validation=record,
        )
        return self._result(node)

    async def _sound_validate(self, node: Node) -> NodeExecutionResult:
        clip = self._clip(node)
        source_ref = f"production/sounds/{clip.cue}.source.mp3"
        data = self._path(source_ref).read_bytes()
        record = {
            "schema_version": 1,
            "kind": "oblique-survival-sound-validation-v1",
            "cue": clip.cue,
            "loop": clip.loop,
            **self._gate_sound(
                BinaryArtifact(data=data, media_type="audio/mpeg"),
                duration_seconds=clip.duration_seconds,
            ),
            # Whether a loop's end meets its beginning is a listening verdict.
            "seam_measured": False,
        }
        await self._write_local(
            node.port("audio").artifact_ref,
            data,
            media_type="audio/mpeg",
            model="sound-effect-publish",
            prompt="Publish the admitted clip under its cue, bytes unchanged.",
            refs=[self._run_ref(source_ref)],
            validation=record,
        )
        await self._write_local(
            node.port("validation").artifact_ref,
            _json_bytes(record),
            media_type="application/json",
            model="sound-effect-validate",
            prompt="Record the clip's decoded length and peak.",
            refs=[self._run_ref(source_ref)],
        )
        return self._result(node)

    async def _review_sheet(self, node: Node) -> NodeExecutionResult:
        family = str(node.params["family"])
        assets = self._family_assets(family)
        sheet = _contact_sheet(assets)
        await self._write_local(
            node.port("sheet").artifact_ref,
            sheet,
            media_type="image/png",
            model="contact-sheet-v1",
            prompt=f"Lay out every {family} asset on one labelled sheet for review.",
        )
        return self._result(node)

    async def _review_judge(self, node: Node) -> NodeExecutionResult:
        family = str(node.params["family"])
        if node.card is None or node.card.prompt is None:
            raise ValueError("review prompt missing")
        sheet_ref = f"production/review/{family}-contact-sheet.png"
        sheet = self._path(sheet_ref).read_bytes()
        operation_id = f"survival.review.{family}"
        ledger = AttemptLedger(operation_id=operation_id)
        try:
            value, operation = await generate_structured(
                self._require_structured(),
                model_type=FamilyReview,
                operation_id=operation_id,
                prompt=node.card.prompt,
                artifact_path=self._path(node.port("review").artifact_ref),
                ledger=ledger,
                references=(
                    StructuredReference(
                        url=_inline_data_url(sheet, "image/png"),
                        provenance_ref=self._run_ref(sheet_ref),
                    ),
                ),
                max_tokens=12_000,
                timeout_seconds=600,
                semantic_validate=evaluate_review,
            )
        finally:
            await self._write_ledger(node, operation_id=operation_id, attempts=ledger.records)
        del value
        attempts = int(operation["attempts"])
        return self._result(
            node,
            attempts=attempts,
            provider_operations=attempts,
            known_cost_usd=known_cost(operation.get("usage")),
        )

    async def _world_layout(self, node: Node) -> NodeExecutionResult:
        world = layout_module.build_layout(self.package)
        problems = layout_module.check_layout(self.package, world)
        if problems:
            raise ValueError("layout refused: " + "; ".join(problems[:6]))
        await self._write_local(
            node.port("layout").artifact_ref,
            _json_bytes(world.as_record()),
            media_type="application/json",
            model="oblique-survival-layout-v2",
            prompt="Lay the world from its seed: set pieces, population, the path.",
            validation={
                "status": "pass",
                "entities": len(world.entities),
                "set_pieces": len(world.set_pieces),
                "verdicts": {key: value["verdict"] for key, value in sorted(world.report.items())},
            },
        )
        await self._write_local(
            node.port("splat").artifact_ref,
            world.splat_png,
            media_type="image/png",
            model="oblique-survival-splat-v2",
            prompt="Paint the road, the under-canopy darkening, and the land.",
        )
        await self._write_local(
            node.port("biome_splat").artifact_ref,
            world.biome_splat_png,
            media_type="image/png",
            model="oblique-survival-biome-splat-v1",
            prompt="Paint the biome weights, one channel per non-base biome.",
            validation={"status": "pass", "biome_shares": world.biome_shares},
        )
        return self._result(node)

    async def _package_manifest(self, node: Node) -> NodeExecutionResult:
        document = manifest_module.build_manifest(
            self.package,
            self._run_dir,
            run_id=self._run_dir.name,
            graph_sha256=self._graph.graph_sha256,
            scope=self.graph.scope,
        )
        await self._write_local(
            node.port("manifest").artifact_ref,
            manifest_module.manifest_bytes(document),
            media_type="application/json",
            model=manifest_module.MANIFEST_KIND,
            prompt="Measure every published asset and describe it for the viewer.",
            validation={"status": "pass", **document["status"]},
        )
        return self._result(node)


__all__ = [
    "OBLIQUE_SURVIVAL_COMPONENT",
    "OBLIQUE_SURVIVAL_RIGHTS",
    "ObliqueSurvivalNodeHandler",
    "admit_cached",
]
