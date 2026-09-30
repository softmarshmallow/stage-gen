"""Build the static showcase: content/*.mdx + run folders -> site/.

Per page: parse the MDX, run the page's adapter to write `record.json` and derived media, render
the body with the fixed component set, then fill the shared shell. The index lists every page,
including planned ones. CSS is compiled last, from the classes the templates and components use.
"""

from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

from .adapters import ADAPTERS
from .components import (
    CHECKER,
    Page,
    drawer_data,
    minutes,
    money,
    node_graph,
    related_links,
    render_blocks,
)
from .mdx import MdxError, parse
from .media import Media

ROOT = Path(__file__).resolve().parent.parent  # apps/showcase
REPO = ROOT.parent.parent


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def fill(template: str, values: dict[str, str]) -> str:
    return re.sub(r"\{\{(\w+)\}\}", lambda m: values[m.group(1)], template)


def build_page(slug: str, front: dict, body: list, site: Path, related: str = "") -> dict:
    out = site / slug
    if out.exists():
        shutil.rmtree(out)
    run = front["run"]
    media = Media(out / "media", REPO)
    record = ADAPTERS[run["adapter"]](REPO, media, run)
    page = Page(front, record)
    html_body = render_blocks(page, body)
    graph = node_graph(page)
    footer = esc(
        front.get(
            "footer",
            "Every picture on this page comes from one real run of this workflow. "
            "Nothing was drawn for it.",
        )
    )
    shell = (ROOT / "templates" / "page.html").read_text(encoding="utf-8")
    (out / "index.html").write_text(
        fill(
            shell,
            {
                "title": esc(front["title"]),
                "promise": esc(front["promise"]),
                "body": html_body,
                "graph": graph,
                "footer": footer,
                "related": related,
                "data": json.dumps(drawer_data(page)).replace("</", "<\\/"),
            },
        ),
        encoding="utf-8",
    )
    (out / "record.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    (out / "figures.json").write_text(
        json.dumps({"run": run["path"], "files": media.ledger}, indent=2), encoding="utf-8"
    )
    hero = next(iter(record["outputs"].values()))["poster"]
    m = record["metrics"]
    cost = m.get("cost_usd", m.get("estimated_cost_usd"))
    meta = " · ".join(
        x
        for x in (
            minutes(m["wall_seconds"]),
            money(cost) and ("about " if "cost_usd" not in m else "") + money(cost),
        )
        if x
    )
    return {
        "slug": slug,
        "front": front,
        "hero": f"{slug}/{hero['src']}",
        "hero_bg": hero["bg"],
        "meta": meta,
        "hero_wide": hero["width"] >= hero["height"] * 1.6,
    }


def planned_still(slug: str, front: dict, site: Path) -> dict:
    target = site / "stills" / f"{slug}.webp"
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(REPO / front["still"]) as im:
        im = im.convert("RGBA")
        if front.get("still_crop"):
            im = im.crop(tuple(front["still_crop"]))
        flat = Image.new("RGBA", im.size, (228, 228, 231, 255))
        flat.alpha_composite(im)
        square = Media.pad_to(flat.convert("RGB"), 1.0)
        square.thumbnail((720, 720), Image.LANCZOS)
        square.save(target, "WEBP", quality=84)
    return {
        "slug": slug,
        "front": front,
        "hero": f"stills/{slug}.webp",
        "hero_bg": "#e4e4e7",
        "meta": "not built yet",
    }


def build_index(cards: list[dict], site: Path) -> None:
    items = []
    for c in sorted(cards, key=lambda c: c["front"].get("order", 99)):
        f, planned = c["front"], c["meta"] == "not built yet"
        ground = CHECKER if c["hero_bg"] == "transparent" else f"background:{esc(c['hero_bg'])}"
        # A wide sheet fills the square with its middle instead of shrinking to a strip.
        fit = (
            "h-full w-full object-cover"
            if c.get("hero_wide")
            else "max-h-full max-w-full object-contain"
        )
        inner = (
            '<div class="flex aspect-square items-center justify-center overflow-hidden '
            f'rounded-sm" style="{ground}">'
            f'<img class="{fit}" src="{esc(c["hero"])}" alt=""></div>'
            '<h2 class="mt-4 font-medium group-hover:underline group-hover:underline-offset-2">'
            f"{esc(f['title'])}</h2>"
            f'<p class="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{esc(f["promise"])}</p>'
            f'<p class="mt-3 text-sm text-zinc-500">{esc(c["meta"])}</p>'
        )
        items.append(
            f'<div class="opacity-50">{inner}</div>'
            if planned
            else f'<a class="group block" href="{esc(c["slug"])}/index.html">{inner}</a>'
        )
    shell = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    (site / "index.html").write_text(shell.replace("{{cards}}", "".join(items)), encoding="utf-8")


def compile_css(site: Path) -> None:
    out = site / "assets" / "showcase.css"
    out.parent.mkdir(parents=True, exist_ok=True)
    source = (
        (ROOT / "styles" / "showcase.css")
        .read_text(encoding="utf-8")
        .replace("{{root}}", str(ROOT))
    )
    subprocess.run(
        [
            "node",
            str(REPO / "web" / "scripts" / "showcase-tailwind.mjs"),
            str(REPO / "web"),
            str(out),
        ],
        input=source,
        text=True,
        check=True,
    )


def build(site: Path, only: frozenset[str] = frozenset()) -> None:
    """Build every page and the index, or just the named pages while one is being written."""
    parsed: dict[str, tuple[dict, list]] = {}
    for path in sorted((ROOT / "content").glob("*.mdx")):
        try:
            parsed[path.stem] = parse(path.read_text(encoding="utf-8"))
        except MdxError as error:
            sys.exit(f"{path.name}: {error}")
    fronts = {slug: front for slug, (front, _) in parsed.items()}
    for slug, front in fronts.items():
        if unknown := sorted(set(front.get("related", [])) - fronts.keys()):
            sys.exit(f"{slug}.mdx: related names {', '.join(unknown)}, which is not a page")
    if only - parsed.keys():
        sys.exit(f"no such page: {', '.join(sorted(only - parsed.keys()))}")
    cards = []
    for slug, (front, body) in parsed.items():
        if only and slug not in only:
            continue
        try:
            if front.get("status") == "planned":
                cards.append(planned_still(slug, front, site))
            else:
                cards.append(build_page(slug, front, body, site, related_links(front, fronts)))
                print(f"built {slug}")
        except MdxError as error:
            sys.exit(f"{slug}.mdx: {error}")
    if not only:
        build_index(cards, site)
    compile_css(site)
    print(site / "index.html")
