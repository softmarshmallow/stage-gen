// Player: the node graph view and its drawer: setView and the overview/graph switch, ELK layout (elkjs from npm, not the CDN), edges, trace, openNode, the camera (pan, zoom, pinch, wheel, gestures), node clicks, `button.jump` links and route() from the URL hash.
//
// Moved from the graph sections of the retired showcase's page script, up to the clip
// buttons, and its route(): same logic, same constants and the same comments, typed.
// Root: #graph, with the drawer data (the node records by id) as its config. The rest of the
// page shell is found by id, as the old script found it: #vp, #stage, #edges, .node, #drawer,
// #dbody, #dx, #overview, #to-overview, #to-graph, #zin, #zout, #zfit, #zpct, button.jump.
//
// The graph is one per page (its parts are ids), so its state stays in module bindings, as
// the old script kept it in top-level ones; the cleanup mount() returns resets them. Two
// things differ from the old script, both because of where the code now lives:
// - ELK is imported from npm on the first arrange() instead of loaded by a script tag;
// - the node data is the mount's config instead of an inlined `const NODES`.


import type { ElkExtendedEdge, ElkNode, ElkPoint, LayoutOptions } from "elkjs/lib/elk-api";
import { $, CHECKER, esc, human, type Mount } from "./dom";

/** What the reviewer said, as the example document records a verdict. */
interface Verdict {
  readonly accepted: boolean;
  readonly criteria: readonly { readonly name: string; readonly passed: boolean; readonly evidence: string }[];
  readonly issues: readonly unknown[];
}

/** One node of the drawer data (the site's blocks/drawer.ts writes it), keyed as the old script's NODES. */
export interface GraphNode {
  readonly id: string;
  readonly title: string;
  readonly kind: string;
  readonly description: string;
  readonly model: string;
  readonly time: string | null;
  readonly cost: string | null;
  readonly tries: string | null;
  readonly not_needed: string | null;
  readonly verdict: Verdict | null;
  readonly rationale: string | null;
  readonly open_issues: readonly unknown[];
  readonly pictures: readonly { readonly src: string; readonly width: number; readonly height: number; readonly alpha?: boolean }[];
  readonly depends_on: readonly string[];
  readonly checks: readonly { readonly name: string; readonly passed: boolean }[];
  readonly prompt: string | null;
}

interface Box {
  l: number;
  t: number;
  r: number;
  b: number;
}

interface Route {
  readonly from: string;
  readonly to: string;
  readonly d: string;
}

/** Safari's trackpad pinch event (not in the DOM typings). */
type GestureEvent = UIEvent & { readonly scale: number; readonly clientX: number; readonly clientY: number };

const H5 = "mb-2 mt-7 text-sm font-medium";

let NODES: Record<string, GraphNode> = {};
let vp: HTMLElement;
let stage: HTMLElement;
const graphShown = (): boolean => !$("#graph")!.classList.contains("hidden");
let framed = false;

/** Whether the drawer data holds a node with this id (route() opens only a known node). */
function hasNode(id: string): boolean {
  return Object.hasOwn(NODES, id);
}

function setView(v: string): void {
  $("#graph")!.classList.toggle("hidden", v !== "graph");
  $("#overview")!.classList.toggle("hidden", v === "graph");
  $("#to-overview")!.setAttribute("aria-pressed", String(v !== "graph"));
  $("#to-graph")!.setAttribute("aria-pressed", String(v === "graph"));
  // The graph is a canvas: the page under it neither bounces nor goes back on a sideways swipe.
  document.documentElement.classList.toggle("overscroll-none", v === "graph");
  if (v !== "graph" || framed) return;
  framed = true;
  stage.style.opacity = "0"; // not shown until it is arranged
  void arrange().then(() => {
    drawEdges();
    frame(false, 0.3, 1);
    stage.style.opacity = "1";
  });
}

// A box in the stage's own pixels, whatever the camera is doing.
function boxOf(el: HTMLElement): Box {
  let x = 0,
    y = 0;
  for (let e: HTMLElement = el; e !== stage; e = e.offsetParent as HTMLElement) {
    x += e.offsetLeft + (e === el ? 0 : e.clientLeft);
    y += e.offsetTop + (e === el ? 0 : e.clientTop);
  }
  return { l: x, t: y, r: x + el.offsetWidth, b: y + el.offsetHeight };
}

