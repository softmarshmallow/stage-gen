"""The fixed component set every workflow page composes.

A component is a pure function of (page context, props, children) -> HTML. It reads the page's
showcase record and never a run folder, so an MDX port can reimplement each one with the same
name and props. The record holds raw values; wording and number formatting live here and in the
page. Unknown components and props fail the build. Tailwind scans this file: keep class strings
literal.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .mdx import CodeBlock, Element, Heading, ListBlock, MdxError, Paragraph, inline, plain


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


# ------------------------------------------------------------------------------ formatting


def minutes(seconds: float) -> str:
    return f"{round(seconds / 60)} min" if seconds >= 90 else f"{round(seconds)} s"


def clock(ms: float | None) -> str | None:
    if ms is None:
        return None
    s = ms / 1000
    if s < 1:
        return "under a second"
    return f"{round(s)} s" if s < 60 else f"{int(s // 60)} min {int(s % 60)} s"


def money(usd: object) -> str | None:
    return None if usd in (None, "") else f"${float(usd):.2f}"


def size(n: int) -> str:
    return f"{n / 1e6:.1f} MB" if n >= 1e6 else f"{n / 1e3:.0f} KB"


# ------------------------------------------------------------------------------ page context


@dataclass
class Page:
    front: dict
    record: dict
    refs: list | None = None  # set while an <Agent> prompt renders, so its references are numbered
    frame_box: str = "aspect-[3/4]"  # set by <Filmstrip> for its frames: portrait by default, landscape for wide sheets

    def node(self, node_id: str) -> dict:
        try:
            return self.record["nodes"][node_id]
        except KeyError:
            raise MdxError(f"no node {node_id!r} in this run") from None

    def title_of(self, node_id: str) -> str:
        node = self.node(node_id)
        tail = re.split(r"[/.]", node["type_id"])[-1]
        labels = self.front.get("node_labels", {})
        label = labels.get(node_id) or labels.get(tail) or tail.replace("_", " ").capitalize()
        if (m := re.search(r"_(\d\d)$", node_id)) and int(m.group(1)) > 1:
            label += f", round {int(m.group(1))}"
        return label


@dataclass
class Component:
    render: Callable[[Page, dict, object], str]
    props: dict[str, type]
    required: tuple[str, ...] = ()


REGISTRY: dict[str, Component] = {}


def component(name: str, props: dict[str, type] | None = None, required: tuple[str, ...] = ()):
    def register(fn):
        REGISTRY[name] = Component(fn, props or {}, required)
        return fn

    return register


def render_blocks(page: Page, blocks: list) -> str:
    out = []
    for block in blocks:
        if isinstance(block, Heading):
            cls = (
                "mt-16 border-b border-zinc-200 pb-2 font-medium dark:border-zinc-800"
                if block.level == 2
                else "mt-8 font-medium"
            )
            out.append(f'<h{block.level} class="{cls}">{inline(block.text)}</h{block.level}>')
        elif isinstance(block, Paragraph):
            out.append(
                f'<p class="mt-6 max-w-3xl text-zinc-700 dark:text-zinc-300">{render_inline(page, block.parts)}</p>'
            )
        elif isinstance(block, CodeBlock):
            out.append(
                '<pre class="mt-4 overflow-x-auto rounded-md border border-zinc-200 bg-zinc-50 p-4 font-mono text-[13px] '
                f'leading-relaxed text-zinc-800 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200">{esc(block.code)}</pre>'
            )
        elif isinstance(block, ListBlock):
            items = "".join(f"<li>{inline(item)}</li>" for item in block.items)
            out.append(
                f'<ul class="mt-4 max-w-3xl list-disc space-y-1.5 pl-5 text-zinc-700 dark:text-zinc-300">{items}</ul>'
            )
        else:
            out.append(render_element(page, block))
    return "".join(out)


def render_element(page: Page, element: Element) -> str:
    spec = REGISTRY.get(element.name)
    if spec is None:
        raise MdxError(f"unknown component <{element.name}>; known: {', '.join(sorted(REGISTRY))}")
    for key, value in element.props.items():
        if key not in spec.props:
            raise MdxError(f"<{element.name}> has no prop {key!r}")
        if not isinstance(value, spec.props[key]):
            raise MdxError(f"<{element.name} {key}> must be {spec.props[key].__name__}")
    for key in spec.required:
        if key not in element.props:
            raise MdxError(f"<{element.name}> needs {key!r}")
    return spec.render(page, element.props, element.children)


def children_of(children: object, name: str) -> list[Element]:
    items = [c for c in children if isinstance(c, Element)] if isinstance(children, list) else []
    if any(c.name != name for c in items):
        raise MdxError(f"only <{name}> may appear here")
    return items


def render_inline(page: Page, parts: list) -> str:
    return "".join(inline(p) if isinstance(p, str) else render_element(page, p) for p in parts)


def text_of(page: Page, children: object) -> str:
    """A sentence's HTML, whether the element held a sentence or a single paragraph block."""
    if isinstance(children, list) and len(children) == 1 and isinstance(children[0], Paragraph):
        children = children[0]
    return render_inline(page, children.parts) if isinstance(children, Paragraph) else ""


CHECKER = (
    "background-color:#fff;background-image:conic-gradient(#e4e4e7 25%,transparent 0 50%,#e4e4e7 0 75%,transparent 0);"
    "background-size:16px 16px"
)


def ground(picture: dict) -> str:
    return CHECKER if picture.get("alpha") else f"background:{esc(picture['bg'])}"


def wide(picture: dict) -> bool:
    return picture["width"] >= picture["height"] * 1.6


def framed(picture: dict, cls: str) -> str:
    """A picture on its own ground colour, or a checkerboard when it is transparent.

    A wide picture, such as a panorama or a tile sheet, keeps its own shape instead of the
    frame's aspect class, so it is not shrunk into a strip.
    """
    style = ground(picture)
    if wide(picture):
        cls = " ".join(c for c in cls.split() if not c.startswith("aspect-"))
        style += f";aspect-ratio:{picture['width']}/{picture['height']}"
    return (
        f'<div class="{cls} flex items-center justify-center overflow-hidden rounded-sm" style="{style}">'
        f'<img class="max-h-full max-w-full object-contain" src="{esc(picture["src"])}" alt="" loading="lazy"></div>'
    )


LINK = "jump text-sm text-zinc-500 underline decoration-zinc-300 underline-offset-2 hover:text-zinc-900 dark:hover:text-zinc-100"
CELL = "border-b border-zinc-200 py-3 pr-6 align-top dark:border-zinc-800"
HEAD = "border-b border-zinc-300 pb-2 pr-6 text-left text-sm font-normal text-zinc-500 dark:border-zinc-700"


def node_link(page: Page, node_id: str) -> str:
    return (
        f'<button class="{LINK}" data-node="{esc(node_id)}">{esc(page.title_of(node_id))}</button>'
    )


# ------------------------------------------------------------------------------ overview blocks


CLIP = (
    "rounded-sm border border-zinc-300 px-2 py-0.5 text-xs text-zinc-600 hover:border-zinc-500 aria-pressed:border-zinc-900 "
    "aria-pressed:text-zinc-900 dark:border-zinc-700 dark:text-zinc-400 dark:aria-pressed:border-zinc-100 "
    "dark:aria-pressed:text-zinc-100"
)


def clip_buttons(model: dict, first: str) -> str:
    """One button per clip the model carries; the pressed one is playing."""
    return "".join(
        f'<button data-clip="{esc(name)}" aria-pressed="{"true" if name == first else "false"}" class="{CLIP}">'
        f"{esc(name.replace('_', ' ').capitalize())}</button>"
        for name in model["clips"]
    )


