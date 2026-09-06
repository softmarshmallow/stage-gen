"""The manifest: the only contract between the pipeline and the viewer.

Two rules hold this file together.

First, **the viewer never infers scale from pixels**. Every image gets a
``px_per_meter`` measured here from the painted alpha bounding box against an
authored world height, and the viewer only ever divides. Nothing an image model
returns carries a size, so magnitude is authored, in player heights, per look:
a look with its own ``look_height_units`` is calibrated from its own painted
extent against its own number (the way the platformer calibrates each actor
state), and a look without one rides the baseline look's ruler, so it is the
size it was drawn at. Either way the drawing's own opinion of the size is kept
as a fact (``drawn_height_meters``, the height at the baseline's ruler) beside
the canonical one, so a stump drawn waist-high shows up in the record as a
drift, and in the world at knee height.

Second, **a missing family is a status, not a crash**. A scope that generated no
actors still produces a manifest the viewer can open; ``status.actors`` says
``missing`` and the block is empty.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sized
from io import BytesIO
from pathlib import Path
from typing import Any, Final, NotRequired, Protocol, TypedDict, cast

from PIL import Image

from stage_gen.components.game_ui.nodes import document_roles, ui_atlas_manifest_block
from stage_gen.recipes.dry_run import is_placeholder
from stage_gen.recipes.oblique_survival.models import (
    MUSIC_CUES,
    Actor,
    MotionState,
    Package,
    Prop,
    strip_key,
)

SCHEMA_VERSION: Final = 1
MANIFEST_KIND: Final = "oblique-survival-manifest-v1"
#: The seam every actor gets. A billboard that moves cannot be handed a skirt
#: decal laid at layout time or a patch of earth painted into its cutout: the
#: first would stay behind, the second would travel with it over water and
#: paths alike. So the actor seam is never the package's ``ground_contact``;
#: it is a contact shadow, drawn by the consumer under the feet every frame.
ACTOR_GROUND_CONTACT: Final = "shadow"

#: The repacked motion strip reserves this many pixels under the feet.
MOTION_BOTTOM_GUTTER_PX: Final = 12


class _BandAccess(Protocol):
    """One single-band image's pixels; Pillow types the accessor as a union."""

    def __getitem__(self, xy: tuple[int, int]) -> int: ...


ALPHA_THRESHOLD: Final = 16
FIXTURE_CANVAS: Final = 1024
FIXTURE_STRIP: Final = (1536, 1024)


# --- the shape of the document -------------------------------------------------------
#
# One TypedDict per block the assembly below returns. The manifest is the only
# contract between the pipeline and the viewer, so the shape is declared where the
# document is built rather than discovered where a consumer trips over a missing key.
# None of this is a runtime type: a TypedDict is a plain dict, and ``manifest_bytes``
# serialises what it always did.

#: An untyped JSON record read back from one of the run's own sidecars (a validation
#: record, an actor's rebase, a prop's anchor, the layout). The blocks below are the
#: manifest's own shape and are typed; a sidecar is a document another node wrote, and
#: coercing what it holds would change what the manifest publishes, so it stays open.
type JsonRecord = dict[str, Any]
#: One row of a lattice as the manifest publishes it: the window the atlas cuts
#: (``index``, ``x``, ``y``, ``w``, ``h``) merged with whatever authored facts the
#: sheet adds to its cells. The merge is open by construction, so the row is not a
#: block of its own.
type CellRow = dict[str, Any]


class LatticeSheet[CellT](Protocol):
    """A sheet of ground pieces: a grid of authored cells at one metre scale.

    Read-only, so a frozen authored sheet (the litter, the forage, the plants)
    satisfies it as it stands.
    """

    @property
    def columns(self) -> int: ...
    @property
    def rows(self) -> int: ...
    @property
    def cell_meters(self) -> float: ...
    @property
    def cell_count(self) -> int: ...
    @property
    def cells(self) -> tuple[CellT, ...]: ...


class SpriteFacts(TypedDict):
    """What ``measure_sprite`` reports about one canvas."""

    width_px: int
    height_px: int
    painted: bool
    bbox: list[int] | None
    bbox_height_px: int
    ground_contact_y_normalized: float
    alpha_bottom_y_normalized: float
    #: Absent on an unpainted canvas, which is the one case a caller branches on.
    bbox_width_px: NotRequired[int]
    center_x_normalized: NotRequired[float]


class StripSpec(TypedDict):
    """One motion strip: the atlas, its cell geometry, and its ruler."""

    atlas: str
    columns: int
    rows: int
    frames: int
    cell_width: int
    cell_height: int
    bottom_gutter_px: int
    px_per_meter: float
    mode: str
    canonical_frame_indices: list[int]
    fps: float
    rebase_multiplier: float
    #: A four-way state only: the same spec once per drawn facing, the front's
    #: fields repeated at the top level for a consumer that does not turn.
    facings: NotRequired[dict[str, StripSpec]]


class ActorStill(TypedDict):
    image: str
    width_px: int
    height_px: int
    px_per_meter: float
    ground_contact_y_normalized: float


class ActorFacings(TypedDict):
    set: str
    side_view: str | None
    names: list[str]


class ActorBlock(TypedDict):
    role: str
    display_name: str
    height_meters: float
    facings: ActorFacings
    facing_authored: str | None
    mirror_for_left: bool
    baseline_state: str
    footprint_radius_meters: float
    shadow_width_meters: float
    ground_contact: str
    still: ActorStill | None
    states: dict[str, StripSpec]
    rebase: str | None


class PropLook(TypedDict):
    image: str
    width_px: int
    height_px: int
    px_per_meter: float
    ground_contact_y_normalized: float
    anchor: list[float] | None


class PropState(TypedDict):
    image: str
    width_px: int
    height_px: int
    px_per_meter: float
    height_meters: float
    height_units_source: str
    drawn_height_meters: float
    ground_contact_y_normalized: float
    anchor: list[float] | None
    floor_plate_suspected: bool
    looks: dict[str, PropLook]


class PropYield(TypedDict):
    item_id: str
    count: int


class PropTool(TypedDict):
    item_id: str
    hits: int
    required: bool


#: One thing that can be done to a prop. ``from`` is the states it is on offer
#: from (a keyword, hence the functional form); ``yield_to`` is ``hand`` (into
#: the pack at the last blow) or ``ground`` (dropped there). A prop lists
#: several in priority order; the consumer offers the first available one for
#: the prop's current state.
PropInteraction = TypedDict(
    "PropInteraction",
    {
        "verb": str,
        "from": list[str],
        "hits": int,
        "next_state": str,
        "fx": str,
        "regrow_seconds": float | None,
        "progress": list[str],
        "yields": list[PropYield],
        "yield_to": str,
        "tool": PropTool | None,
    },
)


class PropDrawn(TypedDict):
    """How the looks were drawn: a fact for the reader, never a switch."""

    kind: str
    columns: NotRequired[int]
    rows: NotRequired[int]


class PropVariants(TypedDict):
    states: list[str]
    weights: list[float]


class PropBlock(TypedDict):
    family: str
    height_meters: float
    footprint_radius_meters: float
    shadow_width_meters: float
    edge: str
    motion_hint: str
    hit_reaction: str
    baseline_state: str
    drawn: PropDrawn
    variants: PropVariants | None
    states: dict[str, PropState]
    interactions: list[PropInteraction]
    anchor_record: str | None


class PieceSheetLook(TypedDict):
    """A season look of a piece sheet: its own atlas and its own cell bounds."""

    atlas: str
    cells: list[CellRow]


class PieceSheetBlock(TypedDict):
    atlas: str
    columns: int
    rows: int
    cell_meters: float
    width_px: int
    height_px: int
    cells: list[CellRow]
    #: The plant sheet only, and only when a season names a look.
    looks: NotRequired[dict[str, PieceSheetLook]]


class BiomeBlock(TypedDict):
    texture: str
    texel_meters: float
    tiling: str
    weight_channel: str
    share: float | None
    tiled_px: int
    tiled_px_height: int
    value_target: float
    #: Measured from the plate itself and carried so the consumer can level the
    #: ground to the authored target; absent from an older validation record.
    luma_mean: float | None
    friction: float


class DecalBlock(TypedDict):
    image: str
    use: str
    families: list[str]
    width_meters: float
    height_meters: float
    width_px: int
    height_px: int


class MacroBlock(TypedDict):
    texture: str
    texel_meters: float
    period_meters: float
    tiling: str
    strength: float
    luma_mean: float


class RoadBlock(TypedDict):
    road_id: str
    texture: str
    texel_meters: float
    tiling: str
    width_meters: float
    edge_meters: float
    splat_channel: str
    value_target: float
    luma_mean: float | None


class WaterBlock(TypedDict):
    texture: str | None
    texel_meters: float
    tiling: str
    colour: list[float]
    value_target: float
    depth_meters: float
    cliff_colour: list[float]
    luma_mean: float | None