// Layout. ELK's layered algorithm places the stages and their cards by what feeds what, and routes
// every edge at right angles around the cards, with one shared trunk where a card fans out or many
// feed one. The page's stages stay as the groups and its rows give the order within them. The graph
// runs to the right, downwards, or to the right and folded into rows, whichever shows it largest:
// many parallel lanes are far taller than a screen running right, and a long chain far wider.
const LAYERED: LayoutOptions = {
  "elk.algorithm": "layered", "elk.edgeRouting": "ORTHOGONAL", "elk.layered.mergeEdges": "true",
  "elk.spacing.nodeNode": "20", "elk.layered.spacing.nodeNodeBetweenLayers": "56",
  "elk.spacing.edgeNode": "16", "elk.layered.spacing.edgeNodeBetweenLayers": "20",
  "elk.spacing.edgeEdge": "10", "elk.layered.spacing.edgeEdgeBetweenLayers": "10",
};
const SIDE = 176; // how wide a stage's words are when they sit beside its cards
const SCREEN = [1600, 1000] as const; // the screen a layout is judged for, so a page looks the same in every window
let routes: Route[] | null = null,
  arranging: Promise<void> | null = null;

interface Room {
  readonly top: number;
  readonly left: number;
  readonly edge: number;
  readonly least: number;
}

function arrange(): Promise<void> {
  return (arranging ??= (async () => {
    // elkjs from npm, fetched the first time the graph is arranged, as the CDN script was.
    const { default: ELK } = await import("elkjs/lib/elk.bundled.js");
    const elk = new ELK(),
      sections = [...stage.querySelectorAll<HTMLElement>(":scope > section")];
    const cards = sections.map((s) =>
      [...s.querySelectorAll<HTMLElement>(".node")].map((n) => ({ id: n.dataset.node as string, width: n.offsetWidth, height: n.offsetHeight })),
    );
    // Edges come into a stage from the side the graph runs from, so its words go on the other
    // side: above the cards when it runs right, to their left when it runs down.
    const words = (down: boolean) =>
      sections.forEach((s) =>
        Object.assign(
          $("header", s)!.style,
          down ? { position: "absolute", left: "16px", top: "16px", width: SIDE + "px" } : { position: "", left: "", top: "", width: "" },
        ),
      );
    const room = (s: HTMLElement, down: boolean): Room => {
      const edge = 16 + s.clientTop,
        h = $("header", s)!.offsetHeight;
      return down ? { top: edge, left: edge + SIDE + 16, edge, least: h + 2 * edge } : { top: edge + h + 16, left: edge, edge, least: 0 };
    };
    // The graph is built afresh for every call, because ELK writes its answer into the one it is
    // given. The written order is asked for at the root only: asked of a stage, elkjs 0.12 throws.
    const layout = (down: boolean, wrap: boolean, rooms: readonly Room[]): Promise<ElkNode> =>
      elk.layout({
        id: "root",
        layoutOptions: {
          ...LAYERED, "elk.direction": down ? "DOWN" : "RIGHT", "elk.hierarchyHandling": "INCLUDE_CHILDREN",
          "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES", "elk.json.edgeCoords": "ROOT",
          "elk.padding": "[top=40,left=40,bottom=40,right=40]",
          ...(wrap ? { "elk.layered.wrapping.strategy": "MULTI_EDGE", "elk.aspectRatio": String(SCREEN[0] / SCREEN[1]) } : {}),
        },
        children: sections.map((s, i) => ({
          id: "stage:" + i, children: cards[i].map((c) => ({ ...c, layoutOptions: { "elk.alignment": down ? "TOP" : "LEFT" } })),
          layoutOptions: {
            ...LAYERED, "elk.direction": down ? "DOWN" : "RIGHT",
            "elk.padding": `[top=${rooms[i].top},left=${rooms[i].left},bottom=${rooms[i].edge},right=${rooms[i].edge}]`,
            "elk.nodeSize.constraints": "MINIMUM_SIZE", "elk.nodeSize.minimum": `(0,${rooms[i].least})`,
          },
        })),
        edges: Object.values(NODES).flatMap((n) => n.depends_on.map((dep) => ({ id: dep + ">" + n.id, sources: [dep], targets: [n.id] }))),
      });
    const put = (g: ElkNode, down: boolean) => {
      words(down);
      Object.assign(stage.style, { display: "block", padding: 0, width: g.width + "px", height: g.height + "px" });
      g.children!.forEach((c, i) => {
        const s = sections[i];
        Object.assign(s.style, { position: "absolute", left: c.x + "px", top: c.y + "px", width: c.width + "px", height: c.height + "px" });
        for (const row of s.querySelectorAll<HTMLElement>(":scope > div")) row.style.display = "contents";
        for (const k of c.children!) Object.assign($("#node-" + CSS.escape(k.id))!.style, { position: "absolute", left: k.x! - s.clientLeft + "px", top: k.y! - s.clientTop + "px" });
      });
      routes = (g.edges as ElkExtendedEdge[]).map((e) => ({ from: e.sources[0], to: e.targets[0], d: e.sections!.map((sec) => rightAngles([sec.startPoint, ...(sec.bendPoints ?? []), sec.endPoint])).join(" ") }));
      extent = null;
    };
    const run = async (down: boolean, wrap: boolean) => {
      words(down);
      let rooms = sections.map((s) => room(s, down)),
        g = await layout(down, wrap, rooms);
      put(g, down);
      const settled = sections.map((s) => room(s, down)); // a stage that came out narrower or wider wraps its words differently
      if (settled.some((r, i) => r.top !== rooms[i].top)) {
        g = await layout(down, wrap, settled);
        put(g, down);
      }
      // How large it shows on a screen. A long chain shows larger folded into rows, at the price
      // of an edge that doubles back at each fold, so folding has to win by a clear margin.
      return { g, down, wrap, shown: Math.min(SCREEN[0] / g.width!, SCREEN[1] / g.height!) * (wrap ? 0.8 : 1) };
    };
    const best = [await run(false, false), await run(true, false), await run(false, true)].reduce((a, b) => (b.shown > a.shown ? b : a));
    put(best.g, best.down);
  })().catch((e: unknown) => console.warn("The graph could not be arranged, so its stages stay in rows joined by plain curves.", e)));
}