@component(
    "Hero", {"input": str, "also": str, "output": str, "clip": str}, required=("input", "output")
)
def hero(page: Page, props: dict, children: object) -> str:
    source = page.record["inputs"].get(props["input"])
    result = page.record["outputs"].get(props["output"])
    if source is None or result is None:
        raise MdxError("<Hero> input and output must name entries of the record")
    if source["kind"] == "text":
        first, _, rest = source["text"].partition("\n\n")
        left = (
            f'<p class="text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">{esc(first)}</p>'
        )
        if rest.strip():
            left += (
                '<details class="mt-4 text-sm text-zinc-500"><summary class="cursor-pointer select-none hover:text-zinc-900 '
                f'dark:hover:text-zinc-100">Rest of the brief</summary><p class="mt-3 leading-relaxed">{esc(rest.strip())}</p></details>'
            )
    else:
        shown = [source]
        if "also" in props:
            # A second picture the workflow takes, stacked under the first.
            second = page.record["inputs"].get(props["also"])
            if second is None or second["kind"] != "image":
                raise MdxError("<Hero also> must name a picture among the record's inputs")
            shown.append(second)
        box = "aspect-square" if len(shown) == 1 else "aspect-[3/2]"
        left = '<div class="h-6"></div>'.join(
            framed(s["picture"], box)
            + f'<p class="mt-3 text-xs text-zinc-500">{esc(s["file"])}</p>'
            for s in shown
        )
    if result["kind"] == "parallax":
        # The loop's map buttons swap this picture for the map they show.
        left = f"<div data-loop-reference>{left}</div>"
    poster = result["poster"]
    note = f"{esc(result['file'])} · {size(result['bytes'])}"
    if result["kind"] == "parallax":
        # The layers alone, scrolling for as long as the page is open: a recorded clip cannot show
        # it, because the layers' periods at their own speeds never line up again in a short loop.
        width, height = result["view"]
        buttons = "".join(
            f'<button data-loop-map="{esc(m["id"])}" aria-pressed="false" class="{SEGMENT}">{esc(m["label"])}</button>'
            for m in result["maps"]
        )
        right = (
            f'<div data-loop class="relative w-full overflow-hidden rounded-sm" style="aspect-ratio:{width}/{height}">'
            f'<div data-world class="absolute left-0 top-0 origin-top-left" style="width:{width}px;height:{height}px"></div></div>'
            f'<div class="mt-3 flex flex-wrap gap-1">{buttons}</div>'
        )
        config = json.dumps({"maps": result["maps"], "view": result["view"]})
        right = f'<div data-parallax-loop="{esc(config)}">{right}</div>'
        note += " · the layers alone, scrolling without end"
    elif result["kind"] == "model":
        first = props.get("clip") or result["clips"][0]
        right = (
            f'<div class="relative aspect-square overflow-hidden rounded-sm" style="{ground(poster)}">'
            f'<img class="absolute inset-0 h-full w-full object-contain" src="{esc(poster["src"])}" alt="">'
            f'<model-viewer id="mv" class="invisible absolute inset-0 h-full w-full" src="{esc(result["src"])}" camera-controls '
            f'autoplay animation-name="{esc(first)}" shadow-intensity="0.5" interaction-prompt="none"></model-viewer></div>'
            f'<div id="clips" class="mt-3 flex flex-wrap gap-1.5">{clip_buttons(result, first)}</div>'
        )
        note += " · drag to turn"
    else:
        right = framed(poster, "aspect-square")
    return (
        '<div class="mt-10 grid gap-px overflow-hidden rounded-sm border border-zinc-200 bg-zinc-200 md:grid-cols-2 dark:border-zinc-800 dark:bg-zinc-800">'
        f'<div class="bg-white p-6 dark:bg-zinc-950">{left}</div>'
        f'<div class="bg-white p-6 dark:bg-zinc-950">{right}<p class="mt-3 text-xs text-zinc-500">{note}</p></div></div>'
    )


METRIC_FORMATS = {"seconds": minutes, "usd": money}


@component("Stats")
def stats(page: Page, props: dict, children: object) -> str:
    cells = "".join(render_element(page, s) for s in children_of(children, "Stat"))
    return f'<div class="mt-10 flex flex-wrap gap-x-16 gap-y-6">{cells}</div>'


@component("Stat", {"metric": str}, required=("metric",))
def stat(page: Page, props: dict, children: object) -> str:
    metrics = page.record["metrics"]
    if props["metric"] not in metrics:
        raise MdxError(
            f"<Stat metric={props['metric']!r}>: this run records {', '.join(sorted(metrics))}"
        )
    unit = props["metric"].rsplit("_", 1)[-1]
    value = METRIC_FORMATS.get(unit, str)(metrics[props["metric"]])
    return (
        f'<div><div class="text-2xl font-medium tabular-nums">{esc(value)}</div>'
        f'<div class="mt-1 text-sm text-zinc-500">{text_of(page, children)}</div></div>'
    )


@component("Filmstrip")
def filmstrip(page: Page, props: dict, children: object) -> str:
    items = children_of(children, "Frame")
    width = {3: "md:grid-cols-3", 4: "md:grid-cols-4", 5: "md:grid-cols-5"}.get(len(items))
    if width is None:
        raise MdxError("<Filmstrip> holds three to five frames")

    # Landscape sheets, and pictures shown side by side, would shrink to strips in portrait boxes,
    # so they get fewer, wider columns.
    def shape(f: Element) -> float:
        pictures = page.node(f.props["node"])["pictures"]
        return sum(
            pictures[i]["width"] / pictures[i]["height"]
            for i in f.props.get("media", [0])
            if i < len(pictures)
        )

    shapes = [shape(f) for f in items if "node" in f.props]
    landscape = bool(shapes) and all(s > 1.1 for s in shapes)
    if landscape:
        width = {3: "md:grid-cols-3", 4: "md:grid-cols-2", 5: "md:grid-cols-3"}[len(items)]
    page.frame_box = "aspect-[4/3]" if landscape else "aspect-[3/4]"
    try:
        frames = "".join(render_element(page, f) for f in items)
    finally:
        page.frame_box = "aspect-[3/4]"
    return f'<div class="mt-6 grid grid-cols-2 gap-6 {width}">{frames}</div>'


@component("Frame", {"node": str, "media": list}, required=("node",))
def frame(page: Page, props: dict, children: object) -> str:
    node = page.node(props["node"])
    picks = props.get("media", [0])
    try:
        pictures = [node["pictures"][i] for i in picks]
    except IndexError:
        raise MdxError(
            f"<Frame node={props['node']!r}> has {len(node['pictures'])} pictures, asked for {picks}"
        ) from None
    images = "".join(
        f'<img class="max-h-full min-w-0 flex-1 object-contain" src="{esc(p["src"])}" alt="">'
        for p in pictures
    )
    return (
        f'<figure><div class="flex {page.frame_box} items-center justify-center gap-2 overflow-hidden rounded-sm p-2" '
        f'style="{ground(pictures[0])}">{images}</div>'
        f'<figcaption class="mt-2 text-sm">{text_of(page, children)}<br>{node_link(page, props["node"])}</figcaption></figure>'
    )


@component("Guards")
def guards(page: Page, props: dict, children: object) -> str:
    rows = "".join(render_element(page, g) for g in children_of(children, "Guard"))
    return (
        f'<table class="mt-4 w-full text-sm"><thead><tr><th class="{HEAD}">By hand</th><th class="{HEAD}">In the graph</th>'
        f'<th class="{HEAD}">How</th></tr></thead><tbody>{rows}</tbody></table>'
    )


@component("Guard", {"node": str, "how": str}, required=("node", "how"))
def guard(page: Page, props: dict, children: object) -> str:
    return (
        f'<tr><td class="{CELL} w-2/5">{text_of(page, children)}</td>'
        f'<td class="{CELL} whitespace-nowrap">{node_link(page, props["node"])}</td>'
        f'<td class="{CELL} text-zinc-500">{inline(props["how"])}</td></tr>'
    )


@component("Models")
def models(page: Page, props: dict, children: object) -> str:
    def role(m: dict) -> str:
        # Lower-case role words mid-sentence, but leave acronyms such as "3D" alone.
        parts = (
            [
                " and ".join(
                    k if k[:2].isupper() or k[0].isdigit() else k.lower() for k in m["roles"]
                )
            ]
            if m["roles"]
            else []
        )
        parts += [f"used by {page.title_of(n)}" for n in m["called_by"]]
        text = ", ".join(p for p in parts if p)
        return text[:1].upper() + text[1:]

    rows = "".join(
        f'<tr><td class="{CELL} font-medium">{esc(m["name"])}</td><td class="{CELL} text-zinc-500">{esc(m["provider"])}</td>'
        f'<td class="{CELL} text-zinc-500">{esc(role(m))}</td></tr>'
        for m in page.record["models"]
    )
    rows += "".join(
        f'<tr><td class="{CELL} font-medium">{esc(t["name"])}</td><td class="{CELL} text-zinc-500">local</td>'
        f'<td class="{CELL} text-zinc-500">{esc(t["role"])}</td></tr>'
        for t in page.front.get("tools", [])
    )
    return f'<table class="mt-4 w-full text-sm"><tbody>{rows}</tbody></table>'


@component("Columns")
def columns(page: Page, props: dict, children: object) -> str:
    if not isinstance(children, list):
        raise MdxError("<Columns> holds blocks")
    groups: list[list] = []
    for block in children:
        if (isinstance(block, Heading) and block.level == 2) or not groups:
            groups.append([])
        groups[-1].append(block)
    width = {1: "", 2: "lg:grid-cols-2", 3: "lg:grid-cols-3"}.get(len(groups))
    if width is None:
        raise MdxError("<Columns> holds one to three columns")
    return f'<div class="grid gap-x-12 {width}">{"".join(f"<div>{render_blocks(page, g)}</div>" for g in groups)}</div>'