class WorldBlock(TypedDict):
    seed: int
    size_meters: float
    spawn_set_piece: str
    set_pieces: list[dict[str, object]]


class SplatBlock(TypedDict):
    image: str
    resolution: int
    #: Metres per plate cell, published so no host infers it from the size.
    cell_meters: float
    channels: dict[str, str | None]
    #: The viewer's composition numbers: floats, plus the per-biome ``level``
    #: map. Mixing, never identity, and open by design.
    blend: dict[str, object]


class BiomeSplatBlock(TypedDict):
    image: str
    resolution: int
    cell_meters: float
    channels: dict[str, str | None]


class GroundBlock(TypedDict):
    size_meters: float
    base_biome: str
    biomes: dict[str, BiomeBlock]
    biome_splat: BiomeSplatBlock | None
    macro: MacroBlock | None
    road: RoadBlock | None
    clutter: PieceSheetBlock | None
    forage: PieceSheetBlock | None
    plants: PieceSheetBlock | None
    water: WaterBlock | None
    splat: SplatBlock | None
    decals: dict[str, DecalBlock]


class FireBlock(TypedDict):
    strip: str
    columns: int
    rows: int
    frames: int
    cell_px: int
    px_per_meter: float
    height_meters: float
    fps: float
    mode: str
    blend: str
    base_origin: list[float]


class DustBlock(TypedDict):
    atlas: str
    width_px: int
    height_px: int
    px_per_meter: float
    cells: list[CellRow]


class FxBlock(TypedDict):
    fire: FireBlock | None
    dust: DustBlock | None


class WeatherPlate(TypedDict):
    """A weather ground plate (the snow cover, the ice), laid like a biome's."""

    texture: str
    texel_meters: float
    tiling: str
    value_target: float
    luma_mean: float | None


class WeatherDropsBlock(TypedDict):
    atlas: str
    width_px: int
    height_px: int
    cells: list[CellRow]
    count_per_screen: int
    layers: int
    fall_speed_meters_per_second: float
    height_meters: float


class WeatherGroundBlock(TypedDict):
    atlas: str
    width_px: int
    height_px: int
    px_per_meter: float
    height_meters: float
    rate_per_100_sqm_per_second: float
    cells: list[CellRow]


class WeatherWetBlock(TypedDict):
    decal_id: str
    dry_seconds: float


class WeatherStrikeBlock(TypedDict):
    atlas: str
    width_px: int
    height_px: int
    height_meters: float
    above: float
    interval_seconds: list[float]
    flash_seconds: float
    cells: list[CellRow]


class WeatherSoundBlock(TypedDict):
    audio: str
    loop: bool
    duration_seconds: float
    peak_dbfs: float | None


class WeatherConditionBlock(TypedDict):
    onset_seconds: float
    decay_seconds: float
    dry_spell_seconds: list[float]
    wet_spell_seconds: list[float]
    tint: list[float]
    desaturate: float
    drops: WeatherDropsBlock | None
    ground: WeatherGroundBlock | None
    wet: WeatherWetBlock | None
    strike: WeatherStrikeBlock | None
    cover: WeatherPlate | None
    ice: WeatherPlate | None
    sound: dict[str, WeatherSoundBlock]


class MusicTrackBlock(TypedDict):
    track_id: str
    audio: str
    take: str | None
    loop: bool
    target_duration_seconds: float
    duration_seconds: float | None
    peak_dbfs: float | None


class MusicTransitionBlock(TypedDict):
    crossfade_seconds: float
    curve: str
    overlap: float
    switch_at: float


class SoundBlock(TypedDict):
    audio: str
    take: str | None
    loop: bool
    duration_seconds: float
    peak_dbfs: float | None
    gain: float
    pitch_jitter: float
    onsets: bool


class IconsBlock(TypedDict):
    atlas: str
    columns: int
    rows: int
    cell_px: int
    width_px: int
    height_px: int
    cells: list[CellRow]


class ItemUseBlock(TypedDict):
    kind: str
    hunger: float
    health: float
    radius_meters: float
    burn_seconds: float
    slots: int
    warmth: float
    insulation: float
    heat_seconds: float


class ItemToolBlock(TypedDict):
    verb: str
    uses: int


class ItemBlock(TypedDict):
    image: str
    width_px: int
    height_px: int
    px_per_meter: float
    height_meters: float
    #: A window on the icon sheet, or nothing, in which case the consumer
    #: shows the pickup sprite.
    icon: dict[str, Any] | None
    display_name: str
    stack_max: int
    use: ItemUseBlock | None
    tool: ItemToolBlock | None


class CraftingStationBlock(TypedDict):
    prop_id: str
    state: str | None
    reach_meters: float


class CraftingProductBlock(TypedDict):
    """An item with a count, or a prop to build in a named look; never both."""

    item_id: NotRequired[str]
    count: NotRequired[int]
    prop_id: NotRequired[str | None]
    state: NotRequired[str | None]


class CraftingRecipeBlock(TypedDict):
    recipe_id: str
    ingredients: dict[str, int]
    station: str
    product: CraftingProductBlock


class CraftingBlock(TypedDict):
    slots: int
    start: dict[str, int]
    stations: dict[str, CraftingStationBlock]
    recipes: list[CraftingRecipeBlock]


class GameplayBlock(TypedDict):
    day_length_seconds: float
    player_speed_meters_per_second: float
    interact_reach_meters: float
    approach_meters: float
    pickup: str
    hunger: dict[str, Any]
    health: dict[str, Any]
    mob: dict[str, Any]
    campfire: dict[str, Any]
    night: dict[str, Any]
    warmth: dict[str, Any]
    torch: dict[str, Any]


class SeasonsCalendar(TypedDict):
    order: list[str]
    days_per_season: int


class SeasonBlock(TypedDict):
    season_id: str
    display_name: str
    snow: float
    cold: float
    night_share: float
    regrow_scale: float
    hidden_forage: list[str]
    barren: list[str]
    look: str


class SeasonsBlock(TypedDict, total=False):
    """Empty when no calendar is authored: the world stays as drawn."""

    calendar: SeasonsCalendar
    seasons: list[SeasonBlock]
    looks: list[str]


class LookGroundPieces(TypedDict):
    orientation: str
    jitter_degrees: float


class LookBlock(TypedDict):
    light: str
    mirror: str
    ground_pieces: LookGroundPieces


class RunBlock(TypedDict):
    run_id: str
    graph_sha256: str | None
    scope: str
    source_digest: str


class StatusBlock(TypedDict):
    actors: str
    props: str
    ground: str
    ground_layers: str
    fx: str
    items: str
    music: str
    weather: str
    sounds: str
    seasons: str
    #: ``none`` for a package with no ui.toml, ``ok`` when every sheet is here.
    ui: str
    layout: str


class StyleBlock(TypedDict):
    label: str
    #: The plate's digest, not its path; absent when the package has no plate.
    reference_sha256: NotRequired[str]


class ScaleBlock(TypedDict):
    player_height_meters: float


class CameraBlock(TypedDict):
    pitch_degrees: float
    fov_degrees: float
    distance_meters: float
    asset_pitch_degrees: float
    follow_lerp: float
    rotation_allowed: bool
    yaw_degrees: float
    yaw_step_degrees: float


class Manifest(TypedDict):
    """The whole document, as ``build_manifest`` returns it."""

    schema_version: int
    kind: str
    package_id: str
    title: str
    presentation_profile: str
    ground_contact: str
    look: LookBlock
    run: RunBlock
    status: StatusBlock
    style: StyleBlock
    scale: ScaleBlock
    #: world.toml as the consumer needs it: the seed, the extent, the set pieces.
    world: WorldBlock
    camera: CameraBlock
    ground: GroundBlock
    actors: dict[str, ActorBlock]
    props: dict[str, PropBlock]
    items: dict[str, ItemBlock]
    icons: IconsBlock | None
    #: The screen-fixed interface sheets, the shared ``ui.<role>`` blocks every
    #: consumer of the game_ui component reads; None for a package with no ui.toml.
    ui: JsonRecord | None
    crafting: CraftingBlock
    fx: FxBlock
    #: Keyed by cue, plus ``transition``; the cue vocabulary is closed, so the
    #: two cannot collide.
    music: dict[str, MusicTrackBlock | MusicTransitionBlock]
    weather: dict[str, WeatherConditionBlock]
    sounds: dict[str, SoundBlock]
    seasons: SeasonsBlock
    layout: JsonRecord | None
    gameplay: GameplayBlock
    reviews: dict[str, str | None]
    publication_authorized: bool


def _present(path: Path) -> bool:
    """True when a run artifact really is one.

    A dry run writes a placeholder at every declared port, so a file being
    there is not evidence that art is: without this the rehearsal's stubs would
    be published as finished work and a consumer would load them. A missing
    family is a status, not a crash, and a stub is a missing family.
    """

    return path.is_file() and not is_placeholder(path)