function rightAngles(p: readonly ElkPoint[], r = 8): string {
  // a path through the points, its corners rounded
  let d = `M${p[0].x},${p[0].y}`;
  for (let i = 1; i < p.length - 1; i++) {
    const a = p[i - 1], b = p[i], c = p[i + 1];
    const k = Math.min(r, Math.hypot(b.x - a.x, b.y - a.y) / 2), m = Math.min(r, Math.hypot(c.x - b.x, c.y - b.y) / 2);
    d += ` L${b.x - Math.sign(b.x - a.x) * k},${b.y - Math.sign(b.y - a.y) * k} Q${b.x},${b.y} ${b.x + Math.sign(c.x - b.x) * m},${b.y + Math.sign(c.y - b.y) * m}`;
  }
  return d + ` L${p.at(-1)!.x},${p.at(-1)!.y}`;
}

function curve(from: string, to: string): string {
  const a = boxOf($("#node-" + CSS.escape(from))!), b = boxOf($("#node-" + CSS.escape(to))!);
  if (b.l >= a.r - 1) {
    const y1 = (a.t + a.b) / 2, y2 = (b.t + b.b) / 2, dx = Math.max(30, (b.l - a.r) / 2);
    return `M${a.r},${y1} C${a.r + dx},${y1} ${b.l - dx},${y2} ${b.l},${y2}`;
  }
  const x1 = (a.l + a.r) / 2, x2 = (b.l + b.r) / 2;
  return `M${x1},${a.b} C${x1},${a.b + 26} ${x2},${b.t - 26} ${x2},${b.t}`;
}

