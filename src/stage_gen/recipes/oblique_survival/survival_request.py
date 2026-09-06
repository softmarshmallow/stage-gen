"""Read one authored oblique-survival package: validate, freeze, digest.

The loader is the recipe's ``_resolve`` target. It touches no provider: every
refusal here happens offline, before a run directory exists and before a cent
is spent. Each authored file lands in the digest ledger under its own name, and
the ledger's fixed-order digest is the package's identity -- so an edit to any
authored byte moves the source lock, and nothing else silently drifts.

An adopted take may be declared two ways. A bare path is read and digested from
disk, as it always was. An inline table ``{ path, sha256 }`` declares the
digest instead: that digest enters the ledger exactly as the file's would, the
file is verified against it when it is present, and its absence is allowed and
recorded so that planning works from the committed text alone while the adopt
node refuses at execution.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Final, Literal, Protocol, TypedDict, cast

from pydantic import ValidationError

from stage_gen.canonical import content_sha256
from stage_gen.components._game_input import AuthoredContractLoadError
from stage_gen.components.game_ui import GameUi, load_game_ui_bytes
from stage_gen.recipes.oblique_survival.models import (
    CLUTTER_CONTACTS,
    DECAL_USES,
    DEFAULT_MUSIC_TRANSITION,
    DROPS_SHAPES,
    EDGE_FIELDS,
    EDGE_KINDS,
    FACING_SETS,
    GROUND_CONTACTS,
    GROUND_MATERIALS,
    HIT_REACTIONS,
    INTERACTION_VERBS,
    ITEM_USES,
    LOOK_LIGHTS,
    MAX_BIOMES,
    MOTION_HINTS,
    MOTION_MODES,
    MUSIC_CUES,
    MUSIC_CURVES,
    PICKUP_MODES,
    RESERVED_STATE_NAMES,
    SHEET_SHAPES,
    SIDE_VIEWS,
    SOUND_CUES,
    WEATHER_CONDITIONS,
    WORLD_KIND,
    YIELD_DESTINATIONS,
    Actor,
    AvoidRule,
    Biome,
    BiomeRules,
    ClusterRule,
    Clutter,
    ClutterCell,
    Condition,
    Crafting,
    Decal,
    DustFx,
    EdgePreference,
    FacingSet,
    FireFx,
    Forage,
    ForageCell,
    HeightPreference,
    IconGlyph,
    IconSheet,
    Interaction,
    Item,
    ItemTool,
    ItemUse,
    Landmass,
    Look,
    MacroPlate,
    MissingTake,
    MotionState,
    MusicTransition,
    NearRule,
    ObliqueSurvivalSource,
    Package,
    PackageFile,
    Placement,
    PlantCell,
    Plants,
    Prop,
    Recipe,
    Road,
    Season,
    SeasonLook,
    Seasons,
    SetPiece,
    SetPieceMember,
    SheetSpec,
    SoundCue,
    SoundEffect,
    SourceError,
    Station,
    ToolSpec,
    Track,
    VariantSpec,
    Water,
    WeatherCover,
    WeatherDrops,
    WeatherGround,
    WeatherIce,
    WeatherSound,
    WeatherStrike,
    WeatherWet,
    World,
    Yield,
)

SURVIVAL_DOCUMENT_NAME: Final = "survival.toml"
#: The shared ``game-ui-v5`` document, optional like music.toml: the interface
#: sheets the host's HUD is dressed in, and the pointers it is played with. Its
#: contract is the game_ui component's.
UI_DOCUMENT_NAME: Final = "ui.toml"


@dataclass(slots=True)
class DigestLedger:
    """Every authored file's name and digest, plus the takes declared but absent.

    A mapping in all but name so the parsers keep writing ``ledger[name] = digest``:
    what is new is only that a digest may come from an author's declaration
    rather than from bytes on disk, and that the absence is remembered.
    """

    digests: dict[str, str] = field(default_factory=dict)
    missing: list[MissingTake] = field(default_factory=list)

    def __setitem__(self, name: str, digest: str) -> None:
        self.digests[name] = digest


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceError(f"{field} must be a non-empty string")
    return " ".join(value.split())


def _number(value: object, *, field: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise SourceError(f"{field} must be a number")
    number = float(value)
    if not low <= number <= high:
        raise SourceError(f"{field} must be within [{low}, {high}], got {number}")
    return number


def _identifier(value: object, *, field: str) -> str:
    text = _text(value, field=field)
    if not text.replace("_", "").isalnum() or not text.islower():
        raise SourceError(f"{field} must be lower_snake_case alphanumeric, got {text!r}")
    return text


def _slug(value: object, *, field: str) -> str:
    """Package ids follow the repository's hyphenated game-id convention."""

    text = _text(value, field=field)
    if not text.replace("-", "").replace("_", "").isalnum() or not text.islower():
        raise SourceError(f"{field} must be a lowercase slug, got {text!r}")
    return text


