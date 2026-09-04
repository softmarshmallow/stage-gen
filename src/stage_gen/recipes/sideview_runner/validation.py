"""The runner genre member: resolution, seam rule, and the placement discipline.

Resolution turns the member's authored sources into typed contracts through
the package capture, locking every reference and pinned take by digest, then
proves the member offline: identity, bindings, the encounter's triangles, and
every chunk against the seam rule, the jump arc and the placement discipline.
Every geometric refusal is derived from the SDK's declared arithmetic at base
speed, credential-free, before any spend.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import Any

from stage_gen.components.game_contract import PreparedGameContract, RunnerGenreMember
from stage_gen.components.game_fx import GameFx, load_game_fx_bytes
from stage_gen.components.game_soundtrack import GameSoundtrack, load_game_soundtrack_bytes
from stage_gen.components.game_voices import GameVoices, load_game_voices_bytes
from stage_gen.components.platformer_content import (
    ItemContentCatalog,
    ProjectileContentCatalog,
    PropContentCatalog,
    load_item_content_bytes,
    load_projectile_content_bytes,
    load_prop_content_bytes,
)
from stage_gen.components.platformer_map import bottom_contiguous_surface_row
from stage_gen.components.runner_audio import (
    GeneratedClipRealization,
    RunnerAudioContract,
    SpokenLineRealization,
    load_runner_audio_bytes,
)
from stage_gen.components.runner_content import (
    RunnerAvatarCatalog,
    RunnerBossCatalog,
    declared_motion_states,
    load_runner_avatar_bytes,
    load_runner_boss_bytes,
)
from stage_gen.components.runner_gameplay import (
    PLACEMENT_PROFILES,
    RUNNER_PLACEMENT_PROFILE,
    CollisionProfile,
    DuckProfile,
    JumpArc,
    PlacementProfile,
    RunnerEncounter,
    RunnerGameplayContract,
    SpeedProfile,
    apron_columns,
    arc_height_rows,
    boss_dodge_window_seconds,
    boss_kill_seconds,
    boss_lane_rows,
    boss_salvo_budget_seconds,
    clearable_span_columns,
    drop_scatter_columns,
    hazard_press_window_seconds,
    jump_arc,
    load_runner_gameplay_bytes,
)
from stage_gen.components.runner_track import (
    RunnerHazard,
    RunnerSegmentChunk,
    RunnerSegments,
    RunnerStructuralGround,
    RunnerTrack,
    load_runner_track_bytes,
    seam_profile,
    validate_structural_ground_material_references,
)
from stage_gen.orchestration.package_capture import (
    GamePackageValidationError,
    PackageCapture,
    assert_subset,
    load_locked,
)


@dataclass(frozen=True, slots=True)
class ResolvedRunnerMember:
    """The runner genre member's resolved contracts, when the game declares one."""

    member: RunnerGenreMember
    gameplay: RunnerGameplayContract
    track: RunnerTrack
    avatar: RunnerAvatarCatalog
    props: PropContentCatalog
    items: ItemContentCatalog
    audio: RunnerAudioContract
    soundtrack: GameSoundtrack | None
    #: The screen-FX document, when the game authors one for this genre.
    fx: GameFx | None
    #: The voice catalog, required exactly when the audio contract speaks a line.
    voices: GameVoices | None
    #: Present exactly when the gameplay declares an encounter.
    bosses: RunnerBossCatalog | None
    projectiles: ProjectileContentCatalog | None

    def identity(self) -> dict[str, object]:
        return {
            "track_id": self.track.track_id,
            "avatar_id": self.avatar.avatar.avatar_id,
            "segment_ids": [entry.segment_id for entry in self.track.segments.chunks],
            "prop_ids": [entry.prop_id for entry in self.props.props],
            "item_ids": [entry.item_id for entry in self.items.items],
            "effect_ids": [entry.effect_id for entry in self.audio.effects],
            "track_ids": [] if self.soundtrack is None else list(self.soundtrack.track_ids),
        }


def resolve_runner_member(
    capture: PackageCapture,
    *,
    game: PreparedGameContract,
    member: RunnerGenreMember,
) -> ResolvedRunnerMember:
    """Resolve and prove the runner member out of the captured package."""

    runner = _load_runner_member(capture, member=member)
    _validate_runner_member(game=game, runner=runner)
    return runner