function drawEdges(): void {
  const svg = $<SVGSVGElement>("#edges")!;
  svg.setAttribute("width", String(stage.offsetWidth));
  svg.setAttribute("height", String(stage.offsetHeight));
  const lines = routes ?? Object.values(NODES).flatMap((n) => n.depends_on.map((dep) => ({ from: dep, to: n.id, d: curve(dep, n.id) })));
  svg.innerHTML = lines
    .map((e) => {
      const idle = NODES[e.from].not_needed || NODES[e.to].not_needed;
      return `<path data-from="${esc(e.from)}" data-to="${esc(e.to)}" class="${idle ? "fill-none stroke-zinc-300 [stroke-dasharray:3_4] dark:stroke-zinc-700" : "fill-none stroke-zinc-400 dark:stroke-zinc-600"}" stroke-width="1" d="${e.d}"/>`;
    })
    .join("");
  trace();
}

// The edges of the card under the pointer, or else of the open one, are drawn over the rest.
let picked: string | null = null,
  pointed: string | null = null;
function trace(): void {
  const id = pointed ?? picked, svg = $<SVGSVGElement>("#edges")!;
  for (const p of [...svg.children] as SVGPathElement[]) {
    const on = id && (p.dataset.from === id || p.dataset.to === id);
    p.style.stroke = on ? "currentColor" : "";
    p.style.strokeWidth = on ? "1.5" : "";
    if (on) svg.append(p);
  }
}

function openNode(id: string): void {
  const n = NODES[id];
  if (!n) return;
  document.querySelectorAll(".node").forEach((e) => e.classList.remove("ring-1", "ring-zinc-900", "dark:ring-zinc-100"));
  $("#node-" + CSS.escape(id))?.classList.add("ring-1", "ring-zinc-900", "dark:ring-zinc-100");
  picked = id;
  trace();
  const facts = [["Model", esc(n.model)], ["Time", esc(n.time)], ["Cost", esc(n.cost)], ["Tries", esc(n.tries)]].filter(([, v]) => v);
  let h = `<p class="text-sm text-zinc-500">${esc(n.kind)}${n.not_needed ? ", planned but not needed" : ""}</p>
    <h4 class="mt-1 text-lg font-semibold">${esc(n.title)}</h4>
    <p class="mt-1 text-sm text-zinc-500">${esc(n.description)}</p>`;
  if (!n.not_needed) h += `<dl class="mt-5 grid grid-cols-[auto_1fr] gap-x-5 gap-y-1.5 text-sm">${facts.map(([k, v]) => `<dt class="text-zinc-500">${k}</dt><dd>${v}</dd>`).join("")}</dl>`;
  else h += `<p class="mt-5 text-sm">${esc(n.not_needed)}.</p>`;
  if (n.verdict) {
    const v = n.verdict;
    h += `<h5 class="${H5}">${v.accepted ? "The reviewer accepted it" : "The reviewer refused it"}</h5>
      <ul class="divide-y divide-zinc-200 text-sm dark:divide-zinc-800">${v.criteria.map((c) =>
      `<li class="py-2.5"><span class="${c.passed ? "text-emerald-700 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}">${c.passed ? "✓" : "✗"}</span> ${esc(human(c.name))}
       <p class="mt-1 text-zinc-600 dark:text-zinc-400">${esc(c.evidence)}</p></li>`).join("")}</ul>`;
    if (v.issues.length) h += `<h5 class="${H5}">Issues</h5><ul class="list-disc pl-5 text-sm">${v.issues.map((i) => `<li>${esc(typeof i === "string" ? i : JSON.stringify(i))}</li>`).join("")}</ul>`;
  }
  if (n.checks.length) h += `<h5 class="${H5}">Checks it ran</h5><ul class="space-y-1 text-sm">${n.checks.map((c) =>
    `<li><span class="${c.passed ? "text-emerald-700 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}">${c.passed ? "✓" : "✗"}</span> ${esc(human(c.name))}</li>`).join("")}</ul>`;
  if (n.prompt) h += `<h5 class="${H5}">Prompt</h5><details class="text-sm text-zinc-600 dark:text-zinc-400"><summary class="cursor-pointer select-none text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">Show the prompt it sent</summary><p class="mt-2 whitespace-pre-line">${esc(n.prompt)}</p></details>`;
  if (n.pictures.length) h += `<h5 class="${H5}">${n.kind === "Reviewer" ? "What it looked at" : "Pictures"}</h5><div class="grid grid-cols-2 gap-2">${n.pictures.map((p) =>
    `<img class="w-full rounded-sm ${p.width > p.height * 1.6 ? "col-span-2" : ""}" style="${p.alpha ? CHECKER : ""}" src="${esc(p.src)}" alt="">`).join("")}</div>`;
  if (n.rationale) h += `<h5 class="${H5}">Its notes</h5><p class="text-sm text-zinc-600 dark:text-zinc-400">${esc(n.rationale)}</p>`;
  if (n.open_issues.length) h += `<h5 class="${H5}">What it flagged for later stages</h5><ul class="list-disc space-y-1 pl-5 text-sm text-zinc-600 dark:text-zinc-400">${n.open_issues.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>`;
  $("#dbody")!.innerHTML = h;
  $("#drawer")!.classList.replace("translate-x-full", "translate-x-0");
}