FOLDER = (
    '<svg class="size-4 shrink-0 text-zinc-400" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2">'
    '<path d="M1.5 3.5h4.2l1.4 1.5h7.4v8.5h-13z" stroke-linejoin="round"/></svg>'
)
FILE = (
    '<svg class="size-4 shrink-0 text-zinc-400" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2">'
    '<path d="M3.5 1.5h6l3 3v10h-9z M9.5 1.5v3h3" stroke-linejoin="round"/></svg>'
)
CHEVRON_OPEN = (
    '<svg class="size-3 text-zinc-400" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.3">'
    '<path d="M3 4.5l3 3 3-3" stroke-linecap="round" stroke-linejoin="round"/></svg>'
)
CHEVRON_SHUT = (
    '<svg class="size-3 text-zinc-400" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.3">'
    '<path d="M4.5 3l3 3-3 3" stroke-linecap="round" stroke-linejoin="round"/></svg>'
)
KINDS = {
    ".glb": "3D model",
    ".json": "JSON record",
    ".png": "PNG image",
    ".webp": "WebP image",
    ".mkv": "Video",
    ".mp4": "Video",
    ".zip": "Archive",
    ".blend": "Blender file",
}


@component("Files")
def files(page: Page, props: dict, children: object) -> str:
    """A file-browser list of the run folder: the paths the page names, their parents, and a count of the rest."""
    tree = page.record["tree"]
    listed = children_of(children, "File")
    notes: dict[str, str] = {}
    order: list[str] = []
    for f in listed:
        path = f.props["path"].rstrip("/")
        if path not in tree:
            raise MdxError(f"<File path={f.props['path']!r}> is not in this run")
        notes[path] = text_of(page, f.children)
        parts = path.split("/")
        for depth in range(1, len(parts) + 1):
            ancestor = "/".join(parts[:depth])
            if ancestor not in order:
                order.append(ancestor)

    def children_in_order(parent: str) -> list[str]:
        return [p for p in order if (p.rsplit("/", 1)[0] if "/" in p else "") == parent]

    rows: list[str] = []

    def walk(parent: str, depth: int) -> None:
        for path in children_in_order(parent):
            entry, name = tree[path], path.rsplit("/", 1)[-1]
            folder = entry["kind"] == "dir"
            is_open = folder and bool(children_in_order(path))
            chevron = (CHEVRON_OPEN if is_open else CHEVRON_SHUT) if folder else ""
            kind = notes.get(path) or (
                f"Folder, {entry['files']} files"
                if folder
                else KINDS.get(Path(name).suffix, "File")
            )
            rows.append(
                '<tr class="even:bg-zinc-50 dark:even:bg-zinc-900/60">'
                f'<td class="py-1.5 pr-4"><span class="flex items-center gap-1.5" style="padding-left:{depth * 18}px">'
                f'<span class="flex w-3 justify-center">{chevron}</span>{FOLDER if folder else FILE}'
                f'<span class="{"font-medium" if path in notes else ""}">{esc(name)}</span></span></td>'
                f'<td class="whitespace-nowrap py-1.5 pr-4 text-right tabular-nums text-zinc-500">{size(entry["bytes"])}</td>'
                f'<td class="py-1.5 text-zinc-500">{kind}</td></tr>'
            )
            walk(path, depth + 1)

    walk("", 0)
    top = [p for p in tree if p and "/" not in p]
    rest = [p for p in top if p not in order]
    if rest:
        folders = sum(1 for p in rest if tree[p]["kind"] == "dir")
        counts = [
            f"{n} more {word}{'' if n == 1 else 's'}"
            for n, word in ((folders, "folder"), (len(rest) - folders, "file"))
            if n
        ]
        rows.append(
            f'<tr><td class="py-1.5 pr-4 pl-[18px] text-zinc-400" colspan="3">and {" and ".join(counts)} '
            "the pipeline keeps for recovery and auditing</td></tr>"
        )
    root = page.record["run"]["path"].rstrip("/").rsplit("/", 1)[-1]
    return (
        '<div class="mt-4 overflow-hidden rounded-md border border-zinc-200 dark:border-zinc-800">'
        '<div class="flex items-center gap-2 border-b border-zinc-200 bg-zinc-50 px-3 py-2 text-sm text-zinc-600 dark:border-zinc-800 '
        f'dark:bg-zinc-900 dark:text-zinc-400">{FOLDER}<span>{esc(root)}</span><span class="ml-auto tabular-nums text-zinc-400">'
        f"{tree['']['files']} files, {size(tree['']['bytes'])}</span></div>"
        '<div class="overflow-x-auto px-3 pb-2"><table class="w-full text-sm"><thead><tr>'
        '<th class="py-2 pr-4 text-left text-xs font-normal text-zinc-400">Name</th>'
        '<th class="py-2 pr-4 text-right text-xs font-normal text-zinc-400">Size</th>'
        '<th class="py-2 text-left text-xs font-normal text-zinc-400">Kind</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div></div>"
    )


def only_inside(parent: str) -> Callable[[Page, dict, object], str]:
    def render(page: Page, props: dict, children: object) -> str:
        raise MdxError(f"this element belongs inside <{parent}>")

    return render


REGISTRY["File"] = Component(only_inside("Files"), {"path": str}, ("path",))


SCOPE_HEADINGS = {"Works": "Works well", "Limit": "Not expected to work", "Tip": "Good to know"}


@component("Scope")
def scope(page: Page, props: dict, children: object) -> str:
    """What the workflow is for, what it is not for, and what to expect, as three plain lists."""
    items = [c for c in children if isinstance(c, Element)] if isinstance(children, list) else []
    if any(c.name not in SCOPE_HEADINGS for c in items):
        raise MdxError(f"<Scope> holds only {', '.join(f'<{n}>' for n in SCOPE_HEADINGS)}")
    columns = []
    for name, heading in SCOPE_HEADINGS.items():
        entries = [text_of(page, c.children) for c in items if c.name == name]
        if entries:
            lis = "".join(f'<li class="py-2">{e}</li>' for e in entries)
            columns.append(
                f'<div><h3 class="text-sm font-medium">{heading}</h3>'
                f'<ul class="mt-2 divide-y divide-zinc-200 text-sm text-zinc-700 dark:divide-zinc-800 dark:text-zinc-300">{lis}</ul></div>'
            )
    width = {1: "", 2: "md:grid-cols-2", 3: "md:grid-cols-3"}[len(columns)]
    return f'<div class="mt-6 grid gap-x-10 gap-y-8 {width}">{"".join(columns)}</div>'


for _name in SCOPE_HEADINGS:
    REGISTRY[_name] = Component(only_inside("Scope"), {})


@component(
    "Compare",
    {"node": str, "media": list, "left": str, "right": str, "at": int},
    required=("node", "left", "right"),
)
def compare(page: Page, props: dict, children: object) -> str:
    """Two same-sized pictures of one node, one over the other, with a handle to wipe between them.

    ``at`` is where the handle starts, in percent from the left; halfway unless the middle is the
    very thing the reader should see first.
    """
    node = page.node(props["node"])
    picks = props.get("media", [0, 1])
    try:
        before, after = (node["pictures"][i] for i in picks)
    except (IndexError, ValueError):
        raise MdxError(
            f"<Compare node={props['node']!r}> needs two of its {len(node['pictures'])} pictures, asked for {picks}"
        ) from None
    if (before["width"], before["height"]) != (after["width"], after["height"]):
        raise MdxError(f"<Compare node={props['node']!r}>: the two pictures differ in size")
    label = "absolute top-2 rounded-sm bg-zinc-900/70 px-1.5 py-0.5 text-xs text-white"
    at = props.get("at", 50)
    if not 0 <= at <= 100:
        raise MdxError(f"<Compare at={at}> must be a percentage")
    return (
        '<figure class="mt-6">'
        # A transparent picture sits on its checkerboard in both layers, so the one underneath never shows through.
        # Height is capped at 560 px, so a square sheet does not fill the screen while a wide one keeps the full width.
        f'<div data-compare class="relative select-none overflow-hidden rounded-sm" style="aspect-ratio:{after["width"]}/{after["height"]};'
        f'max-width:{round(560 * after["width"] / after["height"])}px;{ground(after)}">'
        f'<img class="absolute inset-0 h-full w-full" src="{esc(after["src"])}" alt="">'
        f'<div data-before class="absolute inset-0" style="clip-path:inset(0 {100 - at}% 0 0);{ground(before)}"><img class="h-full w-full" src="{esc(before["src"])}" alt=""></div>'
        f'<div data-handle class="pointer-events-none absolute inset-y-0 w-0.5 -translate-x-1/2 bg-white shadow" style="left:{at}%">'
        '<span class="absolute top-1/2 left-1/2 flex size-7 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full '
        'bg-white text-xs text-zinc-700 shadow">⇆</span></div>'
        f'<span class="{label} left-2">{esc(props["left"])}</span><span class="{label} right-2">{esc(props["right"])}</span>'
        f'<input type="range" min="0" max="100" value="{at}" aria-label="Wipe between the two pictures" '
        'class="absolute inset-0 h-full w-full cursor-ew-resize opacity-0"></div>'
        f'<figcaption class="mt-3 max-w-3xl text-sm text-zinc-600 dark:text-zinc-400">{text_of(page, children)}<br>{node_link(page, props["node"])}</figcaption></figure>'
    )


