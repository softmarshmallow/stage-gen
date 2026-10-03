"""Iron Petal Unit's asset build: the game's package, read by the game, written as steps.

    gnode plan pipeline/workflow.py:build --arg package=inputs
    gnode run  pipeline/workflow.py:build --arg package=inputs --live --max-usd 80 \\
        --deliver package=../../../out/iron-petal/{key}

The game's reader resolves its own TOML package, unchanged, and this builder writes one group
of steps per asset: the ground chunks and their shared seam, the scrolling layers, the avatar
and each boss (a concept, a strip per state, two rebase readings), the catalog, the
soundtrack, the one-shot audio, the cut-in plates and the dust atlas. Every painting or draw
is judged by the game's own admission and drawn again when it fails. The last step lays every
published file out at the path the Godot host reads it from and writes ``manifest.json``;
``godot --path godot/games/iron_petal_unit -- --run <dir>`` plays the delivered folder.

The package must sit inside this project (the folder holding ``gnode.yaml``): its authored
references are project files, read by content.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from demo_game_tools.kits.effects_art.directions import (
    cut_in_artifact_refs,
    plate_id_for,
    sprite_dust_artifact_refs,
)
from demo_game_tools.kits.effects_art.models import CutInPortraitSubject
from demo_game_tools.kits.sideview_actor.motion_geometry import DEFAULT_MOTION_ATLAS_GEOMETRY
from demo_game_tools.media.soundtrack.prompt import music_track_prompt
from demo_game_tools.steps.effects import add_cut_in_steps, add_dust_steps
from demo_game_tools.steps.layers import add_layer_steps
from demo_game_tools.steps.rebase import add_rebase_steps
from demo_game_tools.steps.soundtrack import add_track_steps
from demo_game_tools.steps.terrain_atlas import add_atlas_steps
from gnode import Group, StepRef, Workflow
from iron_petal_unit_pipeline.admission import RUNNER_LAYER_GATE
from iron_petal_unit_pipeline.audio.realizations import (
    GeneratedClipRealization,
    SpokenLineRealization,
)
from iron_petal_unit_pipeline.content import (
    RUNNER_BOSS_BASELINE_STATE,
    declared_boss_motion_states,
    declared_motion_states,
)
from iron_petal_unit_pipeline.manifest import runner_material_identity
from iron_petal_unit_pipeline.runner_prompts import (
    avatar_concept_prompt,
    avatar_motion_prompt,
    boss_concept_prompt,
    boss_motion_prompt,
    catalog_asset_prompt,
    fx_plate_prompt,
    ground_prompt,
    layer_loop_prompt,
    layer_prompt,
    soundtrack_direction,
    structural_ground_prompt,
)
from iron_petal_unit_pipeline.runner_request import ResolvedRunnerPackage, resolve_runner_package
from iron_petal_unit_pipeline.track import (
    STRUCTURAL_GROUND_GUIDE_HEIGHT,
    STRUCTURAL_GROUND_GUIDE_WIDTH,
    RunnerStructuralGround,
)

#: The game's node modules, as project paths.
GROUND = "./pipeline/nodes/ground.py"
ACTORS = "./pipeline/nodes/actors.py"
CATALOG = "./pipeline/nodes/catalog.py"
AUDIO = "./pipeline/nodes/audio.py"
PACKAGE = "./pipeline/nodes/package.py"
LAYERS = "./pipeline/nodes/layers.py"
REBASE = "./pipeline/nodes/rebase.py"
SOUNDTRACK = "./pipeline/nodes/soundtrack.py"
EFFECTS = "./pipeline/nodes/effects.py"

#: Draws a judged painting or clip gets before the run stops on it.
TAKES = 6
#: The avatar's baseline: every other strip is rebased against its run.
AVATAR_BASELINE_STATE = "run"
#: The most one build of the shipped package may cost, every redraw included.
BUDGET_USD = 80.0

_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_REDRAW = {"regenerate": {"max": TAKES, "then": "fail"}}


def _name(value: str) -> str:
    if not _NAME.fullmatch(value):
        raise ValueError(f"{value!r} cannot name a step: write it in lower_snake_case")
    return value


def _project_root(package: Path) -> Path:
    for folder in (package, *package.parents):
        if (folder / "gnode.yaml").is_file():
            return folder
    raise ValueError(f"{package} is not inside a gnode project")


def _paint(
    group: Group,
    *,
    title: str,
    prompt: str,
    size: str,
    background: str,
    pictures: list[Any],
) -> StepRef:
    """One painting: an edit of its first picture when it has any, else from text alone."""

    with_: dict[str, Any] = {"prompt": prompt, "size": size, "background": background}
    if pictures:
        with_["image"] = pictures[0]
        with_["references"] = pictures[1:]
    return group.step(
        "generate",
        title=title,
        uses="gnode/image.edit@1" if pictures else "gnode/image.generate@1",
        with_=with_,
        requires=["transparent_background"] if background == "transparent" else [],
        view=True,
    )


class _Build:
    """One package's steps, and every file the runtime package publishes, by runtime path."""

    def __init__(self, resolved: ResolvedRunnerPackage, root: Path, project: Path) -> None:
        self.resolved = resolved
        self.runner = resolved.runner
        self.track = resolved.runner.track
        self.root = root
        self.project = project
        self.published: dict[str, Any] = {}
        #: Authored references the manifest names, republished at their package paths.
        self.references: set[str] = set()
        #: Each boss's concept painting: what a cut-in portrait of it copies.
        self.boss_concepts: dict[str, StepRef] = {}

    def path(self, source: str) -> str:
        """A package file as a project path, read by content."""

        return "./" + (self.root / source).relative_to(self.project).as_posix()

    def route(self, capability: str) -> str:
        """The project's route for a capability, as ``gnode.yaml`` declares it."""

        project = yaml.safe_load((self.project / "gnode.yaml").read_text(encoding="utf-8"))
        route = (project.get("routes") or {}).get(capability)
        if not isinstance(route, str):
            raise ValueError(f"gnode.yaml declares no route for {capability}")
        return route

    def publish(self, runtime_path: str, value: Any) -> None:
        if runtime_path in self.published:
            raise ValueError(f"two steps publish {runtime_path}")
        self.published[runtime_path] = value

    # ---------------------------------------------------------------- ground

    def ground(self, wf: Workflow) -> None:
        group = wf.group("ground", title="Ground")
        sources = {entry.reference_id: entry.source for entry in self.track.references}
        ground = self.track.ground
        materials = [self.path(sources[reference_id]) for reference_id in ground.reference_ids]
        if not isinstance(ground, RunnerStructuralGround):
            self._atlas(group, materials)
            return
        segments = self.track.segments
        material_identity = runner_material_identity(self.resolved)
        chunks: list[tuple[str, Group, dict[str, Any], StepRef, StepRef]] = []
        for chunk in segments.chunks:
            chunk_group = group.group(_name(chunk.segment_id), title=f"Chunk {chunk.segment_id}")
            facts = {
                "segment_id": chunk.segment_id,
                "occupancy": list(chunk.occupancy),
                "walk_surface_row": segments.walk_surface_row,
                "material_identity": material_identity,
            }
            guide = chunk_group.step(
                "guide",
                title="Compose the occupancy guide",
                uses=f"{GROUND}#structural_guide",
                with_={**facts, "material": materials},
                view=True,
            )
            painting = _paint(
                chunk_group,
                title="Paint over the guide",
                prompt=structural_ground_prompt(self.resolved, self.track, chunk),
                size=f"{STRUCTURAL_GROUND_GUIDE_WIDTH}x{STRUCTURAL_GROUND_GUIDE_HEIGHT}",
                background="transparent",
                pictures=[guide.outputs.image, *materials],
            )
            chunk_group.step(
                "admit",
                title="Hold the painting to the guide",
                uses=f"{GROUND}#admit_structural",
                judges="generate",
                with_={
                    **facts,
                    "image": painting.outputs.image,
                    "guide": guide.outputs.image,
                    "material": materials,
                    "projection": ground.projection_mode(),
                },
                on_reject=_REDRAW,
            )
            chunks.append((chunk.segment_id, chunk_group, facts, guide, painting))
        # The first chunk's painted right apron becomes the seam every chunk shares.
        first_facts, first_guide, first_painting = chunks[0][2:]
        bridge = group.step(
            "seam_bridge",
            title="Take the shared seam",
            uses=f"{GROUND}#seam_bridge",
            with_={
                **first_facts,
                "raw": first_painting.outputs.image,
                "guide": first_guide.outputs.image,
                "material": materials,
            },
            view=True,
        )
        self.publish("world/ground/shared-seam-bridge.png", bridge.outputs.image)
        self.publish("world/ground/shared-seam-bridge.validation.json", bridge.outputs.validation)
        for segment_id, chunk_group, facts, guide, painting in chunks:
            published = chunk_group.step(
                "publish",
                title="Mask it and install the seam",
                uses=f"{GROUND}#canonicalize_structural",
                with_={
                    **facts,
                    "raw": painting.outputs.image,
                    "guide": guide.outputs.image,
                    "bridge": bridge.outputs.image,
                    "material": materials,
                },
                view=True,
            )
            self.publish(f"world/ground/{segment_id}.png", published.outputs.image)
            self.publish(f"world/ground/{segment_id}.validation.json", published.outputs.validation)

    def _atlas(self, group: Group, materials: list[str]) -> None:
        prompt = ground_prompt(self.resolved, self.track)
        steps = add_atlas_steps(group, nodes=GROUND, prompt=prompt, materials=materials)
        self.publish("world/ground.png", steps["publish"].outputs.image)
        self.publish("world/ground.validation.json", steps["publish"].outputs.validation)

    # ---------------------------------------------------------------- layers

    def layers(self, wf: Workflow) -> None:
        sources = {entry.reference_id: entry.source for entry in self.track.references}
        group = wf.group("layers", title="Scrolling layers")
        for layer in self.track.layers:
            construction = layer.loop_construction or self.track.continuity.loop_construction
            steps = add_layer_steps(
                group.group(_name(layer.layer_id), title=f"Layer {layer.layer_id}"),
                nodes=LAYERS,
                references=[self.path(sources[ref_id]) for ref_id in layer.reference_ids],
                prompt=layer_prompt(
                    self.resolved, layer.prompt, transparent=layer.alpha_mode == "transparent"
                ),
                size="1536x1024",
                layer=layer.model_dump(mode="json"),
                construction=construction,
                fallback=self.track.continuity.loop_fallback,
                label=f"{self.track.track_id}/{layer.layer_id}",
                loop_prompt=layer_loop_prompt(layer.prompt),
                gate=RUNNER_LAYER_GATE,
                # The opaque cover ships as painted and is placed by its anchor alone.
                place_opaque=False,
            )
            published = steps["publish"]
            self.publish(f"world/layers/{layer.layer_id}.png", published.outputs.image)
            self.publish(
                f"world/layers/{layer.layer_id}.validation.json", published.outputs.validation
            )

    # ---------------------------------------------------------------- actors

    def _actor(
        self,
        group: Group,
        *,
        folder: str,
        display_name: str,
        concept_prompt: str,
        references: list[str],
        motions: dict[str, tuple[str, str]],
        baseline_state: str,
    ) -> StepRef:
        """A concept, one strip per state (prompt and anchor), and the two rebase readings."""

        concept_group = group.group("concept", title="Identity concept")
        concept = _paint(
            concept_group,
            title="Draw the identity concept",
            prompt=concept_prompt,
            size="1024x1536",
            background="transparent",
            pictures=list(references),
        )
        concept_group.step(
            "admit",
            title="Admit the cut-out",
            uses=f"{ACTORS}#admit_concept",
            judges="generate",
            with_={"image": concept.outputs.image},
            on_reject=_REDRAW,
        )
        self.publish(f"{folder}/concept.png", concept.outputs.image)
        atlases: dict[str, Any] = {}
        for state, (prompt, anchor) in motions.items():
            state_group = group.group(_name(state), title=f"The {state} strip")
            strip = _paint(
                state_group,
                title=f"Draw the {state} strip",
                prompt=prompt,
                size=DEFAULT_MOTION_ATLAS_GEOMETRY.provider_size,
                background="transparent",
                pictures=[concept.outputs.image],
            )
            state_group.step(
                "admit",
                title="Admit every cell",
                uses=f"{ACTORS}#admit_motion",
                judges="generate",
                with_={"image": strip.outputs.image, "anchor": anchor},
                on_reject=_REDRAW,
            )
            repacked = state_group.step(
                "publish",
                title="Repack into canonical cells",
                uses=f"{ACTORS}#repack_motion",
                with_={"raw": strip.outputs.image, "state": state, "anchor": anchor},
                view=True,
            )
            atlases[state] = repacked.outputs.image
            self.publish(f"{folder}/{state}.png", repacked.outputs.image)
            self.publish(f"{folder}/{state}.validation.json", repacked.outputs.validation)
        geometry = DEFAULT_MOTION_ATLAS_GEOMETRY
        rebase = add_rebase_steps(
            group.group("rebase", title="Rebase every state to the baseline"),
            nodes=REBASE,
            display_name=display_name,
            states=list(motions),
            baseline_state=baseline_state,
            geometry={state: (geometry.columns, geometry.rows) for state in motions},
            atlases=atlases,
        )
        self.publish(f"{folder}/rebase-verification.json", rebase["record"].outputs.record)
        return concept

    def avatar(self, wf: Workflow) -> None:
        avatar = self.runner.avatar.avatar
        sources = {entry.reference_id: entry.source for entry in self.runner.avatar.references}
        anchors = {entry.state: entry.anchor for entry in avatar.motions}
        self._actor(
            wf.group("avatar", title=f"Avatar {avatar.display_name}"),
            folder="avatar",
            display_name=avatar.display_name,
            concept_prompt=avatar_concept_prompt(self.resolved, avatar),
            references=[self.path(sources[reference_id]) for reference_id in avatar.reference_ids],
            motions={
                state: (avatar_motion_prompt(self.resolved, avatar, state), anchors[state])
                for state in declared_motion_states(avatar)
            },
            baseline_state=AVATAR_BASELINE_STATE,
        )

    def bosses(self, wf: Workflow) -> None:
        if self.runner.bosses is None:
            return
        sources = {entry.reference_id: entry.source for entry in self.runner.bosses.references}
        group = wf.group("bosses", title="Bosses")
        for boss in self.runner.bosses.bosses:
            anchors = {entry.state: entry.anchor for entry in boss.motions}
            self.boss_concepts[boss.boss_id] = self._actor(
                group.group(_name(boss.boss_id), title=f"Boss {boss.display_name}"),
                folder=f"boss/{boss.boss_id}",
                display_name=boss.display_name,
                concept_prompt=boss_concept_prompt(self.resolved, boss),
                references=[self.path(sources[ref_id]) for ref_id in boss.reference_ids],
                motions={
                    state: (boss_motion_prompt(self.resolved, boss, state), anchors[state])
                    for state in declared_boss_motion_states(boss)
                },
                baseline_state=RUNNER_BOSS_BASELINE_STATE,
            )

    # --------------------------------------------------------------- catalog

    def catalog(self, wf: Workflow) -> None:
        families: list[tuple[str, list[tuple[str, str, list[str], str | None]], dict[str, str]]] = [
            (
                "prop",
                [(e.prop_id, e.prompt, e.reference_ids, None) for e in self.runner.props.props],
                {e.reference_id: e.source for e in self.runner.props.references},
            ),
            (
                "item",
                [(e.item_id, e.prompt, e.reference_ids, None) for e in self.runner.items.items],
                {e.reference_id: e.source for e in self.runner.items.references},
            ),
        ]
        projectiles = self.runner.projectiles
        if projectiles is not None:
            # A thrown object is the one catalog subject the runtime moves, so the axis it was
            # drawn along is part of the direction rather than a detail.
            families.append(
                (
                    "projectile",
                    [
                        (e.projectile_id, e.prompt, e.reference_ids, e.silhouette)
                        for e in projectiles.projectiles
                    ],
                    {e.reference_id: e.source for e in projectiles.references},
                )
            )
        for family, entries, sources in families:
            if not entries:
                continue
            group = wf.group(f"{family}s", title=f"{family.capitalize()}s")
            for entity_id, prompt_text, reference_ids, silhouette in entries:
                entity = group.group(_name(entity_id), title=f"The {entity_id} {family}")
                painting = _paint(
                    entity,
                    title=f"Draw the {family}",
                    prompt=catalog_asset_prompt(
                        self.resolved, family=family, prompt_text=prompt_text, silhouette=silhouette
                    ),
                    size="1024x1024",
                    background="transparent",
                    pictures=[self.path(sources[reference_id]) for reference_id in reference_ids],
                )
                entity.step(
                    "admit",
                    title="Admit the cut-out",
                    uses=f"{CATALOG}#admit_catalog",
                    judges="generate",
                    with_={"image": painting.outputs.image, "family": family},
                    on_reject=_REDRAW,
                )
                published = entity.step(
                    "publish",
                    title="Trim it",
                    uses=f"{CATALOG}#publish_catalog",
                    with_={"raw": painting.outputs.image, "family": family, "entity_id": entity_id},
                    view=True,
                )
                self.publish(f"catalog/{family}s/{entity_id}.png", published.outputs.image)
                self.publish(
                    f"catalog/{family}s/{entity_id}.validation.json", published.outputs.validation
                )

    # ----------------------------------------------------------------- audio

    def soundtrack(self, wf: Workflow) -> None:
        soundtrack = self.runner.soundtrack
        if soundtrack is None:
            return
        group = wf.group("soundtrack", title="Soundtrack")
        for track_id in soundtrack.track_ids:
            track = soundtrack.track(track_id)
            steps = add_track_steps(
                group.group(_name(track_id), title=f"Track {track_id}"),
                nodes=SOUNDTRACK,
                track_id=track_id,
                prompt=music_track_prompt(
                    medium="a 2D game",
                    game_id=self.resolved.package.game.game_id,
                    track_id=track_id,
                    creative_brief=track.creative_brief,
                    generation=track.generation,
                    direction=soundtrack_direction(),
                ),
                target_duration_seconds=track.generation.target_duration_seconds,
                instrumental=track.generation.instrumental,
                seamless_loop=track.generation.seamless_loop,
            )
            self.publish(f"soundtrack/{track_id}.mp3", steps["generate"].outputs.audio)
            self.publish(
                f"soundtrack/{track_id}.validation.json", steps["record"].outputs.validation
            )

    def sounds(self, wf: Workflow) -> None:
        effects = self.runner.audio.generated_effects()
        if not effects:
            return
        group = wf.group("sounds", title="Sound effects")
        for effect in effects:
            clip = effect.realization
            assert isinstance(clip, GeneratedClipRealization)
            _first_take(effect.effect_id, clip.take)
            entity = group.group(_name(effect.effect_id), title=f"The {effect.effect_id} clip")
            if clip.pinned is not None:
                audio = self._pinned(entity, effect.effect_id, clip.pinned, spoken=False)
            else:
                draw = entity.step(
                    "generate",
                    title="Generate the clip",
                    # The authored text is the entire prompt; playback gain stays out of it, so
                    # a rebalance after listening is never a redraw.
                    uses="gnode/sound.generate@1",
                    with_={
                        "prompt": clip.prompt,
                        "duration": clip.duration_seconds,
                        "loop": False,
                        **(
                            {}
                            if clip.prompt_influence is None
                            else {"prompt_influence": clip.prompt_influence}
                        ),
                    },
                    requires=["exact_duration"],
                    view=True,
                )
                entity.step(
                    "admit",
                    title="Admit the payload and its level",
                    uses=f"{AUDIO}#admit_clip",
                    judges="generate",
                    with_={"audio": draw.outputs.audio},
                    on_reject=_REDRAW,
                )
                audio = draw.outputs.audio
                self.publish(f"audio/{effect.effect_id}.mp3", audio)
            record = entity.step(
                "record",
                title="Measure it",
                uses=f"{AUDIO}#record_clip",
                with_={
                    "audio": audio,
                    "effect_id": effect.effect_id,
                    "duration_seconds": clip.duration_seconds,
                    "pinned": clip.pinned is not None,
                },
            )
            self.publish(f"audio/{effect.effect_id}.validation.json", record.outputs.validation)

    def lines(self, wf: Workflow) -> None:
        lines = self.runner.audio.spoken_lines()
        if not lines:
            return
        group = wf.group("lines", title="Spoken lines")
        for effect in lines:
            line = effect.realization
            assert isinstance(line, SpokenLineRealization)
            _first_take(effect.effect_id, line.take)
            entity = group.group(_name(effect.effect_id), title=f"The {effect.effect_id} line")
            if line.pinned is not None:
                audio = self._pinned(
                    entity, effect.effect_id, line.pinned, spoken=True, max_seconds=line.max_seconds
                )
            else:
                voices = self.runner.voices
                voice = None if voices is None else voices.voice(line.voice_id)
                if voice is None:
                    raise ValueError(
                        f"spoken line {effect.effect_id} names voice {line.voice_id!r}, which the "
                        "package does not cast"
                    )
                speech_route = self.route("speech.generate")
                if speech_route.rpartition("@")[2] != voice.provider.name:
                    raise ValueError(
                        f"voice {voice.voice_id} is cast on {voice.provider.name!r} but the "
                        f"speech route is {speech_route}"
                    )
                draw = entity.step(
                    "generate",
                    title="Speak the line",
                    # The text is authored, verbatim, annotations included; the read is keyed on
                    # the cast provider voice, so recasting a name redraws it.
                    uses="gnode/speech.generate@1",
                    with_={
                        "text": line.text,
                        "voice": voice.provider.voice,
                        "language_code": voice.language_code,
                        **({} if line.stability is None else {"stability": line.stability}),
                    },
                    view=True,
                )
                entity.step(
                    "admit",
                    title="Admit the read and its length",
                    uses=f"{AUDIO}#admit_line",
                    judges="generate",
                    with_={"audio": draw.outputs.audio, "max_seconds": line.max_seconds},
                    on_reject=_REDRAW,
                )
                audio = draw.outputs.audio
                self.publish(f"audio/{effect.effect_id}.mp3", audio)
            record = entity.step(
                "record",
                title="Measure it",
                uses=f"{AUDIO}#record_line",
                with_={
                    "audio": audio,
                    "effect_id": effect.effect_id,
                    "voice_id": line.voice_id,
                    "max_seconds": line.max_seconds,
                    "pinned": line.pinned is not None,
                },
            )
            self.publish(f"audio/{effect.effect_id}.validation.json", record.outputs.validation)

    def _pinned(
        self,
        group: Group,
        effect_id: str,
        pinned: Any,
        *,
        spoken: bool,
        max_seconds: float | None = None,
    ) -> Any:
        """A reviewed take from the package, republished with its sidecar; it buys nothing."""

        take = group.step(
            "republish",
            title="Republish the reviewed take",
            uses=f"{AUDIO}#republish_take",
            with_={
                "audio": self.path(pinned.source),
                "provenance": self.path(pinned.provenance_source),
                "spoken": spoken,
                "max_seconds": max_seconds,
            },
        )
        self.publish(f"audio/{effect_id}.mp3", take.outputs.audio)
        self.publish(f"audio/{effect_id}.mp3.meta.json", take.outputs.provenance)
        return take.outputs.audio

    # -------------------------------------------------------------------- fx

    def fx(self, wf: Workflow) -> None:
        fx = self.runner.fx
        if fx is None:
            return
        group = wf.group("fx", title="Screen effects")

        def style(task: str) -> str:
            return fx_plate_prompt(self.resolved, task)

        def subject_image(subject: CutInPortraitSubject) -> Any:
            concept = self.boss_concepts.get(subject.actor_id)
            if concept is None:
                raise ValueError(
                    f"cut-in portrait subject {subject.actor_id!r} is not a boss this package draws"
                )
            return concept.outputs.image

        plates = add_cut_in_steps(
            group.group("frame", title="Cut-in frame"),
            lambda portrait_id: group.group(
                f"portrait_{_name(portrait_id)}", title=f"Cut-in portrait {portrait_id}"
            ),
            nodes=EFFECTS,
            fx=fx,
            style_prompt=style,
            reference_path=self.path,
            subject_image=subject_image,
        )
        for plate_name, steps in plates.items():
            plate_id = "frame" if plate_name == "frame" else plate_id_for("portrait", plate_name)
            _raw, plate_ref, _placement, validation_ref, _evidence, review_ref = (
                cut_in_artifact_refs(plate_id)
            )
            self.publish(plate_ref, steps["plate"].outputs.image)
            self.publish(validation_ref, steps["plate"].outputs.validation)
            if "review" in steps:
                self.publish(review_ref, steps["review"].outputs.json)
        dust = add_dust_steps(
            group.group("dust", title="Ground dust"),
            nodes=EFFECTS,
            fx=fx,
            style_prompt=style,
            reference_path=self.path,
        )
        if dust is not None:
            _raw_ref, atlas_ref, validation_ref = sprite_dust_artifact_refs()
            self.publish(atlas_ref, dust["atlas"].outputs.image)
            self.publish(validation_ref, dust["atlas"].outputs.validation)
        self.references.update(entry.source for entry in fx.references)

    # --------------------------------------------------------------- package

    def package(self, wf: Workflow) -> StepRef:
        for references in (
            self.track.references,
            self.runner.avatar.references,
            self.runner.props.references,
            self.runner.items.references,
        ):
            self.references.update(entry.source for entry in references)
        package = self.resolved.package
        return wf.step(
            "package",
            title="Lay out the runtime package",
            uses=f"{PACKAGE}#assemble_package",
            with_={
                "package": {entry.path: self.path(entry.path) for entry in package.files},
                "published": dict(sorted(self.published.items())),
                "references": sorted(self.references),
            },
            view=True,
        )


def _first_take(effect_id: str, take: int) -> None:
    if take != 1:
        raise ValueError(
            f"{effect_id} asks for take {take}: choose a take in pipeline/workflow.takes.yaml"
        )


def build(package: str) -> Workflow:
    """Every asset the package declares, judged, and laid out as the runtime package."""

    root = Path(package).resolve()
    resolved = resolve_runner_package(root)
    game = resolved.package.game
    track = resolved.runner.track
    built = _Build(resolved, root, _project_root(root))
    wf = Workflow(
        "iron-petal-unit",
        title=f"{game.display_name}: {track.display_name}",
        description="Every asset Iron Petal Unit's package declares, laid out for the Godot host.",
        budget={"max_usd": BUDGET_USD},
    )
    built.ground(wf)
    built.layers(wf)
    built.avatar(wf)
    built.bosses(wf)
    built.catalog(wf)
    built.soundtrack(wf)
    built.sounds(wf)
    built.lines(wf)
    built.fx(wf)
    wf.outputs(package=built.package(wf).outputs.files)
    return wf


__all__ = ["BUDGET_USD", "TAKES", "build"]