# --- artifact refs -------------------------------------------------------------------


def ground_ref(biome_id: str) -> str:
    return f"package/ground/{biome_id}.png"


def decal_ref(decal_id: str) -> str:
    return f"package/ground/decals/{decal_id}.png"


def macro_ref() -> str:
    return "package/ground/macro.png"


def road_ref(road_id: str) -> str:
    return f"package/ground/road-{road_id}.png"


def clutter_ref() -> str:
    return "package/ground/clutter.png"


def forage_ref() -> str:
    return "package/ground/forage.png"


def plants_ref() -> str:
    return "package/ground/plants.png"


def plants_look_ref(look: str) -> str:
    """The plant sheet in a season's look, beside the summer sheet."""

    return f"package/ground/plants.{look}.png"


def icons_ref() -> str:
    return "package/items/icons.png"


def water_ref() -> str:
    return "package/ground/water.png"


def splat_ref() -> str:
    return "package/world/splat.png"


def biome_splat_ref() -> str:
    return "package/world/biomes.png"


#: The biome-weight plate's channels, in biome declaration order after the base.
BIOME_CHANNELS: Final = ("r", "g", "b")


def layout_ref() -> str:
    return "package/world/layout.json"


def concept_ref(actor_id: str) -> str:
    return f"package/actors/{actor_id}/concept.png"


def state_ref(actor_id: str, state: str, facing: str | None = None) -> str:
    """One strip. A four-way actor's strips carry their facing: ``walk.left.png``."""

    if facing is None:
        return f"package/actors/{actor_id}/states/{state}.png"
    return f"package/actors/{actor_id}/states/{state}.{facing}.png"


def rebase_ref(actor_id: str) -> str:
    return f"package/actors/{actor_id}/rebase.json"


def prop_ref(prop_id: str, state: str) -> str:
    return f"package/props/{prop_id}/{state}.png"


def prop_look_ref(prop_id: str, state: str, look: str) -> str:
    """A season look of one prop state: the summer sprite repainted."""

    return f"package/props/{prop_id}/{state}.{look}.png"


def anchor_ref(prop_id: str) -> str:
    return f"package/props/{prop_id}/anchor.json"


def item_ref(item_id: str) -> str:
    return f"package/items/{item_id}.png"


def fire_ref() -> str:
    return "package/fx/fire.png"


def dust_ref() -> str:
    return "package/fx/dust.png"


def music_ref(track_id: str) -> str:
    return f"package/music/{track_id}.mp3"


def sound_ref(cue: str) -> str:
    return f"package/sounds/{cue}.mp3"


def weather_ref(condition_id: str, layer: str, extension: str = "png") -> str:
    """One file per layer under the condition: package/weather/rain/drops.png."""

    return f"package/weather/{condition_id}/{layer}.{extension}"


def review_ref(family: str) -> str:
    return f"production/review/{family}.json"


# --- measurement ---------------------------------------------------------------------


def alpha_bbox(data: bytes) -> tuple[int, int, int, int] | None:
    """Painted bounds as (left, top, right, bottom), right/bottom exclusive."""

    with Image.open(BytesIO(data)) as opened:
        image = opened.convert("RGBA")
        alpha = image.getchannel("A")
    mask = alpha.point(lambda value: 255 if value > ALPHA_THRESHOLD else 0)
    return mask.getbbox()


#: The ground line is looked for in this share of the subject's height, from
#: the bottom, and is the lowest row still at least this share of the widest
#: row in that band.
GROUND_LINE_BAND_SHARE: Final = 0.20
#: A quarter, not a half: half lifted a boulder off the ground, because a
#: convex base narrows toward its bottom and its widest band row is the band's
#: top. A quarter removes root tips and frond slivers and keeps a real base.
GROUND_LINE_WIDTH_SHARE: Final = 0.25


def ground_line_y(data: bytes) -> tuple[int, int] | None:
    """The row where the subject stands, not the lowest pixel it has.

    A flared trunk, a drooping frond, a root tip: the lowest opaque row of a
    prop is very often a sliver hanging below the line the object actually
    rests on. The skirt decals made this visible, because a ring drawn at the
    anchor showed every trunk standing a third of a metre behind its own
    roots. The ground line is the lowest row in the bottom band that is still
    at least a quarter as wide as the band's widest row: the sliver is gone,
    the base is kept, and the front edge of a pitched base stays the foot.
    Returns ``(ground_line_row, lowest_alpha_row)`` in canvas pixels.
    """

    with Image.open(BytesIO(data)) as opened:
        alpha = opened.convert("RGBA").getchannel("A")
    box = alpha.point(lambda value: 255 if value > ALPHA_THRESHOLD else 0).getbbox()
    if box is None:
        return None
    left, top, right, bottom = box
    band_top = max(top, bottom - max(2, round((bottom - top) * GROUND_LINE_BAND_SHARE)))
    pixels = cast(_BandAccess, alpha.load())
    widths: dict[int, int] = {}
    for row in range(band_top, bottom):
        columns = [x for x in range(left, right) if pixels[x, row] > ALPHA_THRESHOLD]
        widths[row] = (max(columns) - min(columns) + 1) if columns else 0
    widest = max(widths.values()) if widths else 0
    ground = bottom - 1
    for row in range(bottom - 1, band_top - 1, -1):
        if widths.get(row, 0) >= widest * GROUND_LINE_WIDTH_SHARE:
            ground = row
            break
    return ground + 1, bottom


def measure_sprite(data: bytes) -> SpriteFacts:
    """Canvas size, painted bounds, and where the subject meets the ground."""

    with Image.open(BytesIO(data)) as opened:
        width, height = opened.size
    box = alpha_bbox(data)
    if box is None:
        return {
            "width_px": width,
            "height_px": height,
            "painted": False,
            "bbox": None,
            "bbox_height_px": 0,
            "ground_contact_y_normalized": 1.0,
            "alpha_bottom_y_normalized": 1.0,
        }
    left, top, right, bottom = box
    line = ground_line_y(data)
    ground = line[0] if line else bottom
    return {
        "width_px": width,
        "height_px": height,
        "painted": True,
        "bbox": [left, top, right, bottom],
        "bbox_width_px": right - left,
        "bbox_height_px": bottom - top,
        "center_x_normalized": round((left + right) / 2.0 / width, 5),
        # The card's foot. The ground line, not the lowest pixel; see above.
        "ground_contact_y_normalized": round(ground / height, 5),
        "alpha_bottom_y_normalized": round(bottom / height, 5),
    }


def _read_json(path: Path) -> JsonRecord | None:
    if not _present(path):
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


# --- assembly ------------------------------------------------------------------------