SHAPE_WORDS = {
    "steps": "Steps",
    "concavity_and_hole": "Hollow and hole",
    "one_cell_floating": "Thin ledge",
    "solid_ground": "Solid block",
}


@component("Painter", {"start": list}, required=("start",))
def painter(page: Page, props: dict, children: object) -> str:
    """A small tile map you can draw on, composed live from a real atlas through its neighbour lookup.

    Each <Atlas> names an atlas output of the record; the first is shown first. `start` is the
    shape the page opens with, as rows of 0 and 1. The preset shapes are the ones the atlas was
    validated against, plus the middle of the level it was made for.
    """
    items = children_of(children, "Atlas")
    if not items:
        raise MdxError("<Painter> holds one or more <Atlas output=...>")
    start = props["start"]
    if not start or any(
        not isinstance(r, str) or len(r) != len(start[0]) or set(r) - {"0", "1"} for r in start
    ):
        raise MdxError("<Painter start> is a list of equal-length rows of 0 and 1")
    atlases = []
    for item in items:
        out = page.record["outputs"].get(item.props["output"])
        if out is None or out["kind"] != "atlas":
            raise MdxError(f"<Atlas output={item.props['output']!r}> is not an atlas of this run")
        atlases.append(
            {
                "label": text_of(page, item.children),
                "src": out["src"],
                "cell": out["cell_px"],
                "columns": out["columns"],
                "rows": out["rows"],
                "lookup": out["lookup"],
            }
        )
    first = page.record["outputs"][items[0].props["output"]]
    shapes = {"Start again": start, "Part of the level": first["level"]}
    shapes |= {
        SHAPE_WORDS.get(k, k.replace("_", " ").capitalize()): v
        for k, v in first["shapes"].items()
        if k in SHAPE_WORDS
    }
    shapes["Clear"] = ["0" * len(start[0])] * len(start)
    button = (
        "rounded-sm border border-zinc-300 px-2 py-0.5 text-xs text-zinc-600 hover:border-zinc-500 aria-pressed:border-zinc-900 "
        "aria-pressed:text-zinc-900 dark:border-zinc-700 dark:text-zinc-400 dark:aria-pressed:border-zinc-100 dark:aria-pressed:text-zinc-100"
    )
    toggles = (
        "".join(
            f'<button data-atlas="{i}" aria-pressed="{"true" if i == 0 else "false"}" class="{button}">{a["label"]}</button>'
            for i, a in enumerate(atlases)
        )
        if len(atlases) > 1
        else ""
    )
    presets = "".join(
        f'<button data-shape="{esc(name)}" class="{button}">{esc(name)}</button>' for name in shapes
    )
    config = json.dumps({"start": start, "shapes": shapes, "atlases": atlases})
    return (
        f'<div data-painter="{esc(config)}" class="mt-6">'
        f'<div class="flex flex-wrap items-center gap-x-6 gap-y-2"><div class="flex gap-1.5">{toggles}</div>'
        f'<div class="flex flex-wrap gap-1.5">{presets}</div></div>'
        '<canvas class="mt-4 block w-full cursor-crosshair touch-none rounded-sm bg-zinc-50 dark:bg-zinc-900"></canvas>'
        '<p class="mt-3 max-w-3xl text-sm text-zinc-500">Click or drag to add or take away ground. Each cell looks at its eight '
        "neighbours and takes one of the 47 tiles; point at a cell to see which one in the atlas below.</p>"
        f'<div class="relative mt-4 max-w-3xl overflow-hidden rounded-sm" style="{CHECKER}">'
        f'<img data-sheet class="block w-full" src="{esc(atlases[0]["src"])}" alt="">'
        '<div data-highlight class="pointer-events-none absolute hidden outline-2 outline-offset-0 outline-zinc-900 dark:outline-zinc-100" '
        'style="box-shadow:0 0 0 9999px rgb(255 255 255 / 0.55)"></div></div></div>'
    )


REGISTRY["Atlas"] = Component(only_inside("Painter"), {"output": str}, ("output",))


FEATURE_WORDS = {
    "canvas_left_eye": "Eye on the left",
    "canvas_right_eye": "Eye on the right",
    "mouth": "Mouth",
}
STATE_WORDS = {
    ("eyes", "rest"): "Open",
    ("eyes", "eyes_half"): "Half",
    ("eyes", "eyes_closed"): "Closed",
    ("mouth", "rest"): "Rest",
}
SEGMENT = (
    "rounded-sm border border-zinc-300 px-2.5 py-1 text-xs text-zinc-600 hover:border-zinc-500 aria-pressed:border-zinc-900 "
    "aria-pressed:bg-zinc-900 aria-pressed:text-white dark:border-zinc-700 dark:text-zinc-400 dark:aria-pressed:border-zinc-100 "
    "dark:aria-pressed:bg-zinc-100 dark:aria-pressed:text-zinc-900"
)


def state_words(group: str, state: str) -> str:
    return (
        STATE_WORDS.get((group, state))
        or state.removeprefix(f"{group}_").removeprefix("mouth_").upper()
    )


@component("FaceRig", {"output": str}, required=("output",))
def face_rig(page: Page, props: dict, children: object) -> str:
    """The delivered face patches stacked on the rest state, with each eye and the mouth set separately.

    This is what a game does with the output: every feature is its own patch at one offset. The
    buttons set a feature's state; Blink and Wink replay the run's own blink timing; the timeline
    button plays the exact timeline the run rendered. The element's sentence is the caption.
    """
    rig = page.record["outputs"].get(props["output"])
    if rig is None or rig["kind"] != "face_rig":
        raise MdxError(f"<FaceRig output={props['output']!r}> is not a face rig of this run")
    place = rig["place"]
    at = f"left:{place['left']:.3f}%;top:{place['top']:.3f}%;width:{place['width']:.3f}%;height:{place['height']:.3f}%"
    layers = "".join(
        f'<img data-patch data-feature="{esc(p["feature"])}" data-state="{esc(p["state"])}" class="absolute hidden" style="{at}" '
        f'src="{esc(p["src"])}" alt="">'
        for p in rig["patches"]
    )
    picture = (
        f'<div class="relative aspect-square w-full max-w-[520px] overflow-hidden rounded-sm" style="{CHECKER}">'
        f'<img class="absolute inset-0 size-full" src="{esc(rig["base"])}" alt="">{layers}'
        f'<img data-changes class="absolute hidden" style="{at}" src="{esc(rig["changes"])}" alt=""></div>'
    )
    rows = "".join(
        f'<div class="flex flex-wrap items-center gap-3"><span class="w-32 text-zinc-500">{esc(FEATURE_WORDS.get(f["id"], f["id"]))}</span>'
        '<div class="flex gap-1">'
        + "".join(
            f'<button data-set="{esc(f["id"])}" data-state="{esc(s)}" aria-pressed="{"true" if s == "rest" else "false"}" '
            f'class="{SEGMENT}">{esc(state_words(f["group"], s))}</button>'
            for s in f["states"]
        )
        + "</div></div>"
        for f in rig["features"]
    )
    action = (
        "rounded-sm border border-zinc-300 px-2.5 py-1 text-xs text-zinc-700 hover:border-zinc-500 dark:border-zinc-700 "
        "dark:text-zinc-300"
    )
    toggle = "flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400"
    controls = (
        f'<div class="flex flex-col gap-3 text-sm">{rows}'
        '<div class="mt-3 flex flex-wrap gap-2">'
        f'<button data-action="blink" class="{action}">Blink</button><button data-action="wink" class="{action}">Wink</button>'
        f'<button data-action="timeline" class="{action}">Play the run\'s timeline</button></div>'
        f'<label class="{toggle} mt-1"><input data-auto="blink" type="checkbox" class="accent-zinc-900"> Blink on its own</label>'
        f'<label class="{toggle}"><input data-auto="talk" type="checkbox" class="accent-zinc-900"> Talk</label>'
        f'<label class="{toggle}"><input data-show-changes type="checkbox" class="accent-zinc-900"> Show every pixel that can change</label>'
        f'<p class="mt-3 max-w-md text-sm text-zinc-500">{text_of(page, children)} All {rig["combinations_verified"]} combinations the '
        "run rendered were rebuilt from these patches when this page was built, pixel for pixel.</p></div>"
    )
    config = json.dumps({"features": rig["features"], "timeline": rig["timeline"]})
    return f'<div data-face-rig="{esc(config)}" class="mt-6 grid items-start gap-8 md:grid-cols-[minmax(0,520px)_1fr]">{picture}{controls}</div>'