def _load_runner_member(
    capture: PackageCapture, *, member: RunnerGenreMember
) -> ResolvedRunnerMember:
    gameplay = load_locked(
        capture.member(member.gameplay.source),
        load_runner_gameplay_bytes,
        "invalid_runner_gameplay",
    )
    track = load_locked(
        capture.member(member.track.source),
        load_runner_track_bytes,
        "invalid_runner_track",
    )
    avatar = load_locked(
        capture.member(member.content.avatar.source),
        load_runner_avatar_bytes,
        "invalid_runner_avatar",
    )
    props = load_locked(
        capture.member(member.content.props.source),
        load_prop_content_bytes,
        "invalid_prop_content",
    )
    items = load_locked(
        capture.member(member.content.items.source),
        load_item_content_bytes,
        "invalid_item_content",
    )
    audio = load_locked(
        capture.member(member.audio.source),
        load_runner_audio_bytes,
        "invalid_runner_audio",
    )
    bosses = (
        None
        if member.content.bosses is None
        else load_locked(
            capture.member(member.content.bosses.source),
            load_runner_boss_bytes,
            "invalid_runner_boss",
        )
    )
    projectiles = (
        None
        if member.content.projectiles is None
        else load_locked(
            capture.member(member.content.projectiles.source),
            load_projectile_content_bytes,
            "invalid_projectile_content",
        )
    )
    soundtrack = (
        None
        if member.soundtrack is None
        else load_locked(
            capture.member(member.soundtrack.source),
            lambda data: load_game_soundtrack_bytes(data, source_suffix=".toml"),
            "invalid_soundtrack_contract",
        )
    )
    fx = (
        None
        if member.fx is None
        else load_locked(
            capture.member(member.fx.source),
            load_game_fx_bytes,
            "invalid_game_fx_contract",
        )
    )
    if fx is not None:
        for fx_reference in fx.references:
            capture.image(
                fx_reference.source,
                fx_reference.source_sha256,
                f"fx reference {fx_reference.reference_id}",
            )
    voices = (
        None
        if member.voices is None
        else load_locked(
            capture.member(member.voices.source),
            load_game_voices_bytes,
            "invalid_game_voices_contract",
        )
    )
    # A pinned take is a reviewed audition the package carries by digest: the
    # bytes and the sidecar that produced them, both locked into the closure,
    # and the sidecar must describe exactly those bytes.
    for effect in audio.pinned_effects():
        realization = effect.realization
        assert isinstance(realization, GeneratedClipRealization | SpokenLineRealization)
        pinned = realization.pinned
        assert pinned is not None
        capture.audio_take(
            source=pinned.source,
            digest=pinned.source_sha256,
            provenance_source=pinned.provenance_source,
            provenance_digest=pinned.provenance_sha256,
            label=f"runner audio {effect.effect_id} pinned take",
        )
    track_reference_bytes: dict[str, bytes] = {}
    for track_reference in track.references:
        track_reference_bytes[track_reference.reference_id] = capture.image(
            track_reference.source,
            track_reference.source_sha256,
            f"track {track.track_id} reference {track_reference.reference_id}",
        )
    if isinstance(track.ground, RunnerStructuralGround):
        try:
            validate_structural_ground_material_references(
                [track_reference_bytes[reference_id] for reference_id in track.ground.reference_ids]
            )
        except ValueError as error:
            raise GamePackageValidationError(
                "invalid_reference_image",
                f"track {track.track_id} structural-ground references are unusable: {error}",
            ) from error
    catalogs: list[tuple[str, Any]] = [("avatar", avatar), ("prop", props), ("item", items)]
    if bosses is not None:
        catalogs.append(("boss", bosses))
    if projectiles is not None:
        catalogs.append(("projectile", projectiles))
    for label, catalog in catalogs:
        for content_reference in catalog.references:
            capture.image(
                content_reference.source,
                content_reference.source_sha256,
                f"runner {label} reference {content_reference.reference_id}",
            )
    return ResolvedRunnerMember(
        member=member,
        gameplay=gameplay,
        track=track,
        avatar=avatar,
        props=props,
        items=items,
        audio=audio,
        soundtrack=soundtrack,
        fx=fx,
        voices=voices,
        bosses=bosses,
        projectiles=projectiles,
    )


#: The moments the runner runtime emits unconditionally.
RUNNER_BASE_FX_MOMENTS: frozenset[str] = frozenset({"stage_start"})