// The graph's camera. The stage is moved and scaled as one layer; nothing inside it is laid out again.
const cam = { x: 0, y: 0, z: 1 }, ZOOM = [0.2, 2.5] as const, GRID = 24;
const clamp = (v: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, v));
const clearWidth = (): number => vp.clientWidth - ($("#drawer")!.classList.contains("translate-x-0") ? $("#drawer")!.offsetWidth : 0);
let extent: Box | null = null; // measured once, the first time the graph is on screen
function bounds(): Box {
  if (extent) return extent;
  const boxes = [...stage.querySelectorAll<HTMLElement>(":scope > section")].map(boxOf);
  return (extent = { l: Math.min(...boxes.map((b) => b.l)), t: Math.min(...boxes.map((b) => b.t)), r: Math.max(...boxes.map((b) => b.r)), b: Math.max(...boxes.map((b) => b.b)) });
}
let settle: ReturnType<typeof setTimeout> | undefined;
function place(glide = false): void {
  const b = bounds(), keep = 120; // some of the graph always stays in view
  cam.x = clamp(cam.x, keep - b.r * cam.z, vp.clientWidth - keep - b.l * cam.z);
  cam.y = clamp(cam.y, keep - b.b * cam.z, vp.clientHeight - keep - b.t * cam.z);
  let step = GRID * cam.z;
  while (step < 16) step *= 2;
  const ease = glide ? " .2s ease-out" : "";
  stage.style.transition = glide ? "transform" + ease : "none";
  vp.style.transition = glide ? `background-position${ease}, background-size${ease}` : "none";
  // Held as one layer while it moves, then let go so the text is redrawn sharp at the new size.
  stage.style.willChange = "transform";
  clearTimeout(settle);
  settle = setTimeout(() => {
    stage.style.willChange = "auto";
  }, 260);
  stage.style.transform = `translate(${cam.x}px,${cam.y}px) scale(${cam.z})`;
  vp.style.backgroundSize = `${step}px ${step}px`;
  vp.style.backgroundPosition = `${cam.x}px ${cam.y}px`;
  $("#zpct")!.textContent = Math.round(cam.z * 100) + "%";
}
function zoomAt(x: number, y: number, z: number): void {
  // keeps the point under (x, y) in the viewport where it is
  z = clamp(z, ...ZOOM);
  cam.x = x - ((x - cam.x) * z) / cam.z;
  cam.y = y - ((y - cam.y) * z) / cam.z;
  cam.z = z;
}
function frame(glide = true, least: number = ZOOM[0], most = 1): void {
  // the whole graph, centred where it fits
  const b = bounds(), pad = 32, w = vp.clientWidth, h = vp.clientHeight;
  cam.z = clamp(Math.min((w - 2 * pad) / (b.r - b.l), (h - 2 * pad) / (b.b - b.t)), least, most);
  cam.x = (b.r - b.l) * cam.z > w - 2 * pad ? pad - b.l * cam.z : (w - (b.l + b.r) * cam.z) / 2;
  cam.y = (b.b - b.t) * cam.z > h - 2 * pad ? pad - b.t * cam.z : (h - (b.t + b.b) * cam.z) / 2;
  place(glide);
}
function centreOn(el: HTMLElement): void {
  const b = boxOf(el);
  cam.z = Math.max(cam.z, 1);
  cam.x = clearWidth() / 2 - ((b.l + b.r) / 2) * cam.z;
  cam.y = vp.clientHeight / 2 - ((b.t + b.b) / 2) * cam.z;
  place(true);
}
function reveal(el: HTMLElement): void {
  // the least move that shows a node clear of the drawer
  const b = boxOf(el), pad = 24, w = clearWidth(), h = vp.clientHeight;
  const l = b.l * cam.z + cam.x, r = b.r * cam.z + cam.x, t = b.t * cam.z + cam.y, bottom = b.b * cam.z + cam.y;
  const dx = l < pad ? pad - l : r > w - pad ? Math.max(w - pad - r, pad - l) : 0;
  const dy = t < pad ? pad - t : bottom > h - pad ? Math.max(h - pad - bottom, pad - t) : 0;
  if (dx || dy) {
    cam.x += dx;
    cam.y += dy;
    place(true);
  }
}
const zoomBy = (k: number): void => {
  zoomAt(clearWidth() / 2, vp.clientHeight / 2, cam.z * k);
  place(true);
};