@component("PartStage", {"output": str, "clip": str}, required=("output",))
def part_stage(page: Page, props: dict, children: object) -> str:
    """The delivered model with each of its parts shown or hidden on its own.

    The export keeps the parts it was fitted from as separate meshes on one skeleton, which is what
    lets a game swap one of them. The buttons hide a part by its material, so the rest keeps
    playing the chosen clip. The element's sentence is the caption.
    """
    model = page.record["outputs"].get(props["output"])
    if model is None or model["kind"] != "model" or not model.get("parts"):
        raise MdxError(
            f"<PartStage output={props['output']!r}> is not a model made of separate parts"
        )
    first = props.get("clip") or model["clips"][0]
    viewer = (
        f'<div class="relative aspect-square w-full max-w-[520px] overflow-hidden rounded-sm" style="{ground(model["poster"])}">'
        f'<model-viewer class="absolute inset-0 h-full w-full" src="{esc(model["src"])}" loading="lazy" camera-controls '
        f'autoplay animation-name="{esc(first)}" shadow-intensity="0" interaction-prompt="none"></model-viewer></div>'
    )
    rows = "".join(
        '<div class="flex items-center gap-3">'
        f'<button data-part="{esc(part["id"])}" aria-pressed="true" class="{SEGMENT} w-16">{esc(part["id"].capitalize())}</button>'
        f'<span class="text-zinc-500">{part["triangles"]:,} triangles</span></div>'
        for part in model["parts"]
    )
    controls = (
        f'<div class="flex flex-col gap-3 text-sm">{rows}'
        f'<div class="mt-3 flex flex-wrap gap-1.5">{clip_buttons(model, first)}</div>'
        f'<p class="mt-3 max-w-md text-sm text-zinc-500">{text_of(page, children)}</p></div>'
    )
    config = json.dumps({part["id"]: part["materials"] for part in model["parts"]})
    return f'<div data-part-stage="{esc(config)}" class="mt-6 grid items-start gap-8 md:grid-cols-[minmax(0,520px)_1fr]">{viewer}{controls}</div>'


MOTION_WORDS = {
    "idle": "Idle",
    "walk": "Walk",
    "run": "Run",
    "jump": "Jump",
    "crouch": "Crouch",
    "climb_ladder": "Ladder",
    "climb_rope": "Rope",
    "basic_attack": "Attack",
    "skill_cast": "Cast",
    "hurt": "Hurt",
    "death": "Death",
}
MOTION_GROUPS = (
    ("Move", ("idle", "walk", "run", "jump", "crouch")),
    ("Climb", ("climb_ladder", "climb_rope")),
    ("Act", ("basic_attack", "skill_cast")),
    ("React", ("hurt", "death")),
)
KBD = "rounded-sm border border-zinc-300 px-1 font-sans text-[11px] text-zinc-600 dark:border-zinc-700 dark:text-zinc-400"


@component("SpriteStage", {"output": str}, required=("output",))
def sprite_stage(page: Page, props: dict, children: object) -> str:
    """The delivered strips on a stage, drawn the way the game draws them, to play one by one or to drive.

    Each strip is scaled by the ruler and its own size correction and stood on the ground by the
    bottom of its cell; right-facing strips are mirrored for left. Loops loop, one-shots play once,
    a hold holds its frame, and a climb steps its frames by the distance climbed. The buttons play a
    state; the keyboard drives the character as a game would. The element's sentence is the caption.
    """
    sprite = page.record["outputs"].get(props["output"])
    if sprite is None or sprite["kind"] != "sprite_set":
        raise MdxError(
            f"<SpriteStage output={props['output']!r}> is not an animation set of this run"
        )
    known = [s["state"] for s in sprite["states"]]
    groups = [(label, [s for s in names if s in known]) for label, names in MOTION_GROUPS]
    groups.append(
        ("Other", [s for s in known if not any(s in names for _, names in MOTION_GROUPS)])
    )
    rows = "".join(
        f'<div class="flex flex-wrap items-center gap-3"><span class="w-14 text-zinc-500">{esc(label)}</span><div class="flex flex-wrap gap-1">'
        + "".join(
            f'<button data-play="{esc(s)}" aria-pressed="false" class="{SEGMENT}">'
            f"{esc(MOTION_WORDS.get(s, s.replace('_', ' ').capitalize()))}</button>"
            for s in names
        )
        + "</div></div>"
        for label, names in groups
        if names
    )
    stage = (
        '<div data-stage tabindex="0" aria-label="Character stage: click, then use the arrow keys" class="relative w-full touch-manipulation '
        "select-none overflow-hidden rounded-sm border border-zinc-200 bg-zinc-50 outline-none focus-visible:border-zinc-500 "
        'dark:border-zinc-800 dark:bg-zinc-900" style="aspect-ratio:16/7">'
        '<div data-ground class="absolute inset-x-0 bottom-0 top-[84%] border-t border-zinc-300 bg-zinc-100 dark:border-zinc-700 dark:bg-zinc-800/60"></div>'
        '<div data-ladder class="absolute top-0 hidden border-x-[3px] border-zinc-400 dark:border-zinc-500"></div>'
        '<div data-rope class="absolute top-0 hidden w-[3px] bg-zinc-400 dark:bg-zinc-500"></div>'
        '<div data-shadow class="absolute rounded-[50%] bg-black blur-[3px]"></div>'
        '<div data-body class="absolute bg-no-repeat"></div>'
        f'<p data-hint class="absolute left-3 top-2 text-xs text-zinc-400">Click here, then use <kbd class="{KBD}">←</kbd> '
        f'<kbd class="{KBD}">→</kbd> <kbd class="{KBD}">↑</kbd> <kbd class="{KBD}">↓</kbd></p></div>'
    )
    toggle = "flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400"
    controls = (
        f'<div class="mt-5 grid gap-6 text-sm md:grid-cols-[1fr_minmax(0,22rem)]"><div class="flex flex-col gap-2.5">{rows}</div>'
        '<div class="flex flex-col gap-2">'
        f'<label class="{toggle}"><input data-opt="raw" type="checkbox" class="accent-zinc-900"> Without the size correction</label>'
        f'<label class="{toggle}"><input data-opt="box" type="checkbox" class="accent-zinc-900"> Show each frame\'s box</label>'
        f'<p class="mt-2 text-xs leading-relaxed text-zinc-500"><kbd class="{KBD}">←</kbd> <kbd class="{KBD}">→</kbd> walk, '
        f'with <kbd class="{KBD}">Shift</kbd> run, <kbd class="{KBD}">↑</kbd> jump, <kbd class="{KBD}">↓</kbd> crouch, '
        f'<kbd class="{KBD}">Z</kbd> attack, <kbd class="{KBD}">X</kbd> cast. On a ladder or rope, <kbd class="{KBD}">↑</kbd> '
        f'<kbd class="{KBD}">↓</kbd> climb and <kbd class="{KBD}">←</kbd> <kbd class="{KBD}">→</kbd> let go.</p></div></div>'
        '<p data-info class="mt-4 min-h-5 text-sm text-zinc-700 dark:text-zinc-300"></p>'
        f'<p class="mt-2 max-w-2xl text-sm text-zinc-500">{text_of(page, children)} Every strip was cut again from the model\'s own '
        "picture when this page was built, and matched the delivered file byte for byte.</p>"
    )
    config = json.dumps({key: sprite[key] for key in ("states", "per_unit", "baseline")})
    return f'<div data-sprite-stage="{esc(config)}" class="mt-6">{stage}{controls}</div>'


ACTION = (
    "rounded-sm border border-zinc-300 px-2.5 py-1 text-xs text-zinc-700 hover:border-zinc-500 dark:border-zinc-700 "
    "dark:text-zinc-300"
)