def runner_fx_moments(gameplay: RunnerGameplayContract) -> frozenset[str]:
    """The moments this runner member can actually play.

    A bound moment outside the set is paid generation the runtime would never
    reach, so it is refused offline. `encounter_start` is emitted only by a
    member that declares an encounter, which makes the moment vocabulary a
    function of the gameplay rather than a constant.
    """

    if gameplay.encounter is None:
        return RUNNER_BASE_FX_MOMENTS
    return RUNNER_BASE_FX_MOMENTS | {"encounter_start"}


def _validate_runner_member(*, game: PreparedGameContract, runner: ResolvedRunnerMember) -> None:
    """Cross-validate the runner family: identity, bindings, seams, and clearable layouts.

    Every geometric refusal below is proved from the SDK's declared arithmetic
    (`jump_arc` and friends) against the placement discipline selected by
    `RUNNER_PLACEMENT_PROFILE`, at base speed - the worst case, since airtime
    is fixed by construction. This runs credential-free, before any spend.
    """

    owned = [
        runner.gameplay.game_id,
        runner.track.game_id,
        runner.avatar.game_id,
        runner.props.game_id,
        runner.items.game_id,
        runner.audio.game_id,
        *(() if runner.soundtrack is None else (runner.soundtrack.game_id,)),
        *(() if runner.fx is None else (runner.fx.game_id,)),
        *(() if runner.voices is None else (runner.voices.game_id,)),
    ]
    if any(game_id != game.game_id for game_id in owned):
        raise GamePackageValidationError(
            "cross_game_identity", "every package contract must share game.toml game_id"
        )
    # A spoken line names a voice; the catalog is where the name becomes a
    # provider reference with a rights statement. Refused here, offline, so no
    # graph is ever planned around a voice nobody cast.
    spoken_voice_ids = runner.audio.voice_ids()
    if spoken_voice_ids and runner.voices is None:
        raise GamePackageValidationError(
            "unresolved_cross_reference",
            "runner audio speaks a line but the package binds no voices.toml catalog",
        )
    if runner.voices is not None:
        assert_subset(set(spoken_voice_ids), set(runner.voices.voice_ids()), "spoken line voice_id")
    if runner.fx is not None:
        unplayed = sorted(set(runner.fx.moment_names()) - runner_fx_moments(runner.gameplay))
        if unplayed:
            raise GamePackageValidationError(
                "invalid_game_fx_contract",
                "the runner runtime emits no such moment: " + ", ".join(unplayed),
            )
        # The only actor the runner draws that a moment can announce is the boss of
        # the encounter that announces it. A portrait naming any other id would be a
        # plate drawn from a concept the run has no reason to hold.
        encounter = runner.gameplay.encounter
        for portrait in () if runner.fx.cut_in is None else runner.fx.cut_in.portraits:
            if portrait.subject is None:
                continue
            if encounter is None or portrait.subject.actor_id != encounter.boss_id:
                raise GamePackageValidationError(
                    "unresolved_cross_reference",
                    f"cut_in portrait {portrait.portrait_id} takes its identity from "
                    f"{portrait.subject.actor_id!r}, which is not this member's encounter boss",
                )
    if runner.member.cast.avatar_id != runner.avatar.avatar.avatar_id:
        raise GamePackageValidationError(
            "unresolved_cross_reference",
            "runner cast avatar_id must equal the avatar catalog's avatar",
        )
    avatar = runner.avatar.avatar
    if (
        avatar.silhouette_mode == "visible_rider_machine_v1"
        and avatar.body_kind not in game.proportion.by_body_kind
    ):
        raise GamePackageValidationError(
            "invalid_runner_avatar",
            "a visible rider-and-machine avatar requires an explicit "
            f"proportion.by_body_kind.{avatar.body_kind} override measured in visible rider heads",
        )
    if runner.gameplay.track_id != runner.track.track_id:
        raise GamePackageValidationError(
            "unresolved_cross_reference",
            "runner gameplay track_id must equal the track member's track_id",
        )
    prop_ids = {entry.prop_id for entry in runner.props.props}
    item_ids = {entry.item_id for entry in runner.items.items}
    assert_subset(
        {hazard.prop_id for chunk in runner.track.segments.chunks for hazard in chunk.hazards},
        prop_ids,
        "segment hazard prop_id",
    )
    assert_subset(
        {pickup.item_id for chunk in runner.track.segments.chunks for pickup in chunk.pickups},
        item_ids,
        "segment pickup item_id",
    )

    gameplay = runner.gameplay
    jump = gameplay.jump_profile()
    speed = gameplay.speed_profile()
    collision = gameplay.collision_profile()
    duck = gameplay.duck_profile()
    placement = PLACEMENT_PROFILES[RUNNER_PLACEMENT_PROFILE]
    arc = jump_arc(jump, speed)
    apron = apron_columns(jump, placement, speed)
    player_height_rows = game.scale.player_height_tiles
    prop_height_rows: dict[str, float | None] = {
        entry.prop_id: (
            None if entry.height_units is None else entry.height_units * player_height_rows
        )
        for entry in runner.props.props
    }

    declares_overhead = any(
        hazard.anchor == "overhead"
        for chunk in runner.track.segments.chunks
        for hazard in chunk.hazards
    )
    if declares_overhead and duck is None:
        raise GamePackageValidationError(
            "invalid_runner_gameplay",
            "track hangs overhead hazards; gameplay declares no duck_profile to clear them",
        )
    declared_states = declared_motion_states(runner.avatar.avatar)
    if duck is not None and "slide" not in declared_states:
        raise GamePackageValidationError(
            "invalid_runner_avatar",
            "gameplay declares a duck_profile; the avatar declares no slide motion to wear",
        )
    if duck is None and "slide" in declared_states:
        # The coupling holds in both directions: the recipe fans out and pays
        # for every declared strip, so a slide no duck profile can ever
        # trigger would be silent dead spend, not staged art.
        raise GamePackageValidationError(
            "invalid_runner_avatar",
            "avatar declares a slide motion but gameplay declares no duck_profile to trigger it",
        )

    # The same triangle for how a survivable blow is shown. `docs/game-contract.md`
    # requires visible gameplay to have visual coverage: a subsystem may not
    # advertise an actor transition without either a validated asset or an
    # explicitly contracted nonvisual representation. `blink_v1` is that
    # contracted representation and owes no art; `drawn_v1` owes the strip.
    # Both directions are refused, because a paid hurt pose nothing plays is
    # dead spend exactly as an untriggerable slide is.
    vitals = gameplay.run.vitals
    representation = None if vitals is None else vitals.hurt_representation
    if representation == "drawn_v1" and "hurt" not in declared_states:
        raise GamePackageValidationError(
            "invalid_runner_avatar",
            'gameplay declares hurt_representation = "drawn_v1"; '
            "the avatar declares no hurt motion to wear",
        )
    if representation != "drawn_v1" and "hurt" in declared_states:
        raise GamePackageValidationError(
            "invalid_runner_avatar",
            "avatar declares a hurt motion but gameplay does not declare "
            'hurt_representation = "drawn_v1" to play it',
        )

    # The encounter's own triangles. A boss is the most expensive thing a
    # runner package can author - a concept plate, three strips, a rebase
    # judgement and two projectiles - so every half of the obligation is
    # refused here, offline, rather than discovered when the graph has already
    # fanned out or, worse, when the run is played.
    encounter = gameplay.encounter
    arena_ids = {chunk.segment_id for chunk in runner.track.segments.arena_chunks()}
    if encounter is not None and "fly" not in declared_states:
        raise GamePackageValidationError(
            "invalid_runner_avatar",
            "gameplay declares an encounter; the avatar declares no fly motion to wear",
        )
    if encounter is None and "fly" in declared_states:
        raise GamePackageValidationError(
            "invalid_runner_avatar",
            "avatar declares a fly motion but gameplay declares no encounter to trigger it",
        )
    if encounter is None:
        if runner.bosses is not None:
            raise GamePackageValidationError(
                "invalid_runner_boss",
                "package declares a boss catalog but gameplay declares no encounter to fight it",
            )
        if runner.projectiles is not None:
            raise GamePackageValidationError(
                "invalid_projectile_content",
                "package declares projectiles but gameplay declares no encounter to fire them",
            )
        if arena_ids:
            raise GamePackageValidationError(
                "invalid_runner_track",
                "track authors arena chunks no encounter is fought over: "
                + ", ".join(sorted(arena_ids)),
            )
    else:
        if runner.bosses is None:
            raise GamePackageValidationError(
                "unresolved_cross_reference",
                "gameplay declares an encounter but the package declares no boss catalog",
            )
        if runner.projectiles is None:
            raise GamePackageValidationError(
                "unresolved_cross_reference",
                "gameplay declares an encounter but the package declares no projectile catalog",
            )
        assert_subset(
            {encounter.boss_id},
            {entry.boss_id for entry in runner.bosses.bosses},
            "encounter boss_id",
        )
        assert_subset({encounter.arena_segment_id}, arena_ids, "encounter arena_segment_id")
        projectile_ids = {entry.projectile_id for entry in runner.projectiles.projectiles}
        named_projectiles = {encounter.boss_projectile_id, encounter.player_projectile_id}
        assert_subset(named_projectiles, projectile_ids, "encounter projectile_id")
        # The runner has exactly two projectile roles and no second weapon, so
        # an unnamed projectile is art nothing can ever put in the air. The
        # platformer deliberately tolerates the same shape because its weapon
        # class is a runtime choice; here there is nothing to choose.
        unfired = sorted(projectile_ids - named_projectiles)
        if unfired:
            raise GamePackageValidationError(
                "invalid_projectile_content",
                "package draws projectiles no encounter fires: " + ", ".join(unfired),
            )
        unfought = sorted(arena_ids - {encounter.arena_segment_id})
        if unfought:
            raise GamePackageValidationError(
                "invalid_runner_track",
                "track authors arena chunks the encounter is not fought over: "
                + ", ".join(unfought),
            )
        unmatched = sorted({entry.boss_id for entry in runner.bosses.bosses} - {encounter.boss_id})
        if unmatched:
            raise GamePackageValidationError(
                "invalid_runner_boss",
                "package draws bosses no encounter fights: " + ", ".join(unmatched),
            )
        _validate_runner_encounter(
            encounter=encounter,
            walk_surface_row=runner.track.segments.walk_surface_row,
            player_height_rows=player_height_rows,
            placement=placement,
        )

    segments = runner.track.segments
    for chunk in segments.chunks:
        if chunk.role == "arena":
            # An arena is flat, empty and seam-profiled in every column, which
            # the track contract already proved. Every proof below is about
            # reacting to authored terrain, and there is none here: the demand
            # during an encounter is the boss, proved by the encounter itself.
            continue
        _validate_runner_chunk(
            chunk=chunk,
            segments=segments,
            gameplay=gameplay,
            arc=arc,
            apron=apron,
            placement=placement,
            speed=speed,
            collision=collision,
            duck=duck,
            player_height_rows=player_height_rows,
            prop_height_rows=prop_height_rows,
        )


