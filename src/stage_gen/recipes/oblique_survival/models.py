"""Authored oblique-survival package: the frozen contracts the graph reads.

Everything the graph and the manifest need about the authored intent is shaped
here and nowhere else, so a prompt change is a source change and lands in the
node's input digest. Magnitudes stay in player-height units all the way through
this module; the conversion to meters happens once, in ``manifest.py``.

Reading, validating and digesting the authored files is
``survival_request.py``'s job; this module holds only what a validated package
is. ``ObliqueSurvivalSource`` is the root document's pydantic contract, which is
where the authored identity ``oblique-survival-package-v2`` is declared, and
``WORLD_KIND`` is ``world.toml``'s.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict

from stage_gen.canonical import content_sha256

MOTION_MODES: Final = frozenset({"hold", "loop", "once", "gameplay_driven"})
MOTION_HINTS: Final = frozenset({"sway_top", "bob", "flicker", "none"})
#: What a blow does to the standing card. Authored per prop, never inferred
#: from its family or its idle motion: a boulder holds still under the pick.
HIT_REACTIONS: Final = frozenset({"shake", "none"})
EDGE_KINDS: Final = frozenset({"hard", "soft"})
#: The base biome plus the three channels of the biome-weight plate. A fifth
#: biome needs a second weight plate, not a fifth channel: the plate's alpha is
#: not usable as data, because browsers premultiply an image's colour by its
#: alpha on decode and the low-alpha texels come back wrong.
MAX_BIOMES: Final = 4
FRAME_COUNT: Final = 4
#: The verbs an interaction may use and a tool may serve. The consumer binds
#: each to a key; a verb outside this set has no key and is refused offline.
INTERACTION_VERBS: Final = ("chop", "gather", "mine", "light")
#: Where an interaction's yield goes when the last blow lands. ``hand``: straight
#: into the pack, the way a tuft of grass or a handful of twigs is simply taken;
#: ``ground``: dropped at the thing for the player to pick up after, the way a
#: felled trunk's logs lie where the crown lands. Authored per prop and required
#: whenever the interaction yields anything; a verb says nothing about it.
YIELD_DESTINATIONS: Final = ("hand", "ground")
#: What a press of the use key does with the selected item.
#: What the use key does with an item. ``wear`` and ``warm`` came with the
#: winter: a worn thing insulates while it is carried, a warm thing holds the
#: cold off for a while once lit at a fire.
ITEM_USES: Final = ("consume", "light", "carry", "wear", "warm")
#: world.toml's own identity: the world's extent, its landmass, its biome
#: rules, its set pieces and the population order.
WORLD_KIND: Final = "oblique-survival-world-v1"
#: What an object's ``edge`` preference may be measured from.
EDGE_FIELDS: Final = ("water", "biome", "road", "set_piece")


class SourceError(ValueError):
    """The authored package is not usable. Raised before any spend."""


@dataclass(frozen=True, slots=True)
class MotionState:
    state: str
    mode: Literal["hold", "loop", "once", "gameplay_driven"]
    fps: float
    direction: str


#: The facing sets. A facing is named from the CAMERA, never from the world:
#: ``front`` faces the viewer, ``back`` faces away, ``left`` and ``right`` face
#: the screen's left and right. The camera turns in 45-degree detents and the
#: runtime resolves an actor's world heading against the camera's yaw, so the
#: same four cards serve every detent.
#:
#:   four_way          front, back, left and right, all four drawn. The player
#:                     always carries this set: it is what a billboard actor in
#:                     this camera needs to be walked in every direction.
#:   single_mirrored   one authored right-turned three-quarter card, mirrored
#:                     for leftward motion and reused toward and away from the
#:                     camera. Enough for a mob, which needs less detail.
FACING_SETS: tuple[str, ...] = ("four_way", "single_mirrored")
FOUR_WAY_FACINGS: tuple[str, ...] = ("front", "back", "left", "right")
#: How the two side facings are drawn: a three-quarter view turned toward
#: that side ("quarter", the reference genre's choice, the face still reads) or
#: a full profile ("profile").
SIDE_VIEWS: tuple[str, ...] = ("quarter", "profile")


@dataclass(frozen=True, slots=True)
class FacingSet:
    set: str
    side_view: str

    @property
    def four_way(self) -> bool:
        return self.set == "four_way"

    @property
    def facings(self) -> tuple[str, ...]:
        """The drawn facings; empty for a single mirrored card."""

        return FOUR_WAY_FACINGS if self.four_way else ()


def strip_key(state: str, facing: str | None) -> str:
    """The name one strip goes by in records and the rebase: ``walk`` or ``walk.left``."""

    return state if facing is None else f"{state}.{facing}"


@dataclass(frozen=True, slots=True)
class Actor:
    actor_id: str
    role: Literal["player", "mob"]
    display_name: str
    height_units: float
    baseline_state: str
    footprint_radius_units: float
    shadow_width_units: float
    concept_prompt: str
    states: tuple[MotionState, ...]
    facings: FacingSet
    #: An authored picture of THIS actor, carried into the concept node as
    #: reference image 1 with the style plate demoted to image 2. The prose
    #: alone could never hold a character: it describes an outfit, and the
    #: model fills in the body. A package may have none, in which case the
    #: brief stands alone as it always did. Path is relative to the source
    #: root and its digest is bound into the concept node's identity, so
    #: swapping the picture re-bills the concept and everything off it.
    appearance_reference: str | None = None
    appearance_reference_digest: str | None = None
    #: Where and how the layout scatters this actor. The mob's; the player has none.
    placement: Placement | None = None

    def state(self, name: str) -> MotionState:
        for entry in self.states:
            if entry.state == name:
                return entry
        raise SourceError(f"actor {self.actor_id} has no state {name!r}")

    @property
    def strips(self) -> tuple[tuple[str, str | None], ...]:
        """Every (state, facing) strip this actor draws; facing is None for a single card."""

        facings: tuple[str | None, ...] = self.facings.facings or (None,)
        return tuple((entry.state, facing) for entry in self.states for facing in facings)

    @property
    def baseline_key(self) -> str:
        """The strip the rebase and the scale are measured against."""

        return strip_key(self.baseline_state, "front" if self.facings.four_way else None)

    @property
    def state_names(self) -> tuple[str, ...]:
        return tuple(entry.state for entry in self.states)


@dataclass(frozen=True, slots=True)
class Yield:
    item_id: str
    count: int


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """The tool an interaction wants: the item, the hits it takes with it, and
    whether the bare hand may do it at all (at the interaction's own hits)."""

    item_id: str
    hits: int
    required: bool


@dataclass(frozen=True, slots=True)
class Interaction:
    """One thing that can be done to a prop, from the states it applies to.

    A prop lists several (``[[props.interactions]]``); the consumer resolves
    the one on offer for the prop's current state — the first, in authored
    order, whose ``from`` holds the state and whose tool (if required) is
    carried; when none is available the first that applies is offered with
    its refusal, so the player learns what the thing needs.
    """

    verb: str
    #: The states this applies from. Explicit, never inferred from
    #: ``next_state``: a fire is lit from ``unlit``, a boulder mined from
    #: ``whole`` and every progress look, a bush gathered from ``full``.
    from_states: tuple[str, ...]
    hits: int
    next_state: str
    fx: str
    yields: tuple[Yield, ...]
    regrow_seconds: float | None
    #: ``hand`` or ``ground`` (``YIELD_DESTINATIONS``); ``ground`` when there is
    #: nothing to yield. Gameplay, not identity: no node digests it.
    yield_to: str
    #: The look after hit 1, hit 2, ... before ``next_state``, clamped to the
    #: last entry. An author's binding: what these looks mean (a rock's mining
    #: progress, a tree losing its leaves) is said in the briefs, never here.
    progress: tuple[str, ...] = ()
    #: Gameplay, not identity: the consumer reads it, no node digests it.
    tool: ToolSpec | None = None


#: The lattice shapes a sheet may take, at SHEET_CELL_PX-square cells: the
#: provider's canvases are 1024x1024, 1536x1024 and 1024x1536, and a 512-px
#: cell divides each of them exactly. Three looks cannot be a sheet (there is
#: no 3x1 canvas); the author adds a fourth look.
SHEET_SHAPES: Final = ((2, 2), (3, 2), (2, 3))
#: A state may not be called this: it would collide with the sheet node ids.
RESERVED_STATE_NAMES: Final = ("sheet",)


@dataclass(frozen=True, slots=True)
class SheetSpec:
    """All of a prop's looks painted together into one lattice, one image op.

    What a sheet buys is one shared drawing scale by construction and one op
    for N looks; what it costs is half the pixels per look and a whole-sheet
    retry when one cell fails. The taxonomy is structural: a prop is drawn as
    single sprites or as a sheet, and the system knows nothing of why.
    """

    columns: int
    rows: int

    @property
    def cell_count(self) -> int:
        return self.columns * self.rows


@dataclass(frozen=True, slots=True)
class EdgePreference:
    """A preference for the band near something: the water, a biome's edge,
    the road, a set piece. Weight 1 within, ``outside`` beyond the falloff."""

    of: str
    within_meters: float
    falloff_meters: float
    outside: float


@dataclass(frozen=True, slots=True)
class HeightPreference:
    """A band of the rules-only height field, 0 at the coast and 1 inland."""

    min: float
    max: float
    falloff: float


@dataclass(frozen=True, slots=True)
class ClusterRule:
    """Sparse but clumped: parents where the habitat is best, children round each."""

    parents_per_100m2: float
    mean_size: float
    radius_meters: float


@dataclass(frozen=True, slots=True)
class NearRule:
    """Placed round another object's final points (a fern under a pine)."""

    host: str
    radius_meters: float
    mean: float
    chance: float


@dataclass(frozen=True, slots=True)
class AvoidRule:
    target: str
    radius_meters: float


@dataclass(frozen=True, slots=True)
class Placement:
    """Where and how an object stands in the world: the object's own block.

    The object owns its habitat, so adding an object never edits a biome. One
    of four processes: ``density_per_100m2`` alone is Poisson, ``cluster`` is
    a Matérn cluster (the density is parents times mean size), ``spacing_meters``
    alone is a jittered grid, ``near`` attaches to another object. The rest
    shapes the intensity (habitat, edge, height), the rarity, the quota and
    the keep-outs. The generator that reads this knows none of the words.
    """

    habitat: Mapping[str, float]
    density_per_100m2: float | None = None
    cluster: ClusterRule | None = None
    spacing_meters: float | None = None
    near: NearRule | None = None
    edge: EdgePreference | None = None
    height: HeightPreference | None = None
    chance: float = 1.0
    min_per_world: int = 0
    max_per_world: int | None = None
    avoid: tuple[AvoidRule, ...] = ()
    clearing_radius_meters: float = 0.0

    @property
    def process_kind(self) -> str:
        if self.cluster is not None:
            return "cluster"
        if self.near is not None:
            return "near"
        if self.spacing_meters is not None and self.density_per_100m2 is None:
            return "spaced"
        return "poisson"


@dataclass(frozen=True, slots=True)
class VariantSpec:
    """Looks the layout picks from, one per placed instance, by weight.

    The other author's binding. A tree's age, a boulder's mossiness, a season:
    the author names the looks and weights them, and the layout draws from the
    seed it already publishes. Nothing downstream knows the axis has a name.
    """

    states: tuple[str, ...]
    weights: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class Prop:
    prop_id: str
    family: str
    height_units: float
    footprint_radius_units: float
    shadow_width_units: float
    edge: Literal["hard", "soft"]
    motion_hint: str
    #: ``shake`` (the card rocks about its foot, away from the tool) or ``none``
    #: (it holds still; debris and the camera kick are unaffected). Required:
    #: the author says what a thing is made of, the system never guesses.
    hit_reaction: str
    max_components: int
    prompt: str
    states: tuple[str, ...]
    state_prompt: Mapping[str, str]
    #: What can be done to it, in authored order (the order is the priority
    #: when more than one applies from a state). Empty for a thing that only
    #: stands.
    interactions: tuple[Interaction, ...]
    #: The look every other look is measured against: its painted height is
    #: ``height_units``, its sprite is the one the anchor loop places, and the
    #: layout falls back to it. Defaults to the first declared state.
    baseline_state: str
    #: The canonical size of every other look, in player heights. Nothing an
    #: image model returns carries a size, so a look's magnitude is authored
    #: and its pixels only supply a ruler: each authored look is calibrated
    #: from its own painted extent against its own number. A look absent here
    #: shares the baseline's ruler instead (drawn at the same scale, so the
    #: same size in the world as it was drawn), which is what a cracked rock
    #: wants and a stump does not.
    look_height_units: Mapping[str, float]
    #: Where and how the layout scatters this prop. Absent means never
    #: scattered: a station is built, a camp prop is a set-piece member.
    placement: Placement | None = None
    #: The soft disc of shade the plate carries under this prop, in metres.
    #: 0 means none. An attribute, not a family rule: the plate knows no tree.
    canopy_radius_meters: float = 0.0
    #: Drawn as one sheet (all looks together, one op) rather than as one
    #: sprite per look. Optional; absent means sprites.
    sheet: SheetSpec | None = None
    #: The looks a placed instance may take, and how often. Optional.
    variants: VariantSpec | None = None
    #: Per season look, per state: a brief that replaces the season's shared
    #: clause for that one paintover (props.toml [props.season_prompt.<look>]).
    #: Read by the look prompt alone; prop_prompt never sees it.
    season_prompt: Mapping[str, Mapping[str, str]] = field(default_factory=dict)

    def prompt_for(self, state: str) -> str:
        suffix = self.state_prompt.get(state, "")
        return f"{self.prompt} {suffix}".strip() if suffix else self.prompt

    def authored_height_units(self, state: str) -> float | None:
        """This look's canonical height, or None when it rides the baseline's ruler."""

        if state == self.baseline_state:
            return self.height_units
        return self.look_height_units.get(state)

    def height_share(self, state: str) -> float | None:
        """How tall this look is against the baseline look, when the author said."""

        authored = self.authored_height_units(state)
        return None if authored is None else authored / self.height_units


@dataclass(frozen=True, slots=True)
class ItemUse:
    """What the use key does with the item. ``consume`` spends one and moves
    the vitals; ``light`` lights the item as a torch for ``burn_seconds``;
    ``carry`` is passive, extra ``slots`` while the item is in the pack;
    ``wear`` is passive too, ``insulation`` off the cold while in the pack;
    ``warm`` is the torch's shape, lit and spent after ``heat_seconds``."""

    kind: str
    hunger: float = 0.0
    health: float = 0.0
    radius_meters: float = 0.0
    burn_seconds: float = 0.0
    slots: int = 0
    #: ``consume`` may also give warmth; ``wear`` takes this share off the
    #: cold's drain while carried; ``warm`` holds the drain off this long.
    warmth: float = 0.0
    insulation: float = 0.0
    heat_seconds: float = 0.0


@dataclass(frozen=True, slots=True)
class ItemTool:
    """The item serves an interaction verb and lasts this many completed uses."""

    verb: str
    uses: int


@dataclass(frozen=True, slots=True)
class Item:
    item_id: str
    height_units: float
    #: The pickup's brief, the only field a node digests.
    prompt: str
    display_name: str = ""
    #: How many share one slot. Gameplay, never identity.
    stack_max: int = 10
    use: ItemUse | None = None
    tool: ItemTool | None = None
    #: The icon sheet's brief for this item; the pickup brief when absent.
    icon_brief: str = ""


@dataclass(frozen=True, slots=True)
class IconGlyph:
    """A HUD glyph filling an icon-sheet cell the items left over."""

    glyph: str
    brief: str


@dataclass(frozen=True, slots=True)
class IconSheet:
    """One lattice of inventory icons: the items in order, then the glyphs."""

    columns: int
    rows: int
    cell_px: int
    style_emphasis: str
    glyphs: tuple[IconGlyph, ...]
    take: str | None

    @property
    def cell_count(self) -> int:
        return self.columns * self.rows


@dataclass(frozen=True, slots=True)
class Station:
    """A prop the player must stand near to craft, in a look if one is named."""

    station_id: str
    prop_id: str
    state: str | None
    reach_meters: float


@dataclass(frozen=True, slots=True)
class Recipe:
    """Ingredients in, one product out: an item with a count, or a placed prop."""

    recipe_id: str
    ingredients: Mapping[str, int]
    station: str
    product_item: tuple[str, int] | None = None
    product_prop: str | None = None


@dataclass(frozen=True, slots=True)
class Crafting:
    """crafting.toml: the pack, the start, the stations and the recipes."""

    slots: int
    start: Mapping[str, int]
    stations: tuple[Station, ...]
    recipes: tuple[Recipe, ...]

    def station(self, station_id: str) -> Station:
        for entry in self.stations:
            if entry.station_id == station_id:
                return entry
        raise SourceError(f"unknown station {station_id!r}")


@dataclass(frozen=True, slots=True)
class Biome:
    biome_id: str
    texel_meters: float
    prompt: str
    #: This biome's share of the land, solved by the layout. The first biome
    #: declared is the base and owns whatever the others leave; its share is
    #: the remainder and is not authored.
    share: float
    #: Mean greyscale value the plate must arrive at. A number, not an adjective:
    #: three rounds of prompt strengthening moved a forest floor 0.186 -> 0.235
    #: -> 0.263 and stalled, because the package style block is prepended to
    #: every prompt and a "muted earth palette" obeys itself too well on ground.
    #: Value is therefore a package decision, declared per biome.
    value_target: float
    #: Style direction that applies to this plate instead of the package's, so a
    #: ground plate is not dragged down by a mood written for props and actors.
    style_emphasis: str
    #: The largest thing the plate may contain, in metres. The first plates were
    #: pictures of ground painted at about a metre across and stretched over
    #: eight: half-metre leaves, metre-wide stones. A material swatch states its
    #: real span and its largest feature, and the prompt says both in centimetres.
    feature_max_meters: float
    #: How a dropped pickup stops on this ground: a coefficient of friction,
    #: sliding deceleration = friction * g. A property of the surface, not of
    #: the item: a log stops the same way a stone does on the same earth, and
    #: both slide further on scree than in a bog.
    friction: float
    #: "field": mostly bare ground colour with a few tone marks, the way a
    #: woodland floor is. "fabric": the whole plate covered in strokes lying
    #: one way in two close tones, the way the reference paints its turf; the
    #: fine grain is inside the stroke, not laid over it. Chooses the clause.
    material: str
    #: An auditioned draw kept in the package (explore/ground-audition/) and
    #: adopted through the plate gate instead of re-drawn. The route has no
    #: seed, so a brief is a draw; the take is the pick.
    take: str | None


GROUND_MATERIALS: Final = ("field", "fabric")


#: How a pickup gets from the ground into the inventory. "manual": the player
#: stands within reach and presses the interact key, the reference's way.
#: "magnet": a settled pickup within a metre is drawn to the player and counted
#: on arrival. A game decision, so a field, refused when it names anything else.
PICKUP_MODES: Final = ("manual", "magnet")

GROUND_CONTACTS: Final = ("shadow", "skirt_decal", "painted_base", "none")
#: "wet" is a decal the layout scatters for a weather condition and the
#: runtime fades with wetness (weather.toml [conditions.wet]).
DECAL_USES: Final = ("pad", "skirt", "free", "wet")


@dataclass(frozen=True, slots=True)
class Decal:
    decal_id: str
    width_meters: float
    height_meters: float
    prompt: str
    #: "pad" under camp structures, "skirt" under props of ``families``, "free"
    #: for a decal the layout places some other way.
    use: str
    families: tuple[str, ...]
    #: For a skirt: its laid width as a multiple of the prop's shadow width.
    scale: float


@dataclass(frozen=True, slots=True)
class MacroPlate:
    """A slow colour field multiplied over the fine material: the abstract layer.

    The reference genre's ground is flat colour fields with soft painted
    boundaries, and everything recognisable is a sprite. This plate is those
    fields; it is gated to contain no drawing at all.
    """

    texel_meters: float
    #: Metres the plate spans at playback. Consumer mixing: the plate is an
    #: abstract cloud, so how many metres it covers on the ground is a read of
    #: the same picture, not a different picture, and no cache key sees it.
    #: Absent, the mirrored plate's own span (twice texel_meters).
    period_meters: float | None
    strength: float
    prompt: str


@dataclass(frozen=True, slots=True)
class Road:
    """A track painted into the splat's green channel and rendered as a layer.

    The road's fill is a material plate like a biome's; its edge is the splat
    mask eroded by noise in the shader. The one thing a splat road cannot do is
    align its texture to the direction of travel, which is why it is a dirt
    track and not a plank road.
    """

    road_id: str
    width_meters: float
    length_meters: float
    texel_meters: float
    feature_max_meters: float
    value_target: float
    style_emphasis: str
    edge_meters: float
    prompt: str


@dataclass(frozen=True, slots=True)
class Water:
    """The plane beyond the coast. A material plate like the ground's, darker."""

    texel_meters: float
    feature_max_meters: float
    value_target: float
    style_emphasis: str
    prompt: str
    colour: tuple[float, float, float]
    #: How far below the ground the water lies. The reference draws the land
    #: as a raised slab with a cliff face under its far edge; the viewer draws
    #: that face by re-sampling the land mask up the view ray, and the depth
    #: is how tall the face is. Consumer mixing: no node reads it.
    depth_meters: float
    cliff_colour: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class ClutterCell:
    """One litter cutout: what it is, how it meets the ground, where it may land."""

    brief: str
    contact: str
    biomes: tuple[str, ...]
    #: This cell's own placement, replacing the sheet's for this cell alone.
    placement: Placement | None = None


CLUTTER_CONTACTS: Final = ("pressed", "fallen", "growing")


@dataclass(frozen=True, slots=True)
class Clutter:
    """One sheet of small ground-litter cutouts, scattered flat at true scale."""

    columns: int
    rows: int
    cell_meters: float
    #: How the sheet's cells are scattered; a cell may carry its own.
    placement: Placement
    cells: tuple[ClutterCell, ...]
    #: Drawing direction for the sheet only, stated after the package's so it
    #: wins: the first sheet came back glossy, and the plates are matte.
    style_emphasis: str
    #: An auditioned sheet adopted through the lattice gate (explore/ground-audition/).
    take: str | None

    @property
    def cell_count(self) -> int:
        return self.columns * self.rows

    def cells_for(self, biome_id: str) -> tuple[int, ...]:
        return tuple(index for index, cell in enumerate(self.cells) if biome_id in cell.biomes)


@dataclass(frozen=True, slots=True)
class ForageCell:
    """One forageable cutout: a litter cell that also names what taking it yields."""

    brief: str
    contact: str
    biomes: tuple[str, ...]
    item_id: str
    count: int
    regrow_seconds: float
    placement: Placement | None = None


@dataclass(frozen=True, slots=True)
class Forage:
    """One sheet of pickups lying on the ground, scattered flat like the litter."""

    columns: int
    rows: int
    cell_meters: float
    placement: Placement
    cells: tuple[ForageCell, ...]
    style_emphasis: str
    take: str | None

    @property
    def cell_count(self) -> int:
        return self.columns * self.rows

    def cells_for(self, biome_id: str) -> tuple[int, ...]:
        return tuple(index for index, cell in enumerate(self.cells) if biome_id in cell.biomes)


@dataclass(frozen=True, slots=True)
class PlantCell:
    """One standing plant: what it is, how it meets the ground, where it may grow."""

    brief: str
    contact: str
    biomes: tuple[str, ...]
    placement: Placement | None = None


@dataclass(frozen=True, slots=True)
class Plants:
    """The mid-scale: one sheet of knee- to waist-high plants, scattered by the
    layout like the litter but stood up as cards at true size. Not a prop:
    nothing here is interactable, and there are thousands of them."""

    columns: int
    rows: int
    cell_meters: float
    placement: Placement
    cells: tuple[PlantCell, ...]
    style_emphasis: str
    take: str | None

    @property
    def cell_count(self) -> int:
        return self.columns * self.rows

    def cells_for(self, biome_id: str) -> tuple[int, ...]:
        return tuple(index for index, cell in enumerate(self.cells) if biome_id in cell.biomes)


@dataclass(frozen=True, slots=True)
class FireFx:
    columns: int
    rows: int
    fps: float
    height_units: float
    prompt: str

    @property
    def frames(self) -> int:
        return self.columns * self.rows


@dataclass(frozen=True, slots=True)
class DustFx:
    kinds: tuple[str, ...]
    height_units: float
    prompt: str


#: The clock states a music track may play under. The viewer crossfades the
#: day track into the night track by the same night factor that tints the
#: world, so exactly one track per cue is the contract.
MUSIC_CUES: Final = ("day", "night")


@dataclass(frozen=True, slots=True)
class Track:
    """One authored music loop. The brief is the prompt, verbatim."""

    track_id: str
    cue: str
    target_duration_seconds: float
    prompt: str
    #: An auditioned draw of this brief, chosen by ear, kept inside the package
    #: as an authored asset (path relative to the source root, digested). When
    #: set, the pipeline adopts it through the music gate instead of asking the
    #: route again: the route has no seed, and a re-draw is a new song.
    take: str | None


#: The shapes a fade may take, as a rising gain over its own window: `linear`
#: is a straight line, `equal_power` a quarter sine (the two gains square-sum
#: to one), `exponential` a square (quiet for longer, then quick).
MUSIC_CURVES: Final = ("linear", "equal_power", "exponential")


@dataclass(frozen=True, slots=True)
class MusicTransition:
    """How a consumer moves from one loop to the other.

    Mixing, not art: no prompt, no digest and no cache key reads any of it, so
    retuning a transition costs nothing and re-bills nothing. The clock only
    picks the cue (`switch_at` on the same night factor that tints the world);
    the fade then runs on its own timeline, so it lasts `crossfade_seconds`
    whatever the day length is.
    """

    #: How long a whole change of cue takes, end to end.
    crossfade_seconds: float
    curve: str
    #: 1: both loops span the whole window, the classic crossfade. 0: the
    #: outgoing loop is gone before the incoming one starts. Two unrelated
    #: songs held together at half gain sound broken, which is what the
    #: overlap is for.
    overlap: float
    #: The night factor at which the cue flips. A consumer holds the flip with
    #: a little hysteresis so a hand on the clock cannot make it stutter.
    switch_at: float


#: What a package gets when music.toml declares no [transition].
DEFAULT_MUSIC_TRANSITION: Final = MusicTransition(
    crossfade_seconds=2.5, curve="equal_power", overlap=0.35, switch_at=0.5
)


#: The world conditions a consumer plays. Closed for the same reason the
#: screen-FX moment vocabulary is: a condition nobody drives is paid art
#: nobody sees, and the loader refuses it offline. See weather.toml's header
#: for why weather is its own family and not a screen-FX moment.
WEATHER_CONDITIONS: Final = ("rain", "snow")


#: The things the player does that make a sound, named by the runtime that
#: plays them (they are the events it emits) and closed for the reason the
#: music cues are: a clip nobody plays is paid audio nobody hears. `footstep`
#: is the walk cycle; `chop` and `mine` are the blow of the interaction verb of
#: the same name; `pickup` is a drop taken; `fire` loops beside a lit campfire;
#: `eat` is a berry eaten; `footstep_snow` is the walk while the snow factor
#: is past a half. See sounds.toml's header.
SOUND_CUES: Final = ("footstep", "chop", "mine", "pickup", "fire", "eat", "footstep_snow")


@dataclass(frozen=True, slots=True)
class SoundEffect:
    """One authored sound-effect clip. The brief is the prompt, verbatim; the
    duration is exact, and it is the repetition control (half a second is one
    footstep, two seconds is a walk)."""

    cue: str
    prompt: str
    duration_seconds: float
    loop: bool
    #: An auditioned draw of this brief, chosen by ear, kept inside the package
    #: as an authored asset (path relative to the source root, digested). When
    #: set, the pipeline adopts it through the clip gate instead of asking the
    #: route again: the route has no seed, and a re-draw is a new sound.
    take: str | None
    #: Consumer mixing, never identity: the route's level swings 40 dB between
    #: draws and may not be repaired, so the set is balanced at playback; up
    #: to 4 (+12 dB) so a quiet take can be lifted, not only a loud one cut.
    gain: float
    #: Semitones either way a consumer may detune a play, so a repeated cue (a
    #: walk) is not one sample on a trigger.
    pitch_jitter: float
    #: The clip is a run of events (a walk, not a step): a consumer cuts it at
    #: the onsets it finds and plays one per trigger. Mixing, not identity:
    #: the file is whole, the cut is the player's. The route serves a run
    #: better than a single half-second event.
    onsets: bool


@dataclass(frozen=True, slots=True)
class WeatherDrops:
    """A two-cell sheet (a streak, a drop) run as a screen-space particle system."""

    kinds: tuple[str, ...]
    count_per_screen: int
    layers: int
    fall_speed_meters_per_second: float
    height_units: float
    prompt: str
    #: "streak": a tall thin left cell and a small right one (rain). "blob": a
    #: round left cell (snow). Chooses the sheet clause; the default reproduces
    #: the rain sheet's prompt exactly, so it is not a re-bill.
    shape: str = "streak"


DROPS_SHAPES: Final = ("streak", "blob")


@dataclass(frozen=True, slots=True)
class WeatherGround:
    """A four-cell puff sheet laid flat where drops land: the dust sheet's technique."""

    kinds: tuple[str, ...]
    height_units: float
    rate_per_100_sqm_per_second: float
    prompt: str


@dataclass(frozen=True, slots=True)
class WeatherWet:
    """A binding to a ``use = "wet"`` decal the layout scatters and wetness fades."""

    decal_id: str
    per_100_sqm: float
    dry_seconds: float


@dataclass(frozen=True, slots=True)
class WeatherStrike:
    """A four-cell bolt sheet stood in the world at a strike point, plus a flash."""

    above: float
    interval_seconds: tuple[float, float]
    flash_seconds: float
    height_units: float
    prompt: str


@dataclass(frozen=True, slots=True)
class SoundCue:
    """One sound-effect clip. The brief is the prompt, verbatim; the duration is exact."""

    prompt: str
    duration_seconds: float
    loop: bool


@dataclass(frozen=True, slots=True)
class WeatherSound:
    ambience: SoundCue | None
    strike: SoundCue | None


@dataclass(frozen=True, slots=True)
class WeatherCover:
    """A ground plate laid over every biome by coverage: the reference's winter
    turf. Drawn on the ground plate route with a pale value band, mirrored
    like a biome plate, blended in the ground shader through the same torn
    erosion a biome edge gets. Sprites keep their own look (caps are later)."""

    texel_meters: float
    feature_max_meters: float
    value_target: float
    style_emphasis: str
    prompt: str


@dataclass(frozen=True, slots=True)
class WeatherIce:
    """The water, frozen: a plate on the water route with the cover's pale band,
    mirrored like every plate, mixed over the water by the condition's factor
    with the waves stilled. A look, not a floor. Snow only."""

    texel_meters: float
    value_target: float
    style_emphasis: str
    prompt: str
    #: An auditioned draw kept in the package, adopted through the plate gate.
    take: str | None = None


@dataclass(frozen=True, slots=True)
class Condition:
    """One authored weather condition: the world's clock for it, its wash, its layers."""

    condition_id: str
    onset_seconds: float
    decay_seconds: float
    dry_spell_seconds: tuple[float, float]
    wet_spell_seconds: tuple[float, float]
    tint: tuple[float, float, float]
    desaturate: float
    drops: WeatherDrops | None
    ground: WeatherGround | None
    wet: WeatherWet | None
    strike: WeatherStrike | None
    sound: WeatherSound | None
    cover: WeatherCover | None
    ice: WeatherIce | None

    @property
    def sound_cues(self) -> tuple[tuple[str, SoundCue], ...]:
        if self.sound is None:
            return ()
        return tuple(
            (name, cue)
            for name, cue in (("ambience", self.sound.ambience), ("strike", self.sound.strike))
            if cue is not None
        )


@dataclass(frozen=True, slots=True)
class Season:
    """One season of the calendar: what it holds while it lasts."""

    season_id: str
    display_name: str
    #: The snow condition's factor the season holds, ramped through that
    #: condition's onset and decay.
    snow: float
    #: Scales [gameplay.warmth].drain_per_second.
    cold: float
    #: The share of a day that is night.
    night_share: float
    #: Scales every regrow timer; 0 stops growth.
    regrow_scale: float
    #: Forage cells of these items hide while the season lasts.
    hidden_forage: tuple[str, ...]
    #: Props whose interaction is refused while the season lasts.
    barren: tuple[str, ...]
    #: The prop look this season shows, or "" for the summer sprites.
    look: str


@dataclass(frozen=True, slots=True)
class SeasonLook:
    """A set of paintovers, one per prop state, under one shared clause."""

    look_id: str
    prompt: str


@dataclass(frozen=True, slots=True)
class Seasons:
    """seasons.toml: the calendar, its seasons in order, and the looks they name."""

    order: tuple[str, ...]
    days_per_season: int
    seasons: tuple[Season, ...]
    looks: tuple[SeasonLook, ...]

    def season(self, season_id: str) -> Season:
        for entry in self.seasons:
            if entry.season_id == season_id:
                return entry
        raise SourceError(f"unknown season {season_id!r}")

    def look(self, look_id: str) -> SeasonLook:
        for entry in self.looks:
            if entry.look_id == look_id:
                return entry
        raise SourceError(f"unknown season look {look_id!r}")


#: The lights the look contract knows. Each one is a prompt clause in
#: prompts.py and a review question; a light with no clause is refused here,
#: offline, rather than drawn from nowhere.
LOOK_LIGHTS: Final = ("overhead",)


@dataclass(frozen=True, slots=True)
class Look:
    """The look contract: the rules that keep one look across every asset.

    See ``[look]`` in survival.toml. Mirroring is not a field because it is
    not a choice: nothing is mirrored for variety, and only an actor's facing
    is mirrored at all, which the overhead light makes safe.
    """

    #: Where the one light comes from, in every drawn asset.
    light: str
    #: How far a piece lying on the ground may turn from facing the camera.
    ground_piece_jitter_degrees: float


@dataclass(frozen=True, slots=True)
class MissingTake:
    """A take the package declared by digest whose bytes are not on disk.

    An authored take may be declared as ``take = { path = "...", sha256 = "..." }``
    instead of a bare path, and then the declared digest -- not the file -- is
    what enters the digest ledger. That makes the package's identity a function
    of its committed text alone, so a package whose large media is kept outside
    the repository still plans, still digests, and still builds the same graph.
    The absence is recorded here rather than ignored: the adopt node refuses at
    execution, after planning has already proved what the run would cost.
    """

    path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class Landmass:
    land_share: float
    coast_noise_lattice: int
    coast_crinkle: float
    shore_margin_meters: float
    height_octave_lattice: int
    height_octave_weight: float


@dataclass(frozen=True, slots=True)
class BiomeRules:
    """The spatial rules of the biomes; the plates stay in ground.toml."""

    islet_lattice: int
    islet_share: float


@dataclass(frozen=True, slots=True)
class SetPieceMember:
    prop: str
    state: str
    dx: float
    dz: float
    #: A worn pad under the member, scaled; None draws none.
    pad_scale: float | None


@dataclass(frozen=True, slots=True)
class SetPiece:
    """An authored composition the layout sites whole."""

    set_piece_id: str
    count: int
    at: Literal["origin", "band"]
    band_meters: tuple[float, float]
    biome: str | None
    clearing_radius_meters: float
    pad_decal: str | None
    #: The player's spawn offset, on the set piece the world names as its spawn.
    spawn: tuple[float, float] | None
    members: tuple[SetPieceMember, ...]


@dataclass(frozen=True, slots=True)
class World:
    """world.toml: the extent, the landmass, the biome rules, the set pieces."""

    seed: int
    size_meters: float
    landmass: Landmass
    biomes: BiomeRules
    spawn_set_piece: str
    set_pieces: tuple[SetPiece, ...]
    population_order: tuple[str, ...]

    def set_piece(self, set_piece_id: str) -> SetPiece:
        for entry in self.set_pieces:
            if entry.set_piece_id == set_piece_id:
                return entry
        raise SourceError(f"unknown set piece {set_piece_id!r}")

    @property
    def spawn(self) -> SetPiece:
        return self.set_piece(self.spawn_set_piece)


@dataclass(frozen=True, slots=True)
class Package:
    """The whole authored intent, frozen, with one digest per source file."""

    root: Path
    package_id: str
    title: str
    digests: Mapping[str, str]
    style_label: str
    style_keywords: tuple[str, ...]
    style_avoid: tuple[str, ...]
    #: The style plate: one authored picture of what the keywords mean, carried
    #: as reference image 1 by every generative image node. A package may have
    #: none, in which case the prose stands alone. Path is relative to the
    #: source root and its digest is part of the package digest, so redrawing
    #: the plate re-bills every node that carries it.
    style_reference: str | None
    style_reference_digest: str | None
    profile: str
    #: The authored seam between a billboard and the ground. See survival.toml.
    ground_contact: str
    #: The look contract. See survival.toml [look].
    look: Look
    player_height_meters: float
    minimum_height_units: float
    #: Two open sub-documents of survival.toml, carried verbatim into the
    #: manifest for the consumer to read: the camera rig and the gameplay
    #: numbers. Their keys are the author's and grow without a schema change,
    #: so the value type stays ``Any`` on purpose; the few entries this package
    #: depends on are read through ``.get(key, default)`` and coerced at the
    #: point of use, and the handful that are refusal-bearing
    #: (``gameplay.pickup`` and the two reach numbers) are validated in
    #: ``survival_request._gameplay``.
    camera: Mapping[str, Any]
    #: world.toml, parsed: the layout reads nothing else about where things go.
    world: World
    gameplay: Mapping[str, Any]
    facing_authored: str
    player: Actor
    mob: Actor
    props: tuple[Prop, ...]
    items: tuple[Item, ...]
    #: items.toml [icons]: the inventory icon sheet. One op for every item.
    icons: IconSheet
    #: crafting.toml. Gameplay the manifest carries and no node reads.
    crafting: Crafting
    biomes: tuple[Biome, ...]
    decals: tuple[Decal, ...]
    macro: MacroPlate | None
    road: Road | None
    clutter: Clutter | None
    #: ground.toml [forage]: the pickups lying on the ground. Optional like the litter.
    forage: Forage | None
    #: ground.toml [plants]: the standing mid-scale. Optional like the litter.
    plants: Plants | None
    water: Water | None
    #: ground.toml [blend]: the viewer's composition numbers. Mixing, never
    #: identity; see BLEND_KEYS.
    blend: Mapping[str, float]
    #: ground.toml [blend] level: biome_id -> display luma; see LEVEL_RANGE.
    level: Mapping[str, float]
    fire: FireFx
    dust: DustFx
    #: Music is optional: a package with no music.toml plays in silence and the
    #: manifest says so. When present, one track per cue.
    music: tuple[Track, ...]
    #: How a consumer crossfades those tracks. Mixing, never identity.
    music_transition: MusicTransition
    #: Weather is optional the same way: no weather.toml, no weather, and the
    #: manifest says "none". When present, one entry per condition.
    weather: tuple[Condition, ...]
    #: Sound effects are optional the same way: no sounds.toml, a silent player,
    #: and the manifest says "none". When present, one clip per cue.
    sounds: tuple[SoundEffect, ...]
    #: Seasons are optional the same way: no seasons.toml, the world stays as
    #: drawn. When present, the calendar and the looks it names.
    seasons: Seasons | None
    #: The takes this package declares by digest whose bytes are not on disk.
    #: Empty for a package that carries all of its own media.
    missing_takes: tuple[MissingTake, ...] = ()

    @property
    def actors(self) -> tuple[Actor, ...]:
        return (self.player, self.mob)

    def actor(self, actor_id: str) -> Actor:
        for entry in self.actors:
            if entry.actor_id == actor_id:
                return entry
        raise SourceError(f"unknown actor {actor_id!r}")

    def prop(self, prop_id: str) -> Prop:
        for entry in self.props:
            if entry.prop_id == prop_id:
                return entry
        raise SourceError(f"unknown prop {prop_id!r}")

    def item(self, item_id: str) -> Item:
        for entry in self.items:
            if entry.item_id == item_id:
                return entry
        raise SourceError(f"unknown item {item_id!r}")

    def biome(self, biome_id: str) -> Biome:
        for entry in self.biomes:
            if entry.biome_id == biome_id:
                return entry
        raise SourceError(f"unknown biome {biome_id!r}")

    def source_digest(self) -> str:
        """One digest over every authored file, in a fixed order."""

        joined = "\n".join(f"{name}={self.digests[name]}" for name in sorted(self.digests))
        return content_sha256(joined.encode("utf-8"))

    def meters(self, height_units: float) -> float:
        return round(height_units * self.player_height_meters, 4)

    def missing_take(self, take: str) -> MissingTake | None:
        """The record of a declared take whose bytes are absent, or None when it is here."""

        for entry in self.missing_takes:
            if entry.path == take:
                return entry
        return None

    def identity(self) -> Mapping[str, object]:
        """The identity document the run directory records beside its plan.

        Structure only, and one digest that stands for every authored byte: a
        consumer reading a run needs to know which package it came from and
        whether that package has moved since, not to re-read the package.
        """

        return {
            "schema_version": 1,
            "kind": "oblique-survival-identity-v1",
            "package_id": self.package_id,
            "title": self.title,
            "source_digest": self.source_digest(),
            "presentation_profile": self.profile,
            "publication_authorized": False,
        }


class ObliqueSurvivalSource(BaseModel):
    """The root document's contract: ``survival.toml``'s own identity.

    The loader validates the whole authored package by hand, field by field,
    because its refusals name the authored line that is wrong. What this model
    owns is narrower and cannot be expressed that way: the identity string the
    repository's contract table reads, pinned as a one-value ``Literal`` so a
    document written against an older grammar is refused rather than guessed
    at. Extra keys are allowed here on purpose -- the rest of the document is
    the loader's to accept or refuse.
    """

    model_config = ConfigDict(extra="allow")

    schema_version: Literal[1]
    kind: Literal["oblique-survival-package-v2"]