@component("ParallaxLoop", {"output": str}, required=("output",))
def parallax_loop(page: Page, props: dict, children: object) -> str:
    """A map's layers alone, scrolling without end, to play with; no ground and no character.

    Every layer is placed by its anchor and scrolled at its own parallax in the game's 1280x720 view.
    The camera runs on its own at a chosen speed and direction, or follows a drag or the arrow keys.
    Toggles move every layer at one speed and mark each layer's wrap and cuts; the table turns each
    layer on or off and changes its speed, height and size. The element's sentence is the caption.
    """
    backgrounds = page.record["outputs"].get(props["output"])
    if backgrounds is None or backgrounds["kind"] != "parallax":
        raise MdxError(
            f"<ParallaxLoop output={props['output']!r}> is not a set of parallax maps of this run"
        )
    width, height = backgrounds["view"]
    maps = "".join(
        f'<button data-map="{esc(m["id"])}" aria-pressed="false" class="{SEGMENT}">{esc(m["label"])}</button>'
        for m in backgrounds["maps"]
    )
    stage = (
        f'<div data-stage tabindex="0" aria-label="Layers: drag to scroll, or use the arrow keys" class="relative w-full cursor-grab '
        "touch-none select-none overflow-hidden rounded-sm border border-zinc-200 bg-sky-200 outline-none active:cursor-grabbing "
        f'focus-visible:border-zinc-500 dark:border-zinc-800" style="aspect-ratio:{width}/{height}">'
        f'<div data-world class="absolute left-0 top-0 origin-top-left" style="width:{width}px;height:{height}px"></div>'
        '<p data-hint class="absolute left-3 top-2 rounded-sm bg-white/80 px-1.5 py-0.5 text-xs text-zinc-600">Drag to scroll, '
        f'or click and use <kbd class="{KBD}">←</kbd> <kbd class="{KBD}">→</kbd>; <kbd class="{KBD}">Space</kbd> pauses</p></div>'
    )
    toggle = "flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400"
    controls = (
        '<div class="mt-4 flex flex-wrap items-center gap-x-6 gap-y-3">'
        f'<button data-play aria-pressed="true" class="{ACTION} w-16">Pause</button>'
        f'<label class="{toggle}">Camera <input data-speed type="range" min="-600" max="600" step="10" value="110" '
        'class="w-40 accent-zinc-900"><span data-speed-value class="w-24 tabular-nums"></span></label>'
        f'<label class="{toggle}"><input data-opt="flat" type="checkbox" class="accent-zinc-900"> Every layer at one speed</label>'
        f'<label class="{toggle}"><input data-opt="marks" type="checkbox" class="accent-zinc-900"> Mark where each layer repeats, '
        "and where it was cut</label></div>"
        f'<div class="mt-5 overflow-x-auto"><table class="w-full text-sm"><thead><tr><th class="{HEAD} w-8"></th>'
        f'<th class="{HEAD}">Layer</th><th class="{HEAD}">Moves at</th><th class="{HEAD}">Repeats every</th>'
        f'<th class="{HEAD}">How it loops</th><th class="{HEAD}">Move down</th><th class="{HEAD}">Size</th></tr></thead>'
        "<tbody data-layers></tbody></table></div>"
        f'<div class="mt-3 flex flex-wrap gap-2"><button data-placement="game" class="{ACTION}">Back to the game\'s placement</button></div>'
        f'<p class="mt-3 max-w-2xl text-sm text-zinc-500">{text_of(page, children)}</p>'
    )
    config = json.dumps({"maps": backgrounds["maps"], "view": backgrounds["view"]})
    return (
        f'<div data-parallax-playground="{esc(config)}" class="mt-6"><div class="mb-3 flex flex-wrap gap-1">{maps}</div>'
        f"{stage}{controls}</div>"
    )


@component("ParallaxStage", {"output": str}, required=("output",))
def parallax_stage(page: Page, props: dict, children: object) -> str:
    """The maps as the game draws them, with the character walking the ground and the camera following.

    Every layer is placed by its anchor and scrolled at its own parallax in the game's 1280x720 view,
    the ground is composed from the map's atlas and grid, and the character walks on it. Toggles
    move every layer at the ground's speed, and mark each layer's wrap and cuts so a seam could be
    looked for. The table below lists the current map's layers and hides any of them. The element's
    sentence is the caption.
    """
    backgrounds = page.record["outputs"].get(props["output"])
    if backgrounds is None or backgrounds["kind"] != "parallax":
        raise MdxError(
            f"<ParallaxStage output={props['output']!r}> is not a set of parallax maps of this run"
        )
    width, height = backgrounds["view"]
    maps = "".join(
        f'<button data-map="{esc(m["id"])}" aria-pressed="false" class="{SEGMENT}">{esc(m["label"])}</button>'
        for m in backgrounds["maps"]
    )
    stage = (
        f'<div data-stage tabindex="0" aria-label="Map stage: click, then use the arrow keys" class="relative w-full select-none '
        f'overflow-hidden rounded-sm border border-zinc-200 bg-sky-200 outline-none focus-visible:border-zinc-500 dark:border-zinc-800" '
        f'style="aspect-ratio:{width}/{height}">'
        f'<div data-world class="absolute left-0 top-0 origin-top-left" style="width:{width}px;height:{height}px"></div>'
        '<p data-hint class="absolute left-3 top-2 rounded-sm bg-white/80 px-1.5 py-0.5 text-xs text-zinc-600">Click here, then '
        f'<kbd class="{KBD}">←</kbd> <kbd class="{KBD}">→</kbd> to walk, <kbd class="{KBD}">Shift</kbd> to run, '
        f'<kbd class="{KBD}">↑</kbd> or <kbd class="{KBD}">Space</kbd> to jump</p></div>'
    )
    toggle = "flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400"
    controls = (
        '<div class="mt-4 flex flex-wrap gap-x-6 gap-y-2">'
        f'<label class="{toggle}"><input data-opt="auto" type="checkbox" checked class="accent-zinc-900"> Walk automatically</label>'
        f'<label class="{toggle}"><input data-opt="flat" type="checkbox" class="accent-zinc-900"> Every layer at the ground\'s speed</label>'
        f'<label class="{toggle}"><input data-opt="marks" type="checkbox" class="accent-zinc-900"> Mark where each layer repeats, '
        "and where it was cut</label></div>"
        f'<div class="mt-5 overflow-x-auto"><table class="w-full text-sm"><thead><tr><th class="{HEAD} w-8"></th>'
        f'<th class="{HEAD}">Layer</th><th class="{HEAD}">Moves at</th><th class="{HEAD}">Repeats every</th>'
        f'<th class="{HEAD}">How it loops</th><th class="{HEAD}">Move down</th><th class="{HEAD}">Size</th></tr></thead>'
        "<tbody data-layers></tbody></table></div>"
        f'<div class="mt-3 flex flex-wrap gap-2"><button data-placement="game" class="{ACTION}">Back to the game\'s placement</button></div>'
        f'<p class="mt-3 max-w-2xl text-sm text-zinc-500">{text_of(page, children)} Each layer is baked for this page the way the game '
        "bakes it: resized to the 720-pixel view, then given its contrast, saturation, haze and blur by the game's own formulas.</p>"
    )
    config = json.dumps(
        {"maps": backgrounds["maps"], "walker": backgrounds["walker"], "view": backgrounds["view"]}
    )
    return (
        f'<div data-parallax-stage="{esc(config)}" class="mt-6"><div class="mb-3 flex flex-wrap gap-1">{maps}</div>'
        f"{stage}{controls}</div>"
    )


def nine_slice(sheet: dict, scale: float) -> str:
    """CSS for a nine-slice sheet at the insets its gate measured, drawn `scale` times its natural size.

    The source image is left to the caller, so a button can swap it per state from its classes.
    """
    k = sheet["draw_scale"] / scale  # sheet pixels per CSS pixel
    i = sheet["insets"]
    widths = " ".join(f"{round(i[side] / k, 1)}px" for side in ("top", "right", "bottom", "left"))
    repeat = "round" if sheet["band_fill"] == "tile" else "stretch"
    return (
        f"border-style:solid;border-width:{widths};border-image-slice:{i['top']} {i['right']} {i['bottom']} {i['left']} fill;"
        f"border-image-width:{widths};border-image-repeat:{repeat}"
    )


TEXT_TONE = {"black": "text-zinc-900", "white": "text-white"}