// Mouse and touch. One pointer drags the canvas, from a node as well as from empty space; two
// pinch. A press that did not travel is still a click on the node under it.
const touches = new Map<number, [number, number]>();
let dragging = false,
  travelled = 0;
const hold = () => {
  const p = [...touches.values()];
  return {
    x: p.reduce((s, q) => s + q[0], 0) / p.length, y: p.reduce((s, q) => s + q[1], 0) / p.length,
    d: p.length > 1 ? Math.hypot(p[0][0] - p[1][0], p[0][1] - p[1][1]) : 0,
  };
};
function release(e: PointerEvent): void {
  touches.delete(e.pointerId);
  if (touches.size) return;
  vp.classList.replace("cursor-grabbing", "cursor-grab");
  setTimeout(() => {
    dragging = false;
  }); // after the click this release may still produce
}

function route(): void {
  const hash = location.hash.slice(1);
  if (!hash.startsWith("graph")) {
    setView("overview");
    return;
  }
  setView("graph");
  const id = hash.split("/")[1];
  if (id && hasNode(id)) {
    openNode(id);
    void arrange().then(() => centreOn($("#node-" + CSS.escape(id))!));
  }
}

/** The drawer data: each node's record, by node id (the site's blocks/drawer.ts writes it). */
export type GraphNodes = Readonly<Record<string, GraphNode>>;