def _actor_block(package: Package, run_dir: Path, actor: Actor) -> ActorBlock | None:
    height_meters = package.meters(actor.height_units)
    concept_path = run_dir / concept_ref(actor.actor_id)
    rebase = _read_json(run_dir / rebase_ref(actor.actor_id)) or {}
    multipliers: dict[str, float] = {}
    for entry in rebase.get("states", []) if isinstance(rebase.get("states"), list) else []:
        if isinstance(entry, dict) and isinstance(entry.get("state"), str):
            value = entry.get("multiplier")
            if isinstance(value, int | float) and not isinstance(value, bool) and value > 0:
                multipliers[entry["state"]] = float(value)

    four_way = actor.facings.four_way
    baseline_facing = "front" if four_way else None
    baseline_path = run_dir / state_ref(actor.actor_id, actor.baseline_state, baseline_facing)
    baseline_px_per_meter: float | None = None
    if _present(baseline_path):
        facts = measure_sprite(baseline_path.read_bytes())
        columns = 4
        cell_height = facts["height_px"]
        if facts["painted"] and cell_height:
            # A strip's painted bbox spans every frame, so the tallest frame is
            # what the height means; that is the frame the figure stands full in.
            baseline_px_per_meter = _strip_subject_height(
                baseline_path.read_bytes(), columns
            ) / max(height_meters, 1e-6)

    def strip_spec(motion: MotionState, facing: str | None) -> StripSpec | None:
        path = run_dir / state_ref(actor.actor_id, motion.state, facing)
        if not _present(path):
            return None
        data = path.read_bytes()
        facts = measure_sprite(data)
        columns = 4
        multiplier = multipliers.get(strip_key(motion.state, facing), 1.0)
        px_per_meter = (
            baseline_px_per_meter / multiplier
            if baseline_px_per_meter
            else _strip_subject_height(data, columns) / max(height_meters, 1e-6)
        )
        return {
            "atlas": state_ref(actor.actor_id, motion.state, facing),
            "columns": columns,
            "rows": 1,
            "frames": columns,
            "cell_width": facts["width_px"] // columns,
            "cell_height": facts["height_px"],
            "bottom_gutter_px": MOTION_BOTTOM_GUTTER_PX,
            "px_per_meter": round(px_per_meter, 4),
            "mode": motion.mode,
            "canonical_frame_indices": list(range(columns)),
            "fps": motion.fps,
            "rebase_multiplier": round(multiplier, 4),
        }

    states: dict[str, StripSpec] = {}
    for motion in actor.states:
        if not four_way:
            spec = strip_spec(motion, None)
            if spec is not None:
                states[motion.state] = spec
            continue
        # A four-way state is one spec per facing. The front's fields are
        # repeated at the top level so a consumer that knows one strip per
        # state (the gallery, a duration) still reads the state; a consumer
        # that turns the actor reads ``facings``.
        facings = {
            facing: spec
            for facing in actor.facings.facings
            if (spec := strip_spec(motion, facing)) is not None
        }
        if not facings:
            continue
        head = cast("StripSpec", dict(facings.get("front") or next(iter(facings.values()))))
        head["facings"] = facings
        states[motion.state] = head

    still: ActorStill | None = None
    if _present(concept_path):
        data = concept_path.read_bytes()
        facts = measure_sprite(data)
        if facts["painted"]:
            still = {
                "image": concept_ref(actor.actor_id),
                "width_px": facts["width_px"],
                "height_px": facts["height_px"],
                "px_per_meter": round(facts["bbox_height_px"] / max(height_meters, 1e-6), 4),
                "ground_contact_y_normalized": facts["ground_contact_y_normalized"],
            }
    if still is None and not states:
        return None
    return {
        "role": actor.role,
        "display_name": actor.display_name,
        "height_meters": round(height_meters, 4),
        # The facing set is the taxonomy; the runtime resolves a heading
        # against the camera's yaw into one of these names.
        "facings": {
            "set": actor.facings.set,
            "side_view": actor.facings.side_view if four_way else None,
            "names": list(actor.facings.facings) if four_way else [package.facing_authored],
        },
        "facing_authored": None if four_way else package.facing_authored,
        "mirror_for_left": not four_way,
        "baseline_state": actor.baseline_state,
        "footprint_radius_meters": round(package.meters(actor.footprint_radius_units), 4),
        "shadow_width_meters": round(package.meters(actor.shadow_width_units), 4),
        # An actor moves, so it can carry no asset-based seam: no skirt is laid
        # under it, no patch is painted into it, and its strips are drawn under
        # the floor ban. Its seam is the shadow, at full strength, whatever
        # the package chose for the props (``ground_contact`` at the top).
        "ground_contact": ACTOR_GROUND_CONTACT,
        "still": still,
        "states": states,
        "rebase": rebase_ref(actor.actor_id) if rebase else None,
    }


def _strip_subject_height(data: bytes, columns: int) -> float:
    """Tallest per-cell painted height in a single-row strip.

    A whole-strip bbox measures the union of four poses, which is taller than any
    one of them whenever a pose leans or reaches. The figure's height is the
    tallest single frame.
    """

    with Image.open(BytesIO(data)) as opened:
        image = opened.convert("RGBA")
    width, height = image.size
    cell = width // max(columns, 1)
    tallest = 0
    for index in range(columns):
        crop = image.crop((index * cell, 0, (index + 1) * cell, height))
        mask = crop.getchannel("A").point(lambda value: 255 if value > ALPHA_THRESHOLD else 0)
        box = mask.getbbox()
        if box is not None:
            tallest = max(tallest, box[3] - box[1])
    return float(tallest)


def _prop_block(package: Package, run_dir: Path, prop: Prop) -> PropBlock | None:
    baseline_state = prop.baseline_state
    baseline_path = run_dir / prop_ref(prop.prop_id, baseline_state)
    if not _present(baseline_path):
        return None
    baseline = measure_sprite(baseline_path.read_bytes())
    if not baseline["painted"]:
        return None
    height_meters = package.meters(prop.height_units)
    px_per_meter = baseline["bbox_height_px"] / max(height_meters, 1e-6)

    anchor_record = _read_json(run_dir / anchor_ref(prop.prop_id)) or {}
    per_state_anchor = anchor_record.get("per_state_anchor")
    motion_hint = anchor_record.get("motion_hint") or prop.motion_hint
    footprint_units = anchor_record.get("footprint_radius_units")
    footprint_meters = (
        package.meters(float(footprint_units))
        if isinstance(footprint_units, int | float) and not isinstance(footprint_units, bool)
        else package.meters(prop.footprint_radius_units)
    )

    states: dict[str, PropState] = {}
    for state in prop.states:
        authored_units = prop.authored_height_units(state)
        path = run_dir / prop_ref(prop.prop_id, state)
        if not _present(path):
            continue
        facts = measure_sprite(path.read_bytes())
        if not facts["painted"]:
            continue
        anchor: list[float] | None = None
        if isinstance(per_state_anchor, dict):
            entry = per_state_anchor.get(state)
            if isinstance(entry, dict) and {"x", "y"} <= set(entry):
                anchor = [float(entry["x"]), float(entry["y"])]
        if anchor is None:
            default = anchor_record.get("anchor")
            if isinstance(default, dict) and {"x", "y"} <= set(default):
                anchor = [float(default["x"]), float(default["y"])]
        validation = (
            _read_json(run_dir / f"production/validation/props/{prop.prop_id}-{state}.json") or {}
        )
        # The canonical size: this look's own ruler when the author sized it,
        # the baseline's when not. The drawing's own opinion rides alongside.
        drawn_height_meters = facts["bbox_height_px"] / px_per_meter
        if authored_units is not None:
            look_meters = package.meters(authored_units)
            look_px_per_meter = facts["bbox_height_px"] / max(look_meters, 1e-6)
            source = "authored"
        else:
            look_meters = drawn_height_meters
            look_px_per_meter = px_per_meter
            source = "baseline_ruler"
        # The season looks: the same drawing with the season added, sized
        # with THIS state's ruler (a cap adds real height) and standing on the
        # same anchor; its own contact row, since that is what the drift gate
        # held within a hair of the summer's.
        looks: dict[str, PropLook] = {}
        for look in package.seasons.looks if package.seasons is not None else ():
            look_path = run_dir / prop_look_ref(prop.prop_id, state, look.look_id)
            if not _present(look_path):
                continue
            look_facts = measure_sprite(look_path.read_bytes())
            if not look_facts["painted"]:
                continue
            looks[look.look_id] = {
                "image": prop_look_ref(prop.prop_id, state, look.look_id),
                "width_px": look_facts["width_px"],
                "height_px": look_facts["height_px"],
                "px_per_meter": round(look_px_per_meter, 4),
                "ground_contact_y_normalized": look_facts["ground_contact_y_normalized"],
                "anchor": anchor,
            }
        states[state] = {
            "image": prop_ref(prop.prop_id, state),
            "width_px": facts["width_px"],
            "height_px": facts["height_px"],
            "px_per_meter": round(look_px_per_meter, 4),
            "height_meters": round(look_meters, 4),
            "height_units_source": source,
            "drawn_height_meters": round(drawn_height_meters, 4),
            "ground_contact_y_normalized": facts["ground_contact_y_normalized"],
            "anchor": anchor,
            "floor_plate_suspected": bool(validation.get("floor_plate_suspected", False)),
            "looks": looks,
        }
    if not states:
        return None

    interactions: list[PropInteraction] = [
        {
            "verb": interaction.verb,
            # The states this is on offer from; the consumer resolves the
            # first available one, in this order, for the prop's state.
            "from": list(interaction.from_states),
            "hits": interaction.hits,
            "next_state": interaction.next_state,
            "fx": interaction.fx,
            "regrow_seconds": interaction.regrow_seconds,
            "progress": list(interaction.progress),
            "yields": [
                {"item_id": produced.item_id, "count": produced.count}
                for produced in interaction.yields
            ],
            # Gameplay: where the yield goes when the last blow lands.
            "yield_to": interaction.yield_to,
            # Gameplay: the tool the verb wants, and what the bare hand may do.
            "tool": (
                {
                    "item_id": interaction.tool.item_id,
                    "hits": interaction.tool.hits,
                    "required": interaction.tool.required,
                }
                if interaction.tool is not None
                else None
            ),
        }
        for interaction in prop.interactions
    ]
    return {
        "family": prop.family,
        "height_meters": round(height_meters, 4),
        "footprint_radius_meters": round(footprint_meters, 4),
        "shadow_width_meters": round(package.meters(prop.shadow_width_units), 4),
        "edge": prop.edge,
        "motion_hint": motion_hint,
        # Authored, not the anchor loop's: what the card does under a blow.
        "hit_reaction": prop.hit_reaction,
        "baseline_state": baseline_state,
        # How the looks were drawn: a fact for the reader, never a switch for
        # the viewer, which reads per-look sprites either way.
        "drawn": (
            {"kind": "sheet", "columns": prop.sheet.columns, "rows": prop.sheet.rows}
            if prop.sheet is not None
            else {"kind": "sprites"}
        ),
        "variants": (
            {"states": list(prop.variants.states), "weights": list(prop.variants.weights)}
            if prop.variants is not None
            else None
        ),
        "states": states,
        "interactions": interactions,
        "anchor_record": anchor_ref(prop.prop_id) if anchor_record else None,
    }