@component("UiKit", {"backdrop": str, "buttons": list}, required=("buttons",))
def ui_kit(page: Page, props: dict, children: object) -> str:
    """A small game screen built from the delivered UI sheets and laid out by the gate's own measurements.

    The panel and the top bar stretch by the measured insets, the buttons swap to their hover,
    pressed and disabled cells, and the icons carry the roles the code names. The text colour on
    each surface is the one the gate found readable. `backdrop` names an input picture to sit
    behind it all; the element's sentence is written on the panel.
    """
    out = page.record["outputs"]
    need = ("panel_frame", "button_rect", "preview_icons")
    if missing := [k for k in need if k not in out]:
        raise MdxError(f"<UiKit> needs the sheets {', '.join(missing)} in this run")
    panel, button, icons = (out[k] for k in need)
    labels = props["buttons"]
    if not labels or not all(isinstance(x, str) for x in labels):
        raise MdxError("<UiKit buttons> is a list of button labels")

    face = panel["states"][0]
    k = panel["draw_scale"]
    panel_css = (
        f"{nine_slice(panel, 1)};border-image-source:url({esc(face['src'])});width:{round(face['width'] / k * 0.9)}px;"
        f"height:{round(face['height'] / k * 0.75)}px;min-width:{round((panel['insets']['left'] + panel['insets']['right']) / k + 80)}px;"
        f"min-height:{round((panel['insets']['top'] + panel['insets']['bottom']) / k + 40)}px"
    )
    # A grip on the frame's outer corner: the browser's own resize grip would sit under the corner ornament.
    dialogue = (
        f'<div class="relative max-w-full"><div data-panel class="max-w-full overflow-hidden {TEXT_TONE[face["text"]]}" style="{panel_css}">'
        f'<p class="p-3 text-[17px] font-medium leading-relaxed">{text_of(page, children)}</p></div>'
        '<button data-grip aria-label="Resize the panel" class="absolute -bottom-2 -right-2 flex size-6 cursor-nwse-resize touch-none '
        'items-center justify-center rounded-full bg-zinc-900/80 text-white shadow">'
        '<svg class="size-3" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5">'
        '<path d="M3 9h6V3M9 9L3 3" stroke-linecap="round" stroke-linejoin="round"/></svg></button></div>'
    )

    bar_css = f"{nine_slice(panel, 0.32)};border-image-source:url({esc(face['src'])})"
    tools = "".join(
        f'<button data-glyph="{esc(g["name"].replace("_", " "))}" data-words="{esc(g["words"])}" '
        f'class="size-10 shrink-0 transition-transform hover:-translate-y-0.5"><img class="size-full" src="{esc(g["src"])}" alt="{esc(g["name"])}"></button>'
        for g in icons["glyphs"]
    )
    bar = f'<div class="flex flex-wrap items-center gap-1.5" style="{bar_css}">{tools}</div>'

    states = {s["state"]: s for s in button["states"]}
    normal = states["normal"]
    scale = 0.75
    # The state images reach CSS as variables, which the page's script sets to absolute URLs: a url() inside a
    # variable resolves against the stylesheet that uses it, not against this page.
    variables = " ".join(
        f'data-{s[0]}="{esc(states[s]["src"])}"' for s in ("normal", "hover", "pressed", "disabled")
    )
    button_css = f"{nine_slice(button, scale)};height:{round(normal['height'] / (button['draw_scale'] / scale))}px"
    buttons = "".join(
        f'<button {"disabled " if i == len(labels) - 1 else ""}class="w-52 px-2 text-[15px] font-semibold {TEXT_TONE[normal["text"]]} '
        "[border-image-source:var(--n)] hover:[border-image-source:var(--h)] active:[border-image-source:var(--p)] "
        f'disabled:[border-image-source:var(--d)] disabled:opacity-90" {variables} style="{button_css}">{esc(label)}</button>'
        for i, label in enumerate(labels)
    )

    backdrop = ""
    if props.get("backdrop"):
        picture = page.record["inputs"][props["backdrop"]]["picture"]
        # The screen takes the picture's own shape, and still grows if the interface needs more room.
        backdrop = f"background:url({esc(picture['src'])}) center/cover;aspect-ratio:{picture['width']}/{picture['height']}"
    return (
        f'<div data-ui-kit class="mt-6 overflow-hidden rounded-sm bg-zinc-200 dark:bg-zinc-800" style="{backdrop}">'
        '<div class="flex h-full flex-col gap-6 bg-zinc-950/15 p-6">'
        f"{bar}"
        f'<div class="flex flex-wrap items-start gap-6">{dialogue}<div class="flex flex-col gap-3">{buttons}</div></div>'
        "</div></div>"
        '<p class="mt-3 max-w-3xl text-sm text-zinc-500">Built in your browser from the sheets the run delivered, laid out by '
        "the gate's own measurements. Drag the round grip on the panel's corner to resize it; the buttons swap to their hover, pressed and disabled "
        "cells. <span data-kit-caption>Point at an icon to see its role.</span></p>"
    )


# ------------------------------------------------------------------------------ try it


DOCUMENT = (
    '<svg class="size-4 shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2">'
    '<path d="M3.5 1.5h6l3 3v10h-9z M9.5 1.5v3h3 M5.5 8h5 M5.5 10.5h5" stroke-linejoin="round"/></svg>'
)


def reference(page: Page, props: dict) -> dict:
    source = page.record["inputs"].get(props["input"])
    if source is None:
        raise MdxError(
            f"<Ref input={props['input']!r}>: the record's inputs are {', '.join(page.record['inputs'])}"
        )
    return source


@component("Ref", {"input": str}, required=("input",))
def ref(page: Page, props: dict, children: object) -> str:
    """An inline reference to one of the workflow's inputs, shown as a chip like an attachment in an agent's prompt box."""
    source = reference(page, props)
    label = text_of(page, children) or esc(source.get("file", props["input"]))
    number = ""
    if page.refs is not None:
        page.refs.append(props["input"])
        number = (
            f'<span class="flex size-4 items-center justify-center rounded-full bg-zinc-100 text-[10px] font-semibold '
            f'text-zinc-900">{len(page.refs)}</span>'
        )
    if source["kind"] == "image":
        icon = f'<img class="size-6 rounded-sm object-cover object-top" style="{ground(source["picture"])}" src="{esc(source["picture"]["src"])}" alt="">'
    else:
        icon = DOCUMENT
    tone = (
        "bg-zinc-800 text-zinc-100"
        if page.refs is not None
        else "bg-zinc-100 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-100"
    )
    title = (
        esc(source["text"][:240] + "…") if source["kind"] == "text" else esc(source.get("file", ""))
    )
    return (
        f'<span class="mx-0.5 inline-flex items-center gap-1.5 rounded-md py-0.5 pl-1 pr-2 align-middle text-[14px] leading-6 {tone}" '
        f'title="{title}">{icon}{number}{label}</span>'
    )


def plain_prompt(page: Page, paragraphs: list[Paragraph]) -> str:
    """The prompt as text to paste: each reference names the file to attach; a text input is appended in full."""
    lines, appended = [], []
    for p in paragraphs:
        words = []
        for part in p.parts:
            if isinstance(part, str):
                words.append(plain(part))
                continue
            source = reference(page, part.props)
            label = (
                plain(" ".join(x for x in part.children.parts if isinstance(x, str)))
                if isinstance(part.children, Paragraph)
                else ""
            )
            if source["kind"] == "text":
                words.append(f"{label} (below)" if label else "the text below")
                appended.append(source["text"])
            else:
                words.append(
                    f"{label} (attach {source.get('file', 'your file')})"
                    if label
                    else f"the attached {source.get('file', 'file')}"
                )
        lines.append("".join(words))
    text = "\n\n".join(lines)
    for extra in appended:
        text += "\n\n---\n" + extra
    return text


@component("Try")
def try_it(page: Page, props: dict, children: object) -> str:
    """Tabs with the same request two ways: a prompt for your own agent, and the commands it would run."""
    labels = {"Agent": "For agents", "Shell": "Command line"}
    panes = [c for c in children if isinstance(c, Element)] if isinstance(children, list) else []
    if not panes or any(p.name not in labels for p in panes):
        raise MdxError("<Try> holds <Agent> and <Shell>")
    tabs = "".join(
        f'<button data-tab="{i}" aria-pressed="{"true" if i == 0 else "false"}" class="border-b-2 border-transparent px-1 pb-2 '
        "text-sm text-zinc-500 aria-pressed:border-zinc-900 aria-pressed:text-zinc-900 dark:aria-pressed:border-zinc-100 "
        f'dark:aria-pressed:text-zinc-100">{labels[p.name]}</button>'
        for i, p in enumerate(panes)
    )
    bodies = "".join(
        f'<div data-pane="{i}" class="{"" if i == 0 else "hidden"}">{render_element(page, p)}</div>'
        for i, p in enumerate(panes)
    )
    return f'<div data-tabs class="mt-6"><div class="flex gap-6 border-b border-zinc-200 dark:border-zinc-800">{tabs}</div><div class="mt-6">{bodies}</div></div>'


COPY = (
    '<svg class="size-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3">'
    '<rect x="5.5" y="5.5" width="8" height="8" rx="1.5"/><path d="M3.5 10.5h-1v-8h8v1"/></svg>'
)


@component("Agent")
def agent(page: Page, props: dict, children: object) -> str:
    paragraphs = (
        [b for b in children if isinstance(b, Paragraph)] if isinstance(children, list) else []
    )
    if not paragraphs:
        raise MdxError("<Agent> holds the prompt as one or more paragraphs")
    page.refs = []
    try:
        body = "".join(
            f'<p class="[&+&]:mt-3">{render_inline(page, p.parts)}</p>' for p in paragraphs
        )
    finally:
        page.refs = None
    copy = plain_prompt(page, paragraphs)
    return (
        '<div class="max-w-3xl rounded-3xl bg-zinc-900 p-5 text-[15px] leading-8 text-zinc-100 dark:ring-1 dark:ring-zinc-800">'
        f"{body}"
        '<div class="mt-4 flex items-center justify-between">'
        '<span class="flex size-8 items-center justify-center rounded-full border border-zinc-700 text-zinc-400">+</span>'
        '<div class="flex items-center gap-3">'
        f'<button data-copy="{esc(copy)}" class="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs text-zinc-400 '
        f'hover:bg-zinc-800 hover:text-zinc-100">{COPY}<span>Copy prompt</span></button>'
        '<span class="flex size-9 items-center justify-center rounded-full bg-zinc-100 text-zinc-900">'
        '<svg class="size-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6">'
        '<path d="M8 13V3.5M4 7l4-4 4 4" stroke-linecap="round" stroke-linejoin="round"/></svg></span>'
        "</div></div></div>"
        '<p class="mt-3 text-sm text-zinc-500">Paste it into an agent that can use this repository, and attach your own files '
        "where the prompt refers to them.</p>"
    )


