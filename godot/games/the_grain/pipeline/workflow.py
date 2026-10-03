"""The Grain's asset builds: a point-and-click room and a dialogue scene, read by the game.

    gnode plan pipeline/workflow.py:room --arg package=inputs/rooms/window
    gnode plan pipeline/workflow.py:scene --arg package=inputs
    gnode run  pipeline/workflow.py:room --arg package=inputs/rooms/window --live \\
        --max-usd 20 --deliver package=../../../out/the-grain-window/{key}

Each game reader resolves its own package, unchanged, and proves it first (a room must be
finishable, a scene's scenarios admitted) so nothing is paid for against a broken puzzle.
A model picks one approved style mode for the whole room or scene; every image prompt ends
with that mode's clause for its asset kind, and every image is drawn against the package's
authored style plate. Every painting is judged by the game's own gate and drawn again when
it fails. The last step lays the published files out at the paths the Godot host reads
and writes the room's ``manifest.json`` or the scene's ``bundle.json``.

A package must sit inside this project (the folder holding ``gnode.yaml``): its authored
references are project files, read by content.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from demo_game_tools.kits.ui_art.nodes import document_roles
from demo_game_tools.media.ui import GameUi
from demo_game_tools.steps.ui_atlas import add_ui_sheet_steps
from gnode import Group, StepRef, Workflow
from stage_gen.image_style import ImageAssetKind
from the_grain_pipeline.dialogue_scene.build import (
    PLAN_SYSTEM,
    PROVIDER_BACKGROUND_HEIGHT,
    PROVIDER_BACKGROUND_WIDTH,
    SPRITE_HEIGHT,
    SPRITE_WIDTH,
    plan_frame,
    scene_files,
)
from the_grain_pipeline.dialogue_scene.prompts import background_prompt, plan_prompt, track_prompt
from the_grain_pipeline.dialogue_scene.prompts import ui_atlas_prompt as scene_ui_prompt
from the_grain_pipeline.dialogue_scene.scene_request import (
    read_scene_document,
    resolve_dialogue_scene,
)
from the_grain_pipeline.pointclick_room.room_prompts import (
    backdrop_prompt,
    hotspot_sprite_prompt,
    item_icon_prompt,
    narration_ids,
    narration_prompt,
    ui_atlas_prompt,
)
from the_grain_pipeline.pointclick_room.room_request import (
    ResolvedPointClickRoom,
    read_room_document,
    resolve_pointclick_room,
)
from the_grain_pipeline.pointclick_room.runtime import SPRITE_SIZE
from the_grain_pipeline.style import style_question

#: The game's node modules, as project paths.
STYLE = "./pipeline/nodes/style.py"
ROOM = "./pipeline/nodes/room.py"
SCENE = "./pipeline/nodes/scene.py"
INTERFACE = "./pipeline/nodes/interface.py"

#: Draws a judged painting or answer gets before the run stops on it.
TAKES = 6
#: The most one room build may cost, every redraw included.
ROOM_BUDGET_USD = 25.0
#: The most one scene build may cost, every redraw included.
SCENE_BUDGET_USD = 150.0
#: The narration answer's instruction, as the room recipe has always sent it.
NARRATION_SYSTEM = (
    "Return only the strict narration JSON. No puzzle hints beyond the listed "
    "facts, no new items, no meta commentary."
)
#: The asset kinds a room's style anchor must treat.
ROOM_ASSET_KINDS: tuple[ImageAssetKind, ...] = ("environment_background", "illustration")
#: The asset kinds a scene's style anchor must treat.
SCENE_ASSET_KINDS: tuple[ImageAssetKind, ...] = (
    "concept_art",
    "character_sprite",
    "environment_background",
)

_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_REDRAW = {"regenerate": {"max": TAKES, "then": "fail"}}


def _name(value: str) -> str:
    name = value.replace("-", "_")
    if not _NAME.fullmatch(name):
        raise ValueError(f"{value!r} cannot name a step: write it in lower snake or kebab case")
    return name


def _project_root(package: Path) -> Path:
    for folder in (package, *package.parents):
        if (folder / "gnode.yaml").is_file():
            return folder
    raise ValueError(f"{package} is not inside a gnode project")


class _Package:
    """One package inside the project: its files as project paths, and what it publishes."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.project = _project_root(root)
        self.published: dict[str, Any] = {}

    def path(self, source: str) -> str:
        """A package file as a project path, read by content."""

        return "./" + (self.root / source).relative_to(self.project).as_posix()

    def publish(self, runtime_path: str, value: Any) -> None:
        if runtime_path in self.published:
            raise ValueError(f"two steps publish {runtime_path}")
        self.published[runtime_path] = value