def _piece_sheet_block[CellT](
    sheet: LatticeSheet[CellT] | None,
    run_dir: Path,
    *,
    ref: str,
    validation: str,
    per_cell: Callable[[CellT], Mapping[str, Any]],
) -> PieceSheetBlock | None:
    """A lattice of ground pieces (the litter, the forage) as the viewer reads
    it: the atlas, its cell geometry from the gate's record, and per cell the
    authored facts ``per_cell`` picks off the declared cell."""

    if sheet is None or not _present(run_dir / ref):
        return None
    facts = _read_json(run_dir / validation) or {}
    with Image.open(BytesIO((run_dir / ref).read_bytes())) as opened:
        sheet_w, sheet_h = opened.size
    cell_w = sheet_w // sheet.columns
    cell_h = sheet_h // sheet.rows
    cells = facts.get("cells") or [
        {
            "index": index,
            "x": (index % sheet.columns) * cell_w,
            "y": (index // sheet.columns) * cell_h,
            "w": cell_w,
            "h": cell_h,
        }
        for index in range(sheet.cell_count)
    ]
    out: list[CellRow] = []
    for cell in cells:
        declared = sheet.cells[int(cell["index"])]
        out.append(
            {
                **{key: cell[key] for key in ("index", "x", "y", "w", "h") if key in cell},
                **per_cell(declared),
            }
        )
    return {
        "atlas": ref,
        "columns": sheet.columns,
        "rows": sheet.rows,
        "cell_meters": sheet.cell_meters,
        "width_px": sheet_w,
        "height_px": sheet_h,
        "cells": out,
    }


def _ground_block(package: Package, run_dir: Path) -> GroundBlock:
    biomes: dict[str, BiomeBlock] = {}
    for index, biome in enumerate(package.biomes):
        path = run_dir / ground_ref(biome.biome_id)
        if not _present(path):
            continue
        with Image.open(BytesIO(path.read_bytes())) as opened:
            width, height = opened.size
        facts = _read_json(run_dir / f"production/validation/ground/{biome.biome_id}.json") or {}
        biomes[biome.biome_id] = {
            "texture": ground_ref(biome.biome_id),
            "texel_meters": biome.texel_meters * 2.0,
            "tiling": "mirror_repeat_2d",
            # "base" for the first biome; else this biome's channel in the
            # biome-weight plate. The base's weight is what the others leave.
            "weight_channel": "base" if index == 0 else BIOME_CHANNELS[index - 1],
            "share": biome.share if index > 0 else None,
            "tiled_px": width,
            "tiled_px_height": height,
            # Six bracketing runs showed the plate's value does not follow the
            # number in the prompt; ink density decides it. So the plate's
            # measured value travels with it and the consumer levels the ground
            # to the authored target, which is deterministic.
            "value_target": biome.value_target,
            "luma_mean": (facts.get("source") or {}).get("luma_mean"),
            # The surface's say in how a drop stops (sliding deceleration is
            # friction * g); the consumer samples the biome under the pickup.
            "friction": biome.friction,
        }
    decals: dict[str, DecalBlock] = {}
    for decal in package.decals:
        path = run_dir / decal_ref(decal.decal_id)
        if not _present(path):
            continue
        drawn = measure_sprite(path.read_bytes())
        decals[decal.decal_id] = {
            "image": decal_ref(decal.decal_id),
            "use": decal.use,
            "families": list(decal.families),
            "width_meters": decal.width_meters,
            "height_meters": decal.height_meters,
            "width_px": drawn["width_px"],
            "height_px": drawn["height_px"],
        }
    # The abstract layer, the track, and the litter. Each is absent, not
    # broken, when its file is not there; the viewer falls back per layer.
    macro: MacroBlock | None = None
    if package.macro is not None and _present(run_dir / macro_ref()):
        facts = _read_json(run_dir / "production/validation/ground/macro.json") or {}
        macro = {
            "texture": macro_ref(),
            "texel_meters": package.macro.texel_meters * 2.0,
            # Metres the field spans at playback (mixing): the reference's
            # blotches are 5 to 12 m, a few to a screen.
            "period_meters": package.macro.period_meters
            if package.macro.period_meters is not None
            else package.macro.texel_meters * 2.0,
            "tiling": "mirror_repeat_2d",
            "strength": package.macro.strength,
            # The shader divides by this so the plate changes hue and value
            # locally without shifting the ground's mean.
            "luma_mean": float((facts.get("source") or {}).get("luma_mean", 0.5)),
        }
    road: RoadBlock | None = None
    if package.road is not None and _present(run_dir / road_ref(package.road.road_id)):
        facts = (
            _read_json(run_dir / f"production/validation/ground/road-{package.road.road_id}.json")
            or {}
        )
        road = {
            "road_id": package.road.road_id,
            "texture": road_ref(package.road.road_id),
            "texel_meters": package.road.texel_meters * 2.0,
            "tiling": "mirror_repeat_2d",
            "width_meters": package.road.width_meters,
            "edge_meters": package.road.edge_meters,
            "splat_channel": "r",
            "value_target": package.road.value_target,
            "luma_mean": (facts.get("source") or {}).get("luma_mean"),
        }
    clutter = _piece_sheet_block(
        package.clutter,
        run_dir,
        ref=clutter_ref(),
        validation="production/validation/ground/clutter.json",
        per_cell=lambda cell: {"contact": cell.contact, "biomes": list(cell.biomes)},
    )
    forage = _piece_sheet_block(
        package.forage,
        run_dir,
        ref=forage_ref(),
        validation="production/validation/ground/forage.json",
        per_cell=lambda cell: {
            "contact": cell.contact,
            "biomes": list(cell.biomes),
            "item_id": cell.item_id,
            "count": cell.count,
            "regrow_seconds": cell.regrow_seconds,
        },
    )
    plants = _piece_sheet_block(
        package.plants,
        run_dir,
        ref=plants_ref(),
        validation="production/validation/ground/plants.json",
        per_cell=lambda cell: {"contact": cell.contact, "biomes": list(cell.biomes)},
    )
    if plants is not None:
        # A season look of the sheet: its own atlas and its own cell bounds
        # (a snow cap grows a plant's box), keyed by the look id. The viewer
        # swaps the atlas and the windows together when the look changes.
        looks: dict[str, PieceSheetLook] = {}
        for look in package.seasons.looks if package.seasons is not None else ():
            block = _piece_sheet_block(
                package.plants,
                run_dir,
                ref=plants_look_ref(look.look_id),
                validation=f"production/validation/ground/plants.{look.look_id}.json",
                per_cell=lambda cell: {},
            )
            if block is not None:
                looks[look.look_id] = {"atlas": block["atlas"], "cells": block["cells"]}
        plants["looks"] = looks
    water: WaterBlock | None = None
    if package.water is not None:
        facts = _read_json(run_dir / "production/validation/ground/water.json") or {}
        water = {
            "texture": water_ref() if _present(run_dir / water_ref()) else None,
            "texel_meters": package.water.texel_meters * 2.0,
            "tiling": "mirror_repeat_2d",
            "colour": list(package.water.colour),
            "value_target": package.water.value_target,
            # The slab: how far the water lies below the ground, and the
            # cliff face the viewer draws under the far coast. Mixing.
            "depth_meters": package.water.depth_meters,
            "cliff_colour": list(package.water.cliff_colour),
            "luma_mean": (facts.get("source") or {}).get("luma_mean"),
        }
    splat: SplatBlock | None = None
    splat_path = run_dir / splat_ref()
    if _present(splat_path):
        with Image.open(BytesIO(splat_path.read_bytes())) as opened:
            cells_px = opened.size[0]
        channels: dict[str, str | None] = {"r": None, "g": "darken", "b": None, "a": "land"}
        if package.road is not None:
            channels["r"] = package.road.road_id
        splat = {
            "image": splat_ref(),
            "resolution": cells_px,
            "cell_meters": round(package.world.size_meters / cells_px, 4),
            "channels": channels,
            "blend": {
                # Defaults; ground.toml [blend] overrides any of them, and
                # none of them is identity (BLEND_KEYS in source.py).
                "edge_softness": 0.12,
                "edge_noise_strength": 0.35,
                "edge_shadow": 0.0,
                "edge_shadow_width": 0.4,
                "edge_ink": 0.0,
                "edge_ink_width": 0.12,
                "bomb_meters": 0.0,
                "bomb_rotate": 1.0,
                "macro_tint_strength": 0.15,
                # The road edge is eroded by a finer grain than the biome edge:
                # a torn edge at track scale, not at biome scale.
                "road_edge_softness": 0.10,
                "road_noise_tile_meters": 3.0,
                "road_noise_strength": 0.45,
                # The coast: a torn edge like the road's, a dark ink rim inside
                # it, and a shadow band on the water outside it.
                "shore_noise_tile_meters": 4.0,
                "shore_noise_strength": 0.5,
                "shore_rim": 0.14,
                "shore_shadow_meters": 1.6,
                "edge_fine_meters": 0.7,
                "edge_fine_strength": 0.0,
                "edge_rim": 0.0,
                "pool_gain": 0.0,
                "pool_radius_meters": 9.0,
                "vignette": 0.0,
                "grade_lift": 0.0,
                "grade_warmth": 0.0,
                "grade_desaturate": 0.0,
                "wave_ink": 0.0,
                "wave_meters": 1.6,
                "shadow_scale": 1.0,
                "shadow_strength": 1.0,
                "decal_gain": 1.0,
                "flow_meters": 200.0,
                "edge_streak": 0.0,
                "smudge_meters": 0.3,
                "smudge": 0.0,
                "edge_bleed": 0.0,
                "edge_bleed_width": 1.0,
                "paper": 0.0,
                "paper_px": 3.0,
                "stroke": 0.0,
                "stroke_meters": 5.0,
                "stroke_cover": 1.0,
                **package.blend,
                # Per-biome display value the leveller uses instead of the
                # plate's value_target; absent biomes keep their target.
                "level": dict(package.level),
            },
        }
    biome_splat: BiomeSplatBlock | None = None
    biome_splat_path = run_dir / biome_splat_ref()
    if _present(biome_splat_path):
        with Image.open(BytesIO(biome_splat_path.read_bytes())) as opened:
            cells_px = opened.size[0]
        biome_splat = {
            "image": biome_splat_ref(),
            "resolution": cells_px,
            "cell_meters": round(package.world.size_meters / cells_px, 4),
            "channels": {
                channel: (
                    package.biomes[index + 1].biome_id if index + 1 < len(package.biomes) else None
                )
                for index, channel in enumerate(BIOME_CHANNELS)
            },
        }
    return {
        "size_meters": float(package.world.size_meters),
        "base_biome": package.biomes[0].biome_id,
        "biomes": biomes,
        "biome_splat": biome_splat,
        "macro": macro,
        "road": road,
        "clutter": clutter,
        "forage": forage,
        "plants": plants,
        "water": water,
        "splat": splat,
        "decals": decals,
    }


def _fx_block(package: Package, run_dir: Path) -> FxBlock:
    block: FxBlock = {"fire": None, "dust": None}
    fire_path = run_dir / fire_ref()
    if _present(fire_path):
        with Image.open(BytesIO(fire_path.read_bytes())) as opened:
            width, height = opened.size
        record = _read_json(run_dir / "production/validation/fx-fire.json") or {}
        cell_px = width // package.fire.columns
        height_meters = package.meters(package.fire.height_units)
        block["fire"] = {
            "strip": fire_ref(),
            "columns": package.fire.columns,
            "rows": package.fire.rows,
            "frames": package.fire.frames,
            "cell_px": cell_px,
            "px_per_meter": round(cell_px / max(height_meters, 1e-6), 4),
            "height_meters": round(height_meters, 4),
            "fps": package.fire.fps,
            "mode": str(record.get("mode", "loop")),
            "blend": "additive",
            "base_origin": [0.5, 0.95],
        }
    dust_path = run_dir / dust_ref()
    if _present(dust_path):
        with Image.open(BytesIO(dust_path.read_bytes())) as opened:
            width, height = opened.size
        record = _read_json(run_dir / "production/validation/fx-dust.json") or {}
        cells = record.get("cells")
        if not isinstance(cells, list) or not cells:
            half_w, half_h = width // 2, height // 2
            cells = [
                {
                    "kind": kind,
                    "x": (index % 2) * half_w,
                    "y": (index // 2) * half_h,
                    "w": half_w,
                    "h": half_h,
                }
                for index, kind in enumerate(package.dust.kinds)
            ]
        height_meters = package.meters(package.dust.height_units)
        block["dust"] = {
            "atlas": dust_ref(),
            "width_px": width,
            "height_px": height,
            "px_per_meter": round(
                max(int(cell.get("h", 1)) for cell in cells) / max(height_meters, 1e-6), 4
            ),
            "cells": cells,
        }
    return block


def _weather_block(package: Package, run_dir: Path) -> dict[str, WeatherConditionBlock]:
    """One entry per condition, its clock and wash always, each layer only when
    its file is there. A consumer drives ``weather.rain`` on [0, 1] and reads
    whatever layers arrived; a missing layer is absent, not broken."""

    block: dict[str, WeatherConditionBlock] = {}
    for condition in package.weather:
        cid = condition.condition_id
        entry: WeatherConditionBlock = {
            "onset_seconds": condition.onset_seconds,
            "decay_seconds": condition.decay_seconds,
            "dry_spell_seconds": list(condition.dry_spell_seconds),
            "wet_spell_seconds": list(condition.wet_spell_seconds),
            "tint": list(condition.tint),
            "desaturate": condition.desaturate,
            "drops": None,
            "ground": None,
            "wet": None,
            "strike": None,
            "cover": None,
            "ice": None,
            "sound": {},
        }
        validation = run_dir / "production/validation"
        cover = condition.cover
        if cover is not None and _present(run_dir / weather_ref(cid, "cover")):
            record = _read_json(validation / f"weather-{cid}-cover.json") or {}
            entry["cover"] = {
                "texture": weather_ref(cid, "cover"),
                "texel_meters": cover.texel_meters * 2.0,
                "tiling": "mirror_repeat_2d",
                "value_target": cover.value_target,
                "luma_mean": (record.get("source") or {}).get("luma_mean"),
            }
        ice = condition.ice
        if ice is not None and _present(run_dir / weather_ref(cid, "ice")):
            record = _read_json(validation / f"weather-{cid}-ice.json") or {}
            entry["ice"] = {
                "texture": weather_ref(cid, "ice"),
                "texel_meters": ice.texel_meters * 2.0,
                "tiling": "mirror_repeat_2d",
                "value_target": ice.value_target,
                "luma_mean": (record.get("source") or {}).get("luma_mean"),
            }
        drops = condition.drops
        if drops is not None and _present(run_dir / weather_ref(cid, "drops")):
            with Image.open(BytesIO((run_dir / weather_ref(cid, "drops")).read_bytes())) as opened:
                width, height = opened.size
            record = _read_json(validation / f"weather-{cid}-drops.json") or {}
            cells = record.get("cells") or [
                {"kind": kind, "x": i * (width // 2), "y": 0, "w": width // 2, "h": height}
                for i, kind in enumerate(drops.kinds)
            ]
            entry["drops"] = {
                "atlas": weather_ref(cid, "drops"),
                "width_px": width,
                "height_px": height,
                "cells": [{k: c[k] for k in ("kind", "x", "y", "w", "h")} for c in cells],
                "count_per_screen": drops.count_per_screen,
                "layers": drops.layers,
                "fall_speed_meters_per_second": drops.fall_speed_meters_per_second,
                "height_meters": round(package.meters(drops.height_units), 4),
            }
        ground = condition.ground
        if ground is not None and _present(run_dir / weather_ref(cid, "ground")):
            with Image.open(BytesIO((run_dir / weather_ref(cid, "ground")).read_bytes())) as opened:
                width, height = opened.size
            record = _read_json(validation / f"weather-{cid}-ground.json") or {}
            cells = record.get("cells") or [
                {
                    "kind": kind,
                    "x": (i % 2) * (width // 2),
                    "y": (i // 2) * (height // 2),
                    "w": width // 2,
                    "h": height // 2,
                }
                for i, kind in enumerate(ground.kinds)
            ]
            height_meters = package.meters(ground.height_units)
            entry["ground"] = {
                "atlas": weather_ref(cid, "ground"),
                "width_px": width,
                "height_px": height,
                "px_per_meter": round(
                    max(int(c.get("h", 1)) for c in cells) / max(height_meters, 1e-6), 4
                ),
                "height_meters": round(height_meters, 4),
                "rate_per_100_sqm_per_second": ground.rate_per_100_sqm_per_second,
                "cells": [{k: c[k] for k in ("kind", "x", "y", "w", "h")} for c in cells],
            }
        wet = condition.wet
        if wet is not None and _present(run_dir / decal_ref(wet.decal_id)):
            entry["wet"] = {"decal_id": wet.decal_id, "dry_seconds": wet.dry_seconds}
        strike = condition.strike
        if strike is not None and _present(run_dir / weather_ref(cid, "strike")):
            with Image.open(BytesIO((run_dir / weather_ref(cid, "strike")).read_bytes())) as opened:
                width, height = opened.size
            record = _read_json(validation / f"weather-{cid}-strike.json") or {}
            cells = record.get("cells") or [
                {
                    "kind": f"bolt_{i}",
                    "x": (i % 2) * (width // 2),
                    "y": (i // 2) * (height // 2),
                    "w": width // 2,
                    "h": height // 2,
                }
                for i in range(4)
            ]
            height_meters = package.meters(strike.height_units)
            entry["strike"] = {
                "atlas": weather_ref(cid, "strike"),
                "width_px": width,
                "height_px": height,
                "height_meters": round(height_meters, 4),
                "above": strike.above,
                "interval_seconds": list(strike.interval_seconds),
                "flash_seconds": strike.flash_seconds,
                "cells": [{k: c[k] for k in ("kind", "x", "y", "w", "h")} for c in cells],
            }
        for name, cue in condition.sound_cues:
            path = run_dir / weather_ref(cid, f"sound-{name}", "mp3")
            if not _present(path):
                continue
            record = _read_json(validation / f"weather-{cid}-sound-{name}.json") or {}
            entry["sound"][name] = {
                "audio": weather_ref(cid, f"sound-{name}", "mp3"),
                "loop": cue.loop,
                "duration_seconds": record.get("duration_seconds", cue.duration_seconds),
                "peak_dbfs": record.get("peak_dbfs"),
            }
        block[cid] = entry
    return block


def _weather_status(package: Package, block: Mapping[str, WeatherConditionBlock]) -> str:
    """none when no weather is authored; else ok only when every authored layer arrived."""

    if not package.weather:
        return "none"
    expected = 0
    present = 0
    for condition in package.weather:
        # Read as an open mapping: the layer names are a loop, not literals.
        entry: Mapping[str, Any] = block.get(condition.condition_id) or {}
        for layer in ("drops", "ground", "wet", "strike", "cover", "ice"):
            if getattr(condition, layer) is not None:
                expected += 1
                present += 1 if entry.get(layer) else 0
        for name, _cue in condition.sound_cues:
            expected += 1
            present += 1 if (entry.get("sound") or {}).get(name) else 0
    if present == 0:
        return "missing"
    return "ok" if present >= expected else "partial"


def _music_block(
    package: Package, run_dir: Path
) -> dict[str, MusicTrackBlock | MusicTransitionBlock]:
    """One entry per admitted track, keyed by cue, so a consumer asks for
    ``music.day`` and never has to know a track id, plus the ``transition``
    that says how a consumer moves between them. ``transition`` is not a cue
    and the cue vocabulary is closed, so the two cannot collide."""

    block: dict[str, MusicTrackBlock | MusicTransitionBlock] = {}
    for track in package.music:
        path = run_dir / music_ref(track.track_id)
        if not _present(path):
            continue
        record = _read_json(run_dir / f"production/validation/music-{track.track_id}.json") or {}
        block[track.cue] = {
            "track_id": track.track_id,
            "audio": music_ref(track.track_id),
            "take": track.take,
            "loop": True,
            "target_duration_seconds": track.target_duration_seconds,
            "duration_seconds": record.get("duration_seconds"),
            "peak_dbfs": record.get("peak_dbfs"),
        }
    if block:
        transition = package.music_transition
        block["transition"] = {
            "crossfade_seconds": transition.crossfade_seconds,
            "curve": transition.curve,
            "overlap": transition.overlap,
            "switch_at": transition.switch_at,
        }
    return block


def _sounds_block(package: Package, run_dir: Path) -> dict[str, SoundBlock]:
    """One entry per admitted clip, keyed by cue, with the mixing a consumer
    applies at playback (``gain``, ``pitch_jitter``) beside the measured facts.
    A cue whose file is absent is absent, not broken."""

    block: dict[str, SoundBlock] = {}
    for clip in package.sounds:
        path = run_dir / sound_ref(clip.cue)
        if not _present(path):
            continue
        record = _read_json(run_dir / f"production/validation/sound-{clip.cue}.json") or {}
        block[clip.cue] = {
            "audio": sound_ref(clip.cue),
            "take": clip.take,
            "loop": clip.loop,
            "duration_seconds": record.get("duration_seconds", clip.duration_seconds),
            "peak_dbfs": record.get("peak_dbfs"),
            "gain": clip.gain,
            "pitch_jitter": clip.pitch_jitter,
            "onsets": clip.onsets,
        }
    return block


def _icons_block(package: Package, run_dir: Path) -> IconsBlock | None:
    """The inventory icon sheet: the atlas and one window per item or glyph."""

    path = run_dir / icons_ref()
    if not _present(path):
        return None
    facts = _read_json(run_dir / "production/validation/items/icons.json") or {}
    with Image.open(BytesIO(path.read_bytes())) as opened:
        sheet_w, sheet_h = opened.size
    icons = package.icons
    cell_w = sheet_w // icons.columns
    cell_h = sheet_h // icons.rows
    names = [item.item_id for item in package.items] + [glyph.glyph for glyph in icons.glyphs]
    cells = facts.get("cells") or [
        {
            "index": index,
            "x": (index % icons.columns) * cell_w,
            "y": (index // icons.columns) * cell_h,
            "w": cell_w,
            "h": cell_h,
        }
        for index in range(icons.cell_count)
    ]
    out = []
    for cell in cells:
        index = int(cell["index"])
        if index >= len(names):
            continue
        is_item = index < len(package.items)
        out.append(
            {
                **{key: cell[key] for key in ("index", "x", "y", "w", "h") if key in cell},
                ("item_id" if is_item else "glyph"): names[index],
            }
        )
    return {
        "atlas": icons_ref(),
        "columns": icons.columns,
        "rows": icons.rows,
        "cell_px": icons.cell_px,
        "width_px": sheet_w,
        "height_px": sheet_h,
        "cells": out,
    }


def _ui_block(package: Package, run_dir: Path) -> JsonRecord | None:
    """The interface sheets, published exactly as every other consumer sees them.

    The validate node is the only place the detected geometry exists, so the
    block is read from its record rather than from the declared template; the
    component projects it, and this recipe adds nothing of its own. None when
    the package authors no ui.toml, and None when a scope drew no sheets, which
    the status tells apart.
    """

    if package.ui is None:
        return None
    roles = document_roles(package.ui)
    for role in roles:
        if not _present(run_dir / f"ui/{role.role}.png"):
            return None
        if not _present(run_dir / f"ui/{role.role}.validation.json"):
            return None
    return ui_atlas_manifest_block(
        read_validation=lambda ref: (run_dir / ref).read_bytes(),
        publish=lambda ref: ref,
        publish_provenance=lambda _ref: None,
        roles=roles,
    )


def _items_block(package: Package, run_dir: Path, icons: IconsBlock | None) -> dict[str, ItemBlock]:
    windows: dict[str, dict[str, Any]] = {}
    for cell in icons["cells"] if icons is not None else ():
        if "item_id" in cell:
            windows[cell["item_id"]] = {key: cell[key] for key in ("x", "y", "w", "h")}
    items: dict[str, ItemBlock] = {}
    for item in package.items:
        path = run_dir / item_ref(item.item_id)
        if not _present(path):
            continue
        facts = measure_sprite(path.read_bytes())
        if not facts["painted"]:
            continue
        height_meters = package.meters(item.height_units)
        items[item.item_id] = {
            "image": item_ref(item.item_id),
            "width_px": facts["width_px"],
            "height_px": facts["height_px"],
            "px_per_meter": round(facts["bbox_height_px"] / max(height_meters, 1e-6), 4),
            "height_meters": round(height_meters, 4),
            # The inventory representation: a window on the icon sheet, or
            # nothing, in which case the consumer shows the pickup sprite.
            "icon": windows.get(item.item_id),
            # Gameplay, authored in items.toml and read by the consumer only.
            "display_name": item.display_name or item.item_id.replace("_", " "),
            "stack_max": item.stack_max,
            "use": (
                {
                    "kind": item.use.kind,
                    "hunger": item.use.hunger,
                    "health": item.use.health,
                    "radius_meters": item.use.radius_meters,
                    "burn_seconds": item.use.burn_seconds,
                    "slots": item.use.slots,
                    "warmth": item.use.warmth,
                    "insulation": item.use.insulation,
                    "heat_seconds": item.use.heat_seconds,
                }
                if item.use is not None
                else None
            ),
            "tool": (
                {"verb": item.tool.verb, "uses": item.tool.uses} if item.tool is not None else None
            ),
        }
    return items


def _crafting_block(package: Package) -> CraftingBlock:
    """crafting.toml as the consumer reads it. Mixing, never identity."""

    crafting = package.crafting
    return {
        "slots": crafting.slots,
        "start": dict(crafting.start),
        "stations": {
            station.station_id: {
                "prop_id": station.prop_id,
                "state": station.state,
                "reach_meters": station.reach_meters,
            }
            for station in crafting.stations
        },
        "recipes": [
            {
                "recipe_id": recipe.recipe_id,
                "ingredients": dict(recipe.ingredients),
                "station": recipe.station,
                "product": (
                    {"item_id": recipe.product_item[0], "count": recipe.product_item[1]}
                    if recipe.product_item is not None
                    else {"prop_id": recipe.product_prop, "state": recipe.product_state}
                ),
            }
            for recipe in crafting.recipes
        ],
    }


def _gameplay_block(package: Package) -> GameplayBlock:
    gameplay = package.gameplay
    return {
        "day_length_seconds": gameplay.get("day_length_seconds", 180.0),
        "player_speed_meters_per_second": gameplay.get("player_speed_meters_per_second", 3.0),
        "interact_reach_meters": gameplay.get("interact_reach_meters", 0.6),
        # Beyond the reach and inside this radius the key first walks the
        # player to the target, then acts. Never below the reach.
        "approach_meters": gameplay.get(
            "approach_meters", gameplay.get("interact_reach_meters", 1.2)
        ),
        # "manual" (stand within reach, press interact) or "magnet" (a settled
        # drop within a metre is drawn in). Authored in survival.toml.
        "pickup": gameplay.get("pickup", "manual"),
        "hunger": dict(gameplay.get("hunger", {})),
        "health": dict(gameplay.get("health", {})),
        "mob": dict(gameplay.get("mob", {})),
        "campfire": dict(gameplay.get("campfire", {})),
        "night": dict(gameplay.get("night", {})),
        # The cold and the small heats. Authored in survival.toml; the season
        # (seasons.toml) says how much of the cold is on.
        "warmth": dict(gameplay.get("warmth", {})),
        "torch": dict(gameplay.get("torch", {})),
    }


def _seasons_block(package: Package) -> SeasonsBlock:
    """The calendar and its seasons, for the consumer that turns them. None
    authored is an empty block: the world stays as drawn."""

    seasons = package.seasons
    if seasons is None:
        return SeasonsBlock()
    return {
        "calendar": {"order": list(seasons.order), "days_per_season": seasons.days_per_season},
        "seasons": [
            {
                "season_id": season.season_id,
                "display_name": season.display_name,
                "snow": season.snow,
                "cold": season.cold,
                "night_share": season.night_share,
                "regrow_scale": season.regrow_scale,
                "hidden_forage": list(season.hidden_forage),
                "barren": list(season.barren),
                "look": season.look,
            }
            for season in seasons.seasons
        ],
        "looks": [look.look_id for look in seasons.looks],
    }


def _seasons_status(package: Package, props: Mapping[str, PropBlock]) -> str:
    """none without a calendar; a calendar with no look is complete as it is;
    a look is ok only when every prop state has its repaint."""

    seasons = package.seasons
    if seasons is None:
        return "none"
    if not seasons.looks:
        return "ok"
    expected = len(seasons.looks) * sum(len(prop.states) for prop in package.props)
    present = sum(
        len(state["looks"]) for block in props.values() for state in block["states"].values()
    )
    if present == 0:
        return "missing"
    return "ok" if present >= expected else "partial"


def _status(block: Sized, expected: int) -> str:
    if not block:
        return "missing"
    return "ok" if len(block) >= expected else "partial"


def _world_block(package: Package) -> WorldBlock:
    world = package.world
    return {
        "seed": world.seed,
        "size_meters": float(world.size_meters),
        "spawn_set_piece": world.spawn_set_piece,
        "set_pieces": [
            {
                "set_piece_id": piece.set_piece_id,
                "count": piece.count,
                "at": piece.at,
                "band_meters": list(piece.band_meters),
                "biome": piece.biome,
                "clearing_radius_meters": piece.clearing_radius_meters,
                "members": [
                    {"prop": member.prop, "state": member.state, "dx": member.dx, "dz": member.dz}
                    for member in piece.members
                ],
            }
            for piece in world.set_pieces
        ],
    }


def build_manifest(
    package: Package,
    run_dir: Path,
    *,
    run_id: str,
    graph_sha256: str | None,
    scope: str,
) -> Manifest:
    """Read whatever the run produced and describe it. Never raises on absence."""

    actors: dict[str, ActorBlock] = {}
    for actor in package.actors:
        actor_block = _actor_block(package, run_dir, actor)
        if actor_block is not None:
            actors[actor.actor_id] = actor_block
    props: dict[str, PropBlock] = {}
    for prop in package.props:
        prop_block = _prop_block(package, run_dir, prop)
        if prop_block is not None:
            props[prop.prop_id] = prop_block
    ground = _ground_block(package, run_dir)
    fx = _fx_block(package, run_dir)
    icons = _icons_block(package, run_dir)
    items = _items_block(package, run_dir, icons)
    ui = _ui_block(package, run_dir)
    music = _music_block(package, run_dir)
    weather = _weather_block(package, run_dir)
    sounds = _sounds_block(package, run_dir)
    layout = _read_json(run_dir / layout_ref())

    reviews: dict[str, str | None] = {}
    for family in ("actors", "props", "ground", "fx", "seasons"):
        path = run_dir / review_ref(family)
        reviews[family] = review_ref(family) if _present(path) else None

    style: StyleBlock = {"label": package.style_label}
    # The plate's digest, not its path: a consumer only needs to know which
    # picture the art was drawn against, and two runs that differ here are not
    # comparable.
    if package.style_reference_digest:
        style["reference_sha256"] = package.style_reference_digest

    # The optional ground layers, read by name once so the status below counts
    # them without indexing the block with a variable key.
    water_block = ground["water"]
    ground_layers: dict[str, object] = {
        "macro": ground["macro"],
        "road": ground["road"],
        "clutter": ground["clutter"],
        "forage": ground["forage"],
        "plants": ground["plants"],
        "water": water_block if water_block is not None and water_block["texture"] else None,
    }

    fx_present = sum(1 for value in fx.values() if value)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": MANIFEST_KIND,
        "package_id": package.package_id,
        "title": package.title,
        "presentation_profile": package.profile,
        # The authored seam between billboard and ground; the viewer sets its
        # shadow strength from it and never chooses a seam of its own.
        "ground_contact": package.ground_contact,
        # The look contract, for the consumer that lays the art down: every
        # asset was drawn under this one light; a ground piece (litter, a
        # patch) keeps its lower edge toward the camera and rotation_degrees
        # is a jitter about that aim, not a heading; nothing is mirrored
        # except an actor's facing.
        "look": {
            "light": package.look.light,
            "mirror": "facing_only",
            "ground_pieces": {
                "orientation": "camera_facing",
                "jitter_degrees": package.look.ground_piece_jitter_degrees,
            },
        },
        "run": {
            "run_id": run_id,
            "graph_sha256": graph_sha256,
            "scope": scope,
            "source_digest": package.source_digest(),
        },
        "status": {
            "actors": _status(actors, len(package.actors)),
            "props": _status(props, len(package.props)),
            "ground": _status(ground["biomes"], len(package.biomes)),
            "ground_layers": _status(
                {name: value for name, value in ground_layers.items() if value},
                sum(
                    1
                    for k in (
                        package.macro,
                        package.road,
                        package.clutter,
                        package.forage,
                        package.plants,
                        package.water,
                    )
                    if k is not None
                ),
            ),
            "fx": "missing" if fx_present == 0 else ("ok" if fx_present == 2 else "partial"),
            "items": _status(items, len(package.items)),
            # No tracks authored is silence by design, not a missing family.
            # Counted over the cues only: the transition beside them is mixing.
            "music": (
                "none"
                if not package.music
                else _status(
                    {cue: entry for cue, entry in music.items() if cue in MUSIC_CUES},
                    len(package.music),
                )
            ),
            "weather": _weather_status(package, weather),
            # No clips authored is a silent player by design, not a missing family.
            "sounds": "none" if not package.sounds else _status(sounds, len(package.sounds)),
            "seasons": _seasons_status(package, props),
            # No ui.toml is a HUD of plain boxes by design, not a missing family.
            "ui": "none" if package.ui is None else ("ok" if ui is not None else "missing"),
            "layout": "ok" if layout else "missing",
        },
        "style": style,
        "scale": {"player_height_meters": package.player_height_meters},
        "world": _world_block(package),
        "camera": {
            "pitch_degrees": package.camera.get("pitch_degrees", 55.0),
            "fov_degrees": package.camera.get("fov_degrees", 35.0),
            "distance_meters": package.camera.get("distance_meters", 18.0),
            "asset_pitch_degrees": package.camera.get("asset_pitch_degrees", 30.0),
            "follow_lerp": package.camera.get("follow_lerp", 0.08),
            "rotation_allowed": bool(package.camera.get("rotation_allowed", False)),
            "yaw_degrees": package.camera.get("yaw_degrees", 45.0),
            "yaw_step_degrees": package.camera.get("yaw_step_degrees", 45.0),
        },
        "ground": ground,
        "actors": actors,
        "props": props,
        "items": items,
        "icons": icons,
        "ui": ui,
        "crafting": _crafting_block(package),
        "fx": fx,
        "music": music,
        "weather": weather,
        "sounds": sounds,
        "seasons": _seasons_block(package),
        "layout": layout,
        "gameplay": _gameplay_block(package),
        "reviews": reviews,
        "publication_authorized": False,
    }


def manifest_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")