@component("Shell")
def shell(page: Page, props: dict, children: object) -> str:
    blocks = children if isinstance(children, list) else []
    code = "\n\n".join(b.code for b in blocks if isinstance(b, CodeBlock))
    if not code:
        raise MdxError("<Shell> holds at least one ``` code block")
    return (
        f'<div class="max-w-3xl">{render_blocks(page, blocks)}'
        f'<button data-copy="{esc(code)}" class="mt-3 flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-900 '
        f'dark:hover:text-zinc-100">{COPY}<span>Copy commands</span></button></div>'
    )


# ------------------------------------------------------------------------------ related pages


def related_links(front: dict, pages: dict[str, dict]) -> str:
    """A line under the promise naming the pages this one points to with `related`."""
    links = ", ".join(
        f'<a class="underline decoration-zinc-300 underline-offset-2 hover:text-zinc-900 dark:hover:text-zinc-100" '
        f'href="../{esc(slug)}/index.html">{esc(pages[slug]["title"])}</a>'
        for slug in front.get("related", [])
    )
    return f'<p class="mt-4 text-sm text-zinc-500">See also: {links}</p>' if links else ""


# ------------------------------------------------------------------------------ node graph view


NOT_NEEDED = {
    "verdict_reused": "Nothing changed, so the first verdict stands",
    "revision_reused": "The first round passed",
    "recovery_not_started": "Not needed: the first rig passed",
}


def node_card(page: Page, node_id: str) -> str:
    n = page.node(node_id)
    idle = bool(n["not_needed"])
    status = ""
    if n["verdict"]:
        status = (
            '<span class="text-[11px] text-emerald-700 dark:text-emerald-400">✓ accepted</span>'
            if n["verdict"]["accepted"]
            else '<span class="text-[11px] text-red-600 dark:text-red-400">✗ refused</span>'
        )
    elif n["checks"] and not idle:
        status = (
            '<span class="text-[11px] text-emerald-700 dark:text-emerald-400">✓ checked</span>'
            if all(c["passed"] for c in n["checks"])
            else '<span class="text-[11px] text-red-600 dark:text-red-400">✗ check failed</span>'
        )
    elif n["state"] == "failed":
        status = '<span class="text-[11px] text-red-600 dark:text-red-400">failed</span>'
    thumb = n["thumb"]
    if thumb is None and n["kind"] == "Reviewer" and not idle:
        thumb = next(
            (page.node(d)["thumb"] for d in n["depends_on"] if page.node(d)["thumb"]), None
        )  # what it judged
    if n["kind"] == "Gate" and node_id != page.front["run"]["output_node"]:
        thumb = None
    picture = framed(thumb, "aspect-[16/10] w-full") if thumb and not idle else ""
    if idle:
        foot = f'<p class="text-[11px] leading-snug text-zinc-400">{esc(NOT_NEEDED.get(n["not_needed"], "Not needed"))}</p>'
        frame = "border-dashed border-zinc-300 bg-transparent text-zinc-400 dark:border-zinc-700"
    else:
        bits = [b for b in (n["model"], clock(n["duration_ms"]), money(n["cost_usd"])) if b]
        foot = f'<p class="text-[11px] leading-snug text-zinc-500">{esc(" · ".join(bits))}</p>'
        frame = "border-zinc-200 bg-white hover:border-zinc-400 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:border-zinc-600"
    return (
        f'<button class="node relative z-[2] flex w-48 flex-col gap-1.5 rounded-sm border p-2.5 text-left {frame}" data-node="{esc(node_id)}" id="node-{esc(node_id)}">'
        f'<span class="flex items-center justify-between"><span class="text-[11px] text-zinc-400">{esc(n["kind"])}</span>{status}</span>'
        f'<span class="text-[13px] font-medium leading-snug">{esc(page.title_of(node_id))}</span>{picture}{foot}</button>'
    )


def node_graph(page: Page) -> str:
    stages = page.front.get("stages", [])
    placed = [nid for s in stages for row in s["rows"] for nid in row]
    missing = sorted(set(page.record["nodes"]) - set(placed))
    unknown = sorted(set(placed) - set(page.record["nodes"]))
    doubled = sorted({nid for nid in placed if placed.count(nid) > 1})
    if missing or unknown or doubled:
        raise MdxError(
            f"stages must place every node once: unplaced {missing}, unknown {unknown}, doubled {doubled}"
        )
    return "".join(
        '<section class="w-min rounded-sm border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">'
        f'<header class="mb-4"><h3 class="text-sm font-medium">{esc(s["label"])}</h3>'
        f'<p class="mt-1 text-xs leading-snug text-zinc-500">{inline(s.get("note", ""))}</p></header>'
        + "".join(
            f'<div class="mt-4 flex items-start gap-5 first-of-type:mt-0">{"".join(node_card(page, nid) for nid in row)}</div>'
            for row in s["rows"]
        )
        + "</section>"
        for s in stages
    )


CHECK_WORDS = {
    "all_native_frames_lossless_verified": "Every frame decoded again and verified lossless",
    "canonical_first_frame_exact": "The first frame is exactly the handed-on picture",
    "loop_endpoints_exact": "The first and last frames match exactly",
    "middle_motion_preserved_outside_authored_fields": "Motion outside the held face is left as generated",
    "alpha_exact": "Transparency is unchanged",
    "decoded_visible_rgba_and_alpha_exact": "The saved files decode to exactly the same pixels",
    "feature_masks_disjoint": "Eye and mouth areas do not overlap",
    "outside_support_rgba_exact": "Every pixel outside the patches is unchanged",
    "rest_rgba_exact": "The resting face matches the original exactly",
    "paint_canvas_exact": "The sheet came back at exactly the size it was asked for",
    "joins_within_tone_limit": "No join between two tiles steps in tone beyond the limit",
    "material_painted": "Every tile is painted, none left flat",
    "no_transparent_pixels": "No tile has a hole in it",
    "lookup_complete": "Every one of the 47 neighbour patterns has a tile",
    "reserved_cell_clear": "The one reserved cell is left empty",
    "exterior_transparent": "Everything outside the art is fully transparent",
    "bands_tile_cleanly": "The edge bands repeat without a visible seam",
    "text_area_quiet": "The text area is quiet enough to write on",
    "text_readable": "Text on it reaches readable contrast",
    "states_same_shape": "All four states keep the same outline and size",
    "states_distinct": "Each state is visibly different from the normal one",
    "glyphs_in_order": "All 16 icons are there, each in its own cell",
    "glyphs_one_size": "The icons read as one set, at one size",
    "nothing_outside_cells": "Nothing is drawn outside the cells",
    "transparent_ground": "The drawing has a truly transparent background",
    "canvas_edges_clear": "Nothing touches the edge of the canvas",
    "every_frame_drawn": "Every frame has a pose in it",
    "one_pose_per_frame": "Each pose was found whole and given its own cell",
    "wrap_like_its_interior": "The wrap steps no more than the layer's own columns do",
    "cuts_like_its_interior": "Both cuts step no more than the layer's own columns do, and the two pictures agreed there",
    "repaint_admitted": "The repaint passed that test",
    "loops_after_trim": "It still loops after its empty rows are trimmed",
}


def check_words(name: str) -> str:
    text = CHECK_WORDS.get(name, name.replace("_", " "))
    return text[:1].upper() + text[1:]


def drawer_data(page: Page) -> dict:
    """What the node drawer shows, keyed by node id, with wording already applied."""
    out = {}
    for nid, n in page.record["nodes"].items():
        tries = n["attempts"]
        out[nid] = {
            "id": nid,
            "title": page.title_of(nid),
            "kind": n["kind"],
            "description": n["description"],
            "model": f"{n['model']} via {n['provider']}" if n["model"] else "Runs locally",
            "time": clock(n["duration_ms"]),
            "cost": money(n["cost_usd"]),
            "tries": None
            if not tries
            else ("first try" if tries == 1 else f"{tries} tries of {n['max_attempts']}"),
            "not_needed": NOT_NEEDED.get(n["not_needed"], "Not needed")
            if n["not_needed"]
            else None,
            "verdict": n["verdict"],
            "rationale": n["rationale"],
            "open_issues": n["open_issues"],
            "pictures": n["pictures"],
            "depends_on": n["depends_on"],
            "checks": [
                {"name": check_words(c["name"]), "passed": c["passed"]} for c in n["checks"]
            ],
            "prompt": n["prompt"],
        }
    return out