def _style(wf: Workflow, *, brief: str, asset_kinds: tuple[ImageAssetKind, ...]) -> StepRef:
    """The style selection, its judge, and the anchor record whose clauses prompts end with."""

    group = wf.group("style", title="Pick the style")
    prompt, system = style_question(brief, asset_kinds)
    schema = group.step("schema", title="The selection's shape", uses=f"{STYLE}#selection_schema")
    selection = group.step(
        "select",
        title="Pick one approved style",
        uses="gnode/structured.generate@1",
        with_={"prompt": prompt, "system": system, "schema": schema.outputs.schema},
    )
    kinds = {"asset_kinds": list(asset_kinds)}
    group.step(
        "admit",
        title="An approved style for every kind drawn",
        uses=f"{STYLE}#admit_style",
        judges="select",
        with_={"selection": selection.outputs.json, **kinds},
        on_reject=_REDRAW,
    )
    return group.step(
        "anchor",
        title="Record the anchor",
        uses=f"{STYLE}#style_record",
        with_={"selection": selection.outputs.json, **kinds},
        view=True,
    )


def _anchored(prompt: str, anchor: StepRef, asset_kind: ImageAssetKind) -> str:
    """The prompt with its asset kind's style clause appended, as the style compiler does."""

    return f"{prompt.rstrip()}\n\n{getattr(anchor.outputs.clauses, asset_kind)}"


def _paint(
    group: Group,
    *,
    title: str,
    prompt: str,
    size: str,
    transparent: bool,
    pictures: list[Any],
    gate: dict[str, Any],
    judge: str,
) -> StepRef:
    """One image edited from the package's references, judged, drawn again when refused."""

    painting = group.step(
        "generate",
        title=title,
        uses="gnode/image.edit@1",
        with_={
            "image": pictures[0],
            "references": pictures[1:],
            "prompt": prompt,
            "size": size,
            "background": "transparent" if transparent else "opaque",
        },
        requires=["transparent_background"] if transparent else [],
        view=True,
    )
    group.step(
        "admit",
        title="Hold it to its gate",
        uses=judge,
        judges="generate",
        with_={"image": painting.outputs.image, **gate},
        on_reject=_REDRAW,
    )
    return painting


def _interface(
    wf: Workflow,
    package: _Package,
    ui: GameUi,
    style_prompt: Any,
    reference_path: Any,
) -> None:
    group = wf.group("interface", title="Interface")
    for role in document_roles(ui):
        steps = add_ui_sheet_steps(
            group.group(_name(role.role), title=f"The {role.role} sheet"),
            nodes=INTERFACE,
            ui=ui,
            role=role,
            style_prompt=style_prompt,
            reference_path=reference_path,
        )
        package.publish(f"ui/{role.role}.png", steps["publish"].outputs.image)
        package.publish(f"ui/{role.role}.validation.json", steps["publish"].outputs.validation)


# --------------------------------------------------------------------------- room


def _room_files(resolved: ResolvedPointClickRoom) -> list[str]:
    """Every file of the room package the package step reads the room from again."""

    return sorted(
        {
            "room.toml",
            "ui.toml",
            *(reference.source for reference in resolved.room.references),
            *resolved.ui_references,
        }
    )


