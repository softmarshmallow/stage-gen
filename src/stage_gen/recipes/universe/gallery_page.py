"""Consumer-owned static gallery page rendered from a gallery run's manifest.

This is the minimum V1 consumer: one HTML file, no build step, no external
assets. It lives in ``<run>/consumer/`` and references the canonical package
images by relative path. It never copies or promotes anything back into the
package.
"""

from __future__ import annotations

# ruff: noqa: E501
import contextlib
import html
import json
from pathlib import Path

from stage_gen.components._authored_package import read_package_member
from stage_gen.recipes.universe.universe_graph import (
    INPUT_POSTER_PROXY_REF,
    INPUT_UNIVERSE_REF,
)

CLASS_ORDER = ("actor", "collective", "place", "thing", "kind", "system", "event", "idea")


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _read_within(run_dir: Path, ref: str) -> bytes:
    """Read one run-relative file, following no symlink below the run.

    Lexical confinement is not enough here. A manifest is data the page is
    handed, and a run directory can be unpacked from anywhere, so a symlinked
    ancestor inside the run would let a crafted manifest pull bytes out of the
    run and publish them into the page. Each segment is opened ``O_NOFOLLOW``
    instead, which makes the check and the read the same operation.
    """

    return read_package_member(run_dir, ref, label="gallery page input")