def _strings(value: object, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise SourceError(f"{field} must be a non-empty list")
    return tuple(_text(item, field=f"{field}[]") for item in value)


def _colour(value: object, *, field: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise SourceError(f"{field} must be three numbers")
    parts = tuple(_number(item, field=field, low=0.0, high=1.0) for item in value)
    return (parts[0], parts[1], parts[2])


def _digest(value: object, *, field: str) -> str:
    """A declared sha256, in the one spelling the ledger stores."""

    text = _text(value, field=field)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise SourceError(f"{field} must be 64 lowercase hexadecimal characters, got {text!r}")
    return text


def _identifiers(value: object, *, field: str) -> tuple[str, ...]:
    """A possibly empty list of identifiers."""

    if not isinstance(value, list):
        raise SourceError(f"{field} must be a list")
    out = tuple(_identifier(entry, field=f"{field}[]") for entry in value)
    if len(set(out)) != len(out):
        raise SourceError(f"{field} repeats an entry")
    return out


SEASON_KEYS: Final = frozenset(
    {
        "season_id",
        "display_name",
        "snow",
        "cold",
        "night_share",
        "regrow_scale",
        "hidden_forage",
        "barren",
        "look",
    }
)


def _seasons(
    doc: Mapping[str, object] | None, *, items: Sequence[Item], props: Sequence[Prop]
) -> Seasons | None:
    """The optional seasons file. Refuses offline a calendar no consumer could
    play: an order naming an undeclared season, a look with no clause, a barren
    prop that has nothing to refuse, a hidden item nobody forages."""

    if doc is None:
        return None
    if doc.get("kind") != "oblique-survival-seasons-v1":
        raise SourceError("seasons.toml kind must be oblique-survival-seasons-v1")
    unknown = sorted(set(doc) - {"schema_version", "kind", "package_id", "calendar", "seasons"})
    if unknown:
        raise SourceError(f"seasons.toml has unknown keys {unknown}")
    calendar = doc.get("calendar")
    if not isinstance(calendar, dict):
        raise SourceError("seasons.toml must declare a [calendar] table")
    unknown = sorted(set(calendar) - {"order", "days_per_season"})
    if unknown:
        raise SourceError(f"seasons.toml [calendar] has unknown keys {unknown}")
    order = tuple(
        _identifier(s, field="calendar.order[]")
        for s in _strings(calendar.get("order"), field="calendar.order")
    )
    if not order:
        raise SourceError("calendar.order names no season")
    if len(set(order)) != len(order):
        raise SourceError("calendar.order repeats a season")
    days = calendar.get("days_per_season")
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 30:
        raise SourceError("calendar.days_per_season must be an integer within [1, 30]")
    rows = doc.get("seasons")
    if not isinstance(rows, list) or not rows:
        raise SourceError("seasons.toml must declare at least one [[seasons]] entry")
    item_ids = {item.item_id for item in items}
    gatherable = {prop.prop_id for prop in props if prop.interactions}
    seasons: list[Season] = []
    looks: dict[str, SeasonLook] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise SourceError("[[seasons]] entry must be a table")
        season_id = _identifier(row.get("season_id"), field="season_id")
        if any(s.season_id == season_id for s in seasons):
            raise SourceError(f"seasons.toml repeats season {season_id!r}")
        field_name = f"seasons.{season_id}"
        unknown = sorted(set(row) - SEASON_KEYS)
        if unknown:
            raise SourceError(f"{field_name} has unknown keys {unknown}")
        hidden = _identifiers(row.get("hidden_forage", []), field=f"{field_name}.hidden_forage")
        for item_id in hidden:
            if item_id not in item_ids:
                raise SourceError(f"{field_name}.hidden_forage names undeclared item {item_id!r}")
        barren = _identifiers(row.get("barren", []), field=f"{field_name}.barren")
        for prop_id in barren:
            if prop_id not in gatherable:
                raise SourceError(
                    f"{field_name}.barren names {prop_id!r}, which has no interaction to refuse"
                )
        look_id = ""
        look_raw = row.get("look")
        if look_raw is not None:
            if not isinstance(look_raw, dict):
                raise SourceError(f"{field_name}.look must be a table with a prompt")
            unknown = sorted(set(look_raw) - {"prompt"})
            if unknown:
                raise SourceError(f"{field_name}.look has unknown keys {unknown}")
            look_id = season_id
            looks[look_id] = SeasonLook(
                look_id=look_id,
                prompt=_text(look_raw.get("prompt"), field=f"{field_name}.look.prompt"),
            )
        seasons.append(
            Season(
                season_id=season_id,
                display_name=" ".join(str(row.get("display_name", season_id)).split()),
                snow=_number(row.get("snow", 0.0), field=f"{field_name}.snow", low=0.0, high=1.0),
                cold=_number(row.get("cold", 0.0), field=f"{field_name}.cold", low=0.0, high=1.0),
                night_share=_number(
                    row.get("night_share", 0.38),
                    field=f"{field_name}.night_share",
                    low=0.2,
                    high=0.8,
                ),
                regrow_scale=_number(
                    row.get("regrow_scale", 1.0),
                    field=f"{field_name}.regrow_scale",
                    low=0.0,
                    high=1.0,
                ),
                hidden_forage=hidden,
                barren=barren,
                look=look_id,
            )
        )
    declared = {s.season_id for s in seasons}
    for season_id in order:
        if season_id not in declared:
            raise SourceError(f"calendar.order names undeclared season {season_id!r}")
    return Seasons(
        order=order, days_per_season=days, seasons=tuple(seasons), looks=tuple(looks.values())
    )


def _png_reference(
    root: Path, raw: object, digests: DigestLedger, *, field: str
) -> tuple[str | None, str | None]:
    """Resolve, digest and confine one authored PNG. Refuses before any spend.

    Shared by the style plate and by an actor's appearance reference: both are
    authored pictures that ride into a prompt, and both must stay inside the
    source package, be real PNGs, and have their digest bound into the node
    identity so replacing the picture re-bills what carries it.
    """

    if raw is None:
        return None, None
    if not isinstance(raw, str) or not raw.strip():
        raise SourceError(f"{field} must be a non-empty relative path")
    relative = PurePosixPath(raw.strip())
    if relative.is_absolute() or ".." in relative.parts:
        raise SourceError(f"{field} must stay inside the source package")
    if relative.suffix.lower() != ".png":
        raise SourceError(f"{field} must be a .png")
    path = root / Path(*relative.parts)
    resolved_root = root.resolve()
    current = resolved_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise SourceError(f"{field} must not traverse a symlink")
    if not path.is_file():
        raise SourceError(f"{field} not found: {relative}")
    if not path.resolve().is_relative_to(resolved_root):
        raise SourceError(f"{field} must stay inside the source package")
    raw_bytes = path.read_bytes()
    if not raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise SourceError(f"{field} must be a PNG")
    digest = content_sha256(raw_bytes)
    digests[relative.as_posix()] = digest
    return relative.as_posix(), digest


def _ui(root: Path, digests: DigestLedger) -> tuple[GameUi, dict[str, PackageFile]]:
    """ui.toml and the bytes behind its references, digested into the ledger.

    The document's own contract is the shared game_ui component's, so it is
    parsed there; what this loader owns is the same confinement, digest binding
    and refusals every other authored picture in the package gets. A reference
    is read once here and carried on the package, because the atlas triplet
    hands it to the provider as reference image 1.
    """

    path = root / UI_DOCUMENT_NAME
    raw = path.read_bytes()
    digests[path.name] = content_sha256(raw)
    try:
        ui = load_game_ui_bytes(raw)
    except AuthoredContractLoadError as error:
        raise SourceError(f"{UI_DOCUMENT_NAME} is not a game-ui-v5 document: {error}") from None
    references: dict[str, PackageFile] = {}
    for reference in ui.references:
        field_name = f"{UI_DOCUMENT_NAME} references.{reference.reference_id}.source"
        source, digest = _png_reference(root, reference.source, digests, field=field_name)
        assert source is not None and digest is not None
        if digest != reference.source_sha256:
            raise SourceError(
                f"{field_name} {source!r} does not match its declared sha256: "
                f"declared {reference.source_sha256}, found {digest}"
            )
        references[source] = PackageFile(
            data=(root / Path(*PurePosixPath(source).parts)).read_bytes(), sha256=digest
        )
    return ui, references


def _load_toml(path: Path, digests: DigestLedger) -> dict[str, object]:
    if not path.is_file():
        raise SourceError(f"missing source file: {path.name}")
    raw = path.read_bytes()
    digests[path.name] = content_sha256(raw)
    value = tomllib.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise SourceError(f"{path.name} must be a table")
    return value


def _subtable(doc: Mapping[str, object], key: str) -> Mapping[str, Any]:
    """One sub-table of a parsed document, or an empty one.

    A parsed TOML document is ``Mapping[str, object]``: what a key holds is the
    author's business until something checks it. The loader below reads a dozen
    sub-tables and hands each entry to a field checker that names the field it
    refuses, so the narrowing is stated once here rather than at each read, and
    the sub-table's own values stay open because its keys are the author's.

    It checks nothing on purpose: a key holding something other than a table
    reaches the same field checker it always did, and is refused there by name.
    """

    return cast("Mapping[str, Any]", doc.get(key, {}))


def _motion_states(rows: object, *, actor_id: str) -> tuple[MotionState, ...]:
    if not isinstance(rows, list) or not rows:
        raise SourceError(f"actor {actor_id} declares no states")
    states: list[MotionState] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise SourceError(f"actor {actor_id} state must be a table")
        state = _identifier(row.get("state"), field=f"{actor_id}.state")
        if state in seen:
            raise SourceError(f"actor {actor_id} repeats state {state!r}")
        seen.add(state)
        mode = _text(row.get("mode"), field=f"{actor_id}.{state}.mode")
        if mode not in MOTION_MODES:
            raise SourceError(f"{actor_id}.{state}.mode must be one of {sorted(MOTION_MODES)}")
        fps = _number(row.get("fps"), field=f"{actor_id}.{state}.fps", low=1.0, high=30.0)
        if mode == "hold" and fps:
            pass
        states.append(
            MotionState(
                state=state,
                mode=mode,  # type: ignore[arg-type]
                fps=fps,
                direction=_text(row.get("direction"), field=f"{actor_id}.{state}.direction"),
            )
        )
    return tuple(states)


def _actor(
    block: object,
    *,
    role: Literal["player", "mob"],
    key: str,
    root: Path,
    digests: DigestLedger,
    biome_ids: Sequence[str] = (),
) -> Actor:
    if not isinstance(block, dict):
        raise SourceError(f"[{key}] must be a table")
    actor_id = _identifier(block.get("actor_id"), field=f"{key}.actor_id")
    if role == "player" and "placement" in block:
        raise SourceError("the player is not scattered; it spawns on the spawn set piece")
    placement = (
        _placement(block.get("placement"), field=f"{key}.placement", biome_ids=biome_ids)
        if role == "mob"
        else None
    )
    height = (
        1.0
        if role == "player"
        else _number(block.get("height_units"), field=f"{key}.height_units", low=0.1, high=8.0)
    )
    if role == "player" and "height_units" in block:
        raise SourceError("the player is the scale unit and must not declare height_units")
    states = _motion_states(block.get("states"), actor_id=actor_id)
    baseline = _identifier(block.get("baseline_state", "idle"), field=f"{key}.baseline_state")
    if baseline not in {entry.state for entry in states}:
        raise SourceError(f"{key}.baseline_state {baseline!r} is not one of its states")
    facings = _facings(block.get("facings"), role=role, key=key)
    appearance, appearance_digest = _png_reference(
        root,
        block.get("appearance_reference"),
        digests,
        field=f"{key}.appearance_reference",
    )
    return Actor(
        actor_id=actor_id,
        role=role,
        display_name=_text(block.get("display_name"), field=f"{key}.display_name"),
        height_units=height,
        baseline_state=baseline,
        footprint_radius_units=_number(
            block.get("footprint_radius_units"), field=f"{key}.footprint", low=0.0, high=3.0
        ),
        shadow_width_units=_number(
            block.get("shadow_width_units"), field=f"{key}.shadow", low=0.05, high=6.0
        ),
        concept_prompt=_text(block.get("concept_prompt"), field=f"{key}.concept_prompt"),
        states=states,
        facings=facings,
        appearance_reference=appearance,
        appearance_reference_digest=appearance_digest,
        placement=placement,
    )


def _facings(block: object, *, role: Literal["player", "mob"], key: str) -> FacingSet:
    """The facing set. The player always carries four; a mob defaults to one mirrored card."""

    if block is None:
        block = {"set": "four_way" if role == "player" else "single_mirrored"}
    if not isinstance(block, dict):
        raise SourceError(f"[{key}.facings] must be a table")
    chosen = _text(block.get("set", "single_mirrored"), field=f"{key}.facings.set")
    if chosen not in FACING_SETS:
        raise SourceError(f"{key}.facings.set must be one of {list(FACING_SETS)}, got {chosen!r}")
    if role == "player" and chosen != "four_way":
        raise SourceError(
            "the player always carries the four_way facing set (front, back, left, right); "
            "single_mirrored is for actors that need less detail"
        )
    side_view = _text(block.get("side_view", "quarter"), field=f"{key}.facings.side_view")
    if side_view not in SIDE_VIEWS:
        raise SourceError(
            f"{key}.facings.side_view must be one of {list(SIDE_VIEWS)}, got {side_view!r}"
        )
    return FacingSet(set=chosen, side_view=side_view)


def _interactions(rows: object, *, prop_id: str, states: Sequence[str]) -> tuple[Interaction, ...]:
    """``[[props.interactions]]``: each says what it does and the states it does it from."""

    if rows is None:
        return ()
    if not isinstance(rows, list):
        raise SourceError(f"{prop_id}.interactions must be a list of [[props.interactions]] tables")
    out: list[Interaction] = []
    for index, row in enumerate(rows):
        out.append(_interaction(row, field=f"{prop_id}.interactions[{index}]", states=states))
    offered: dict[tuple[str, str], int] = {}
    for index, interaction in enumerate(out):
        for state in interaction.from_states:
            key = (state, interaction.verb)
            if key in offered:
                raise SourceError(
                    f"{prop_id}.interactions[{index}] and [{offered[key]}] both {interaction.verb} "
                    f"from {state!r}; one verb per state, or the key could not choose"
                )
            offered[key] = index
    return tuple(out)


def _interaction(block: object, *, field: str, states: Sequence[str]) -> Interaction:
    if not isinstance(block, dict):
        raise SourceError(f"{field} must be a table")
    prop_id = field
    next_state = _identifier(block.get("next_state"), field=f"{prop_id}.next_state")
    if next_state not in states:
        raise SourceError(f"{prop_id}.next_state {next_state!r} is not a declared state")
    rows = block.get("yields", [])
    if not isinstance(rows, list):
        raise SourceError(f"{prop_id}.yields must be a list")
    yields: list[Yield] = []
    for row in rows:
        if not isinstance(row, dict):
            raise SourceError(f"{prop_id}.yields[] must be a table")
        count = row.get("count")
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 99:
            raise SourceError(f"{prop_id} yield count must be an integer within [1, 99]")
        yields.append(
            Yield(item_id=_identifier(row.get("item_id"), field=f"{prop_id}.yield"), count=count)
        )
    hits = block.get("hits", 1)
    if not isinstance(hits, int) or isinstance(hits, bool) or not 1 <= hits <= 20:
        raise SourceError(f"{prop_id}.hits must be an integer within [1, 20]")
    raw_progress = block.get("progress", [])
    if not isinstance(raw_progress, list):
        raise SourceError(f"{prop_id}.progress must be a list of states")
    progress = tuple(_identifier(s, field=f"{prop_id}.progress[]") for s in raw_progress)
    for look in progress:
        if look not in states:
            raise SourceError(f"{prop_id}.progress names undeclared state {look!r}")
    if len(set(progress)) != len(progress):
        raise SourceError(f"{prop_id}.progress repeats a state")
    if next_state in progress:
        raise SourceError(f"{prop_id}.progress may not contain next_state {next_state!r}")
    if len(progress) > hits - 1:
        raise SourceError(
            f"{prop_id}.progress lists {len(progress)} looks but only {hits - 1} hits "
            "come before the last one"
        )
    raw_from = block.get("from")
    if raw_from is None:
        raise SourceError(
            f"{prop_id} must say the states it applies from: "
            "from = [...] (one or more declared states)"
        )
    if not isinstance(raw_from, list) or not raw_from:
        raise SourceError(f"{prop_id}.from must be a non-empty list of declared states")
    from_states = tuple(_identifier(s, field=f"{prop_id}.from[]") for s in raw_from)
    for state in from_states:
        if state not in states:
            raise SourceError(f"{prop_id}.from names undeclared state {state!r}")
    if len(set(from_states)) != len(from_states):
        raise SourceError(f"{prop_id}.from repeats a state")
    for look in progress:
        if look not in from_states:
            raise SourceError(
                f"{prop_id}.progress look {look!r} is not in from; the interaction could not "
                "go on from it"
            )
    regrow = block.get("regrow_seconds")
    verb = _identifier(block.get("verb"), field=f"{prop_id}.verb")
    if verb not in INTERACTION_VERBS:
        raise SourceError(f"{prop_id}.verb must be one of {list(INTERACTION_VERBS)}, got {verb!r}")
    raw_yield_to = block.get("yield_to")
    if yields:
        if raw_yield_to is None:
            raise SourceError(
                f"{prop_id} yields something and must say where it goes: "
                f"yield_to = {' | '.join(repr(d) for d in YIELD_DESTINATIONS)}"
            )
        yield_to = _text(raw_yield_to, field=f"{prop_id}.yield_to")
        if yield_to not in YIELD_DESTINATIONS:
            raise SourceError(
                f"{prop_id}.yield_to must be one of {list(YIELD_DESTINATIONS)}, got {yield_to!r}"
            )
    elif raw_yield_to is not None:
        raise SourceError(f"{prop_id} yields nothing; yield_to has no meaning")
    else:
        yield_to = "ground"
    raw_tool = block.get("tool")
    tool: ToolSpec | None = None
    if raw_tool is not None:
        if not isinstance(raw_tool, dict):
            raise SourceError(f"{prop_id}.tool must be a table of item_id, hits, required")
        unknown = sorted(set(raw_tool) - {"item_id", "hits", "required"})
        if unknown:
            raise SourceError(f"{prop_id}.tool has unknown keys {unknown}")
        tool_hits = raw_tool.get("hits", hits)
        if (
            not isinstance(tool_hits, int)
            or isinstance(tool_hits, bool)
            or not 1 <= tool_hits <= 20
        ):
            raise SourceError(f"{prop_id}.tool.hits must be an integer within [1, 20]")
        required = raw_tool.get("required", False)
        if not isinstance(required, bool):
            raise SourceError(f"{prop_id}.tool.required must be a boolean")
        tool = ToolSpec(
            item_id=_identifier(raw_tool.get("item_id"), field=f"{prop_id}.tool.item_id"),
            hits=tool_hits,
            required=required,
        )
    return Interaction(
        verb=verb,
        from_states=from_states,
        hits=hits,
        next_state=next_state,
        fx=_identifier(block.get("fx", "dust"), field=f"{prop_id}.fx"),
        yields=tuple(yields),
        regrow_seconds=(
            None
            if regrow is None
            else _number(regrow, field=f"{prop_id}.regrow_seconds", low=1.0, high=600.0)
        ),
        yield_to=yield_to,
        progress=progress,
        tool=tool,
    )


def _sheet(raw: object, *, prop_id: str, states: Sequence[str]) -> SheetSpec | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise SourceError(f"{prop_id}.sheet must be a table with columns and rows")
    columns = raw.get("columns")
    rows = raw.get("rows")
    if (
        not isinstance(columns, int)
        or not isinstance(rows, int)
        or isinstance(columns, bool)
        or isinstance(rows, bool)
    ):
        raise SourceError(f"{prop_id}.sheet columns and rows must be integers")
    if (columns, rows) not in SHEET_SHAPES:
        raise SourceError(
            f"{prop_id}.sheet {columns}x{rows} is not a lattice the provider's canvases hold; "
            f"choose one of {['x'.join(map(str, shape)) for shape in SHEET_SHAPES]}"
        )
    if columns * rows != len(states):
        raise SourceError(
            f"{prop_id}.sheet has {columns * rows} cells but {len(states)} states are declared; "
            "a sheet holds exactly one look per cell (add a look, or draw sprites)"
        )
    return SheetSpec(columns=columns, rows=rows)


def _variants(raw: object, *, prop_id: str, states: Sequence[str]) -> VariantSpec | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise SourceError(f"{prop_id}.variants must be a table with states and weights")
    names = raw.get("states")
    weights = raw.get("weights")
    if not isinstance(names, list) or not names:
        raise SourceError(f"{prop_id}.variants.states must be a non-empty list")
    looks = tuple(_identifier(s, field=f"{prop_id}.variants.states[]") for s in names)
    for look in looks:
        if look not in states:
            raise SourceError(f"{prop_id}.variants names undeclared state {look!r}")
    if len(set(looks)) != len(looks):
        raise SourceError(f"{prop_id}.variants repeats a state")
    if weights is None:
        weights = [1.0] * len(looks)
    if not isinstance(weights, list) or len(weights) != len(looks):
        raise SourceError(f"{prop_id}.variants.weights must list one weight per state")
    parsed = tuple(
        _number(weight, field=f"{prop_id}.variants.weights[]", low=1e-6, high=1000.0)
        for weight in weights
    )
    return VariantSpec(states=looks, weights=parsed)


def _props(
    rows: object, *, minimum_height_units: float, biome_ids: Sequence[str]
) -> tuple[Prop, ...]:
    if not isinstance(rows, list) or not rows:
        raise SourceError("props.toml declares no props")
    props: list[Prop] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise SourceError("[[props]] entry must be a table")
        prop_id = _identifier(row.get("prop_id"), field="prop_id")
        if prop_id in seen:
            raise SourceError(f"props.toml repeats prop_id {prop_id!r}")
        seen.add(prop_id)
        states = tuple(_identifier(s, field=f"{prop_id}.states[]") for s in row.get("states", []))
        if not states:
            raise SourceError(f"{prop_id} declares no states")
        if len(set(states)) != len(states):
            raise SourceError(f"{prop_id} repeats a state")
        for reserved in RESERVED_STATE_NAMES:
            if reserved in states:
                raise SourceError(
                    f"{prop_id} may not call a state {reserved!r}; the name is reserved"
                )
        baseline_state = _identifier(
            row.get("baseline_state", states[0]), field=f"{prop_id}.baseline_state"
        )
        if baseline_state not in states:
            raise SourceError(
                f"{prop_id}.baseline_state {baseline_state!r} is not a declared state"
            )
        state_prompt_raw = row.get("state_prompt", {})
        if not isinstance(state_prompt_raw, dict):
            raise SourceError(f"{prop_id}.state_prompt must be a table")
        unknown = set(state_prompt_raw) - set(states)
        if unknown:
            raise SourceError(f"{prop_id}.state_prompt names undeclared states: {sorted(unknown)}")
        state_prompt = {
            str(key): " ".join(str(value).split()) for key, value in state_prompt_raw.items()
        }
        season_raw = row.get("season_prompt", {})
        if not isinstance(season_raw, dict):
            raise SourceError(
                f"{prop_id}.season_prompt must be a table of look = {{ state = brief }}"
            )
        season_prompt: dict[str, dict[str, str]] = {}
        for look_raw, table in season_raw.items():
            look = _identifier(look_raw, field=f"{prop_id}.season_prompt key")
            if not isinstance(table, dict):
                raise SourceError(
                    f"{prop_id}.season_prompt.{look} must be a table of state = brief"
                )
            unknown = set(table) - set(states)
            if unknown:
                raise SourceError(
                    f"{prop_id}.season_prompt.{look} names undeclared states: {sorted(unknown)}"
                )
            season_prompt[look] = {
                str(key): " ".join(str(value).split()) for key, value in table.items()
            }
        height = _number(
            row.get("height_units"), field=f"{prop_id}.height_units", low=0.01, high=20.0
        )
        if height < minimum_height_units:
            raise SourceError(
                f"{prop_id}.height_units {height} is under the package "
                f"minimum {minimum_height_units}"
            )
        edge = _text(row.get("edge", "hard"), field=f"{prop_id}.edge")
        if edge not in EDGE_KINDS:
            raise SourceError(f"{prop_id}.edge must be one of {sorted(EDGE_KINDS)}")
        hint = _text(row.get("motion_hint", "none"), field=f"{prop_id}.motion_hint")
        if hint not in MOTION_HINTS:
            raise SourceError(f"{prop_id}.motion_hint must be one of {sorted(MOTION_HINTS)}")
        if "hit_reaction" not in row:
            raise SourceError(
                f"{prop_id}.hit_reaction is required: one of {sorted(HIT_REACTIONS)}, "
                "whether the card rocks under a blow or holds still"
            )
        reaction = _text(row.get("hit_reaction"), field=f"{prop_id}.hit_reaction")
        if reaction not in HIT_REACTIONS:
            raise SourceError(f"{prop_id}.hit_reaction must be one of {sorted(HIT_REACTIONS)}")
        components = row.get("max_components", 1)
        if (
            not isinstance(components, int)
            or isinstance(components, bool)
            or not 1 <= components <= 8
        ):
            raise SourceError(f"{prop_id}.max_components must be an integer within [1, 8]")
        for moved in ("density_share", "biome_weights"):
            if moved in row:
                raise SourceError(
                    f"{prop_id}.{moved} is not authored any more; where and how a prop "
                    "stands is its [props.placement] block"
                )
        if "interaction" in row:
            raise SourceError(
                f"{prop_id}.interaction is not authored any more; list what can be done to it as "
                "[[props.interactions]] tables, each with the states it applies `from`"
            )
        interactions = _interactions(row.get("interactions"), prop_id=prop_id, states=states)
        variants = _variants(row.get("variants"), prop_id=prop_id, states=states)
        raw_looks = row.get("look_height_units", {})
        if not isinstance(raw_looks, dict):
            raise SourceError(f"{prop_id}.look_height_units must be a table of state = units")
        look_height_units: dict[str, float] = {}
        for look, value in raw_looks.items():
            if look not in states:
                raise SourceError(f"{prop_id}.look_height_units names undeclared state {look!r}")
            if look == baseline_state:
                raise SourceError(
                    f"{prop_id}.look_height_units may not size the baseline look {look!r}; "
                    "height_units already does, and two authorities for one size is the defect"
                )
            look_height_units[str(look)] = _number(
                value, field=f"{prop_id}.look_height_units.{look}", low=0.01, high=20.0
            )
        for interaction in interactions:
            if baseline_state in interaction.progress:
                raise SourceError(
                    f"{prop_id}.interactions.progress may not contain the baseline state"
                )
            if variants is not None:
                outcomes = {interaction.next_state, *interaction.progress}
                clash = [look for look in variants.states if look in outcomes]
                if clash:
                    raise SourceError(
                        f"{prop_id}.variants {clash} are outcomes of its interaction; a placed "
                        "instance may not start already spent"
                    )
        props.append(
            Prop(
                prop_id=prop_id,
                family=_identifier(row.get("family"), field=f"{prop_id}.family"),
                height_units=height,
                footprint_radius_units=_number(
                    row.get("footprint_radius_units"),
                    field=f"{prop_id}.footprint",
                    low=0.0,
                    high=5.0,
                ),
                shadow_width_units=_number(
                    row.get("shadow_width_units"), field=f"{prop_id}.shadow", low=0.05, high=8.0
                ),
                edge=edge,  # type: ignore[arg-type]
                motion_hint=hint,
                hit_reaction=reaction,
                max_components=components,
                prompt=_text(row.get("prompt"), field=f"{prop_id}.prompt"),
                states=states,
                state_prompt=state_prompt,
                interactions=interactions,
                baseline_state=baseline_state,
                look_height_units=look_height_units,
                placement=_placement(
                    row.get("placement"), field=f"{prop_id}.placement", biome_ids=biome_ids
                ),
                canopy_radius_meters=_number(
                    row.get("canopy_radius_meters", 0.0),
                    field=f"{prop_id}.canopy_radius_meters",
                    low=0.0,
                    high=32.0,
                ),
                sheet=_sheet(row.get("sheet"), prop_id=prop_id, states=states),
                variants=variants,
                season_prompt=season_prompt,
            )
        )
    return tuple(props)


PLACEMENT_KEYS: Final = frozenset(
    {
        "habitat",
        "density_per_100m2",
        "cluster",
        "spacing_meters",
        "near",
        "edge",
        "height",
        "chance",
        "min_per_world",
        "max_per_world",
        "avoid",
        "clearing_radius_meters",
    }
)


def _count(value: object, *, field: str, low: int, high: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise SourceError(f"{field} must be an integer within [{low}, {high}]")
    return value


def _placement(
    raw: object,
    *,
    field: str,
    biome_ids: Sequence[str],
    default_habitat: Mapping[str, float] | None = None,
) -> Placement | None:
    """One object's placement block. Shape only: what a ``near`` or ``avoid``
    names is resolved once every object is known (``_check_placement``)."""

    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise SourceError(f"{field} must be a table")
    unknown = sorted(set(raw) - PLACEMENT_KEYS)
    if unknown:
        raise SourceError(f"{field} has unknown keys {unknown}")
    habitat_raw = raw.get("habitat", default_habitat)
    if habitat_raw is None:
        raise SourceError(f"{field}.habitat is required: a table of biome_id = weight")
    if not isinstance(habitat_raw, Mapping):
        raise SourceError(f"{field}.habitat must be a table keyed by biome_id")
    habitat: dict[str, float] = {}
    for biome_id, weight in habitat_raw.items():
        if biome_id not in biome_ids:
            raise SourceError(f"{field}.habitat names unknown biome {biome_id!r}")
        habitat[str(biome_id)] = _number(
            weight, field=f"{field}.habitat.{biome_id}", low=0.0, high=1.0
        )
    if not any(weight > 0.0 for weight in habitat.values()):
        raise SourceError(f"{field}.habitat gives every biome weight 0")
    density = (
        _number(raw["density_per_100m2"], field=f"{field}.density_per_100m2", low=0.0, high=400.0)
        if "density_per_100m2" in raw
        else None
    )
    cluster = None
    if "cluster" in raw:
        block = raw["cluster"]
        if not isinstance(block, dict):
            raise SourceError(f"{field}.cluster must be a table")
        unknown = sorted(set(block) - {"parents_per_100m2", "mean_size", "radius_meters"})
        if unknown:
            raise SourceError(f"{field}.cluster has unknown keys {unknown}")
        cluster = ClusterRule(
            parents_per_100m2=_number(
                block.get("parents_per_100m2"),
                field=f"{field}.cluster.parents_per_100m2",
                low=0.0,
                high=100.0,
            ),
            mean_size=_number(
                block.get("mean_size"), field=f"{field}.cluster.mean_size", low=1.0, high=64.0
            ),
            radius_meters=_number(
                block.get("radius_meters"),
                field=f"{field}.cluster.radius_meters",
                low=0.5,
                high=64.0,
            ),
        )
    spacing = (
        _number(raw["spacing_meters"], field=f"{field}.spacing_meters", low=0.5, high=64.0)
        if "spacing_meters" in raw
        else None
    )
    near = None
    if "near" in raw:
        block = raw["near"]
        if not isinstance(block, dict):
            raise SourceError(f"{field}.near must be a table")
        unknown = sorted(set(block) - {"host", "radius_meters", "mean", "chance"})
        if unknown:
            raise SourceError(f"{field}.near has unknown keys {unknown}")
        near = NearRule(
            host=_identifier(block.get("host"), field=f"{field}.near.host"),
            radius_meters=_number(
                block.get("radius_meters"), field=f"{field}.near.radius_meters", low=0.2, high=32.0
            ),
            mean=_number(block.get("mean"), field=f"{field}.near.mean", low=0.01, high=64.0),
            chance=_number(
                block.get("chance", 1.0), field=f"{field}.near.chance", low=0.0, high=1.0
            ),
        )
        if near.chance <= 0.0:
            raise SourceError(f"{field}.near.chance must be above 0")
    processes = [
        name
        for name, present in (
            ("density_per_100m2", density is not None),
            ("cluster", cluster is not None),
            ("near", near is not None),
        )
        if present
    ]
    if len(processes) > 1:
        raise SourceError(f"{field} declares more than one process: {processes}")
    if not processes and spacing is None:
        raise SourceError(
            f"{field} declares no process: one of density_per_100m2, cluster, near, "
            "or spacing_meters alone"
        )
    edge = None
    if "edge" in raw:
        block = raw["edge"]
        if not isinstance(block, dict):
            raise SourceError(f"{field}.edge must be a table")
        unknown = sorted(set(block) - {"of", "within_meters", "falloff_meters", "outside"})
        if unknown:
            raise SourceError(f"{field}.edge has unknown keys {unknown}")
        of = _text(block.get("of"), field=f"{field}.edge.of")
        if of not in EDGE_FIELDS:
            raise SourceError(f"{field}.edge.of must be one of {list(EDGE_FIELDS)}")
        edge = EdgePreference(
            of=of,
            within_meters=_number(
                block.get("within_meters"), field=f"{field}.edge.within_meters", low=0.0, high=256.0
            ),
            falloff_meters=_number(
                block.get("falloff_meters", 0.0),
                field=f"{field}.edge.falloff_meters",
                low=0.0,
                high=256.0,
            ),
            outside=_number(
                block.get("outside", 0.0), field=f"{field}.edge.outside", low=0.0, high=1.0
            ),
        )
    height = None
    if "height" in raw:
        block = raw["height"]
        if not isinstance(block, dict):
            raise SourceError(f"{field}.height must be a table")
        unknown = sorted(set(block) - {"min", "max", "falloff"})
        if unknown:
            raise SourceError(f"{field}.height has unknown keys {unknown}")
        low = _number(block.get("min", 0.0), field=f"{field}.height.min", low=0.0, high=1.0)
        high = _number(block.get("max", 1.0), field=f"{field}.height.max", low=0.0, high=1.0)
        if high < low:
            raise SourceError(f"{field}.height.max is below min")
        height = HeightPreference(
            min=low,
            max=high,
            falloff=_number(
                block.get("falloff", 0.05), field=f"{field}.height.falloff", low=0.0, high=1.0
            ),
        )
    chance = _number(raw.get("chance", 1.0), field=f"{field}.chance", low=0.0, high=1.0)
    if chance <= 0.0:
        raise SourceError(f"{field}.chance must be above 0; leave the object out instead")
    minimum = _count(
        raw.get("min_per_world", 0), field=f"{field}.min_per_world", low=0, high=100_000
    )
    maximum = (
        _count(raw["max_per_world"], field=f"{field}.max_per_world", low=0, high=100_000)
        if "max_per_world" in raw
        else None
    )
    if maximum is not None and maximum < minimum:
        raise SourceError(f"{field}.max_per_world {maximum} is below min_per_world {minimum}")
    avoid_raw = raw.get("avoid", [])
    if not isinstance(avoid_raw, list):
        raise SourceError(f"{field}.avoid must be a list of {{ target, radius_meters }}")
    avoid: list[AvoidRule] = []
    for index, rule in enumerate(avoid_raw):
        if not isinstance(rule, dict):
            raise SourceError(f"{field}.avoid[{index}] must be a table")
        unknown = sorted(set(rule) - {"target", "radius_meters"})
        if unknown:
            raise SourceError(f"{field}.avoid[{index}] has unknown keys {unknown}")
        avoid.append(
            AvoidRule(
                target=_identifier(rule.get("target"), field=f"{field}.avoid[{index}].target"),
                radius_meters=_number(
                    rule.get("radius_meters"),
                    field=f"{field}.avoid[{index}].radius_meters",
                    low=0.1,
                    high=256.0,
                ),
            )
        )
    return Placement(
        habitat=habitat,
        density_per_100m2=density,
        cluster=cluster,
        spacing_meters=spacing,
        near=near,
        edge=edge,
        height=height,
        chance=chance,
        min_per_world=minimum,
        max_per_world=maximum,
        avoid=tuple(avoid),
        clearing_radius_meters=_number(
            raw.get("clearing_radius_meters", 0.0),
            field=f"{field}.clearing_radius_meters",
            low=0.0,
            high=64.0,
        ),
    )


WORLD_KEYS: Final = frozenset(
    {
        "schema_version",
        "kind",
        "package_id",
        "world",
        "landmass",
        "biomes",
        "spawn",
        "set_pieces",
        "population",
    }
)
SET_PIECE_KEYS: Final = frozenset(
    {
        "set_piece_id",
        "count",
        "at",
        "biome",
        "clearing_radius_meters",
        "pad_decal",
        "spawn",
        "members",
    }
)


def _world(doc: Mapping[str, object], *, biome_ids: Sequence[str]) -> World:
    """world.toml. Refuses offline a world no generator could lay: two origins,
    a spawn on nothing, a band inside out, an unknown biome."""

    if doc.get("kind") != WORLD_KIND:
        raise SourceError(f"world.toml kind must be {WORLD_KIND}")
    unknown = sorted(set(doc) - WORLD_KEYS)
    if unknown:
        raise SourceError(f"world.toml has unknown keys {unknown}")
    world = doc.get("world")
    if not isinstance(world, dict):
        raise SourceError("world.toml must declare a [world] table")
    unknown = sorted(set(world) - {"seed", "size_meters"})
    if unknown:
        raise SourceError(f"world.toml [world] has unknown keys {unknown}")
    seed = _count(world.get("seed", 1), field="world.seed", low=0, high=2**31 - 1)
    size = _number(world.get("size_meters"), field="world.size_meters", low=64.0, high=1024.0)
    landmass_raw = doc.get("landmass", {})
    if not isinstance(landmass_raw, dict):
        raise SourceError("world.toml [landmass] must be a table")
    unknown = sorted(
        set(landmass_raw)
        - {
            "land_share",
            "coast_noise_lattice",
            "coast_crinkle",
            "shore_margin_meters",
            "height_octave_lattice",
            "height_octave_weight",
        }
    )
    if unknown:
        raise SourceError(f"world.toml [landmass] has unknown keys {unknown}")
    landmass = Landmass(
        land_share=_number(
            landmass_raw.get("land_share", 0.6), field="landmass.land_share", low=0.2, high=1.0
        ),
        coast_noise_lattice=_count(
            landmass_raw.get("coast_noise_lattice", 6),
            field="landmass.coast_noise_lattice",
            low=2,
            high=32,
        ),
        coast_crinkle=_number(
            landmass_raw.get("coast_crinkle", 0.3),
            field="landmass.coast_crinkle",
            low=0.0,
            high=1.0,
        ),
        shore_margin_meters=_number(
            landmass_raw.get("shore_margin_meters", 2.0),
            field="landmass.shore_margin_meters",
            low=0.0,
            high=20.0,
        ),
        height_octave_lattice=_count(
            landmass_raw.get("height_octave_lattice", 24),
            field="landmass.height_octave_lattice",
            low=0,
            high=128,
        ),
        height_octave_weight=_number(
            landmass_raw.get("height_octave_weight", 0.25),
            field="landmass.height_octave_weight",
            low=0.0,
            high=1.0,
        ),
    )
    biomes_raw = doc.get("biomes", {})
    if not isinstance(biomes_raw, dict):
        raise SourceError("world.toml [biomes] must be a table")
    unknown = sorted(set(biomes_raw) - {"islet_lattice", "islet_share"})
    if unknown:
        raise SourceError(f"world.toml [biomes] has unknown keys {unknown}")
    rules = BiomeRules(
        islet_lattice=_count(
            biomes_raw.get("islet_lattice", 0), field="biomes.islet_lattice", low=0, high=128
        ),
        islet_share=_number(
            biomes_raw.get("islet_share", 0.0), field="biomes.islet_share", low=0.0, high=0.9
        ),
    )
    spawn_raw = doc.get("spawn")
    if not isinstance(spawn_raw, dict) or set(spawn_raw) != {"set_piece"}:
        raise SourceError("world.toml must declare [spawn] with set_piece = <set_piece_id>")
    spawn_id = _identifier(spawn_raw.get("set_piece"), field="spawn.set_piece")
    rows = doc.get("set_pieces", [])
    if not isinstance(rows, list) or not rows:
        raise SourceError("world.toml must declare at least one [[set_pieces]] entry")
    pieces: list[SetPiece] = []
    for row in rows:
        if not isinstance(row, dict):
            raise SourceError("[[set_pieces]] entry must be a table")
        piece_id = _identifier(row.get("set_piece_id"), field="set_pieces[].set_piece_id")
        if any(entry.set_piece_id == piece_id for entry in pieces):
            raise SourceError(f"world.toml repeats set piece {piece_id!r}")
        field_name = f"set_pieces.{piece_id}"
        unknown = sorted(set(row) - SET_PIECE_KEYS)
        if unknown:
            raise SourceError(f"{field_name} has unknown keys {unknown}")
        at_raw = row.get("at")
        at: Literal["origin", "band"]
        band = (0.0, 0.0)
        if at_raw == "origin":
            at = "origin"
        elif isinstance(at_raw, dict) and set(at_raw) == {"distance_meters"}:
            at = "band"
            limits = at_raw["distance_meters"]
            if (
                not isinstance(limits, list)
                or len(limits) != 2
                or any(isinstance(v, bool) or not isinstance(v, int | float) for v in limits)
            ):
                raise SourceError(f"{field_name}.at.distance_meters must be [near, far]")
            near_m, far_m = float(limits[0]), float(limits[1])
            if not 0.0 <= near_m < far_m <= size:
                raise SourceError(
                    f"{field_name}.at.distance_meters must satisfy 0 <= near < far <= size_meters"
                )
            band = (near_m, far_m)
        else:
            raise SourceError(
                f'{field_name}.at must be "origin" or {{ distance_meters = [near, far] }}'
            )
        biome = row.get("biome")
        if biome is not None:
            biome = _identifier(biome, field=f"{field_name}.biome")
            if biome not in biome_ids:
                raise SourceError(f"{field_name}.biome names unknown biome {biome!r}")
        spawn_offset: tuple[float, float] | None = None
        if "spawn" in row:
            offset = row["spawn"]
            if not isinstance(offset, dict) or set(offset) != {"dx", "dz"}:
                raise SourceError(f"{field_name}.spawn must be {{ dx, dz }}")
            spawn_offset = (
                _number(offset["dx"], field=f"{field_name}.spawn.dx", low=-64.0, high=64.0),
                _number(offset["dz"], field=f"{field_name}.spawn.dz", low=-64.0, high=64.0),
            )
        members_raw = row.get("members")
        if not isinstance(members_raw, list) or not members_raw:
            raise SourceError(f"{field_name}.members must list at least one member")
        members: list[SetPieceMember] = []
        for index, member in enumerate(members_raw):
            if not isinstance(member, dict):
                raise SourceError(f"{field_name}.members[{index}] must be a table")
            unknown = sorted(set(member) - {"prop", "state", "dx", "dz", "pad_scale"})
            if unknown:
                raise SourceError(f"{field_name}.members[{index}] has unknown keys {unknown}")
            members.append(
                SetPieceMember(
                    prop=_identifier(
                        member.get("prop"), field=f"{field_name}.members[{index}].prop"
                    ),
                    state=(
                        _identifier(member["state"], field=f"{field_name}.members[{index}].state")
                        if "state" in member
                        else ""
                    ),
                    dx=_number(
                        member.get("dx"),
                        field=f"{field_name}.members[{index}].dx",
                        low=-64.0,
                        high=64.0,
                    ),
                    dz=_number(
                        member.get("dz"),
                        field=f"{field_name}.members[{index}].dz",
                        low=-64.0,
                        high=64.0,
                    ),
                    pad_scale=(
                        _number(
                            member["pad_scale"],
                            field=f"{field_name}.members[{index}].pad_scale",
                            low=0.1,
                            high=8.0,
                        )
                        if "pad_scale" in member
                        else None
                    ),
                )
            )
        pad_decal = row.get("pad_decal")
        if pad_decal is not None:
            pad_decal = _identifier(pad_decal, field=f"{field_name}.pad_decal")
        pieces.append(
            SetPiece(
                set_piece_id=piece_id,
                count=_count(row.get("count", 1), field=f"{field_name}.count", low=1, high=64),
                at=at,
                band_meters=band,
                biome=biome,
                clearing_radius_meters=_number(
                    row.get("clearing_radius_meters", 0.0),
                    field=f"{field_name}.clearing_radius_meters",
                    low=0.0,
                    high=64.0,
                ),
                pad_decal=pad_decal,
                spawn=spawn_offset,
                members=tuple(members),
            )
        )
    origins = [piece for piece in pieces if piece.at == "origin"]
    if len(origins) != 1:
        raise SourceError('world.toml must place exactly one set piece at = "origin"')
    if origins[0].count != 1:
        raise SourceError(f"the origin set piece {origins[0].set_piece_id!r} must have count 1")
    if origins[0].set_piece_id != spawn_id:
        raise SourceError(
            f"spawn.set_piece must name the origin set piece {origins[0].set_piece_id!r}"
        )
    if origins[0].spawn is None:
        raise SourceError(f"the spawn set piece {spawn_id!r} must declare spawn = {{ dx, dz }}")
    population = doc.get("population", {})
    if not isinstance(population, dict):
        raise SourceError("world.toml [population] must be a table")
    unknown = sorted(set(population) - {"order"})
    if unknown:
        raise SourceError(f"world.toml [population] has unknown keys {unknown}")
    order = _identifiers(population.get("order", []), field="population.order")
    return World(
        seed=seed,
        size_meters=size,
        landmass=landmass,
        biomes=rules,
        spawn_set_piece=spawn_id,
        set_pieces=tuple(pieces),
        population_order=order,
    )


def _object_ids(package: Package) -> set[str]:
    """Every id the population may name: scattered props, the mob, the sheets."""

    ids = {prop.prop_id for prop in package.props if prop.placement is not None}
    # A set piece's members stand in the world too, under their prop id: a
    # hound may keep its distance from the campfire.
    ids.update(member.prop for piece in package.world.set_pieces for member in piece.members)
    if package.mob.placement is not None:
        ids.add(package.mob.actor_id)
    for name, sheet in _sheets(package):
        ids.add(name)
        for index, cell in enumerate(sheet.cells):
            if cell.placement is not None:
                ids.add(f"{name}/{index}")
    return ids


class _PlacedCell(Protocol):
    @property
    def placement(self) -> Placement | None: ...


class _PlacedSheet(Protocol):
    @property
    def placement(self) -> Placement: ...

    @property
    def cells(self) -> Sequence[_PlacedCell]: ...


def _sheets(package: Package) -> list[tuple[str, _PlacedSheet]]:
    """The piece sheets the package has, by the name the population knows them as."""

    out: list[tuple[str, _PlacedSheet]] = []
    if package.clutter is not None:
        out.append(("clutter", package.clutter))
    if package.forage is not None:
        out.append(("forage", package.forage))
    if package.plants is not None:
        out.append(("plants", package.plants))
    return out


def _check_placement(package: Package) -> None:
    """A placement that names what the world does not have is a typo, not a
    preference; a set piece that stands on nothing is a run that would refuse."""

    known = _object_ids(package)
    placements: list[tuple[str, Placement]] = [
        (prop.prop_id, prop.placement) for prop in package.props if prop.placement is not None
    ]
    if package.mob.placement is not None:
        placements.append((package.mob.actor_id, package.mob.placement))
    for name, sheet in _sheets(package):
        placements.append((name, sheet.placement))
        for index, cell in enumerate(sheet.cells):
            if cell.placement is not None:
                placements.append((f"{name}/{index}", cell.placement))
    for name, placement in placements:
        if placement.near is not None:
            if placement.near.host not in known:
                raise SourceError(
                    f"{name}.placement.near.host names unknown object {placement.near.host!r}"
                )
            if placement.near.host == name:
                raise SourceError(f"{name}.placement.near.host names itself")
        for rule in placement.avoid:
            if rule.target not in known:
                raise SourceError(f"{name}.placement.avoid names unknown object {rule.target!r}")
    for object_id in package.world.population_order:
        if object_id not in known:
            raise SourceError(f"population.order names unknown object {object_id!r}")
    pads = {decal.decal_id for decal in package.decals if decal.use == "pad"}
    for piece in package.world.set_pieces:
        if piece.pad_decal is not None and piece.pad_decal not in pads:
            raise SourceError(
                f"set_pieces.{piece.set_piece_id}.pad_decal {piece.pad_decal!r} is not a pad decal"
            )
        for member in piece.members:
            prop = package.prop(member.prop)
            if member.state and member.state not in prop.states:
                raise SourceError(
                    f"set_pieces.{piece.set_piece_id} member {member.prop} "
                    f"has no state {member.state!r}"
                )
            if member.pad_scale is not None and piece.pad_decal is None:
                raise SourceError(
                    f"set_pieces.{piece.set_piece_id} member {member.prop} wants a pad "
                    "but the set piece names no pad_decal"
                )


ITEM_KEYS: Final = frozenset(
    {"item_id", "display_name", "height_units", "prompt", "stack_max", "use", "tool", "icon_brief"}
)
ITEM_USE_KEYS: Final = frozenset(
    {
        "kind",
        "hunger",
        "health",
        "radius_meters",
        "burn_seconds",
        "slots",
        "warmth",
        "insulation",
        "heat_seconds",
    }
)


def _item_use(raw: object, *, item_id: str) -> ItemUse | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise SourceError(f"{item_id}.use must be a table")
    unknown = sorted(set(raw) - ITEM_USE_KEYS)
    if unknown:
        raise SourceError(f"{item_id}.use has unknown keys {unknown}")
    kind = _text(raw.get("kind"), field=f"{item_id}.use.kind")
    if kind not in ITEM_USES:
        raise SourceError(f"{item_id}.use.kind must be one of {list(ITEM_USES)}, got {kind!r}")
    hunger = _number(raw.get("hunger", 0.0), field=f"{item_id}.use.hunger", low=-100.0, high=100.0)
    health = _number(raw.get("health", 0.0), field=f"{item_id}.use.health", low=-100.0, high=100.0)
    radius = _number(
        raw.get("radius_meters", 0.0), field=f"{item_id}.use.radius_meters", low=0.0, high=20.0
    )
    burn = _number(
        raw.get("burn_seconds", 0.0), field=f"{item_id}.use.burn_seconds", low=0.0, high=3600.0
    )
    slots = raw.get("slots", 0)
    if not isinstance(slots, int) or isinstance(slots, bool) or not 0 <= slots <= 32:
        raise SourceError(f"{item_id}.use.slots must be an integer within [0, 32]")
    warmth = _number(raw.get("warmth", 0.0), field=f"{item_id}.use.warmth", low=-100.0, high=100.0)
    insulation = _number(
        raw.get("insulation", 0.0), field=f"{item_id}.use.insulation", low=0.0, high=1.0
    )
    heat = _number(
        raw.get("heat_seconds", 0.0), field=f"{item_id}.use.heat_seconds", low=0.0, high=3600.0
    )
    if kind == "consume" and hunger == 0.0 and health == 0.0 and warmth == 0.0:
        raise SourceError(f"{item_id}.use consumes for nothing: give it hunger, health or warmth")
    if kind == "wear" and insulation <= 0.0:
        raise SourceError(f"{item_id}.use wears for nothing: give it insulation in (0, 1]")
    if kind == "warm" and heat <= 0.0:
        raise SourceError(f"{item_id}.use warms for nothing: give it heat_seconds")
    if kind == "light" and (radius <= 0.0 or burn <= 0.0):
        raise SourceError(f"{item_id}.use lights nothing: give it radius_meters and burn_seconds")
    if kind == "carry" and slots <= 0:
        raise SourceError(f"{item_id}.use carries nothing: give it slots")
    return ItemUse(
        kind=kind,
        hunger=hunger,
        health=health,
        radius_meters=radius,
        burn_seconds=burn,
        slots=slots,
        warmth=warmth,
        insulation=insulation,
        heat_seconds=heat,
    )


def _item_tool(raw: object, *, item_id: str) -> ItemTool | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise SourceError(f"{item_id}.tool must be a table of verb and uses")
    unknown = sorted(set(raw) - {"verb", "uses"})
    if unknown:
        raise SourceError(f"{item_id}.tool has unknown keys {unknown}")
    verb = _identifier(raw.get("verb"), field=f"{item_id}.tool.verb")
    if verb not in INTERACTION_VERBS:
        raise SourceError(
            f"{item_id}.tool.verb must be one of {list(INTERACTION_VERBS)}, got {verb!r}"
        )
    uses = raw.get("uses")
    if not isinstance(uses, int) or isinstance(uses, bool) or not 1 <= uses <= 999:
        raise SourceError(f"{item_id}.tool.uses must be an integer within [1, 999]")
    return ItemTool(verb=verb, uses=uses)


def _items(rows: object) -> tuple[Item, ...]:
    if not isinstance(rows, list) or not rows:
        raise SourceError("items.toml must declare at least one [[items]] entry")
    items: list[Item] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise SourceError("[[items]] entry must be a table")
        item_id = _identifier(row.get("item_id"), field="item_id")
        if item_id in seen:
            raise SourceError(f"items.toml repeats item_id {item_id!r}")
        seen.add(item_id)
        unknown = sorted(set(row) - ITEM_KEYS)
        if unknown:
            raise SourceError(f"items.toml {item_id} has unknown keys {unknown}")
        stack_max = row.get("stack_max", 10)
        if (
            not isinstance(stack_max, int)
            or isinstance(stack_max, bool)
            or not 1 <= stack_max <= 99
        ):
            raise SourceError(f"{item_id}.stack_max must be an integer within [1, 99]")
        tool = _item_tool(row.get("tool"), item_id=item_id)
        if tool is not None and stack_max != 1:
            raise SourceError(f"{item_id} is a tool and wears; a tool's stack_max is 1")
        items.append(
            Item(
                item_id=item_id,
                height_units=_number(
                    row.get("height_units"), field=f"{item_id}.height_units", low=0.01, high=2.0
                ),
                prompt=_text(row.get("prompt"), field=f"{item_id}.prompt"),
                display_name=" ".join(str(row.get("display_name", "")).split()),
                stack_max=stack_max,
                use=_item_use(row.get("use"), item_id=item_id),
                tool=tool,
                icon_brief=" ".join(str(row.get("icon_brief", "")).split()),
            )
        )
    return tuple(items)


def _icons(
    block: object,
    *,
    items: Sequence[Item],
    root: Path | None = None,
    digests: DigestLedger | None = None,
) -> IconSheet:
    if not isinstance(block, dict):
        raise SourceError("items.toml must declare an [icons] table")
    unknown = sorted(
        set(block) - {"columns", "rows", "cell_px", "style_emphasis", "glyphs", "take"}
    )
    if unknown:
        raise SourceError(f"items.toml [icons] has unknown keys {unknown}")
    columns = block.get("columns")
    rows = block.get("rows")
    if (
        not isinstance(columns, int)
        or not isinstance(rows, int)
        or not (2 <= columns <= 8 and 2 <= rows <= 8)
    ):
        raise SourceError("icons columns and rows must be integers within [2, 8]")
    cell_px = block.get("cell_px", 256)
    if not isinstance(cell_px, int) or isinstance(cell_px, bool) or cell_px not in (256, 512):
        raise SourceError("icons.cell_px must be 256 or 512")
    raw_glyphs = block.get("glyphs", [])
    if not isinstance(raw_glyphs, list):
        raise SourceError("icons.glyphs must be a list of { glyph, brief }")
    glyphs: list[IconGlyph] = []
    names = {item.item_id for item in items}
    for index, raw in enumerate(raw_glyphs):
        if not isinstance(raw, dict):
            raise SourceError(f"icons.glyphs[{index}] must be a table")
        glyph = _identifier(raw.get("glyph"), field=f"icons.glyphs[{index}].glyph")
        if glyph in names:
            raise SourceError(
                f"icons.glyphs[{index}] {glyph!r} is an item id; a glyph is not an item"
            )
        names.add(glyph)
        glyphs.append(
            IconGlyph(
                glyph=glyph, brief=_text(raw.get("brief"), field=f"icons.glyphs[{index}].brief")
            )
        )
    if len(items) + len(glyphs) != columns * rows:
        raise SourceError(
            f"icons lattice holds {columns * rows} cells but {len(items)} items "
            f"and {len(glyphs)} glyphs "
            "are declared; every cell is painted, so the counts must match"
        )
    return IconSheet(
        columns=columns,
        rows=rows,
        cell_px=cell_px,
        style_emphasis=" ".join(str(block.get("style_emphasis", "")).split()),
        glyphs=tuple(glyphs),
        take=_take(
            block.get("take"), field="icons.take", root=root, digests=digests, suffix=".png"
        ),
    )


def _counts(raw: object, *, field: str, item_ids: set[str]) -> dict[str, int]:
    if not isinstance(raw, dict):
        raise SourceError(f"{field} must be a table of item_id = count")
    out: dict[str, int] = {}
    for item_id, count in raw.items():
        if item_id not in item_ids:
            raise SourceError(f"{field} names undeclared item {item_id!r}")
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 99:
            raise SourceError(f"{field}.{item_id} must be an integer within [1, 99]")
        out[str(item_id)] = count
    return out


def _crafting(
    doc: Mapping[str, object], *, items: Sequence[Item], props: Sequence[Prop]
) -> Crafting:
    if doc.get("kind") != "oblique-survival-crafting-v2":
        raise SourceError("crafting.toml kind must be oblique-survival-crafting-v2")
    item_ids = {item.item_id for item in items}
    prop_by_id = {prop.prop_id: prop for prop in props}
    inventory = doc.get("inventory", {})
    if not isinstance(inventory, dict):
        raise SourceError("crafting.toml [inventory] must be a table")
    slots = inventory.get("slots", 12)
    if not isinstance(slots, int) or isinstance(slots, bool) or not 1 <= slots <= 40:
        raise SourceError("crafting.toml inventory.slots must be an integer within [1, 40]")
    start_block = doc.get("start", {})
    if not isinstance(start_block, dict):
        raise SourceError("crafting.toml [start] must be a table")
    start = _counts(
        start_block.get("inventory", {}), field="crafting.toml start.inventory", item_ids=item_ids
    )
    raw_stations = doc.get("stations", {})
    if not isinstance(raw_stations, dict):
        raise SourceError("crafting.toml [stations] must be a table keyed by station id")
    stations: list[Station] = []
    for station_id, raw in raw_stations.items():
        if not isinstance(raw, dict):
            raise SourceError(f"crafting.toml stations.{station_id} must be a table")
        unknown = sorted(set(raw) - {"prop_id", "state", "reach_meters"})
        if unknown:
            raise SourceError(f"crafting.toml stations.{station_id} has unknown keys {unknown}")
        if station_id == "hand":
            raise SourceError(
                "crafting.toml may not declare a station called 'hand'; that word means no station"
            )
        prop_id = _identifier(raw.get("prop_id"), field=f"stations.{station_id}.prop_id")
        prop = prop_by_id.get(prop_id)
        if prop is None:
            raise SourceError(
                f"crafting.toml stations.{station_id} names undeclared prop {prop_id!r}"
            )
        state = raw.get("state")
        if state is not None:
            state = _identifier(state, field=f"stations.{station_id}.state")
            if state not in prop.states:
                raise SourceError(
                    f"crafting.toml stations.{station_id} wants {prop_id} "
                    f"in undeclared look {state!r}"
                )
        stations.append(
            Station(
                station_id=_identifier(station_id, field="stations"),
                prop_id=prop_id,
                state=state,
                reach_meters=_number(
                    raw.get("reach_meters", 3.0),
                    field=f"stations.{station_id}.reach_meters",
                    low=0.5,
                    high=20.0,
                ),
            )
        )
    station_ids = {station.station_id for station in stations}
    raw_recipes = doc.get("recipes", [])
    if not isinstance(raw_recipes, list) or not raw_recipes:
        raise SourceError("crafting.toml must declare at least one [[recipes]] entry")
    recipes: list[Recipe] = []
    seen: set[str] = set()
    for raw in raw_recipes:
        if not isinstance(raw, dict):
            raise SourceError("[[recipes]] entry must be a table")
        recipe_id = _identifier(raw.get("recipe_id"), field="recipe_id")
        if recipe_id in seen:
            raise SourceError(f"crafting.toml repeats recipe_id {recipe_id!r}")
        seen.add(recipe_id)
        unknown = sorted(set(raw) - {"recipe_id", "ingredients", "product", "station"})
        if unknown:
            raise SourceError(f"crafting.toml {recipe_id} has unknown keys {unknown}")
        ingredients = _counts(
            raw.get("ingredients"), field=f"{recipe_id}.ingredients", item_ids=item_ids
        )
        if not ingredients:
            raise SourceError(f"{recipe_id} has no ingredients")
        product = raw.get("product")
        if not isinstance(product, dict):
            raise SourceError(f"{recipe_id}.product must be a table: item_id and count, or prop_id")
        has_item = "item_id" in product
        has_prop = "prop_id" in product
        if has_item == has_prop:
            raise SourceError(f"{recipe_id}.product names exactly one of item_id or prop_id")
        product_item: tuple[str, int] | None = None
        product_prop: str | None = None
        product_state: str | None = None
        if has_item:
            unknown = sorted(set(product) - {"item_id", "count"})
            if unknown:
                raise SourceError(f"{recipe_id}.product has unknown keys {unknown}")
            item_id = _identifier(product.get("item_id"), field=f"{recipe_id}.product.item_id")
            if item_id not in item_ids:
                raise SourceError(f"{recipe_id} produces undeclared item {item_id!r}")
            count = product.get("count", 1)
            if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 99:
                raise SourceError(f"{recipe_id}.product.count must be an integer within [1, 99]")
            if item_id in ingredients:
                raise SourceError(f"{recipe_id} makes {item_id!r} out of itself")
            product_item = (item_id, count)
        else:
            unknown = sorted(set(product) - {"prop_id", "state"})
            if unknown:
                raise SourceError(f"{recipe_id}.product has unknown keys {unknown}")
            prop_id = _identifier(product.get("prop_id"), field=f"{recipe_id}.product.prop_id")
            if prop_id not in prop_by_id:
                raise SourceError(f"{recipe_id} builds undeclared prop {prop_id!r}")
            product_prop = prop_id
            # The look the thing is built in: a fire is built lit. The prop's
            # baseline look when unsaid, so the consumer never has to guess.
            built_prop = prop_by_id[prop_id]
            product_state = _identifier(
                product.get("state", built_prop.baseline_state),
                field=f"{recipe_id}.product.state",
            )
            if product_state not in built_prop.states:
                raise SourceError(
                    f"{recipe_id}.product.state {product_state!r} is not one of "
                    f"{prop_id}'s states {list(built_prop.states)}"
                )
        station = _identifier(raw.get("station", "hand"), field=f"{recipe_id}.station")
        if station != "hand" and station not in station_ids:
            raise SourceError(f"{recipe_id} wants undeclared station {station!r}")
        recipes.append(
            Recipe(
                recipe_id=recipe_id,
                ingredients=ingredients,
                station=station,
                product_item=product_item,
                product_prop=product_prop,
                product_state=product_state,
            )
        )
    return Crafting(slots=slots, start=start, stations=tuple(stations), recipes=tuple(recipes))


def check_crafting(package: Package) -> None:
    """Refuse a crafting table that cannot be played: an item, recipe or
    station nothing reaches, or a tool that serves the wrong verb. Reachable
    means: in the start inventory, yielded by a prop, lying on the forage
    sheet, or the product of a recipe whose ingredients are all reachable and
    whose station exists (stands in the camp, or is itself a reachable
    product). Offline, before any spend."""

    crafting = package.crafting
    items = {item.item_id for item in package.items}
    reachable: set[str] = set(crafting.start)
    for prop in package.props:
        for interaction in prop.interactions:
            reachable.update(produced.item_id for produced in interaction.yields)
    if package.forage is not None:
        reachable.update(cell.item_id for cell in package.forage.cells)
    # The spawn set piece's members stand before anything is built: the
    # cold firepit is a station on day one.
    built: set[str] = {member.prop for member in package.world.spawn.members}
    stations_by_id = {station.station_id: station for station in crafting.stations}
    pending = list(crafting.recipes)
    progressed = True
    while pending and progressed:
        progressed = False
        for recipe in list(pending):
            if not set(recipe.ingredients) <= reachable:
                continue
            if recipe.station != "hand" and stations_by_id[recipe.station].prop_id not in built:
                continue
            pending.remove(recipe)
            progressed = True
            if recipe.product_item is not None:
                reachable.add(recipe.product_item[0])
            if recipe.product_prop is not None:
                built.add(recipe.product_prop)
    if pending:
        names = ", ".join(recipe.recipe_id for recipe in pending)
        raise SourceError(f"crafting.toml recipes nothing can ever make: {names}")
    unreachable = sorted(items - reachable)
    if unreachable:
        raise SourceError(
            "items.toml declares items nothing yields, forages, starts with "
            f"or crafts: {unreachable}"
        )
    for station in crafting.stations:
        if station.prop_id not in built:
            raise SourceError(
                f"crafting.toml station {station.station_id!r} can never exist: "
                f"nothing builds {station.prop_id!r}"
            )
    for prop in package.props:
        for interaction in prop.interactions:
            tool = interaction.tool
            if tool is None:
                continue
            item = package.item(tool.item_id) if tool.item_id in items else None
            if item is None:
                raise SourceError(
                    f"{prop.prop_id}.interactions.tool names undeclared item {tool.item_id!r}"
                )
            if item.tool is None or item.tool.verb != interaction.verb:
                raise SourceError(
                    f"{prop.prop_id} wants {tool.item_id!r} to {interaction.verb}, but that item "
                    f"declares no tool for that verb"
                )


def _biomes(
    rows: object, *, root: Path | None = None, digests: DigestLedger | None = None
) -> tuple[Biome, ...]:
    """The first entry is the base biome; the rest declare a share of the land."""

    if not isinstance(rows, list) or len(rows) < 1:
        raise SourceError("ground.toml declares no biomes")
    if len(rows) > MAX_BIOMES:
        raise SourceError(
            f"{len(rows)} biomes declared; the biome-weight plate carries at most {MAX_BIOMES} "
            "(the base plus three channels). A fifth needs a second weight plate."
        )
    biomes: list[Biome] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise SourceError("[[biomes]] entry must be a table")
        biome_id = _identifier(row.get("biome_id"), field="biome_id")
        if biome_id in seen:
            raise SourceError(f"two biomes are called {biome_id!r}")
        seen.add(biome_id)
        if "splat_channel" in row:
            raise SourceError(
                f"{biome_id}.splat_channel is not authored any more: the first biome is the base "
                "and the others declare a `share` of the land"
            )
        if index == 0:
            if "share" in row:
                raise SourceError(
                    f"{biome_id} is the base biome and owns the remainder; drop its share"
                )
            share = 0.0
        else:
            share = _number(row.get("share"), field=f"{biome_id}.share", low=0.02, high=0.8)
        biomes.append(
            Biome(
                biome_id=biome_id,
                texel_meters=_number(
                    row.get("texel_meters"), field="texel_meters", low=0.5, high=64.0
                ),
                prompt=_text(row.get("prompt"), field="biome.prompt"),
                share=share,
                value_target=_number(
                    row.get("value_target", 0.42), field="biome.value_target", low=0.2, high=0.8
                ),
                style_emphasis=" ".join(str(row.get("style_emphasis", "")).split()),
                feature_max_meters=_number(
                    row.get("feature_max_meters", 0.15),
                    field="biome.feature_max_meters",
                    low=0.01,
                    high=4.0,
                ),
                friction=_number(
                    row.get("friction", 0.6), field=f"{biome_id}.friction", low=0.05, high=3.0
                ),
                material=_material(row.get("material", "field"), field=f"{biome_id}.material"),
                take=_take(
                    row.get("take"),
                    field=f"{biome_id}.take",
                    root=root,
                    digests=digests,
                    suffix=".png",
                ),
            )
        )
    if sum(b.share for b in biomes) > 0.85:
        raise SourceError(
            "the non-base biomes claim more than 85% of the land; the base needs room"
        )
    return tuple(biomes)


def _look(block: object) -> Look:
    if not isinstance(block, dict):
        raise SourceError("[look] is required: the look contract is stated once, in survival.toml")
    light = _text(block.get("light"), field="look.light")
    if light not in LOOK_LIGHTS:
        raise SourceError(f"look.light must be one of {list(LOOK_LIGHTS)}, got {light!r}")
    for key in ("mirror", "mirror_for_variety", "spin"):
        if key in block:
            raise SourceError(
                f"look.{key} is not a choice: nothing is mirrored for variety and ground pieces "
                f"are never spun; drop the key"
            )
    return Look(
        light=light,
        ground_piece_jitter_degrees=_number(
            block.get("ground_piece_jitter_degrees", 15.0),
            field="look.ground_piece_jitter_degrees",
            low=0.0,
            high=45.0,
        ),
    )


def _decals(rows: object) -> tuple[Decal, ...]:
    if not isinstance(rows, list):
        raise SourceError("[[decals]] must be a list")
    decals: list[Decal] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        use = str(row.get("use", "free"))
        if use not in DECAL_USES:
            raise SourceError(f"decal.use must be one of {list(DECAL_USES)}, got {use!r}")
        families = (
            _strings(row.get("families", []), field="decal.families") if row.get("families") else ()
        )
        if use == "skirt" and not families:
            raise SourceError("a skirt decal must name the prop families it goes under")
        decals.append(
            Decal(
                decal_id=_identifier(row.get("decal_id"), field="decal_id"),
                width_meters=_number(
                    row.get("width_meters"), field="decal.width", low=0.2, high=32.0
                ),
                height_meters=_number(
                    row.get("height_meters"), field="decal.height", low=0.2, high=32.0
                ),
                prompt=_text(row.get("prompt"), field="decal.prompt"),
                use=use,
                families=tuple(families),
                scale=_number(row.get("scale", 1.0), field="decal.scale", low=0.2, high=6.0),
            )
        )
    return tuple(decals)


def _macro(block: object) -> MacroPlate | None:
    if block is None:
        return None
    if not isinstance(block, dict):
        raise SourceError("[macro] must be a table")
    period = block.get("period_meters")
    return MacroPlate(
        texel_meters=_number(
            block.get("texel_meters"), field="macro.texel_meters", low=4.0, high=256.0
        ),
        period_meters=None
        if period is None
        else _number(period, field="macro.period_meters", low=2.0, high=256.0),
        strength=_number(block.get("strength", 0.5), field="macro.strength", low=0.0, high=1.0),
        prompt=_text(block.get("prompt"), field="macro.prompt"),
    )


#: The ground's consumer mixing, ground.toml [blend]: how the viewer composes
#: the plates it was given. Every key is read by no cache key, so retuning any
#: of them re-bills nothing; the dev panel's ground sliders write them back.
#: key -> (low, high). Defaults live in manifest.py beside the shore numbers.
BLEND_KEYS: dict[str, tuple[float, float]] = {
    # The biome edge: the blend band in mask units and the erosion noise.
    "edge_softness": (0.005, 0.5),
    "edge_noise_strength": (0.0, 1.0),
    # The carpet cut: a darkening of the lower carpet along the cut, its width
    # in margin units (a mask's bilinear step is about a quarter metre), and
    # the ink line on the cut itself.
    "edge_shadow": (0.0, 1.0),
    "edge_shadow_width": (0.0, 1.0),
    "edge_ink": (0.0, 1.0),
    "edge_ink_width": (0.0, 0.5),
    # Texture bombing: the hex cell size in metres, and how far a cell may
    # turn its sample (0 = offsets only, which a directional fabric wants; 1 =
    # any angle, which an isotropic plate may take).
    "bomb_meters": (0.0, 30.0),
    "bomb_rotate": (0.0, 1.0),
    # The day grade: one linear gain on the whole ground after levelling.
    # The reference's turf sits near 0.6 luma in daylight; ours arrived as
    # dusk with every plate levelled to its own target.
    "exposure": (0.25, 4.0),
    # The cut's second octave: a fine tear (metres, strength) so the edge
    # scallops in 30-80 cm lobes like torn paper, not a 17 m wobble; and a
    # pale rim on the upper carpet along the cut, the shadow's counterpart.
    "edge_fine_meters": (0.2, 20.0),
    "edge_fine_strength": (0.0, 1.0),
    "edge_rim": (0.0, 1.0),
    # The frame's light, day side: a warm pool around the player (gain at the
    # centre, radius in metres) and a screen vignette toward the corners. The
    # night keeps the firelight it has; these fade with the day.
    "pool_gain": (0.0, 1.0),
    "pool_radius_meters": (1.0, 40.0),
    "vignette": (0.0, 1.0),
    # The grade, applied to ground and sprites alike so they meet: a lift of
    # the blacks, a warm shift of the midtones, a desaturation above mid value.
    "grade_lift": (0.0, 0.2),
    "grade_warmth": (0.0, 1.0),
    "grade_desaturate": (0.0, 1.0),
    # Ink waves on the water: short white strokes, their strength and cell.
    "wave_ink": (0.0, 1.0),
    "wave_meters": (0.5, 6.0),
    # Contact shadows: the ellipse's size over the footprint and its darkness.
    "shadow_scale": (0.5, 3.0),
    "shadow_strength": (0.0, 1.0),
    # The skirt and pad decals' gain over the ground's own level: drawn as
    # pale soil, they read as a stain on a dark turf (pass five) until dimmed.
    "decal_gain": (0.0, 1.5),
    # The brush. One direction field over the whole ground (flow_meters) that
    # every stroke follows: the smear of the plates along it (smudge_meters,
    # smudge), the streak of the cut's fine tear along it (edge_streak, a
    # multiple of edge_fine_meters), and the bleed of the neighbour's colour
    # through the winner across the cut (edge_bleed over edge_bleed_width
    # margin units, in streaks). Paper is a screen-space tooth over the frame.
    # flow_meters is the flow noise's tile; its features are a fortieth of
    # it, so 200 m is a brush that turns over 5 m.
    "flow_meters": (1.0, 400.0),
    "edge_streak": (0.0, 6.0),  # metres along the flow
    "smudge_meters": (0.0, 2.0),
    "smudge": (0.0, 1.0),
    "edge_bleed": (0.0, 1.0),
    "edge_bleed_width": (0.0, 3.0),
    "paper": (0.0, 0.5),
    "paper_px": (1.0, 12.0),
    # The strokes: a noise tile (stroke_meters; the noise's features are a
    # fortieth of its tile, so 5 m is a 12 cm grain) integrated along the flow
    # over smudge_meters, taken by the ground's value at `stroke`, so the
    # brush is seen as streaks that lie with it and not only as a smear.
    "stroke": (0.0, 0.5),
    "stroke_meters": (0.5, 20.0),
    # How much of the ground carries strokes at all (a slow patch mask), so
    # the brushwork is intermittent the way a hand's is and not a pattern.
    "stroke_cover": (0.0, 1.0),
}

#: `[blend] level`: per-biome display value, sRGB luma, that the consumer's
#: leveller uses in place of the plate's `value_target`. The target in the
#: brief is what the plate was asked for; this is what the patchwork needs the
#: neighbours to be, which is a mixing decision: no node reads it.
LEVEL_RANGE = (0.2, 0.95)


def _blend(block: object) -> dict[str, float]:
    if block is None:
        return {}
    if not isinstance(block, dict):
        raise SourceError("[blend] must be a table")
    unknown = sorted(set(block) - set(BLEND_KEYS) - {"level"})
    if unknown:
        raise SourceError(f"ground.toml [blend] has unknown keys {unknown}")
    return {
        key: _number(block[key], field=f"blend.{key}", low=low, high=high)
        for key, (low, high) in BLEND_KEYS.items()
        if key in block
    }


def _level(block: object, biome_ids: Sequence[str]) -> dict[str, float]:
    if block is None or not isinstance(block, dict) or "level" not in block:
        return {}
    level = block["level"]
    if not isinstance(level, dict):
        raise SourceError("ground.toml [blend] level must be a table of biome_id = value")
    unknown = sorted(set(level) - set(biome_ids))
    if unknown:
        raise SourceError(f"ground.toml [blend] level names unknown biomes {unknown}")
    low, high = LEVEL_RANGE
    return {
        biome_id: _number(level[biome_id], field=f"blend.level.{biome_id}", low=low, high=high)
        for biome_id in biome_ids
        if biome_id in level
    }


def _road(block: object) -> Road | None:
    if block is None:
        return None
    if not isinstance(block, dict):
        raise SourceError("[road] must be a table")
    return Road(
        road_id=_identifier(block.get("road_id"), field="road.road_id"),
        width_meters=_number(
            block.get("width_meters"), field="road.width_meters", low=0.5, high=12.0
        ),
        length_meters=_number(
            block.get("length_meters", 30.0), field="road.length_meters", low=4.0, high=400.0
        ),
        texel_meters=_number(
            block.get("texel_meters"), field="road.texel_meters", low=0.5, high=64.0
        ),
        feature_max_meters=_number(
            block.get("feature_max_meters", 0.15),
            field="road.feature_max_meters",
            low=0.01,
            high=4.0,
        ),
        value_target=_number(
            block.get("value_target", 0.42), field="road.value_target", low=0.2, high=0.8
        ),
        style_emphasis=" ".join(str(block.get("style_emphasis", "")).split()),
        edge_meters=_number(
            block.get("edge_meters", 0.6), field="road.edge_meters", low=0.05, high=6.0
        ),
        prompt=_text(block.get("prompt"), field="road.prompt"),
    )


def _water(block: object) -> Water | None:
    if block is None:
        return None
    if not isinstance(block, dict):
        raise SourceError("[water] must be a table")
    return Water(
        texel_meters=_number(
            block.get("texel_meters"), field="water.texel_meters", low=0.5, high=64.0
        ),
        feature_max_meters=_number(
            block.get("feature_max_meters", 0.5),
            field="water.feature_max_meters",
            low=0.01,
            high=8.0,
        ),
        value_target=_number(
            block.get("value_target", 0.26), field="water.value_target", low=0.1, high=0.8
        ),
        style_emphasis=" ".join(str(block.get("style_emphasis", "")).split()),
        prompt=_text(block.get("prompt"), field="water.prompt"),
        colour=_colour(block.get("colour", [0.13, 0.2, 0.22]), field="water.colour"),
        depth_meters=_number(
            block.get("depth_meters", 0.45), field="water.depth_meters", low=0.05, high=8.0
        ),
        cliff_colour=_colour(
            block.get("cliff_colour", [0.16, 0.12, 0.09]), field="water.cliff_colour"
        ),
    )


class PieceSheetScalars(TypedDict):
    """Everything a piece sheet declares beside its cells.

    The keys are exactly the non-``cells`` fields of ``Clutter``, ``Forage``
    and ``Plants``, so ``_clutter`` and its two siblings splat this straight
    into the dataclass and mypy checks the splat.
    """

    columns: int
    rows: int
    cell_meters: float
    placement: Placement
    style_emphasis: str
    take: str | None


def _piece_sheet(
    block: object,
    *,
    field: str,
    biome_ids: Sequence[str],
    root: Path | None = None,
    digests: DigestLedger | None = None,
) -> tuple[PieceSheetScalars, list[dict[str, Any]]] | None:
    """The shared shape of a sheet of ground pieces: a lattice, a density per
    biome, and one cell per lattice cell with a brief, a contact and the
    biomes it may land in. Returns the checked scalars and the raw cells,
    each with its contact and biomes already validated.

    A cell keeps ``dict[str, Any]``: it carries the author's whole table
    through (``**raw``), and the two sheets that add fields of their own read
    them off it, so its keys are open where the scalars are closed."""

    if block is None:
        return None
    if not isinstance(block, dict):
        raise SourceError(f"[{field}] must be a table")
    columns = block.get("columns")
    rows = block.get("rows")
    if (
        not isinstance(columns, int)
        or not isinstance(rows, int)
        or not (2 <= columns <= 8 and 2 <= rows <= 8)
    ):
        raise SourceError(f"{field} columns and rows must be integers within [2, 8]")
    if "density_per_100m2" in block:
        raise SourceError(
            f"{field}.density_per_100m2 is not authored any more; how the sheet is "
            f"scattered is its [{field}.placement] block"
        )
    if "prompt" in block:
        raise SourceError(
            f"{field}.prompt is not authored any more; declare `cells`, one per lattice cell"
        )
    raw_cells = block.get("cells")
    if not isinstance(raw_cells, list) or len(raw_cells) != columns * rows:
        raise SourceError(
            f"{field}.cells must list exactly {columns * rows} cells, one per lattice cell"
        )
    cells: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_cells):
        if not isinstance(raw, dict):
            raise SourceError(f"{field}.cells[{index}] must be a table")
        contact = _text(raw.get("contact"), field=f"{field}.cells[{index}].contact")
        if contact not in CLUTTER_CONTACTS:
            raise SourceError(
                f"{field}.cells[{index}].contact must be one of {list(CLUTTER_CONTACTS)}"
            )
        biomes = _strings(raw.get("biomes"), field=f"{field}.cells[{index}].biomes")
        if not biomes:
            raise SourceError(f"{field}.cells[{index}] names no biome it may land in")
        for biome_id in biomes:
            if biome_id not in biome_ids:
                raise SourceError(f"{field}.cells[{index}] names unknown biome {biome_id!r}")
        cells.append(
            {
                **raw,
                "brief": _text(raw.get("brief"), field=f"{field}.cells[{index}].brief"),
                "contact": contact,
                "biomes": tuple(biomes),
                "placement": _placement(
                    raw.get("placement"),
                    field=f"{field}.cells[{index}].placement",
                    biome_ids=biome_ids,
                    default_habitat={biome_id: 1.0 for biome_id in biomes},
                ),
            }
        )
    everywhere = {biome_id: 1.0 for cell in cells for biome_id in cell["biomes"]}
    placement = _placement(
        block.get("placement"),
        field=f"{field}.placement",
        biome_ids=biome_ids,
        default_habitat=everywhere,
    )
    if placement is None:
        raise SourceError(f"[{field}.placement] is required: how the sheet's cells are scattered")
    for biome_id, weight in placement.habitat.items():
        if weight > 0.0 and not any(biome_id in cell["biomes"] for cell in cells):
            raise SourceError(f"{field} wants pieces on {biome_id!r} but no cell may land there")
    scalars: PieceSheetScalars = {
        "columns": columns,
        "rows": rows,
        "cell_meters": _number(
            block.get("cell_meters"), field=f"{field}.cell_meters", low=0.05, high=4.0
        ),
        "placement": placement,
        "style_emphasis": " ".join(str(block.get("style_emphasis", "")).split()),
        "take": _take(
            block.get("take"), field=f"{field}.take", root=root, digests=digests, suffix=".png"
        ),
    }
    return scalars, cells


def _clutter(
    block: object,
    *,
    biome_ids: Sequence[str],
    root: Path | None = None,
    digests: DigestLedger | None = None,
) -> Clutter | None:
    parsed = _piece_sheet(block, field="clutter", biome_ids=biome_ids, root=root, digests=digests)
    if parsed is None:
        return None
    scalars, cells = parsed
    return Clutter(
        **scalars,
        cells=tuple(
            ClutterCell(
                brief=c["brief"], contact=c["contact"], biomes=c["biomes"], placement=c["placement"]
            )
            for c in cells
        ),
    )


def _plants(
    block: object,
    *,
    biome_ids: Sequence[str],
    root: Path | None = None,
    digests: DigestLedger | None = None,
) -> Plants | None:
    parsed = _piece_sheet(block, field="plants", biome_ids=biome_ids, root=root, digests=digests)
    if parsed is None:
        return None
    scalars, cells = parsed
    for index, cell in enumerate(cells):
        if cell["contact"] != "growing":
            raise SourceError(
                f"plants.cells[{index}] must grow from the ground; "
                "a fallen or pressed thing is litter"
            )
    if scalars["cell_meters"] < 0.5:
        raise SourceError(
            "plants.cell_meters is under half a metre: that is the litter's scale, not a plant's"
        )
    return Plants(
        **scalars,
        cells=tuple(
            PlantCell(
                brief=c["brief"], contact=c["contact"], biomes=c["biomes"], placement=c["placement"]
            )
            for c in cells
        ),
    )


def _forage(
    block: object,
    *,
    biome_ids: Sequence[str],
    item_ids: Sequence[str],
    root: Path | None = None,
    digests: DigestLedger | None = None,
) -> Forage | None:
    parsed = _piece_sheet(block, field="forage", biome_ids=biome_ids, root=root, digests=digests)
    if parsed is None:
        return None
    scalars, cells = parsed
    out: list[ForageCell] = []
    for index, raw in enumerate(cells):
        item_id = _identifier(raw.get("item_id"), field=f"forage.cells[{index}].item_id")
        if item_id not in item_ids:
            raise SourceError(f"forage.cells[{index}] yields undeclared item {item_id!r}")
        count = raw.get("count", 1)
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 99:
            raise SourceError(f"forage.cells[{index}].count must be an integer within [1, 99]")
        out.append(
            ForageCell(
                brief=raw["brief"],
                contact=raw["contact"],
                biomes=raw["biomes"],
                item_id=item_id,
                count=count,
                regrow_seconds=_number(
                    raw.get("regrow_seconds"),
                    field=f"forage.cells[{index}].regrow_seconds",
                    low=1.0,
                    high=3600.0,
                ),
                placement=raw["placement"],
            )
        )
    return Forage(**scalars, cells=tuple(out))


def _music_transition(doc: Mapping[str, object] | None) -> MusicTransition:
    """Read [transition] out of music.toml. Absent is the default, because a
    package that never thought about the fade should still sound deliberate."""

    row = (doc or {}).get("transition")
    if row is None:
        return DEFAULT_MUSIC_TRANSITION
    if not isinstance(row, dict):
        raise SourceError("music.toml [transition] must be a table")
    unknown = set(row) - {"crossfade_seconds", "curve", "overlap", "switch_at"}
    if unknown:
        raise SourceError(f"music.toml [transition] has unknown keys {sorted(unknown)}")
    curve = _text(row.get("curve", DEFAULT_MUSIC_TRANSITION.curve), field="transition.curve")
    if curve not in MUSIC_CURVES:
        raise SourceError(f"transition.curve must be one of {list(MUSIC_CURVES)}, got {curve!r}")
    return MusicTransition(
        crossfade_seconds=_number(
            row.get("crossfade_seconds", DEFAULT_MUSIC_TRANSITION.crossfade_seconds),
            field="transition.crossfade_seconds",
            low=0.1,
            high=20.0,
        ),
        curve=curve,
        overlap=_number(
            row.get("overlap", DEFAULT_MUSIC_TRANSITION.overlap),
            field="transition.overlap",
            low=0.0,
            high=1.0,
        ),
        switch_at=_number(
            row.get("switch_at", DEFAULT_MUSIC_TRANSITION.switch_at),
            field="transition.switch_at",
            low=0.05,
            high=0.95,
        ),
    )


def _music(
    doc: Mapping[str, object] | None,
    *,
    root: Path | None = None,
    digests: DigestLedger | None = None,
) -> tuple[Track, ...]:
    if doc is None:
        return ()
    rows = doc.get("tracks")
    if not isinstance(rows, list) or not rows:
        raise SourceError("music.toml must declare at least one [[tracks]] entry")
    tracks: list[Track] = []
    seen_ids: set[str] = set()
    seen_cues: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise SourceError("[[tracks]] entry must be a table")
        track_id = _identifier(row.get("track_id"), field="track_id")
        if track_id in seen_ids:
            raise SourceError(f"music.toml repeats track_id {track_id!r}")
        seen_ids.add(track_id)
        cue = _text(row.get("cue"), field=f"{track_id}.cue")
        if cue not in MUSIC_CUES:
            raise SourceError(f"{track_id}.cue must be one of {list(MUSIC_CUES)}, got {cue!r}")
        if cue in seen_cues:
            raise SourceError(f"music.toml declares two tracks for the {cue!r} cue")
        seen_cues.add(cue)
        take = _take(row.get("take"), field=f"{track_id}.take", root=root, digests=digests)
        tracks.append(
            Track(
                track_id=track_id,
                cue=cue,
                target_duration_seconds=_number(
                    row.get("target_duration_seconds"),
                    field=f"{track_id}.target_duration_seconds",
                    low=20.0,
                    high=300.0,
                ),
                prompt=_text(row.get("prompt"), field=f"{track_id}.prompt").strip(),
                take=take,
            )
        )
    missing = [cue for cue in MUSIC_CUES if cue not in seen_cues]
    if missing:
        raise SourceError(f"music.toml declares no track for the {missing[0]!r} cue")
    return tuple(tracks)


def _choice(raw: object, choices: Sequence[str], *, field: str) -> str:
    value = _text(raw, field=field)
    if value not in choices:
        raise SourceError(f"{field} must be one of {list(choices)}, got {value!r}")
    return value


def _material(raw: object, *, field: str) -> str:
    value = _text(raw, field=field)
    if value not in GROUND_MATERIALS:
        raise SourceError(f"{field} must be one of {list(GROUND_MATERIALS)}, got {value!r}")
    return value


def _take(
    raw: object,
    *,
    field: str,
    root: Path | None,
    digests: DigestLedger | None,
    suffix: str = ".mp3",
) -> str | None:
    """An auditioned file kept inside the package: resolved, confined,
    digested into the ledger so the lock and the adopt node both see it.

    Two authored forms, one ledger entry either way. ``take = "sounds/eat.take.mp3"``
    reads and digests the bytes. ``take = { path = "...", sha256 = "..." }``
    declares the digest, which is what enters the ledger: the file is verified
    against it when it is here and refused when its bytes differ, and its
    absence is recorded rather than raised, so a package whose media is kept
    outside the repository still plans, still digests and still builds the same
    graph. The refusal for an absent take belongs at the adopt node, which is
    the only place that needs the bytes.
    """

    if raw is None:
        return None
    if root is None or digests is None:
        raise SourceError(f"{field} needs a package root to resolve against")
    declared: str | None = None
    if isinstance(raw, Mapping):
        unknown = sorted(set(raw) - {"path", "sha256"})
        if unknown:
            raise SourceError(f"{field} has unknown keys {unknown}")
        declared = _digest(raw.get("sha256"), field=f"{field}.sha256")
        raw = raw.get("path")
    relative = PurePosixPath(_text(raw, field=field))
    if relative.is_absolute() or ".." in relative.parts or relative.suffix != suffix:
        raise SourceError(f"{field} must be a relative {suffix} path inside the package")
    path = root / relative
    name = relative.as_posix()
    if not path.resolve().is_relative_to(root.resolve()):
        raise SourceError(f"{field} {name!r} is not a file inside the package")
    if declared is None:
        if not path.is_file():
            raise SourceError(f"{field} {name!r} is not a file inside the package")
        digests[name] = content_sha256(path.read_bytes())
        return name
    if path.is_file():
        found = content_sha256(path.read_bytes())
        if found != declared:
            raise SourceError(
                f"{field} {name!r} does not match its declared sha256: "
                f"declared {declared}, found {found}"
            )
    elif path.exists():
        raise SourceError(f"{field} {name!r} is not a file inside the package")
    else:
        digests.missing.append(MissingTake(path=name, sha256=declared))
    digests[name] = declared
    return name


def _sounds(
    doc: Mapping[str, object] | None,
    *,
    root: Path | None = None,
    digests: DigestLedger | None = None,
) -> tuple[SoundEffect, ...]:
    """The optional sounds file: one clip per cue, no cue twice, no cue the
    runtime does not play. A brief over the route's 450 characters, a duration
    the route cannot serve, a take outside the package: refused offline."""

    if doc is None:
        return ()
    rows = doc.get("cues")
    if not isinstance(rows, list) or not rows:
        raise SourceError("sounds.toml must declare at least one [[cues]] entry")
    allowed = {
        "cue",
        "prompt",
        "duration_seconds",
        "loop",
        "take",
        "gain",
        "pitch_jitter",
        "onsets",
    }
    clips: list[SoundEffect] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise SourceError("[[cues]] entry must be a table")
        cue = _text(row.get("cue"), field="cue")
        if cue not in SOUND_CUES:
            raise SourceError(f"sounds.toml cue must be one of {list(SOUND_CUES)}, got {cue!r}")
        if cue in seen:
            raise SourceError(f"sounds.toml declares the {cue!r} cue twice")
        seen.add(cue)
        unknown = sorted(set(row) - allowed)
        if unknown:
            raise SourceError(f"sounds.toml {cue} has unknown keys {unknown}")
        prompt = _text(row.get("prompt"), field=f"{cue}.prompt")
        if len(prompt) > 450:
            raise SourceError(f"{cue}.prompt is over the route's 450-character ceiling")
        loop = row.get("loop", False)
        if not isinstance(loop, bool):
            raise SourceError(f"{cue}.loop must be a boolean")
        onsets = row.get("onsets", False)
        if not isinstance(onsets, bool):
            raise SourceError(f"{cue}.onsets must be a boolean")
        if onsets and loop:
            raise SourceError(f"{cue} cannot both loop and be cut at its onsets")
        clips.append(
            SoundEffect(
                cue=cue,
                prompt=prompt,
                duration_seconds=_number(
                    row.get("duration_seconds"), field=f"{cue}.duration_seconds", low=0.5, high=30.0
                ),
                loop=loop,
                take=_take(row.get("take"), field=f"{cue}.take", root=root, digests=digests),
                # Above 1 is makeup gain: the route's level is a lottery the
                # bytes may not repair, so a quiet take is lifted at playback.
                gain=_number(row.get("gain", 1.0), field=f"{cue}.gain", low=0.0, high=4.0),
                pitch_jitter=_number(
                    row.get("pitch_jitter", 0.0), field=f"{cue}.pitch_jitter", low=0.0, high=12.0
                ),
                onsets=onsets,
            )
        )
    return tuple(clips)


def _range(value: object, *, field: str, low: float, high: float) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise SourceError(f"{field} must be a [low, high] pair")
    first = _number(value[0], field=f"{field}[0]", low=low, high=high)
    second = _number(value[1], field=f"{field}[1]", low=low, high=high)
    if second < first:
        raise SourceError(f"{field} must be ordered low then high")
    return (first, second)


def _sound_cue(raw: object, *, field: str, loop: bool) -> SoundCue | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise SourceError(f"{field} must be a table")
    prompt = _text(raw.get("prompt"), field=f"{field}.prompt")
    if len(prompt) > 450:
        raise SourceError(f"{field}.prompt is over the route's 450-character ceiling")
    return SoundCue(
        prompt=prompt,
        duration_seconds=_number(
            raw.get("duration_seconds"), field=f"{field}.duration_seconds", low=0.5, high=30.0
        ),
        loop=loop,
    )


def _weather(
    doc: Mapping[str, object] | None,
    *,
    decals: Sequence[Decal],
    root: Path | None = None,
    digests: DigestLedger | None = None,
) -> tuple[Condition, ...]:
    """The optional weather file: one entry per condition, every layer optional.

    Refuses offline what no consumer could play: an unknown condition, a wet
    layer bound to a decal that is not declared with ``use = "wet"``, a ground
    sheet that is not four cells, a range that runs backwards.
    """

    if doc is None:
        return ()
    if doc.get("kind") != "oblique-survival-weather-v1":
        raise SourceError("weather.toml kind must be oblique-survival-weather-v1")
    rows = doc.get("conditions")
    if not isinstance(rows, list) or not rows:
        raise SourceError("weather.toml must declare at least one [[conditions]] entry")
    wet_decals = {decal.decal_id for decal in decals if decal.use == "wet"}
    conditions: list[Condition] = []
    for row in rows:
        if not isinstance(row, dict):
            raise SourceError("each [[conditions]] entry must be a table")
        condition_id = _identifier(row.get("condition_id"), field="condition_id")
        if condition_id not in WEATHER_CONDITIONS:
            raise SourceError(
                f"condition_id must be one of {list(WEATHER_CONDITIONS)}, got {condition_id!r}: "
                "a condition no consumer drives is paid art nobody sees"
            )
        if any(c.condition_id == condition_id for c in conditions):
            raise SourceError(f"weather.toml repeats condition {condition_id!r}")
        field = f"conditions.{condition_id}"
        drops_raw = row.get("drops")
        drops = None
        if drops_raw is not None:
            if not isinstance(drops_raw, dict):
                raise SourceError(f"{field}.drops must be a table")
            kinds = _strings(drops_raw.get("kinds"), field=f"{field}.drops.kinds")
            if len(kinds) != 2 or len(set(kinds)) != 2:
                raise SourceError(f"{field}.drops.kinds must name exactly two distinct cells")
            layers = drops_raw.get("layers", 3)
            if not isinstance(layers, int) or not 1 <= layers <= 4:
                raise SourceError(f"{field}.drops.layers must be an integer within [1, 4]")
            count = drops_raw.get("count_per_screen")
            if not isinstance(count, int) or not 1 <= count <= 2000:
                raise SourceError(
                    f"{field}.drops.count_per_screen must be an integer within [1, 2000]"
                )
            drops = WeatherDrops(
                kinds=kinds,
                count_per_screen=count,
                layers=layers,
                fall_speed_meters_per_second=_number(
                    drops_raw.get("fall_speed_meters_per_second"),
                    field=f"{field}.drops.fall_speed_meters_per_second",
                    low=0.5,
                    high=60.0,
                ),
                height_units=_number(
                    drops_raw.get("height_units"),
                    field=f"{field}.drops.height_units",
                    low=0.02,
                    high=4.0,
                ),
                prompt=_text(drops_raw.get("prompt"), field=f"{field}.drops.prompt"),
                shape=_choice(
                    drops_raw.get("shape", "streak"), DROPS_SHAPES, field=f"{field}.drops.shape"
                ),
            )
        ground_raw = row.get("ground")
        ground = None
        if ground_raw is not None:
            if not isinstance(ground_raw, dict):
                raise SourceError(f"{field}.ground must be a table")
            kinds = _strings(ground_raw.get("kinds"), field=f"{field}.ground.kinds")
            if len(kinds) != 4 or len(set(kinds)) != 4:
                raise SourceError(
                    f"{field}.ground.kinds must name exactly four distinct quadrant cells"
                )
            ground = WeatherGround(
                kinds=kinds,
                height_units=_number(
                    ground_raw.get("height_units"),
                    field=f"{field}.ground.height_units",
                    low=0.02,
                    high=4.0,
                ),
                rate_per_100_sqm_per_second=_number(
                    ground_raw.get("rate_per_100_sqm_per_second"),
                    field=f"{field}.ground.rate_per_100_sqm_per_second",
                    low=0.0,
                    high=200.0,
                ),
                prompt=_text(ground_raw.get("prompt"), field=f"{field}.ground.prompt"),
            )
        wet_raw = row.get("wet")
        wet = None
        if wet_raw is not None:
            if not isinstance(wet_raw, dict):
                raise SourceError(f"{field}.wet must be a table")
            decal_id = _identifier(wet_raw.get("decal_id"), field=f"{field}.wet.decal_id")
            if decal_id not in wet_decals:
                raise SourceError(
                    f"{field}.wet binds decal {decal_id!r}, which ground.toml does not declare "
                    'with use = "wet"'
                )
            wet = WeatherWet(
                decal_id=decal_id,
                per_100_sqm=_number(
                    wet_raw.get("per_100_sqm"), field=f"{field}.wet.per_100_sqm", low=0.0, high=20.0
                ),
                dry_seconds=_number(
                    wet_raw.get("dry_seconds"),
                    field=f"{field}.wet.dry_seconds",
                    low=1.0,
                    high=3600.0,
                ),
            )
        strike_raw = row.get("strike")
        strike = None
        if strike_raw is not None:
            if not isinstance(strike_raw, dict):
                raise SourceError(f"{field}.strike must be a table")
            strike = WeatherStrike(
                above=_number(
                    strike_raw.get("above", 0.7), field=f"{field}.strike.above", low=0.0, high=1.0
                ),
                interval_seconds=_range(
                    strike_raw.get("interval_seconds"),
                    field=f"{field}.strike.interval_seconds",
                    low=0.5,
                    high=600.0,
                ),
                flash_seconds=_number(
                    strike_raw.get("flash_seconds", 0.5),
                    field=f"{field}.strike.flash_seconds",
                    low=0.05,
                    high=3.0,
                ),
                height_units=_number(
                    strike_raw.get("height_units"),
                    field=f"{field}.strike.height_units",
                    low=0.5,
                    high=40.0,
                ),
                prompt=_text(strike_raw.get("prompt"), field=f"{field}.strike.prompt"),
            )
        sound_raw = row.get("sound")
        sound = None
        if sound_raw is not None:
            if not isinstance(sound_raw, dict):
                raise SourceError(f"{field}.sound must be a table")
            sound = WeatherSound(
                ambience=_sound_cue(
                    sound_raw.get("ambience"), field=f"{field}.sound.ambience", loop=True
                ),
                strike=_sound_cue(
                    sound_raw.get("strike"), field=f"{field}.sound.strike", loop=False
                ),
            )
            if sound.ambience is None and sound.strike is None:
                raise SourceError(f"{field}.sound declares no cue")
            if sound.strike is not None and strike is None:
                raise SourceError(
                    f"{field}.sound.strike needs a [conditions.strike] layer to play at"
                )
        cover_raw = row.get("cover")
        cover = None
        if cover_raw is not None:
            if not isinstance(cover_raw, dict):
                raise SourceError(f"{field}.cover must be a table")
            cover = WeatherCover(
                texel_meters=_number(
                    cover_raw.get("texel_meters"),
                    field=f"{field}.cover.texel_meters",
                    low=0.5,
                    high=64.0,
                ),
                feature_max_meters=_number(
                    cover_raw.get("feature_max_meters", 0.25),
                    field=f"{field}.cover.feature_max_meters",
                    low=0.01,
                    high=8.0,
                ),
                value_target=_number(
                    cover_raw.get("value_target", 0.82),
                    field=f"{field}.cover.value_target",
                    low=0.4,
                    high=0.97,
                ),
                style_emphasis=" ".join(str(cover_raw.get("style_emphasis", "")).split()),
                prompt=_text(cover_raw.get("prompt"), field=f"{field}.cover.prompt"),
            )
        ice_raw = row.get("ice")
        ice = None
        if ice_raw is not None:
            if not isinstance(ice_raw, dict):
                raise SourceError(f"{field}.ice must be a table")
            if condition_id != "snow":
                raise SourceError(
                    f"{field}.ice: only snow freezes the water; {condition_id} has no ice"
                )
            unknown = sorted(
                set(ice_raw) - {"texel_meters", "value_target", "style_emphasis", "prompt", "take"}
            )
            if unknown:
                raise SourceError(f"{field}.ice has unknown keys {unknown}")
            ice = WeatherIce(
                texel_meters=_number(
                    ice_raw.get("texel_meters"),
                    field=f"{field}.ice.texel_meters",
                    low=0.5,
                    high=64.0,
                ),
                value_target=_number(
                    ice_raw.get("value_target", 0.72),
                    field=f"{field}.ice.value_target",
                    low=0.4,
                    high=0.97,
                ),
                style_emphasis=" ".join(str(ice_raw.get("style_emphasis", "")).split()),
                prompt=_text(ice_raw.get("prompt"), field=f"{field}.ice.prompt"),
                take=_take(
                    ice_raw.get("take"),
                    field=f"{field}.ice.take",
                    root=root,
                    digests=digests,
                    suffix=".png",
                ),
            )
        if (
            drops is None
            and ground is None
            and wet is None
            and strike is None
            and sound is None
            and cover is None
            and ice is None
        ):
            raise SourceError(f"{field} declares no layer at all")
        conditions.append(
            Condition(
                condition_id=condition_id,
                onset_seconds=_number(
                    row.get("onset_seconds"), field=f"{field}.onset_seconds", low=0.5, high=600.0
                ),
                decay_seconds=_number(
                    row.get("decay_seconds"), field=f"{field}.decay_seconds", low=0.5, high=600.0
                ),
                dry_spell_seconds=_range(
                    row.get("dry_spell_seconds"),
                    field=f"{field}.dry_spell_seconds",
                    low=1.0,
                    high=7200.0,
                ),
                wet_spell_seconds=_range(
                    row.get("wet_spell_seconds"),
                    field=f"{field}.wet_spell_seconds",
                    low=1.0,
                    high=7200.0,
                ),
                tint=_colour(row.get("tint", [1.0, 1.0, 1.0]), field=f"{field}.tint"),
                desaturate=_number(
                    row.get("desaturate", 0.0), field=f"{field}.desaturate", low=0.0, high=1.0
                ),
                drops=drops,
                ground=ground,
                wet=wet,
                strike=strike,
                sound=sound,
                cover=cover,
                ice=ice,
            )
        )
    return tuple(conditions)


def _gameplay(block: object) -> dict[str, Any]:
    """Validate the refusal-bearing entries of [gameplay]; carry the rest verbatim.

    The table is open (see ``Package.gameplay``), so the return keeps ``Any``
    values; what this checks is the handful of keys the pipeline and the
    consumer both depend on.
    """

    if not isinstance(block, Mapping):
        raise SourceError("[gameplay] must be a table")
    gameplay = dict(block)
    if "recipe" in gameplay.get("campfire", {}):
        raise SourceError(
            "gameplay.campfire.recipe is not authored any more; the campfire "
            "is a [[recipes]] entry in crafting.toml"
        )
    if "berry_restore" in gameplay.get("hunger", {}):
        raise SourceError(
            "gameplay.hunger.berry_restore is not authored any more; what a "
            "food restores is its `use` in items.toml"
        )
    if "mob_count" in gameplay:
        raise SourceError(
            "gameplay.mob_count is not authored any more; how many hounds roam and "
            "where is actors.toml [mob.placement]"
        )
    pickup = gameplay.get("pickup", "manual")
    if pickup not in PICKUP_MODES:
        raise SourceError(f"gameplay.pickup = {pickup!r} is not one of {', '.join(PICKUP_MODES)}")
    gameplay["pickup"] = pickup
    reach = _number(
        gameplay.get("interact_reach_meters", 1.2),
        field="gameplay.interact_reach_meters",
        low=0.2,
        high=10.0,
    )
    approach = _number(
        gameplay.get("approach_meters", reach),
        field="gameplay.approach_meters",
        low=reach,
        high=50.0,
    )
    gameplay["interact_reach_meters"] = reach
    gameplay["approach_meters"] = approach
    warmth = gameplay.get("warmth", {})
    if not isinstance(warmth, Mapping):
        raise SourceError("gameplay.warmth must be a table")
    if "dark_drain_per_second" in warmth:
        # The dark's own cold, in every season; a number, never a killer.
        _number(
            warmth["dark_drain_per_second"],
            field="gameplay.warmth.dark_drain_per_second",
            low=0.0,
            high=10.0,
        )
    return gameplay


def load_package(root: Path) -> Package:
    """Read and validate every authored file of one package. Raises before any spend."""

    digests = DigestLedger()
    survival = _load_toml(root / SURVIVAL_DOCUMENT_NAME, digests)
    actors = _load_toml(root / "actors.toml", digests)
    props_doc = _load_toml(root / "props.toml", digests)
    items_doc = _load_toml(root / "items.toml", digests)
    crafting_doc = _load_toml(root / "crafting.toml", digests)
    ground = _load_toml(root / "ground.toml", digests)
    music_path = root / "music.toml"
    music_doc = _load_toml(music_path, digests) if music_path.is_file() else None
    weather_path = root / "weather.toml"
    weather_doc = _load_toml(weather_path, digests) if weather_path.is_file() else None
    sounds_path = root / "sounds.toml"
    sounds_doc = _load_toml(sounds_path, digests) if sounds_path.is_file() else None
    seasons_path = root / "seasons.toml"
    seasons_doc = _load_toml(seasons_path, digests) if seasons_path.is_file() else None
    world_doc = _load_toml(root / "world.toml", digests)
    ui: GameUi | None = None
    ui_references: dict[str, PackageFile] = {}
    if (root / UI_DOCUMENT_NAME).is_file():
        ui, ui_references = _ui(root, digests)

    # The root document's own identity is the one field a schema owns rather
    # than this loader: the repository's contract table reads it off the model.
    try:
        ObliqueSurvivalSource.model_validate(survival)
    except ValidationError as error:
        raise SourceError(
            f"{SURVIVAL_DOCUMENT_NAME} is not an oblique-survival package: {error}"
        ) from None
    if items_doc.get("kind") != "oblique-survival-items-v1":
        raise SourceError("items.toml kind must be oblique-survival-items-v1")
    if "world" in survival:
        raise SourceError(
            "survival.toml [world] moved to world.toml; the world's extent, landmass, "
            "biome rules and set pieces are authored there"
        )
    if "items" in props_doc:
        raise SourceError(
            "props.toml [[items]] moved to items.toml; props.toml declares props only"
        )
    if _subtable(survival, "rights").get("publication_authorized") is not False:
        raise SourceError("source package must state publication_authorized = false")

    package_id = _slug(survival.get("package_id"), field="package_id")
    for name, doc in (
        ("actors.toml", actors),
        ("props.toml", props_doc),
        ("items.toml", items_doc),
        ("crafting.toml", crafting_doc),
        ("ground.toml", ground),
        *((("music.toml", music_doc),) if music_doc is not None else ()),
        *((("weather.toml", weather_doc),) if weather_doc is not None else ()),
        *((("sounds.toml", sounds_doc),) if sounds_doc is not None else ()),
        *((("seasons.toml", seasons_doc),) if seasons_doc is not None else ()),
        ("world.toml", world_doc),
    ):
        if doc.get("package_id") != package_id:
            raise SourceError(f"{name} package_id does not match survival.toml")
    if ui is not None and ui.game_id != package_id:
        raise SourceError(f"{UI_DOCUMENT_NAME} game_id does not match survival.toml")

    style = _subtable(survival, "style")
    scale = _subtable(survival, "scale")
    presentation = _subtable(survival, "presentation")
    minimum = _number(
        scale.get("minimum_height_units"), field="minimum_height_units", low=0.01, high=1.0
    )
    fx = _subtable(ground, "fx")
    fire = _subtable(fx, "fire")
    dust = _subtable(fx, "dust")
    columns = fire.get("columns")
    rows = fire.get("rows")
    if (
        not isinstance(columns, int)
        or not isinstance(rows, int)
        or not 2 <= columns <= 8
        or not 2 <= rows <= 8
    ):
        raise SourceError("fx.fire columns and rows must be integers within [2, 8]")

    biomes = _biomes(ground.get("biomes"), root=root, digests=digests)
    decals = _decals(ground.get("decals", []))
    # Before the Package copies the digest ledger: a track's take is digested
    # into it, like the style plate, so the lock and the adopt node see it.
    music = _music(music_doc, root=root, digests=digests)
    music_transition = _music_transition(music_doc)
    sounds = _sounds(sounds_doc, root=root, digests=digests)
    # Same reason: an actor's appearance picture is digested into the ledger,
    # so the lock sees it and swapping the picture re-bills what carries it.
    player_actor = _actor(
        actors.get("player"), role="player", key="player", root=root, digests=digests
    )
    mob_actor = _actor(
        actors.get("mob"),
        role="mob",
        key="mob",
        root=root,
        digests=digests,
        biome_ids=[b.biome_id for b in biomes],
    )
    style_reference, style_reference_digest = _png_reference(
        root, style.get("reference"), digests, field="style.reference"
    )
    # Parsed before the package is built: a take lands in the digest ledger
    # as it is parsed, and the ledger is copied into the package first.
    clutter = _clutter(
        ground.get("clutter"), biome_ids=[b.biome_id for b in biomes], root=root, digests=digests
    )
    items = _items(items_doc.get("items"))
    icons = _icons(items_doc.get("icons"), items=items, root=root, digests=digests)
    forage = _forage(
        ground.get("forage"),
        biome_ids=[b.biome_id for b in biomes],
        item_ids=[item.item_id for item in items],
        root=root,
        digests=digests,
    )
    plants = _plants(
        ground.get("plants"), biome_ids=[b.biome_id for b in biomes], root=root, digests=digests
    )
    props = _props(
        props_doc.get("props"),
        minimum_height_units=minimum,
        biome_ids=[b.biome_id for b in biomes],
    )
    crafting = _crafting(crafting_doc, items=items, props=props)
    seasons = _seasons(seasons_doc, items=items, props=props)
    world = _world(world_doc, biome_ids=[b.biome_id for b in biomes])
    # Same reason as the takes above: an ice take is digested into the ledger
    # before the package copies it.
    weather = _weather(weather_doc, decals=decals, root=root, digests=digests)
    package = Package(
        root=root,
        package_id=package_id,
        title=_text(survival.get("title"), field="title"),
        digests=dict(digests.digests),
        style_label=_text(style.get("label"), field="style.label"),
        style_keywords=_strings(style.get("keywords"), field="style.keywords"),
        style_avoid=_strings(style.get("avoid"), field="style.avoid"),
        style_reference=style_reference,
        style_reference_digest=style_reference_digest,
        profile=_text(presentation.get("profile"), field="presentation.profile"),
        ground_contact=_text(
            presentation.get("ground_contact", "shadow"), field="presentation.ground_contact"
        ),
        look=_look(survival.get("look")),
        player_height_meters=_number(
            scale.get("player_height_meters"), field="player_height_meters", low=0.2, high=10.0
        ),
        minimum_height_units=minimum,
        camera=dict(_subtable(survival, "camera")),
        world=world,
        gameplay=_gameplay(survival.get("gameplay", {})),
        facing_authored=_text(actors.get("facing_authored"), field="facing_authored"),
        player=player_actor,
        mob=mob_actor,
        props=props,
        items=items,
        icons=icons,
        crafting=crafting,
        biomes=biomes,
        decals=decals,
        macro=_macro(ground.get("macro")),
        road=_road(ground.get("road")),
        clutter=clutter,
        forage=forage,
        plants=plants,
        water=_water(ground.get("water")),
        blend=_blend(ground.get("blend")),
        level=_level(ground.get("blend"), [biome.biome_id for biome in biomes]),
        fire=FireFx(
            columns=columns,
            rows=rows,
            fps=_number(fire.get("fps"), field="fx.fire.fps", low=1.0, high=60.0),
            height_units=_number(
                fire.get("height_units"), field="fx.fire.height_units", low=0.05, high=8.0
            ),
            prompt=_text(fire.get("prompt"), field="fx.fire.prompt"),
        ),
        dust=DustFx(
            kinds=_strings(dust.get("kinds"), field="fx.dust.kinds"),
            height_units=_number(
                dust.get("height_units"), field="fx.dust.height_units", low=0.05, high=8.0
            ),
            prompt=_text(dust.get("prompt"), field="fx.dust.prompt"),
        ),
        music=music,
        music_transition=music_transition,
        weather=weather,
        sounds=sounds,
        seasons=seasons,
        missing_takes=tuple(digests.missing),
        ui=ui,
        ui_references=ui_references,
    )

    if package.profile != "elevated_oblique_perspective_ground_plane_v1":
        raise SourceError("this recipe only serves elevated_oblique_perspective_ground_plane_v1")
    if package.ground_contact not in GROUND_CONTACTS:
        raise SourceError(
            f"presentation.ground_contact must be one of {list(GROUND_CONTACTS)}, "
            f"got {package.ground_contact!r}"
        )
    if package.ground_contact == "skirt_decal" and not any(
        d.use == "skirt" for d in package.decals
    ):
        raise SourceError("ground_contact = skirt_decal but ground.toml declares no skirt decal")
    if package.facing_authored != "right":
        raise SourceError("this recipe authors exactly one facing, and it is 'right'")
    if len(package.dust.kinds) != 4:
        raise SourceError("the dust atlas contract holds exactly four quadrant cells")

    declared_items = {item.item_id for item in package.items}
    for prop in package.props:
        if prop.sheet is not None and package.ground_contact == "painted_base":
            raise SourceError(
                f"{prop.prop_id} is drawn as a sheet, and a sheet cannot carry a painted base: "
                "the feathered patch has no magenta equivalent"
            )
        for interaction in prop.interactions:
            for produced in interaction.yields:
                if produced.item_id not in declared_items:
                    raise SourceError(f"{prop.prop_id} yields undeclared item {produced.item_id!r}")
            if interaction.fx not in package.dust.kinds:
                raise SourceError(
                    f"{prop.prop_id}.interactions.fx {interaction.fx!r} is not a dust cell kind"
                )
    check_crafting(package)
    _check_placement(package)
    _check_seasons(package)
    return package


def _check_seasons(package: Package) -> None:
    """A season prompt must name a look the calendar shows; a cold season needs
    a fire that warms; a look's paintovers come from the summer sprites."""

    looks = (
        {look.look_id for look in package.seasons.looks} if package.seasons is not None else set()
    )
    for prop in package.props:
        for look in prop.season_prompt:
            if look not in looks:
                raise SourceError(
                    f"{prop.prop_id}.season_prompt.{look} names a look no season shows; "
                    "seasons.toml declares the looks"
                )
    if package.seasons is None:
        return
    campfire = package.gameplay.get("campfire", {})
    if any(season.cold > 0.0 for season in package.seasons.seasons):
        heat_radius = _number(
            campfire.get("heat_radius_meters", 0.0),
            field="gameplay.campfire.heat_radius_meters",
            low=0.0,
            high=50.0,
        )
        heat_rate = _number(
            campfire.get("heat_per_second", 0.0),
            field="gameplay.campfire.heat_per_second",
            low=0.0,
            high=100.0,
        )
        if heat_radius <= 0.0 or heat_rate <= 0.0:
            raise SourceError(
                "a season is cold but gameplay.campfire has no "
                "heat_radius_meters and heat_per_second; "
                "a cold no fire warms is a death nobody can refuse"
            )
        warmth = package.gameplay.get("warmth")
        if (
            not isinstance(warmth, Mapping)
            or _number(
                warmth.get("drain_per_second", 0.0),
                field="gameplay.warmth.drain_per_second",
                low=0.0,
                high=10.0,
            )
            <= 0.0
        ):
            raise SourceError(
                "a season is cold but gameplay.warmth.drain_per_second is missing or zero"
            )
    snowy = any(season.snow > 0.0 for season in package.seasons.seasons)
    if snowy and not any(condition.condition_id == "snow" for condition in package.weather):
        raise SourceError(
            "a season holds snow but weather.toml declares no snow condition to hold it"
        )


def resolve_survival_source(input_path: Path) -> Package:
    """The recipe executor's ``_resolve``: one authored package, read and frozen.

    A thin name over ``load_package`` so the executor's contract reads the way
    every other recipe's does, and so the argument it is handed is the
    ``--input`` directory rather than a document.
    """

    return load_package(input_path)


def take_path(package: Package, take: str) -> Path:
    """Where an adopted take's bytes are, or a refusal naming its declared digest.

    Called by the adopt nodes, which are the only place the bytes are needed.
    A take declared by digest alone plans and digests exactly as a present one
    does, so this is where the absence is finally paid for -- after the plan
    has already said what the run would cost.
    """

    absent = package.missing_take(take)
    if absent is not None:
        raise SourceError(f"take not on disk: {absent.path} (declared sha256 {absent.sha256})")
    return package.root / Path(*PurePosixPath(take).parts)