def room(package: str) -> Workflow:
    """One room's backdrop, hotspot sprites, item icons, narration and interface."""

    root = Path(package).resolve()
    resolved = resolve_pointclick_room(read_room_document(root), root=root)
    authored = resolved.room
    built = _Package(root)
    wf = Workflow(
        "the-grain-room",
        title=f"The Grain: {authored.display_name}",
        description="One point-and-click room of The Grain, laid out for the Godot host.",
        budget={"max_usd": ROOM_BUDGET_USD},
    )
    anchor = _style(wf, brief=resolved.style_selection_brief, asset_kinds=ROOM_ASSET_KINDS)
    references = [built.path(reference.source) for reference in resolved.style_references]
    backdrop = _paint(
        wf.group("backdrop", title="Backdrop"),
        title="Paint the room",
        prompt=_anchored(backdrop_prompt(authored), anchor, "environment_background"),
        size=f"{authored.scene.width}x{authored.scene.height}",
        transparent=False,
        pictures=references,
        gate={
            "width": authored.scene.width,
            "height": authored.scene.height,
            "alpha": False,
            "isolated": False,
        },
        judge=f"{ROOM}#admit_room_image",
    )
    built.publish("assets/backdrop.png", backdrop.outputs.image)
    cutout = {"width": SPRITE_SIZE, "height": SPRITE_SIZE, "alpha": True, "isolated": True}
    hotspots = wf.group("hotspots", title="Hotspot objects")
    for hotspot in authored.hotspots:
        if hotspot.art != "sprite":
            continue
        sprite = _paint(
            hotspots.group(_name(hotspot.hotspot_id), title=hotspot.label),
            title=f"Draw the {hotspot.label}",
            prompt=_anchored(hotspot_sprite_prompt(authored, hotspot), anchor, "illustration"),
            size=f"{SPRITE_SIZE}x{SPRITE_SIZE}",
            transparent=True,
            pictures=references,
            gate=cutout,
            judge=f"{ROOM}#admit_room_image",
        )
        built.publish(f"assets/hotspots/{hotspot.hotspot_id}.png", sprite.outputs.image)
    items = wf.group("items", title="Inventory items")
    for item in authored.items:
        icon = _paint(
            items.group(_name(item.item_id), title=item.label),
            title=f"Draw the {item.label}",
            prompt=_anchored(item_icon_prompt(authored, item), anchor, "illustration"),
            size=f"{SPRITE_SIZE}x{SPRITE_SIZE}",
            transparent=True,
            pictures=references,
            gate=cutout,
            judge=f"{ROOM}#admit_room_image",
        )
        built.publish(f"assets/items/{item.item_id}.png", icon.outputs.image)
    narration: Any = None
    expected = list(narration_ids(authored))
    if expected:
        group = wf.group("narration", title="Narration")
        schema = group.step(
            "schema", title="The narration's shape", uses=f"{ROOM}#narration_schema"
        )
        answer = group.step(
            "write",
            title="Write the lines the author left open",
            uses="gnode/structured.generate@1",
            with_={
                "prompt": narration_prompt(authored),
                "system": NARRATION_SYSTEM,
                "schema": schema.outputs.schema,
            },
        )
        group.step(
            "check",
            title="Exactly the lines asked for",
            uses=f"{ROOM}#check_narration",
            judges="write",
            with_={"answer": answer.outputs.json, "expected": expected},
            on_reject=_REDRAW,
        )
        narration = group.step(
            "record",
            title="Record the lines",
            uses=f"{ROOM}#narration",
            with_={
                "answer": answer.outputs.json,
                "expected": expected,
                "room_sha256": resolved.room_sha256,
            },
        ).outputs.document

    def ui_reference(source: str) -> str:
        return built.path(source)

    _interface(
        wf,
        built,
        resolved.ui,
        lambda task: ui_atlas_prompt(authored, task),
        ui_reference,
    )
    with_: dict[str, Any] = {
        "room": {source: built.path(source) for source in _room_files(resolved)},
        "published": dict(sorted(built.published.items())),
    }
    if narration is not None:
        with_["narration"] = narration
    package_step = wf.step(
        "package",
        title="Lay out the playable room",
        uses=f"{ROOM}#room_package",
        with_=with_,
        view=True,
    )
    wf.outputs(package=package_step.outputs.files)
    return wf


# -------------------------------------------------------------------------- scene


def _slug(value: str) -> str:
    return value.replace("_", "-")