def render(run_dir: Path) -> str:
    """Render one finished gallery run into a single self-contained HTML page.

    Everything it reads lives inside the run. The gallery run carries its own
    copy of the admitted universe and the poster proxy, so a package can be
    moved, archived, or served from anywhere without the page losing half its
    text.
    """

    run_dir = run_dir.resolve()
    manifest = json.loads(_read_within(run_dir, "manifest.json"))
    universe = json.loads(_read_within(run_dir, INPUT_UNIVERSE_REF))
    proposal = universe["proposal"]
    plan_by_entity = {p["entity_id"]: p for p in universe["plan"]["plans"]}
    consumer = run_dir / "consumer"
    consumer.mkdir(exist_ok=True)
    # A run without a poster proxy still renders; the page just loses its header image.
    poster_shown = False
    with contextlib.suppress(OSError, ValueError):
        (consumer / "poster.jpg").write_bytes(_read_within(run_dir, INPUT_POSTER_PROXY_REF))
        poster_shown = True
    names = {e["entity_id"]: e["display_name"] for e in proposal["entities"]}
    entities_by_id = {e["entity_id"]: e for e in proposal["entities"]}
    incident: dict[str, list[dict[str, object]]] = {eid: [] for eid in names}
    for rel in proposal["relationships"]:
        for me, other in (
            (rel["source_entity_id"], rel["target_entity_id"]),
            (rel["target_entity_id"], rel["source_entity_id"]),
        ):
            if me in incident:
                incident[me].append(
                    {
                        "kind": rel["relationship_kind"],
                        "other": other,
                        "summary": rel["summary"],
                        "outgoing": me == rel["source_entity_id"],
                    }
                )
    markers: dict[str, list[dict[str, object]]] = {}
    for marker in proposal["identity_markers"]:
        markers.setdefault(marker["owner_entity_id"], []).append(marker)

    cards: list[str] = []
    ordered = sorted(
        manifest["entities"],
        key=lambda m: (CLASS_ORDER.index(m["primary_class"]), m["display_name"]),
    )
    for entry in ordered:
        eid = entry["entity_id"]
        entity = entities_by_id[eid]
        plan = plan_by_entity.get(eid, {})
        status = entry["status"]
        record = (
            json.loads(_read_within(run_dir, str(entry["record"]))) if entry.get("record") else None
        )
        teaches = record["review"]["what_the_image_teaches"] if record else ""
        image_html = (
            f'<img loading="lazy" src="../{_e(entry["image"])}" alt="{_e(entity["display_name"])}">'
            if entry.get("image")
            else '<div class="missing">no image</div>'
        )
        chips = "".join(
            f'<span class="chip">{_e(c)}</span>'
            for c in [entity["primary_class"], *entity.get("facets", [])]
        )
        rels = "".join(
            f'<li><span class="kind">{"→" if r["outgoing"] else "←"} {_e(r["kind"])}</span> <a href="#{_e(r["other"])}">{_e(names.get(str(r["other"]), r["other"]))}</a><span class="rel-summary"> {_e(r["summary"])}</span></li>'
            for r in incident[eid]
        )
        facts = "".join(
            f'<li><span class="lineage">{_e(f["lineage"].replace("_", " "))}</span> {_e(f["claim"])}</li>'
            for f in entity["facts"]
        )
        marker_html = "".join(
            f"<li>{_e(m['form'])}: {_e(m['meaning'])}</li>" for m in markers.get(eid, [])
        )
        register = plan.get("scene_register", {})
        register_text = ", ".join(
            str(register.get(k, ""))
            for k in ("scale", "time_of_day", "weather", "setting", "population", "energy")
            if register.get(k)
        )
        blocking = (
            "".join(
                f"<li>{_e(b)}</li>"
                for b in (record["review"]["blocking_findings"] if record else [])
            )
            if status == "rejected"
            else ""
        )
        reason = (
            f'<p class="reason">{_e(entry.get("reason", ""))}</p>' if entry.get("reason") else ""
        )
        cards.append(
            f"""<article class="card status-{_e(status)}" id="{_e(eid)}" data-class="{_e(entity["primary_class"])}" data-status="{_e(status)}">
  <figure>{image_html}<figcaption><span class="status">{_e(status.replace("_", " "))}</span>{chips}</figcaption></figure>
  <div class="body">
    <h3>{_e(entity["display_name"])} <small>{_e(entity["entity_kind"])}</small></h3>
    <p class="summary">{_e(entity["summary"])}</p>
    <details><summary>How it works or lives</summary><p>{_e(entity["how_it_works_or_lives"])}</p><p class="tension"><strong>Present tension.</strong> {_e(entity["present_tension"])}</p></details>
    <details><summary>Facts</summary><ul class="facts">{facts}</ul></details>
    <details open><summary>Relationships ({len(incident[eid])})</summary><ul class="rels">{rels}</ul></details>
    {f"<details><summary>Identity markers</summary><ul>{marker_html}</ul></details>" if marker_html else ""}
    <details><summary>This image</summary>
      <p><strong>{_e(plan.get("primary_purpose", ""))}</strong> · {_e(plan.get("audience_question", ""))}</p>
      <p class="register">{_e(register_text)}</p>
      <p>{_e(plan.get("scene_premise", ""))}</p>
      {f'<p class="teaches"><strong>What it teaches on its own.</strong> {_e(teaches)}</p>' if teaches else ""}
      {f'<ul class="blocking">{blocking}</ul>' if blocking else ""}
      {reason}
    </details>
  </div>
</article>"""
        )

    viewpoints = "".join(
        f'<li><strong>{_e(v["display_name"])}</strong> — {_e(v["summary"])} <em>{_e(v["entry_question"])}</em> <span class="anchors">{" ".join(f"<a href=#{_e(a)}>{_e(names.get(a, a))}</a>" for a in v["anchor_entity_ids"])}</span></li>'
        for v in proposal["viewpoints"]
    )
    tensions = "".join(
        f'<li><strong>{_e(t["summary"])}</strong><br>{_e(t["material_stakes"])}<br><em>{_e(t["competing_legitimate_needs"])}</em> <span class="anchors">{" ".join(f"<a href=#{_e(a)}>{_e(names.get(a, a))}</a>" for a in t["participant_entity_ids"])}</span></li>'
        for t in proposal["institutional_tensions"]
    )
    questions = "".join(f"<li>{_e(q)}</li>" for q in proposal["unresolved_questions"])
    rules = "".join(f"<li>{_e(r['claim'])}</li>" for r in proposal["physical_ecological_rules"])
    counts = " · ".join(f"{_e(k.replace('_', ' '))} {v}" for k, v in manifest["counts"].items())
    class_buttons = "".join(
        f'<button data-filter-class="{c}">{c}</button>'
        for c in CLASS_ORDER
        if any(e["primary_class"] == c for e in manifest["entities"])
    )
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(proposal["title"])}</title>
<style>
:root{{color-scheme:light dark;--bg:#f6f5f2;--fg:#1c1b19;--muted:#6b675f;--card:#fff;--line:#dcd8d0;--accent:#2a6f6f;--warn:#9a4b1f}}
@media(prefers-color-scheme:dark){{:root{{--bg:#141412;--fg:#e8e5df;--muted:#a09b91;--card:#1e1d1a;--line:#33312c;--accent:#7fc4c4;--warn:#e29a62}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
a{{color:var(--accent)}}header{{display:grid;grid-template-columns:minmax(160px,240px) 1fr;gap:28px;padding:32px;max-width:1400px;margin:0 auto}}
header img{{width:100%;border-radius:6px;border:1px solid var(--line)}}h1{{font-size:2.2rem;margin:0 0 8px}}h2{{font-size:1.3rem;margin:32px 0 12px}}
.meta{{color:var(--muted);font-size:.9rem}}section{{max-width:1400px;margin:0 auto;padding:0 32px}}
.intro p{{max-width:70ch}}ul.plain{{padding-left:20px;max-width:90ch}}ul.plain li{{margin-bottom:10px}}.anchors a{{margin-right:8px;font-size:.85rem}}
.filters{{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 20px}}.filters button{{border:1px solid var(--line);background:var(--card);color:var(--fg);padding:6px 12px;border-radius:999px;cursor:pointer}}
.filters button.active{{background:var(--accent);color:#fff;border-color:var(--accent)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:20px;padding-bottom:64px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden;display:flex;flex-direction:column}}
.card.hidden{{display:none}}.card figure{{margin:0;position:relative;background:#000}}.card img{{display:block;width:100%;height:auto}}
.card .missing{{aspect-ratio:3/2;display:grid;place-items:center;color:var(--muted)}}
figcaption{{position:absolute;left:8px;bottom:8px;display:flex;gap:6px;flex-wrap:wrap}}
.chip,.status{{font-size:.72rem;padding:2px 8px;border-radius:999px;background:rgba(0,0,0,.6);color:#fff;backdrop-filter:blur(4px)}}
.status-rejected .status,.status-generation_failed .status,.status-direction_failed .status,.status-review_failed .status{{background:var(--warn)}}
.status-admitted .status{{background:var(--accent)}}.status-rejected img{{opacity:.55}}
.body{{padding:14px 16px 16px}}h3{{margin:0 0 6px;font-size:1.1rem}}h3 small{{color:var(--muted);font-weight:400;font-size:.8rem;margin-left:6px}}
.summary{{margin:0 0 8px}}details{{margin:6px 0}}summary{{cursor:pointer;color:var(--muted);font-size:.9rem}}details p{{margin:6px 0}}
ul.rels,ul.facts{{padding-left:16px;margin:6px 0}}.kind{{color:var(--muted);font-size:.85rem}}.rel-summary{{color:var(--muted);font-size:.85rem}}
.lineage{{font-size:.72rem;color:var(--muted);border:1px solid var(--line);border-radius:4px;padding:0 4px;margin-right:4px}}
.register{{color:var(--muted);font-size:.85rem}}.blocking{{color:var(--warn)}}.reason{{color:var(--warn);font-size:.85rem}}
</style></head><body>
<header>
  <div>{'<img src="poster.jpg" alt="Approved poster">' if poster_shown else ""}</div>
  <div class="intro">
    <h1>{_e(proposal["title"])}</h1>
    <p class="meta">{_e(manifest["medium_id"].replace("_", " "))} · {len(manifest["entities"])} entities · {counts} · unpublished exploration package</p>
    <p>{_e(proposal["premise"]["claim"])}</p>
    <p><strong>Now.</strong> {_e(proposal["present_state"]["claim"])}</p>
    <h2>Ways in</h2><ul class="plain">{viewpoints}</ul>
  </div>
</header>
<section>
  <h2>How the world works</h2><ul class="plain">{rules}</ul>
  <h2>What people disagree about</h2><ul class="plain">{tensions}</ul>
  <h2>Open questions</h2><ul class="plain">{questions}</ul>
  <h2>Entities</h2>
  <div class="filters"><button data-filter-class="all" class="active">all</button>{class_buttons}<button data-filter-status="admitted">admitted only</button></div>
  <div class="grid">{"".join(cards)}</div>
</section>
<script>
const cards=[...document.querySelectorAll('.card')];let cls='all',adm=false;
function apply(){{cards.forEach(c=>{{const ok=(cls==='all'||c.dataset.class===cls)&&(!adm||c.dataset.status==='admitted');c.classList.toggle('hidden',!ok)}})}}
document.querySelectorAll('[data-filter-class]').forEach(b=>b.addEventListener('click',()=>{{cls=b.dataset.filterClass;document.querySelectorAll('[data-filter-class]').forEach(x=>x.classList.toggle('active',x===b));apply()}}));
const admBtn=document.querySelector('[data-filter-status]');admBtn.addEventListener('click',()=>{{adm=!adm;admBtn.classList.toggle('active',adm);apply()}});
</script>
</body></html>
"""
    output = consumer / "index.html"
    output.write_text(page, encoding="utf-8")
    return output.as_posix()
