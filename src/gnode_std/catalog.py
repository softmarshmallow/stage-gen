"""The standard node types (``gnode/<name>@<major>``): their declarations.

A declaration is what a plan needs: inputs, settings, outputs, the paid capability a type
is, and whether it judges. Bodies are attached where they are implemented; a type without
one plans and prices like any other and refuses to run.
"""

from __future__ import annotations

from typing import Any

from gnode import NodeSpec, PortSpec, param_schema

TEXT = {"type": "string"}
TEMPLATE = {"type": "string", "x-gnode-template": True}
OPTIONAL = {"optional": True}


def _p(declared: Any, **extra: Any) -> dict[str, Any]:
    return {**param_schema(declared), **extra}


def _ports(**ports: str) -> dict[str, PortSpec]:
    return {name: PortSpec.parse(notation) for name, notation in ports.items()}


def _spec(name: str, version: int, **fields: Any) -> NodeSpec:
    return NodeSpec(name=name, version=version, **fields)


#: ``(major, declaration)`` for every standard type; ``uses: gnode/<name>@<major>``.
STANDARD_TYPES: tuple[tuple[int, NodeSpec], ...] = (
    # ------------------------------------------------------------------ generation
    (
        1,
        _spec(
            "image.generate",
            1,
            inputs=_ports(references="image[]?"),
            params={
                "prompt": TEMPLATE,
                "size": _p(str, optional=True),
                "background": _p(("opaque", "transparent", "auto"), default="auto"),
                "vars": _p(dict, default={}),
            },
            outputs=_ports(image="image/png"),
            capability="image.generate",
        ),
    ),
    (
        1,
        _spec(
            "image.edit",
            1,
            inputs=_ports(image="image", mask="image?", references="image[]?"),
            params={
                "prompt": TEMPLATE,
                "size": _p(str, optional=True),
                "background": _p(("opaque", "transparent", "auto"), default="auto"),
                "vars": _p(dict, default={}),
            },
            outputs=_ports(image="image/png"),
            capability="image.edit",
        ),
    ),
    (
        1,
        _spec(
            "structured.generate",
            1,
            inputs=_ports(schema="json", context="file[]?"),
            params={
                "prompt": TEMPLATE,
                "system": {**TEMPLATE, "optional": True},
                "vars": _p(dict, default={}),
                "matte": _p(str, default="#ffffff"),
                "max_tokens": _p(int, optional=True),
            },
            outputs=_ports(json="json"),
            capability="structured.generate",
        ),
    ),
    (
        1,
        _spec(
            "video.generate",
            1,
            inputs=_ports(first_frame="image?", last_frame="image?"),
            params={
                "prompt": TEMPLATE,
                "duration": _p(float, optional=True),
                "resolution": _p(str, optional=True),
                "aspect_ratio": _p(str, optional=True),
            },
            outputs=_ports(video="video/mp4"),
            capability="video.generate",
        ),
    ),
    (
        1,
        _spec(
            "speech.generate",
            1,
            params={
                "text": TEXT,
                "voice": TEXT,
                # How literally the voice follows the text, and the language it reads in.
                "stability": _p(float, optional=True),
                "language_code": _p(str, optional=True),
                "max_chars": _p(int, optional=True),
            },
            outputs=_ports(audio="audio"),
            capability="speech.generate",
        ),
    ),
    (
        1,
        _spec(
            "sound.generate",
            1,
            params={
                "prompt": TEMPLATE,
                "duration": _p(float, optional=True),
                # How literally the prompt is followed, and whether the clip should loop.
                "prompt_influence": _p(float, optional=True),
                "loop": _p(bool, default=False),
            },
            outputs=_ports(audio="audio"),
            capability="sound.generate",
        ),
    ),
    (
        1,
        _spec(
            "music.generate",
            1,
            params={"prompt": TEMPLATE, "duration": _p(float, optional=True)},
            outputs=_ports(audio="audio"),
            capability="music.generate",
        ),
    ),
    (
        1,
        _spec(
            "mesh.generate",
            1,
            # Views by name (front, back, left, right): which side each picture shows.
            inputs=_ports(views="image{}"),
            params={
                "face_limit": _p(int, optional=True),
                "quad": _p(bool, default=False),
                "texture": _p(bool, default=True),
                "pbr": _p(bool, default=False),
            },
            outputs=_ports(model="model"),
            capability="mesh.generate",
        ),
    ),
    (
        1,
        _spec(
            "mesh.rig",
            1,
            inputs=_ports(model="model"),
            params={
                "rig_type": _p(str, default="biped"),
                "skeleton": _p(str, default="mixamo"),
                # A route that checks riggability first rigs a model its check doubts.
                "allow_negative_check": _p(bool, default=False),
            },
            outputs=_ports(model="model/gltf-binary"),
            capability="mesh.rig",
        ),
    ),
    (
        1,
        _spec(
            "background.remove",
            1,
            inputs=_ports(image="image"),
            outputs=_ports(image="image/png"),
            capability="background.remove",
        ),
    ),
    # ---------------------------------------------------------- judges, annotators
    (
        1,
        _spec(
            "vision.annotate",
            1,
            inputs=_ports(image="image?", images="image[]?"),
            params={
                "prompt": TEMPLATE,
                "shapes": _p(list, default=["point", "points", "box"]),
                "fields": _p(dict, default={}),
                "grounding": _p(("grid", "native"), default="grid"),
                "vars": _p(dict, default={}),
            },
            outputs=_ports(annotations="annotations"),
            capability="vision.annotate",
        ),
    ),
    (
        1,
        _spec(
            "vision.review",
            1,
            inputs=_ports(image="image?", images="image[]?", feedback="annotations?"),
            params={
                "question": _p(str, optional=True, **{"x-gnode-template": True}),
                "criteria": _p(list, optional=True),
                "report": _p(("annotations", "verdict"), default="annotations"),
                "review_size": _p(int, optional=True),
                "vars": _p(dict, default={}),
            },
            outputs=_ports(annotations="annotations?", mask="image/png?"),
            judge=True,
            capability="vision.review",
        ),
    ),
    (
        1,
        _spec(
            "structured.review",
            1,
            inputs=_ports(subject="json", rubric="text?", context="file[]?"),
            params={"question": _p(str, optional=True), "criteria": _p(list, optional=True)},
            outputs=_ports(),
            judge=True,
            capability="structured.review",
        ),
    ),
    (
        1,
        _spec(
            "image.check_alpha",
            1,
            inputs=_ports(image="image"),
            params={"expect": _p(("transparent", "opaque"), default="transparent")},
            judge=True,
        ),
    ),
    (
        1,
        _spec(
            "image.check_size",
            1,
            inputs=_ports(image="image"),
            params={"width": _p(int, optional=True), "height": _p(int, optional=True)},
            judge=True,
        ),
    ),
    (
        1,
        _spec(
            "audio.check_duration",
            1,
            inputs=_ports(audio="audio"),
            params={"min_s": _p(float, optional=True), "max_s": _p(float, optional=True)},
            judge=True,
        ),
    ),
    # ----------------------------------------------------------------------- media
    (
        1,
        _spec(
            "image.resize",
            1,
            inputs=_ports(image="image"),
            params={
                "longest_side": _p(int, optional=True),
                "width": _p(int, optional=True),
                "height": _p(int, optional=True),
            },
            outputs=_ports(image="image/png"),
        ),
    ),
    (
        1,
        _spec(
            "image.crop",
            1,
            inputs=_ports(image="image", region="annotations?"),
            params={"box": _p(list, optional=True), "padding": _p(float, default=0.0)},
            outputs=_ports(image="image/png"),
        ),
    ),
    (
        1,
        _spec(
            "image.pad",
            1,
            inputs=_ports(image="image"),
            params={"width": _p(int), "height": _p(int)},
            outputs=_ports(image="image/png"),
        ),
    ),
    (
        1,
        _spec(
            "image.compose",
            1,
            inputs=_ports(layers="image[]"),
            params={"width": _p(int), "height": _p(int)},
            outputs=_ports(image="image/png"),
        ),
    ),
    (
        1,
        _spec(
            "image.key",
            1,
            inputs=_ports(image="image"),
            params={"color": _p(str, default="#00ff00")},
            outputs=_ports(image="image/png"),
        ),
    ),
    (
        1,
        _spec(
            "image.mirror_repeat",
            1,
            inputs=_ports(image="image"),
            params={"axis": _p(("x", "y", "xy"), default="x")},
            outputs=_ports(image="image/png"),
        ),
    ),
    (
        1,
        _spec(
            "image.sheet",
            1,
            inputs=_ports(image="image?", images="image{}?"),
            params={"columns": _p(int), "rows": _p(int, optional=True)},
            outputs=_ports(image="image/png?", cells="image{}?"),
        ),
    ),
    (
        1,
        _spec(
            "image.contact_sheet",
            1,
            inputs=_ports(images="image[]"),
            params={"columns": _p(int, default=4)},
            outputs=_ports(image="image/png"),
        ),
    ),
    (1, _spec("video.probe", 1, inputs=_ports(video="video"), outputs=_ports(report="json"))),
    (
        1,
        _spec(
            "video.frames",
            1,
            inputs=_ports(video="video"),
            params={"count": _p(int, default=8)},
            outputs=_ports(frames="image[]"),
        ),
    ),
    (
        1,
        _spec(
            "video.encode",
            1,
            inputs=_ports(frames="image[]"),
            params={"fps": _p(float, default=12.0)},
            outputs=_ports(video="video/mp4"),
        ),
    ),
    (
        1,
        _spec(
            "audio.normalize",
            1,
            inputs=_ports(audio="audio"),
            params={"loudness_lufs": _p(float, default=-16.0)},
            outputs=_ports(audio="audio"),
        ),
    ),
    (
        1,
        _spec(
            "audio.trim",
            1,
            inputs=_ports(audio="audio"),
            params={"start_s": _p(float, default=0.0), "end_s": _p(float, optional=True)},
            outputs=_ports(audio="audio"),
        ),
    ),
    (
        1,
        _spec(
            "audio.concat",
            1,
            inputs=_ports(clips="audio[]"),
            params={"gap_s": _p(float, default=0.0)},
            outputs=_ports(audio="audio"),
        ),
    ),
    (
        1,
        _spec(
            "audio.mix",
            1,
            inputs=_ports(clips="audio{}"),
            params={"timeline": _p(list)},
            outputs=_ports(audio="audio"),
        ),
    ),
    (
        1,
        _spec(
            "annotations.mask",
            1,
            inputs=_ports(annotations="annotations", image="image"),
            params={"tags": _p(list, optional=True)},
            outputs=_ports(mask="image/png"),
        ),
    ),
    (
        1,
        _spec(
            "annotations.filter",
            1,
            inputs=_ports(annotations="annotations"),
            params={"tags": _p(list)},
            outputs=_ports(annotations="annotations"),
        ),
    ),
    # -------------------------------------------------------------------- plumbing
    (1, _spec("select", 1, params={"first_of": _p(list)}, outputs=_ports(value="file?"))),
    (1, _spec("json.merge", 1, inputs=_ports(documents="json[]"), outputs=_ports(json="json"))),
    (
        1,
        _spec(
            "package",
            1,
            params={"files": _p(dict), "manifest": _p(dict, default={})},
            outputs=_ports(files="file{}", manifest="json"),
        ),
    ),
    (1, _spec("files.copy", 1, inputs=_ports(file="file"), outputs=_ports(file="file"))),
)