export const mount: Mount<GraphNodes> = (graph, nodes) => {
  const controller = new AbortController(), { signal } = controller;
  NODES = { ...nodes };
  vp = $("#vp", graph)!;
  stage = $("#stage", graph)!;

  $("#to-overview")!.onclick = () => {
    history.replaceState(null, "", "#");
    setView("overview");
  };
  $("#to-graph")!.onclick = () => {
    history.replaceState(null, "", "#graph");
    setView("graph");
  };

  stage.addEventListener("pointerover", (e) => {
    const id = (e.target as Element).closest<HTMLElement>(".node")?.dataset.node ?? null;
    if (id !== pointed) {
      pointed = id;
      trace();
    }
  }, { signal });
  stage.addEventListener("pointerleave", () => {
    pointed = null;
    trace();
  }, { signal });

  $("#dx")!.onclick = () => {
    $("#drawer")!.classList.replace("translate-x-0", "translate-x-full");
    picked = null;
    trace();
  };
  stage.querySelectorAll<HTMLElement>(".node").forEach((el) =>
    el.addEventListener("click", () => {
      openNode(el.dataset.node as string);
      reveal(el);
    }, { signal }),
  );
  document.querySelectorAll<HTMLElement>("button.jump").forEach((el) =>
    el.addEventListener("click", () => {
      setView("graph");
      history.replaceState(null, "", "#graph/" + el.dataset.node);
      openNode(el.dataset.node as string);
      void arrange().then(() => centreOn($("#node-" + CSS.escape(el.dataset.node as string))!));
    }, { signal }),
  );

  $("#zin")!.onclick = () => zoomBy(1.25);
  $("#zout")!.onclick = () => zoomBy(0.8);
  $("#zfit")!.onclick = () => frame();
  stage.addEventListener("focusin", (e) => {
    const n = (e.target as Element).closest<HTMLElement>(".node");
    if (n?.matches(":focus-visible")) reveal(n);
  }, { signal });

  // Trackpad and wheel. Two fingers pan; a pinch arrives as a wheel with ctrlKey and zooms about the
  // pointer, as does a wheel with the command key held. Taking the event here is also what stops the
  // browser zooming the page or swiping back through history while the graph is up.
  window.addEventListener(
    "wheel",
    (e) => {
      if (!graphShown()) return;
      const target = e.target as Element;
      if (target.closest("#drawer") && !e.ctrlKey && Math.abs(e.deltaY) > Math.abs(e.deltaX)) return; // the drawer scrolls itself
      e.preventDefault();
      if (!vp.contains(target)) return;
      const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? vp.clientHeight : 1, at = vp.getBoundingClientRect();
      if (e.ctrlKey || e.metaKey) zoomAt(e.clientX - at.left, e.clientY - at.top, cam.z * Math.exp(-clamp(e.deltaY * unit, -24, 24) * 0.012));
      else {
        cam.x -= e.deltaX * unit;
        cam.y -= e.deltaY * unit;
      }
      place();
    },
    { passive: false, signal },
  );

  // Safari reports a trackpad pinch as gesture events instead.
  let pinchFrom = 1;
  for (const type of ["gesturestart", "gesturechange", "gestureend"])
    addEventListener(
      type,
      (event) => {
        const e = event as GestureEvent;
        if (!graphShown()) return;
        e.preventDefault();
        if (type === "gesturestart") pinchFrom = cam.z;
        if (type !== "gesturechange" || touches.size > 1 || !vp.contains(e.target as Node)) return;
        const at = vp.getBoundingClientRect();
        zoomAt(e.clientX - at.left, e.clientY - at.top, pinchFrom * e.scale);
        place();
      },
      { passive: false, signal },
    );

  vp.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    if (!touches.size) {
      dragging = false;
      travelled = 0;
    }
    touches.set(e.pointerId, [e.clientX, e.clientY]);
  }, { signal });
  vp.addEventListener("pointermove", (e) => {
    if (!touches.has(e.pointerId)) return;
    if (e.pointerType === "mouse" && !e.buttons) {
      release(e);
      return;
    }
    const a = hold();
    touches.set(e.pointerId, [e.clientX, e.clientY]);
    const b = hold();
    travelled += Math.hypot(b.x - a.x, b.y - a.y);
    if (!dragging) {
      if (touches.size < 2 && travelled < 4) return;
      dragging = true;
      vp.setPointerCapture(e.pointerId);
      vp.classList.replace("cursor-grab", "cursor-grabbing");
    }
    cam.x += b.x - a.x;
    cam.y += b.y - a.y;
    if (a.d && b.d) {
      const at = vp.getBoundingClientRect();
      zoomAt(b.x - at.left, b.y - at.top, (cam.z * b.d) / a.d);
    }
    place();
  }, { signal });
  vp.addEventListener("pointerup", release, { signal });
  vp.addEventListener("pointercancel", release, { signal });
  vp.addEventListener(
    "click",
    (e) => {
      if (dragging) {
        e.stopPropagation();
        e.preventDefault();
      }
    },
    { capture: true, signal },
  );
  vp.addEventListener("dragstart", (e) => e.preventDefault(), { signal }); // a node's picture is not lifted out of the canvas
  addEventListener("resize", () => graphShown() && place(), { signal });

  // The old script ended with `addEventListener("hashchange", route); route();`, after every
  // player section had run. The other players mount in the same commit, so route() waits for
  // a microtask, which runs once they all have, and before the browser paints again. A page
  // opened at #graph… has shown the graph view since its first paint: the shell's inline
  // script set data-view on <html> (see the site's globals.css). route() takes over from it.
  addEventListener("hashchange", route, { signal });
  queueMicrotask(() => {
    if (signal.aborted) return;
    delete document.documentElement.dataset.view;
    route();
  });

  return () => {
    controller.abort();
    for (const id of ["#to-overview", "#to-graph", "#dx", "#zin", "#zout", "#zfit"]) $(id)!.onclick = null;
    clearTimeout(settle);
    // A later mount arranges, frames and traces afresh.
    framed = false;
    routes = null;
    arranging = null;
    extent = null;
    picked = null;
    pointed = null;
    touches.clear();
    dragging = false;
    travelled = 0;
    Object.assign(cam, { x: 0, y: 0, z: 1 });
  };
};