def _validate_runner_encounter(
    *,
    encounter: RunnerEncounter,
    walk_surface_row: int,
    player_height_rows: float,
    placement: PlacementProfile,
) -> None:
    """Prove one encounter survivable and winnable, closed form, before any spend.

    Three refusals, in the order a player meets them: the salvo must leave a
    lane the avatar fits through, the avatar must have time to reach it, and
    the boss must be defeatable before its own budget ends the fight. Every
    number comes from the named profiles, so a package cannot buy fairness by
    lowering a threshold - only by naming a different profile or authoring a
    taller band.
    """

    boss = encounter.boss_profile()
    thrust = encounter.thrust_profile()

    lane = boss_lane_rows(boss, walk_surface_row)
    required = player_height_rows + boss.lane_margin_rows
    if lane < required:
        raise GamePackageValidationError(
            "segment_hazard_unclearable",
            f"encounter {encounter.profile} fires {boss.salvo_shots} shots of "
            f"{boss.projectile_height_rows} rows into a {walk_surface_row}-row band, leaving a "
            f"{lane:.2f}-row lane; the avatar needs {required:.2f} rows "
            f"({player_height_rows:.2f} plus {boss.lane_margin_rows} of margin)",
        )

    window = boss_dodge_window_seconds(boss, thrust, walk_surface_row=walk_surface_row)
    if window < placement.min_hazard_clear_seconds:
        raise GamePackageValidationError(
            "segment_hazard_unclearable",
            f"encounter {encounter.profile} leaves {window:.3f}s to cross the band under "
            f"{encounter.locomotion}; the placement discipline demands "
            f"{placement.min_hazard_clear_seconds}s",
        )

    kill = boss_kill_seconds(boss)
    budget = boss_salvo_budget_seconds(boss)
    if kill > budget:
        raise GamePackageValidationError(
            "invalid_runner_gameplay",
            f"encounter {encounter.profile} needs {kill:.2f}s to defeat its boss but retreats "
            f"after {budget:.2f}s; the fight cannot be won",
        )