def scene(package: str) -> Workflow:
    """One scene's backdrops, each actor's plan and faces, its tracks and interface."""

    root = Path(package).resolve()
    resolved = resolve_dialogue_scene(read_scene_document(root), root=root)
    request = resolved.request
    mode = request.transparency_mode
    if mode == "ai":
        raise ValueError(
            "ai transparency needs a background.remove route, and no project declares one; "
            "choose native or chroma"
        )
    native = mode == "native"
    built = _Package(root)
    wf = Workflow(
        "the-grain-scene",
        title=f"The Grain: {request.display_name}",
        description="One dialogue scene of The Grain, laid out for the Godot host.",
        budget={"max_usd": SCENE_BUDGET_USD},
    )
    anchor = _style(wf, brief=resolved.style_selection_brief, asset_kinds=SCENE_ASSET_KINDS)
    plate = built.path(resolved.style_reference.source)
    contract = resolved.recipe_version

    stages = wf.group("stages", title="Backdrops")
    for stage in resolved.stages:
        group = stages.group(_name(stage.stage_id), title=f"The {stage.stage_id} backdrop")
        raw = _paint(
            group,
            title="Paint the backdrop",
            prompt=_anchored(background_prompt(stage.brief), anchor, "environment_background"),
            size=f"{PROVIDER_BACKGROUND_WIDTH}x{PROVIDER_BACKGROUND_HEIGHT}",
            transparent=False,
            pictures=[plate],
            gate={
                "width": PROVIDER_BACKGROUND_WIDTH,
                "height": PROVIDER_BACKGROUND_HEIGHT,
                "alpha": False,
                "chroma": False,
                "recipe_contract": contract,
            },
            judge=f"{SCENE}#admit_scene_image",
        )
        fitted = group.step(
            "publish",
            title="Fit it to the runtime canvas",
            uses=f"{SCENE}#backdrop",
            with_={"raw": raw.outputs.image},
            view=True,
        )
        built.publish(f"assets/stage-{_slug(stage.stage_id)}.png", fitted.outputs.image)

    face_gate = {
        "width": SPRITE_WIDTH,
        "height": SPRITE_HEIGHT,
        "alpha": native,
        "chroma": mode == "chroma",
        "recipe_contract": contract,
    }
    plans: dict[str, Any] = {}
    actors = wf.group("actors", title="Cast")
    for actor in resolved.actors:
        group = actors.group(_name(actor.actor_id), title=actor.display_name)
        frame = {"frame": plan_frame(resolved, actor)}
        planning = group.group("plan", title="Plan the staging")
        schema = planning.step("schema", title="The plan's shape", uses=f"{SCENE}#plan_schema")
        draft = planning.step(
            "draft",
            title="Lock pose, light and style",
            uses="gnode/structured.generate@1",
            with_={
                "prompt": plan_prompt(request, resolved.art_request_sha256, actor.profile.profile),
                "system": PLAN_SYSTEM,
                "schema": schema.outputs.schema,
                "context": [plate],
            },
        )
        planning.step(
            "admit",
            title="Inside the authored frame",
            uses=f"{SCENE}#admit_plan",
            judges="draft",
            with_={"draft": draft.outputs.json, **frame},
            on_reject=_REDRAW,
        )
        plan = planning.step(
            "record",
            title="Record the plan",
            uses=f"{SCENE}#plan_record",
            with_={"draft": draft.outputs.json, **frame},
            view=True,
        ).outputs.plan
        plans[actor.asset_prefix] = plan
        # The base face is drawn against the style plate and, when the actor binds one, its
        # own identity plate, which the brief then names; every other face edits the base.
        identity = actor.identity_reference
        base_pictures = [plate]
        if identity is not None and identity.source != resolved.style_reference.source:
            base_pictures.append(built.path(identity.source))
        base_source: Any = None
        for index, expression in enumerate(actor.expressions):
            face = group.group(_name(expression.expression_id), title=expression.label)
            brief = face.step(
                "brief",
                title="Compose the face's brief",
                uses=f"{SCENE}#face_brief",
                with_={
                    "plan": plan,
                    "clauses": anchor.outputs.clauses,
                    "base": index == 0,
                    "expression_id": expression.expression_id,
                    "transparency_mode": mode,
                    "has_identity_plate": actor.identity_reference is not None,
                },
            )
            source = _paint(
                face,
                title=f"Draw {actor.display_name}, {expression.label.lower()}",
                prompt=str(brief.outputs.brief.prompt),
                size=f"{SPRITE_WIDTH}x{SPRITE_HEIGHT}",
                transparent=native,
                pictures=base_pictures if base_source is None else [base_source],
                gate=face_gate,
                judge=f"{SCENE}#admit_scene_image",
            )
            if base_source is None:
                base_source = source.outputs.image
            finished = face.step(
                "publish",
                title="Finish the sprite",
                uses=f"{SCENE}#sprite",
                with_={"source": source.outputs.image, "transparency_mode": mode},
                view=True,
            )
            built.publish(
                f"assets/{actor.asset_prefix}-{_slug(expression.expression_id)}.png",
                finished.outputs.image,
            )

    tracks = wf.group("tracks", title="Tracks")
    for track in resolved.tracks:
        group = tracks.group(_name(track.track_id), title=f"The {track.track_id} track")
        draw = group.step(
            "generate",
            title="Compose the track",
            uses="gnode/music.generate@1",
            with_={"prompt": track_prompt(request.game_id, track)},
            view=True,
        )
        group.step(
            "admit",
            title="Playable and long enough",
            uses=f"{SCENE}#admit_scene_track",
            judges="generate",
            with_={"audio": draw.outputs.audio},
            on_reject=_REDRAW,
        )
        built.publish(f"assets/track-{_slug(track.track_id)}.mp3", draw.outputs.audio)

    _interface(wf, built, resolved.ui, scene_ui_prompt, built.path)
    records = {
        path: value for path, value in built.published.items() if path.endswith(".validation.json")
    }
    published = {path: value for path, value in built.published.items() if path not in records}
    package_step = wf.step(
        "package",
        title="Lay out the scene bundle",
        uses=f"{SCENE}#scene_package",
        with_={
            "scene": {source: built.path(source) for source in scene_files(resolved, root)},
            "published": dict(sorted(published.items())),
            "records": dict(sorted(records.items())),
            "plans": plans,
            "anchor": anchor.outputs.anchor,
        },
        view=True,
    )
    wf.outputs(package=package_step.outputs.files)
    return wf


__all__ = ["ROOM_BUDGET_USD", "SCENE_BUDGET_USD", "TAKES", "room", "scene"]