def _validate_runner_chunk(
    *,
    chunk: RunnerSegmentChunk,
    segments: RunnerSegments,
    gameplay: RunnerGameplayContract,
    arc: JumpArc,
    apron: int,
    placement: PlacementProfile,
    speed: SpeedProfile,
    collision: CollisionProfile,
    duck: DuckProfile | None,
    player_height_rows: float,
    prop_height_rows: dict[str, float | None],
) -> None:
    """Prove one chunk against the seam rule, the arc, and the placement discipline."""

    jump = gameplay.jump_profile()
    width = len(chunk.occupancy[0])
    heights = [bottom_contiguous_surface_row(chunk.occupancy, column) for column in range(width)]

    # The seam rule: any chunk may follow any chunk, so both seam columns must
    # be exactly empty above the shared walk surface and solid from that row
    # down. Looking only at the bottom-connected stack would admit a detached
    # floating solid above an otherwise valid edge; structural-ground guide
    # construction would then reject it after provider nodes had fanned out.
    # Keep the stricter proof here, offline, before any spend.
    expected_seam = seam_profile(len(chunk.occupancy), segments.walk_surface_row)
    for label, column in (("first", 0), ("last", width - 1)):
        actual_seam = [row[column] for row in chunk.occupancy]
        if actual_seam != expected_seam:
            raise GamePackageValidationError(
                "segment_seam_mismatch",
                f"segment {chunk.segment_id} {label} column must be empty above and solid "
                f"from walk_surface_row {segments.walk_surface_row} down",
            )

    widest = chunk.max_pit_run()
    if widest > jump.max_clear_gap_columns:
        raise GamePackageValidationError(
            "segment_gap_unclearable",
            f"segment {chunk.segment_id} has a {widest}-column pit; "
            f"{gameplay.run.jump_profile} clears at most {jump.max_clear_gap_columns}",
        )

    # The apron: one flat jump span of calm walk-surface ground at each end,
    # which is the price of keeping the seam rule cross-chunk-check-free - a
    # landing or a demand near a seam would otherwise meet the next chunk's
    # opening obstacle with no surviving launch frame.
    hazard_columns = {hazard.column for hazard in chunk.hazards}
    for column in (*range(min(apron, width)), *range(max(0, width - apron), width)):
        if heights[column] != segments.walk_surface_row:
            raise GamePackageValidationError(
                "segment_placement_violation",
                f"segment {chunk.segment_id} column {column} sits inside the {apron}-column "
                "apron and must present the shared walk surface",
            )
        if column in hazard_columns:
            raise GamePackageValidationError(
                "segment_placement_violation",
                f"segment {chunk.segment_id} places a hazard at column {column}, inside the "
                f"{apron}-column apron",
            )

    # Jump features: every consecutive supported pair, adjacent or across a
    # pit, must be within the arc - a rise steals airtime, so the span and the
    # rise are proved together rather than as two independent bounds.
    supported = [(column, surface) for column, surface in enumerate(heights) if surface is not None]
    jump_landings: list[int] = []
    feature_columns: set[int] = set()
    for (left_column, left_surface), (right_column, right_surface) in pairwise(supported):
        rise = left_surface - right_surface  # positive is up
        if rise > jump.max_rise_tiles:
            raise GamePackageValidationError(
                "invalid_runner_track",
                f"segment {chunk.segment_id} rises more than {jump.max_rise_tiles} tiles "
                f"at column {right_column}",
            )
        gap = right_column - left_column - 1
        if gap > 0:
            span = clearable_span_columns(arc, speed, rise)
            if span is None or gap + 1 > span:
                raise GamePackageValidationError(
                    "segment_gap_unclearable",
                    f"segment {chunk.segment_id} pairs a {gap}-column pit with a {rise}-tile "
                    f"rise at column {right_column}; {gameplay.run.jump_profile} spans "
                    f"{0.0 if span is None else round(span, 2)} columns at that rise",
                )
            jump_landings.append(right_column)
            feature_columns.update(range(left_column + 1, right_column))
        elif rise > 0:
            jump_landings.append(right_column)
            feature_columns.add(right_column)
        elif rise < 0:
            # A drop-off is a landing with no launch: the run leaves the ledge
            # at full speed and touches down inside a scatter zone no verb can
            # shorten. The whole zone must be level and calm at the cap speed,
            # and the drop edge is a terrain feature like any other demand.
            feature_columns.add(right_column)
            scatter = drop_scatter_columns(arc, speed, float(-rise))
            zone_end = min(width, right_column + scatter + placement.min_landing_clear_columns)
            for column in range(right_column, zone_end):
                if heights[column] != right_surface:
                    raise GamePackageValidationError(
                        "segment_placement_violation",
                        f"segment {chunk.segment_id} drop at column {right_column} lands on "
                        f"unlevel or missing ground at column {column}; its scatter zone "
                        f"spans {scatter} columns plus clearance",
                    )

    # Landing clearance: calm, level, hazard-free ground after every landing.
    # A window that runs off the chunk's edge is already proven calm by the
    # end apron, which the placement profile guarantees is at least as wide.
    for landing in jump_landings:
        for column in range(landing, min(width, landing + placement.min_landing_clear_columns)):
            if heights[column] != heights[landing]:
                raise GamePackageValidationError(
                    "segment_placement_violation",
                    f"segment {chunk.segment_id} landing at column {landing} lacks "
                    f"{placement.min_landing_clear_columns} level columns of clearance",
                )
            if column in hazard_columns:
                raise GamePackageValidationError(
                    "segment_placement_violation",
                    f"segment {chunk.segment_id} places a hazard at column {column}, inside "
                    f"the landing clearance of the jump landing at column {landing}",
                )

    # Hazard clusters: adjacent same-anchor hazards read as one silhouette and
    # are proved as one demand; everything else must stand a full separation
    # apart, from each other and from every terrain feature, so no two demands
    # ever share one arc uninvited.
    ordered = sorted(chunk.hazards, key=lambda hazard: hazard.column)
    clusters: list[list[RunnerHazard]] = []
    for hazard in ordered:
        if (
            clusters
            and hazard.anchor == clusters[-1][-1].anchor
            and hazard.column - clusters[-1][-1].column <= 1
        ):
            clusters[-1].append(hazard)
        else:
            clusters.append([hazard])
    for previous, current in pairwise(clusters):
        distance = current[0].column - previous[-1].column
        if distance < placement.min_hazard_separation_columns:
            raise GamePackageValidationError(
                "segment_placement_violation",
                f"segment {chunk.segment_id} places hazards {distance} columns apart at "
                f"columns {previous[-1].column} and {current[0].column}; the placement "
                f"discipline demands {placement.min_hazard_separation_columns}",
            )
    for cluster in clusters:
        for feature in sorted(feature_columns):
            distance = min(abs(feature - cluster[0].column), abs(feature - cluster[-1].column))
            if distance < placement.min_hazard_separation_columns:
                raise GamePackageValidationError(
                    "segment_placement_violation",
                    f"segment {chunk.segment_id} places a hazard {distance} columns from the "
                    f"terrain feature at column {feature}; the placement discipline demands "
                    f"{placement.min_hazard_separation_columns}",
                )

    # Terrain demands answer to the same separation as hazards: two features
    # closer than one flown-at-cap arc share a jump uninvited - the pit whose
    # late launches carry into the next rise's face at ramped speed.
    feature_groups: list[list[int]] = []
    for feature in sorted(feature_columns):
        if feature_groups and feature - feature_groups[-1][-1] <= 1:
            feature_groups[-1].append(feature)
        else:
            feature_groups.append([feature])
    for previous_group, current_group in pairwise(feature_groups):
        distance = current_group[0] - previous_group[-1]
        if distance < placement.min_hazard_separation_columns:
            raise GamePackageValidationError(
                "segment_placement_violation",
                f"segment {chunk.segment_id} places terrain features {distance} columns "
                f"apart at columns {previous_group[-1]} and {current_group[0]}; the "
                f"placement discipline demands {placement.min_hazard_separation_columns}",
            )

    # The press-window proof: a surface cluster must leave at least the
    # discipline's clear seconds of launch-timing slack over its tallest
    # member. If the silhouette is wanted at full height, the correct fix is
    # a taller jump profile, not a lowered threshold.
    for cluster in clusters:
        if cluster[0].anchor != "surface":
            continue
        declared = [prop_height_rows[hazard.prop_id] for hazard in cluster]
        if any(height is None for height in declared):
            undeclared = ", ".join(
                hazard.prop_id
                for hazard, height in zip(cluster, declared, strict=True)
                if height is None
            )
            raise GamePackageValidationError(
                "segment_hazard_unclearable",
                f"segment {chunk.segment_id} hazard [{undeclared}] declares no height_units; "
                "the press-window proof needs one",
            )
        tallest = max(height for height in declared if height is not None)
        span_columns = cluster[-1].column - cluster[0].column + 1
        window = hazard_press_window_seconds(
            arc,
            speed,
            collision,
            hazard_height_rows=tallest,
            span_columns=span_columns,
        )
        if window < placement.min_hazard_clear_seconds:
            names = ", ".join(hazard.prop_id for hazard in cluster)
            raise GamePackageValidationError(
                "segment_hazard_unclearable",
                f"segment {chunk.segment_id} hazard cluster [{names}] leaves a "
                f"{max(0.0, round(window, 3))}s press window at base speed; the placement "
                f"discipline demands {placement.min_hazard_clear_seconds}s",
            )

    # The overhead proof: the ground proof with the anchor flipped. A ducked
    # avatar plus daylight must fit beneath the clearance, and the clearance
    # must still refuse a standing run, or the placement is dead art.
    for hazard in chunk.hazards:
        if hazard.anchor != "overhead":
            continue
        assert duck is not None  # refused member-wide before any chunk
        clearance = hazard.clearance_rows
        assert clearance is not None  # refused by the hazard model
        ducked_rows = player_height_rows * duck.ducked_height_fraction
        if clearance < ducked_rows + duck.min_overhead_clearance_rows:
            raise GamePackageValidationError(
                "segment_hazard_unclearable",
                f"segment {chunk.segment_id} hangs {hazard.prop_id} with {clearance} rows of "
                f"clearance; a ducked avatar needs "
                f"{ducked_rows + duck.min_overhead_clearance_rows}",
            )
        if clearance > player_height_rows - duck.min_overhead_clearance_rows:
            raise GamePackageValidationError(
                "invalid_runner_track",
                f"segment {chunk.segment_id} hangs {hazard.prop_id} with {clearance} rows of "
                "clearance, which admits a standing run and obstructs nothing",
            )

    # The telegraph: under `pickup_arc_v1`, every jump demand carries its own
    # trail - at least three pickups on the arc the clearance proof flew, so
    # greed walks the player down the safe line on first sight.
    if placement.telegraph == "pickup_arc_v1":

        def pickups_on_arc(launch: int) -> int:
            launch_surface = heights[launch]
            if launch_surface is None:
                return 0
            span = clearable_span_columns(arc, speed, 0)
            assert span is not None
            on_arc = 0
            for pickup in chunk.pickups:
                offset = pickup.column - launch
                if offset < 0 or offset > span:
                    continue
                pickup_height = launch_surface - (pickup.row + 0.5)
                expected = arc_height_rows(arc, speed, offset)
                if abs(pickup_height - expected) <= 0.9:
                    on_arc += 1
            return on_arc

        for (left_column, left_surface), (right_column, right_surface) in pairwise(supported):
            rise = left_surface - right_surface
            gap = right_column - left_column - 1
            if gap <= 0 and rise <= 0:
                continue
            launch = left_column if gap > 0 else right_column - 1
            if pickups_on_arc(launch) < 3:
                raise GamePackageValidationError(
                    "segment_untelegraphed",
                    f"segment {chunk.segment_id} demands a jump at column {launch} but "
                    f"places fewer than 3 pickups on its arc; pickup_arc_v1 demands 3",
                )
        # A surface hazard is a jump demand too, and its trail is the only
        # channel that teaches it on first sight. The launch is wherever the
        # authored arc leaves the ground, one to three columns before the
        # cluster - any of those telling the truth satisfies the telegraph.
        for cluster in clusters:
            if cluster[0].anchor != "surface":
                continue
            candidates = range(max(0, cluster[0].column - 3), cluster[0].column)
            if all(pickups_on_arc(launch) < 3 for launch in candidates):
                raise GamePackageValidationError(
                    "segment_untelegraphed",
                    f"segment {chunk.segment_id} demands a jump over the hazard at column "
                    f"{cluster[0].column} but no launch carries 3 pickups on its arc; "
                    "pickup_arc_v1 demands the trail",
                )


__all__ = [
    "RUNNER_BASE_FX_MOMENTS",
    "ResolvedRunnerMember",
    "resolve_runner_member",
    "runner_fx_moments",
]
